"""Pre-tokenized Dataset and dynamic padding; segmentation is mandatory upstream."""
import numpy as np
import torch
from torch.utils.data import Dataset, DataLoader
from transformers import DataCollatorWithPadding
from .data_loader import make_train_sampler


class ViHSDDataset(Dataset):
    def __init__(self, segmented_texts, labels, tokenizer, max_length=128):
        if len(segmented_texts) != len(labels) or not len(labels):
            raise ValueError('Nonempty text and label arrays must have equal lengths')
        if not 2 <= max_length <= 256:
            raise ValueError('Invalid PhoBERT sequence length')
        self.encodings = tokenizer(list(segmented_texts), truncation=True, max_length=max_length,
                                   padding=False, return_token_type_ids=False)
        self.labels = [int(label) for label in labels]
        if not set(self.labels).issubset({0, 1, 2}):
            raise ValueError('Invalid labels')

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, index):
        return {**{k: v[index] for k, v in self.encodings.items()}, 'labels': self.labels[index]}


def token_length_report(texts, tokenizer):
    lengths = np.array([len(tokenizer.encode(text, truncation=False)) for text in texts])
    return {'rows': len(lengths), 'p50': float(np.quantile(lengths, .5)),
            'p95': float(np.quantile(lengths, .95)), 'p99': float(np.quantile(lengths, .99)),
            'max': int(lengths.max()),
            'truncation_fraction': {str(n): float((lengths > n).mean()) for n in [128, 256]}}


def make_loader(dataset, tokenizer, config, training):
    generator = torch.Generator().manual_seed(config.seed)
    sampler = make_train_sampler(dataset.labels, config.seed) if training and config.imbalance == 'sampler' else None
    loader = DataLoader(dataset, batch_size=config.batch_size if training else config.eval_batch_size,
                        shuffle=training and sampler is None, sampler=sampler,
                        collate_fn=DataCollatorWithPadding(tokenizer, pad_to_multiple_of=8),
                        num_workers=config.num_workers, generator=generator,
                        pin_memory=torch.cuda.is_available())
    return loader
