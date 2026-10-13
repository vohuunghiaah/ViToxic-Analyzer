"""Independently verify Stage 3 artifacts against raw data and frozen models."""
from pathlib import Path
import json
import sys
from importlib.metadata import version

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.experiment import metrics, sha256, write_json
from src.preprocessing import PreprocessingConfig, preprocess_text
from src.stage1 import fingerprint


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    out = ROOT / 'outputs/stage3'
    lock = read(out / 'lock.json')
    selection_path = ROOT / 'outputs/stage2/final_selection/selection.json'
    selection = read(selection_path)
    assert selection['selection_split'] == 'validation'
    assert selection['selection_metric'] == 'macro_f1'
    assert selection['selected']['run'] == lock['selected_run']
    previous = read(ROOT / 'outputs/stage2/review/full_audit.json')
    assert lock['checkpoint'] == previous['best_checkpoint_sha256']
    directory = ROOT / 'outputs/stage2/runs' / lock['selected_run']
    for name, path in {'selection': selection_path, 'checkpoint': directory / 'best_model.pt',
                       'baseline': ROOT / 'outputs/stage2/baseline/baseline.joblib',
                       'config': directory / 'config.json',
                       'test': ROOT / 'data/processed/test.csv'}.items():
        assert sha256(path) == lock[name], f'Changed input: {name}'
    audit = read(ROOT / 'outputs/stage1/audit.json')
    assert sha256(ROOT / 'data/raw/ViHSD_test.csv') == audit['provenance']['files']['test']['sha256']
    raw = pd.read_csv(ROOT / 'data/raw/ViHSD_test.csv', keep_default_na=False)
    test = pd.read_csv(ROOT / 'data/processed/test.csv', keep_default_na=False)
    pred = pd.read_csv(out / 'test_predictions.csv', keep_default_na=False)
    assert len(raw) == len(test) == len(pred) == 6680
    assert test.row_id.tolist() == [f'test:{i}' for i in range(len(raw))]
    assert raw.label_id.tolist() == test.label_id.tolist() == pred.label_id.tolist()
    config = PreprocessingConfig(**audit['preprocessing'])
    assert [preprocess_text(t, config) for t in raw.free_text] == test.text_clean.tolist()
    assert test.row_id.tolist() == pred.row_id.tolist()
    assert test.text_clean.tolist() == pred.text_clean.tolist()
    prob = pred[['prob_clean', 'prob_offensive', 'prob_hate']].to_numpy()
    assert np.isfinite(prob).all() and (prob >= 0).all() and (prob <= 1).all()
    assert np.allclose(prob.sum(1), 1, atol=1e-6)
    assert np.array_equal(prob.argmax(1), pred.prediction)
    assert np.allclose(prob.max(1), pred.confidence)
    validation = pd.read_csv(ROOT / 'data/processed/validation.csv', keep_default_na=False)
    keys = set(validation.text_clean.map(fingerprint)) - {''}
    expected_overlap = test.text_clean.map(fingerprint).isin(keys)
    assert np.array_equal(expected_overlap, pred.validation_overlap), 'Overlap must use Stage 1 normalization'
    train = pd.read_csv(ROOT / 'data/processed/train_decontaminated.csv', keep_default_na=False)
    assert not (set(train.text_clean.map(fingerprint)) & set(test.text_clean.map(fingerprint)) - {''})
    saved = read(out / 'metrics.json')
    for model, column in [('baseline', 'baseline_prediction'), ('phobert', 'prediction')]:
        computed = metrics(pred.label_id, pred[column])
        assert computed == saved[model], f'Metrics mismatch: {model}'
    provenance = read(out / 'provenance.json')
    assert sha256(out / 'source_snapshot/evaluate.py') == provenance['evaluation_source_sha256']
    errors = pd.read_csv(out / 'errors.csv')
    assert set(errors.row_id) == set(pred.loc[pred.label_id != pred.prediction, 'row_id'])
    report = {'passed': True, 'rows': len(pred), 'validation_overlap_rows': int(expected_overlap.sum()),
              'train_overlap_rows': 0, 'raw_test_sha256_verified': True,
              'processed_test_reproduced_from_raw': True, 'metrics_recomputed': True,
              'checkpoint_matches_stage2_full_validation_audit': True,
              'selected_from_validation': selection['selected']['run'],
              'packages': {name: version(name) for name in ['torch', 'transformers', 'scikit-learn', 'numpy', 'pandas']},
              'limitations': ['Checks saved test probabilities and metrics; does not repeat PhoBERT inference.',
                              'Baseline saved on Colab with scikit-learn 1.6.1; local version differs. Validation Macro-F1 reproduced before test.']}
    write_json(out / 'verification.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
