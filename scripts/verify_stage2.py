"""Audit completed run without touching test data or modifying training artifacts."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pandas as pd
import torch
from transformers import AutoTokenizer
from src.experiment import metrics, sha256, write_json
from src.model import load_checkpoint_model


def verify(run, baseline, cache, output):
    run, baseline, cache = map(Path, (run, baseline, cache))
    read = lambda name: json.loads((run / name).read_text(encoding='utf-8'))
    manifest, recorded, history = read('manifest.json'), read('validation_metrics.json'), read('history.json')
    predictions = pd.read_csv(run / 'validation_predictions.csv')
    validation = pd.read_csv(ROOT / 'data/processed/validation.csv')
    assert predictions.row_id.tolist() == validation.row_id.tolist(), 'Validation row order mismatch'
    assert predictions.label.tolist() == validation.label_id.tolist(), 'Validation labels mismatch'
    recomputed = metrics(predictions.label, predictions.prediction)
    for key in ['accuracy', 'macro_f1', 'weighted_f1']:
        assert abs(recomputed[key] - recorded[key]) < 1e-10, key
    assert recomputed['confusion_matrix'] == recorded['confusion_matrix']
    for split, filename in [('train', 'train_decontaminated.csv'), ('validation', 'validation.csv')]:
        assert sha256(ROOT / 'data/processed' / filename) == manifest['data_hashes'][split], split
    best_epoch = max(history, key=lambda row: row['validation_macro_f1'])['epoch']
    assert recorded['best_epoch'] == best_epoch
    checkpoint = torch.load(run / 'best_model.pt', map_location='cpu', weights_only=True)
    assert checkpoint['epoch'] == best_epoch
    assert all(checkpoint['validation'][key] == recorded[key] for key in checkpoint['validation'])
    del checkpoint
    last = torch.load(run / 'last_checkpoint.pt', map_location='cpu', weights_only=True, mmap=True)
    assert last['epoch'] + 1 == history[-1]['epoch']
    assert last['history'] == history
    assert last['best_epoch'] == best_epoch
    assert last['data_hashes'] == manifest['data_hashes']
    last_epoch = last['epoch'] + 1
    del last
    model, config = load_checkpoint_model(run)
    tokenizer = AutoTokenizer.from_pretrained(run / 'tokenizer', local_files_only=True, use_fast=False)
    texts = json.loads((cache / (manifest['segmentation_cache_keys'][1] + '.json')).read_text(encoding='utf-8'))
    assert len(texts) == len(validation)
    indices = [int(i) for label in [0, 1, 2] for i in validation.index[validation.label_id.eq(label)][:4]]
    inputs = tokenizer([texts[i] for i in indices], padding=True, truncation=True,
                       max_length=config.max_length, return_token_type_ids=False, return_tensors='pt')
    with torch.no_grad():
        actual = model(**inputs).argmax(-1).tolist()
    expected = predictions.iloc[indices].prediction.tolist()
    assert actual == expected, 'Reloaded checkpoint predictions differ on audit sample'
    baseline_result = json.loads((baseline / 'results.json').read_text(encoding='utf-8'))
    assert baseline_result['train_sha256'] == manifest['data_hashes']['train']
    assert baseline_result['validation_sha256'] == manifest['data_hashes']['validation']
    best_baseline = max(baseline_result['trials'], key=lambda row: row['macro_f1'])
    source = run / 'source_snapshot/src'
    source_matches = {name: sha256(source / name) == expected_hash for name, expected_hash in manifest['code_hashes'].items()}
    write_json(output, {'checked_on': datetime.now(timezone.utc).isoformat(), 'run': run.as_posix(), 'epochs': len(history),
        'best_epoch': best_epoch, 'last_checkpoint_epoch': last_epoch,
        'validation_rows': len(validation), 'recomputed_metrics': recomputed,
        'colab_baseline_macro_f1': best_baseline['macro_f1'],
        'macro_f1_delta': recorded['macro_f1'] - best_baseline['macro_f1'],
        'checkpoint_reload_sample': {'rows': len(indices), 'all_predictions_match': actual == expected},
        'source_snapshot_matches_manifest': source_matches,
        'best_checkpoint_sha256': sha256(run / 'best_model.pt'),
        'limitations': ['Full validation inference was not rerun; metrics recomputed from all saved predictions.',
                       'This verifier covers the original run only; use audit_downloaded_stage2.py for final selection. No test evaluation performed.']})
    print(json.dumps({'best_epoch': best_epoch, 'macro_f1': recorded['macro_f1'],
                      'colab_baseline': best_baseline['macro_f1'], 'sample_matches': len(indices)}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', default='outputs/stage2/runs/phobert_lr2e-5_len128_seed42')
    parser.add_argument('--baseline', default='outputs/stage2/baseline')
    parser.add_argument('--cache', default='data/cache/segmented')
    parser.add_argument('--output', default='outputs/stage2/review/verification.json')
    args = parser.parse_args()
    verify(args.run, args.baseline, args.cache, args.output)
