"""CSV schema checks and train-only imbalance utilities. Torch is optional."""
from pathlib import Path
import numpy as np
import pandas as pd

LABELS = {0: "CLEAN", 1: "OFFENSIVE", 2: "HATE"}
SPLITS = ("train", "validation", "test")


def load_split(data_dir: str | Path, split: str) -> pd.DataFrame:
    if split not in SPLITS:
        raise ValueError(f"Unknown split: {split}")
    path = Path(data_dir) / f"ViHSD_{split}.csv"
    # Preserve literal 'NA', 'null', etc.; empty strings are handled explicitly.
    frame = pd.read_csv(path, keep_default_na=False, dtype={"free_text": str})
    if not {"free_text", "label_id"}.issubset(frame.columns):
        raise ValueError(f"{path}: required columns free_text, label_id")
    labels = pd.to_numeric(frame.label_id, errors="coerce")
    if labels.isna().any() or not labels.isin(LABELS).all():
        raise ValueError(f"{path}: labels must be integers in {{0, 1, 2}}")
    frame["label_id"] = labels.astype(int)
    frame.insert(0, "row_id", [f"{split}:{i}" for i in range(len(frame))])
    return frame


def class_weights(labels) -> dict[int, float]:
    """Balanced weights N / (K * count_k); caller must supply train only."""
    values = np.asarray(labels)
    if values.ndim != 1 or not np.isin(values, list(LABELS)).all():
        raise ValueError("Expected one-dimensional labels in {0, 1, 2}")
    counts = {label: int((values == label).sum()) for label in LABELS}
    if not all(counts.values()):
        raise ValueError("Training split must contain every class")
    return {label: len(values) / (len(LABELS) * count) for label, count in counts.items()}


def make_train_sampler(labels, seed: int = 42):
    """Optional alternative to weighted loss, never use on validation/test."""
    import torch
    from torch.utils.data import WeightedRandomSampler
    weights = class_weights(labels)
    generator = torch.Generator().manual_seed(seed)
    return WeightedRandomSampler(
        [weights[int(label)] for label in labels], len(labels),
        replacement=True, generator=generator,
    )


def make_dataloader(dataset, *, batch_size=16, training=False, sampler=None,
                    seed=42, collate_fn=None):
    """Wrap a future Stage 2 tokenized Dataset; no tokenizer/model downloads."""
    import torch
    from torch.utils.data import DataLoader
    if sampler is not None and not training:
        raise ValueError("Sampling is only allowed for training")
    return DataLoader(dataset, batch_size=batch_size, shuffle=training and sampler is None,
                      sampler=sampler, generator=torch.Generator().manual_seed(seed),
                      num_workers=0, collate_fn=collate_fn)
