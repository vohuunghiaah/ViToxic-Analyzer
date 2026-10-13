"""Serializable experiment configuration. Paths are relative to project root."""
from dataclasses import asdict, dataclass
import json
from pathlib import Path


@dataclass
class TrainConfig:
    model_name: str = 'vinai/phobert-base'
    revision: str = 'main'
    train_path: str = 'data/processed/train_decontaminated.csv'
    validation_path: str = 'data/processed/validation.csv'
    segmenter_dir: str = 'resources/vncorenlp'
    cache_dir: str = 'data/cache/segmented'
    output_dir: str = 'outputs/stage2/runs/phobert_default'
    max_length: int = 128
    batch_size: int = 8
    eval_batch_size: int = 16
    gradient_accumulation_steps: int = 4
    epochs: int = 5
    learning_rate: float = 2e-5
    weight_decay: float = 0.01
    warmup_ratio: float = 0.1
    dropout: float = 0.1
    patience: int = 2
    min_delta: float = 0.0001
    max_grad_norm: float = 1.0
    freeze_epochs: int = 0
    gradient_checkpointing: bool = True
    imbalance: str = 'weighted_loss'
    precision: str = 'fp16'
    device: str = 'auto'
    num_workers: int = 0
    seed: int = 42
    selection_metric: str = 'macro_f1'

    def validate(self):
        for name in ['batch_size', 'eval_batch_size', 'gradient_accumulation_steps', 'epochs', 'patience']:
            if getattr(self, name) < 1:
                raise ValueError(f'{name} must be >= 1')
        if not 2 <= self.max_length <= 256:
            raise ValueError('PhoBERT max_length must be in [2, 256]')
        if not 0 <= self.dropout < 1 or not 0 <= self.warmup_ratio < 1:
            raise ValueError('dropout and warmup_ratio must be in [0, 1)')
        if self.learning_rate <= 0 or self.weight_decay < 0 or self.max_grad_norm <= 0 or self.min_delta < 0:
            raise ValueError('Invalid optimizer or early-stopping settings')
        if not 0 <= self.freeze_epochs < self.epochs or self.num_workers < 0:
            raise ValueError('Invalid freeze_epochs or num_workers')
        if self.imbalance not in {'none', 'weighted_loss', 'sampler'}:
            raise ValueError('Choose ONE imbalance strategy')
        if self.precision not in {'fp32', 'fp16', 'bf16'}:
            raise ValueError('Unknown precision')
        if self.selection_metric not in {'macro_f1', 'loss'}:
            raise ValueError('selection_metric must be macro_f1 or loss')
        if Path(self.train_path).resolve() == Path(self.validation_path).resolve():
            raise ValueError('Train and validation must be different files')
        return self

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_json(cls, path):
        return cls(**json.loads(Path(path).read_text(encoding='utf-8'))).validate()
