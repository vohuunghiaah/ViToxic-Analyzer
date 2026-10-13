"""Audit downloaded Colab artifacts; never train or evaluate test data."""
from pathlib import Path
from datetime import datetime, timezone
import json
import hashlib
import sys
import numpy as np
import pandas as pd
import torch
from transformers import AutoTokenizer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.experiment import metrics, sha256, write_json
from src.model import load_checkpoint_model


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def check(actual, expected, context):
    if isinstance(expected, dict):
        for key, value in expected.items():
            check(actual[key], value, f'{context}.{key}')
    elif isinstance(expected, (float, int)):
        if not np.isclose(actual, expected, rtol=0, atol=1e-10):
            raise ValueError(f'{context}: {actual} != {expected}')
    elif actual != expected:
        raise ValueError(f'{context}: mismatch')


def main():
    torch.set_num_threads(4)
    base = ROOT / 'outputs/stage2'
    selection = read(base / 'final_selection/selection.json')
    table = pd.read_csv(base / 'final_selection/tuning_comparison.csv')
    validation = pd.read_csv(ROOT / 'data/processed/validation.csv')
    hashes = {split: sha256(ROOT / 'data/processed' / filename) for split, filename in
              [('train', 'train_decontaminated.csv'), ('validation', 'validation.csv')]}
    train = pd.read_csv(ROOT / 'data/processed/train_decontaminated.csv').fillna({'text_clean': ''})
    check(selection['data_hashes'], hashes, 'selection data')
    check(selection['selection_split'], 'validation', 'selection split')
    check(selection['selection_metric'], 'macro_f1', 'selection metric')
    runs = sorted((base / 'runs').glob('*/manifest.json')) + sorted((base / 'search_v1').glob('trial_*/manifest.json'))
    results = {}
    snapshots = list((base / 'runs').glob('*/source_snapshot/src')) + [ROOT / 'src']
    for manifest_path in runs:
        run = manifest_path.parent
        manifest, config = read(manifest_path), read(run / 'config.json')
        recorded, history = read(run / 'validation_metrics.json'), read(run / 'history.json')
        predictions = pd.read_csv(run / 'validation_predictions.csv')
        check(manifest['data_hashes'], hashes, run.name)
        check(manifest['evaluation_split'], 'validation', run.name)
        check(predictions.row_id.tolist(), validation.row_id.tolist(), 'row order')
        check(predictions.label.tolist(), validation.label_id.tolist(), 'labels')
        computed = metrics(predictions.label, predictions.prediction)
        check(recorded, computed, run.name)
        epoch = max(history, key=lambda row: row['validation_macro_f1'])['epoch']
        check(recorded['best_epoch'], epoch, 'best epoch')
        checkpoint = torch.load(run / 'best_model.pt', map_location='cpu', weights_only=True, mmap=True)
        checkpoint_issues = []
        for actual_value, expected_value, context in [
                (checkpoint['epoch'], epoch, 'checkpoint epoch'),
                (recorded, checkpoint['validation'], 'checkpoint metrics')]:
            try:
                check(actual_value, expected_value, context)
            except ValueError as error:
                checkpoint_issues.append(str(error))
        finite = all(bool(torch.isfinite(tensor).all()) for tensor in checkpoint['model'].values())
        if not finite:
            raise ValueError(f'{run.name}: nonfinite best weights')
        del checkpoint
        last = torch.load(run / 'last_checkpoint.pt', map_location='cpu', weights_only=True, mmap=True)
        for actual_value, expected_value, context in [
                (last['history'], history, 'last history'),
                (last['epoch'] + 1, history[-1]['epoch'], 'last epoch'),
                (last['best_epoch'], epoch, 'last best epoch'),
                (last['data_hashes'], hashes, 'last hashes')]:
            try:
                check(actual_value, expected_value, context)
            except ValueError as error:
                checkpoint_issues.append(str(error))
        del last
        source = {name: any((folder / name).is_file() and sha256(folder / name) == digest
                           for folder in snapshots) for name, digest in manifest['code_hashes'].items()}
        for name, digest in manifest['segmenter'].items():
            check(sha256(ROOT / 'resources/vncorenlp' / name), digest, 'segmenter')
        for frame, expected_key in zip([train, validation], manifest['segmentation_cache_keys']):
            payload = {'version': 1, 'segmenter': manifest['segmenter'],
                       'rows': list(zip(frame.row_id.tolist(), frame.text_clean.tolist()))}
            key = hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode('utf-8')).hexdigest()
            check(key, expected_key, 'segmentation cache input identity')
        row = dict(run=run.name, learning_rate=config['learning_rate'], max_length=config['max_length'],
                   dropout=config['dropout'], effective_batch=config['batch_size'] * config['gradient_accumulation_steps'],
                   seed=config['seed'], best_epoch=epoch, macro_f1=recorded['macro_f1'],
                   weighted_f1=recorded['weighted_f1'], accuracy=recorded['accuracy'],
                   offensive_f1=recorded['per_class']['OFFENSIVE']['f1-score'],
                   hate_recall=recorded['per_class']['HATE']['recall'])
        results[run.name] = dict(summary=row, path=run.relative_to(ROOT).as_posix(),
                                source_hashes_available=source, best_weights_finite=finite,
                                checkpoint_issues=checkpoint_issues,
                                validation_predictions_verified=len(predictions))
        print(f'{"ISSUE" if checkpoint_issues else "PASS"} artifacts: {run.name} {checkpoint_issues}', flush=True)
    if len(table) != 8 or table.run.nunique() != 8:
        raise ValueError('Expected eight distinct tuning runs')
    for row in table.to_dict('records'):
        check(row, results[row['run']]['summary'], 'comparison')
    winner = max((results[name]['summary'] for name in table.run), key=lambda row: row['macro_f1'])
    check(selection['selected'], winner, 'selected model')
    search = pd.read_csv(base / 'search_v1/comparison.csv')
    for row in search.to_dict('records'):
        check(row['status'], 'completed', 'search status')
        check(row['macro_f1'], results[f"trial_{row['trial']:02d}"]['summary']['macro_f1'], 'search score')
    baseline = read(base / 'baseline/results.json')
    check(baseline['train_sha256'], hashes['train'], 'baseline train')
    check(baseline['validation_sha256'], hashes['validation'], 'baseline validation')
    baseline_best = max(baseline['trials'], key=lambda row: row['macro_f1'])
    run = ROOT / results[winner['run']]['path']
    model, config = load_checkpoint_model(run)
    tokenizer = AutoTokenizer.from_pretrained(run / 'tokenizer', local_files_only=True, use_fast=False)
    key = read(run / 'manifest.json')['segmentation_cache_keys'][1]
    texts = read(ROOT / 'data/cache/segmented' / f'{key}.json')
    check(len(texts), len(validation), 'cache rows')
    actual = []
    with torch.inference_mode():
        for start in range(0, len(texts), 16):
            inputs = tokenizer(texts[start:start+16], padding=True, truncation=True, max_length=config.max_length,
                               return_token_type_ids=False, return_tensors='pt')
            logits = model(**inputs)
            if not bool(torch.isfinite(logits).all()):
                raise ValueError('Nonfinite inference')
            actual.extend(logits.argmax(-1).tolist())
            if start % 256 == 0:
                print(f'Full validation inference: {len(actual)}/{len(texts)}', flush=True)
    saved = pd.read_csv(run / 'validation_predictions.csv').prediction.to_numpy()
    mismatches = np.flatnonzero(np.asarray(actual) != saved).tolist()
    report = dict(checked_at=datetime.now(timezone.utc).isoformat(), runs=results,
                  artifact_consistency_passed=not any(item['checkpoint_issues'] for item in results.values()),
                  selected=winner, baseline_macro_f1=baseline_best['macro_f1'],
                  best_checkpoint_sha256=sha256(run / 'best_model.pt'),
                  full_validation_reload=dict(rows=len(actual), mismatched_indices=mismatches,
                                              metrics=metrics(validation.label_id, actual)),
                  limitations=['No training or test evaluation performed.',
                               'Other runs: saved predictions and checkpoint metadata/finite best weights checked; inference not repeated.',
                               'Baseline score checked from recorded results; baseline inference not repeated.',
                               'Cached segmentation used; Java segmentation not rerun.'])
    write_json(base / 'review/full_audit.json', report)
    print(json.dumps(dict(runs=len(results), winner=winner, inference_mismatches=len(mismatches)), indent=2))
    return 1 if mismatches or not report['artifact_consistency_passed'] else 0


if __name__ == '__main__':
    sys.exit(main())
