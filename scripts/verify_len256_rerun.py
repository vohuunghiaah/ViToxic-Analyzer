"""Verify the replacement length-256 run, including full offline validation."""
import sys
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import torch
from transformers import AutoTokenizer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.experiment import metrics, sha256, write_json
from src.model import load_checkpoint_model
from audit_downloaded_stage2 import check, read


def main():
    torch.set_num_threads(4)
    run = ROOT / 'outputs/stage2/runs/phobert_lr3e-5_len256_seed42_rerun'
    config, manifest = read(run / 'config.json'), read(run / 'manifest.json')
    recorded, history = read(run / 'validation_metrics.json'), read(run / 'history.json')
    check(config, dict(learning_rate=3e-5, max_length=256, dropout=.1, batch_size=8,
                       gradient_accumulation_steps=4, seed=42, epochs=5), 'config')
    validation = pd.read_csv(ROOT / 'data/processed/validation.csv')
    predictions = pd.read_csv(run / 'validation_predictions.csv')
    check(predictions.row_id.tolist(), validation.row_id.tolist(), 'rows')
    check(predictions.label.tolist(), validation.label_id.tolist(), 'labels')
    check(recorded, metrics(predictions.label, predictions.prediction), 'metrics')
    for split, name in [('train', 'train_decontaminated.csv'), ('validation', 'validation.csv')]:
        check(sha256(ROOT / 'data/processed' / name), manifest['data_hashes'][split], split)
    check(manifest['evaluation_split'], 'validation', 'split')
    epoch = max(history, key=lambda row: row['validation_macro_f1'])['epoch']
    check(recorded['best_epoch'], epoch, 'best epoch')
    best = torch.load(run / 'best_model.pt', weights_only=True, mmap=True, map_location='cpu')
    check(best['epoch'], epoch, 'checkpoint epoch')
    check(recorded, best['validation'], 'checkpoint metrics')
    assert all(bool(torch.isfinite(t).all()) for t in best['model'].values())
    del best
    last = torch.load(run / 'last_checkpoint.pt', weights_only=True, mmap=True, map_location='cpu')
    last_issues = []
    for actual_value, expected_value, context in [
            (last['history'], history, 'last history'),
            (last['epoch'] + 1, history[-1]['epoch'], 'last epoch'),
            (last['best_epoch'], epoch, 'last best epoch')]:
        try:
            check(actual_value, expected_value, context)
        except ValueError as error:
            last_issues.append(str(error))
    last_epoch = last['epoch'] + 1
    check(last['data_hashes'], manifest['data_hashes'], 'last data')
    check(last['config'], config, 'last config')
    del last
    snapshots = [ROOT / 'src'] + list((ROOT / 'outputs/stage2/runs').glob('*/source_snapshot/src'))
    for name, digest in manifest['code_hashes'].items():
        assert any((folder / name).exists() and sha256(folder / name) == digest for folder in snapshots), name
    for name, digest in manifest['segmenter'].items():
        check(sha256(ROOT / 'resources/vncorenlp' / name), digest, name)
    print(f'PASS best/config/metrics/hashes; last checkpoint issues: {last_issues}', flush=True)
    model, model_config = load_checkpoint_model(run)
    tokenizer = AutoTokenizer.from_pretrained(run / 'tokenizer', local_files_only=True, use_fast=False)
    texts = read(ROOT / 'data/cache/segmented' / (manifest['segmentation_cache_keys'][1] + '.json'))
    check(len(texts), len(validation), 'cache length')
    actual = np.empty(len(texts), dtype=np.int64)
    # Group similar lengths to reduce CPU padding; restore original order below.
    order = np.argsort(np.array([len(text) for text in texts]), kind='stable')
    with torch.inference_mode():
        for start in range(0, len(texts), 16):
            indices = order[start:start + 16]
            inputs = tokenizer([texts[i] for i in indices], padding=True, truncation=True,
                               max_length=model_config.max_length, return_token_type_ids=False, return_tensors='pt')
            logits = model(**inputs)
            assert bool(torch.isfinite(logits).all())
            actual[indices] = logits.argmax(-1).numpy()
            if start % 512 == 0:
                print(f'Validation {start + len(indices)}/{len(texts)}', flush=True)
    mismatches = np.flatnonzero(actual != predictions.prediction.to_numpy()).tolist()
    report = dict(checked_at=datetime.now(timezone.utc).isoformat(), run=run.relative_to(ROOT).as_posix(),
                  best_epoch=epoch, last_epoch=last_epoch, recorded_metrics=recorded,
                  checkpoint_sha256=sha256(run / 'best_model.pt'), best_metadata_checks_passed=True,
                  last_checkpoint_issues=last_issues,
                  full_validation_reload=dict(rows=len(actual), mismatched_indices=mismatches,
                                              metrics=metrics(validation.label_id, actual)),
                  limitations=['Cached segmentation; no Java rerun, no training, no test evaluation.'])
    write_json(ROOT / 'outputs/stage2/review/len256_rerun_verification.json', report)
    print(json.dumps(dict(macro_f1=recorded['macro_f1'], mismatches=len(mismatches), best_epoch=epoch)))
    return 1 if mismatches or last_issues else 0


if __name__ == '__main__':
    sys.exit(main())
