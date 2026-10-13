import numpy as np
import pandas as pd
import pytest

from src.evaluate import paired_bootstrap, error_tables, render_reports, run
from src.experiment import metrics, load_processed, sha256, write_json


def test_paired_bootstrap_preserves_pairing_and_reproducibility():
    labels = np.tile([0, 1, 2], 20)
    prediction = np.tile([0, 0, 2], 20)
    first = paired_bootstrap(labels, prediction, prediction, repetitions=100)
    assert first['difference'] == [0., 0.]
    assert first == paired_bootstrap(labels, prediction, prediction, repetitions=100)
    worse = paired_bootstrap(labels, np.zeros_like(labels), labels, repetitions=100)
    assert worse['difference'][0] > 0
    with pytest.raises(ValueError):
        paired_bootstrap([], [], [])


def test_error_alignment_overlap_and_absent_classes(tmp_path):
    frame = pd.DataFrame({'row_id': ['test:7', 'test:2', 'test:9'],
                          'text_clean': ['same', 'long', 'clean'], 'label_id': [2, 1, 0]})
    probabilities = np.array([[.8, .1, .1], [.1, .8, .1], [.8, .1, .1]])
    result = error_tables(frame, [0, 1, 0], probabilities, [10, 150, 5], {'  SAME  '})
    assert result.row_id.tolist() == frame.row_id.tolist()
    assert result.correct.tolist() == [False, True, True]
    assert result.validation_overlap.tolist() == [True, False, False]
    scores = metrics(frame.label_id, result.prediction)
    render_reports(tmp_path, {'baseline': scores, 'phobert': scores}, result,
                   {'phobert': [0, 1], 'difference': [0, 0]}, 'fixture')
    errors = pd.read_csv(tmp_path / 'errors.csv')
    assert errors.row_id.tolist() == ['test:7']
    slices = pd.read_csv(tmp_path / 'slices.csv').set_index('slice')
    assert slices.loc['tokens_over_128', 'rows'] == 1
    assert slices.loc['no_validation_overlap', 'rows'] == 2
    assert np.isclose(slices.loc['tokens_over_128', 'macro_f1'], 1/3)
    assert (tmp_path / 'phobert_confusion_matrix.png').is_file()


def test_test_loader_rejects_other_splits_and_duplicate_ids(tmp_path):
    path = tmp_path / 'test.csv'
    for ids in [['train:0', 'test:1'], ['test:0', 'test:0']]:
        pd.DataFrame({'row_id': ids, 'text_clean': ['a', 'b'], 'label_id': [0, 1]}).to_csv(path, index=False)
        with pytest.raises(ValueError):
            load_processed(path, 'test')


def test_evaluation_lock_rejects_changed_checkpoint_and_test_selection(tmp_path):
    stage2 = tmp_path / 'outputs/stage2'
    data = tmp_path / 'data/processed'
    data.mkdir(parents=True)
    for filename in ['train_decontaminated.csv', 'validation.csv', 'test.csv']:
        (data / filename).write_text('fixture', encoding='utf-8')
    hashes = {s: sha256(data / p) for s, p in [('train', 'train_decontaminated.csv'), ('validation', 'validation.csv')]}
    selection = {'selection_split': 'test', 'selection_metric': 'macro_f1',
                 'selected': {'run': 'fixture'}, 'data_hashes': hashes}
    selection_path = stage2 / 'final_selection/selection.json'
    write_json(selection_path, selection)
    with pytest.raises(ValueError, match='selected on validation'):
        run(tmp_path)
    selection['selection_split'] = 'validation'
    write_json(selection_path, selection)
    directory = stage2 / 'runs/fixture'
    write_json(directory / 'manifest.json', {'data_hashes': hashes, 'segmenter': {}})
    write_json(directory / 'config.json', {})
    (directory / 'best_model.pt').write_bytes(b'first checkpoint')
    baseline_dir = stage2 / 'baseline'
    write_json(baseline_dir / 'results.json', {s + '_sha256': h for s, h in hashes.items()})
    (baseline_dir / 'baseline.joblib').write_bytes(b'fixture baseline')
    frozen = {'selection': sha256(selection_path), 'checkpoint': sha256(directory / 'best_model.pt'),
              'baseline': sha256(baseline_dir / 'baseline.joblib'), 'config': sha256(directory / 'config.json'),
              'test': sha256(data / 'test.csv'), 'data_hashes': hashes, 'selected_run': 'fixture',
              'evaluation_split': 'test', 'segmenter': {}}
    output = tmp_path / 'outputs/stage3'
    write_json(output / 'lock.json', frozen)
    write_json(output / 'metrics.json', {'fixture': True})
    assert run(tmp_path) == {'fixture': True}
    (directory / 'best_model.pt').write_bytes(b'changed checkpoint')
    with pytest.raises(ValueError, match='inputs changed'):
        run(tmp_path)
