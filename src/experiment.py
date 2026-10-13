"""Shared metrics, schema, provenance and atomic JSON output."""
import hashlib
import json
import os
from pathlib import Path

import pandas as pd
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from .data_loader import LABELS


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    os.replace(temp, path)


def load_processed(path, split):
    frame = pd.read_csv(path, keep_default_na=False, dtype={'row_id': str, 'text_clean': str})
    if not {'row_id', 'text_clean', 'label_id'}.issubset(frame.columns) or frame.empty:
        raise ValueError(f'{path}: missing required columns or empty dataset')
    if not frame.row_id.str.startswith(split + ':').all() or frame.row_id.duplicated().any():
        raise ValueError(f'{path}: expected unique {split}: row IDs; test is not allowed in Stage 2')
    labels = pd.to_numeric(frame.label_id, errors='coerce')
    if not labels.isin(LABELS).all():
        raise ValueError(f'{path}: labels must be in 0, 1, 2')
    frame['label_id'] = labels.astype(int)
    return frame


def metrics(labels, predictions):
    return {
        'accuracy': float(accuracy_score(labels, predictions)),
        'macro_f1': float(f1_score(labels, predictions, labels=list(LABELS), average='macro', zero_division=0)),
        'weighted_f1': float(f1_score(labels, predictions, labels=list(LABELS), average='weighted', zero_division=0)),
        'per_class': classification_report(labels, predictions, labels=list(LABELS),
                                           target_names=list(LABELS.values()), output_dict=True, zero_division=0),
        'confusion_matrix': confusion_matrix(labels, predictions, labels=list(LABELS)).tolist(),
    }
