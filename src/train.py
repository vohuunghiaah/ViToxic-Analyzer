"""Train PhoBERT; resumable at completed epoch boundaries, validation selection only."""
import argparse
import math
import os
from pathlib import Path
import platform
import random
import time
from importlib.metadata import version

import numpy as np
import pandas as pd
import torch
from torch import nn
from transformers import AutoConfig, AutoTokenizer, get_cosine_schedule_with_warmup
from tqdm.auto import tqdm

from .config import TrainConfig
from .data_loader import class_weights
from .dataset import ViHSDDataset, make_loader, token_length_report
from .experiment import load_processed, metrics, sha256, write_json
from .model import PhoBERTClassifier
from .segmentation import Segmenter, segment_frame


def seed_everything(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True


def choose_device(config):
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu') if config.device == 'auto' else torch.device(config.device)
    if device.type == 'cuda' and not torch.cuda.is_available():
        raise RuntimeError('CUDA unavailable. Select a GPU runtime in Colab.')
    if device.type != 'cuda' and config.precision != 'fp32':
        raise ValueError('Use precision=fp32 on CPU; Colab training should use a GPU')
    if config.precision == 'bf16' and not torch.cuda.is_bf16_supported():
        raise ValueError('GPU does not support bf16; use fp16')
    return device


def atomic_torch_save(value, path):
    path = Path(path)
    temp = path.with_suffix(path.suffix + '.tmp')
    torch.save(value, temp)
    os.replace(temp, path)


def capture_rng(loader):
    state = np.random.get_state()
    result = {'python': random.getstate(), 'numpy': [state[0], state[1].tolist(), state[2], state[3], state[4]],
              'torch': torch.get_rng_state(), 'loader': loader.generator.get_state()}
    if torch.cuda.is_available():
        result['cuda'] = torch.cuda.get_rng_state_all()
    if getattr(loader.sampler, 'generator', None) is not None:
        result['sampler'] = loader.sampler.generator.get_state()
    return result


def restore_rng(state, loader):
    random.setstate(state['python'])
    s = state['numpy']
    np.random.set_state((s[0], np.array(s[1], dtype=np.uint32), s[2], s[3], s[4]))
    torch.set_rng_state(state['torch'])
    loader.generator.set_state(state['loader'])
    if 'cuda' in state and torch.cuda.is_available():
        torch.cuda.set_rng_state_all(state['cuda'])
    if 'sampler' in state:
        loader.sampler.generator.set_state(state['sampler'])


def optimizer_groups(model, weight_decay):
    decay, no_decay = [], []
    for name, parameter in model.named_parameters():
        (no_decay if parameter.ndim == 1 or name.endswith('.bias') else decay).append(parameter)
    # Include frozen encoder params so unfreezing does not require a new optimizer.
    return [{'params': decay, 'weight_decay': weight_decay}, {'params': no_decay, 'weight_decay': 0.0}]


def train_epoch(model, loader, optimizer, scheduler, scaler, device, config, weights):
    model.train()
    if not any(p.requires_grad for p in model.encoder.parameters()):
        model.encoder.eval()
    optimizer.zero_grad(set_to_none=True)
    loss_sum, denominator, group_denominator, correct, rows = 0., 0., 0., 0, 0
    dtype = torch.float16 if config.precision == 'fp16' else torch.bfloat16
    criterion = nn.CrossEntropyLoss(weight=weights, reduction='sum')
    for step, batch in enumerate(tqdm(loader, desc='Train', leave=False)):
        batch = {key: value.to(device) for key, value in batch.items()}
        labels = batch.pop('labels')
        with torch.autocast(device_type=device.type, dtype=dtype, enabled=config.precision != 'fp32'):
            logits = model(**batch)
        loss = criterion(logits.float(), labels)
        if not torch.isfinite(loss):
            raise FloatingPointError('Non-finite training loss')
        batch_denominator = weights[labels].sum().item() if weights is not None else len(labels)
        scaler.scale(loss).backward()
        loss_sum += loss.item()
        denominator += batch_denominator
        group_denominator += batch_denominator
        correct += (logits.argmax(-1) == labels).sum().item()
        rows += len(labels)
        if (step + 1) % config.gradient_accumulation_steps == 0 or step + 1 == len(loader):
            scaler.unscale_(optimizer)
            # Normalize across actual examples/weights, including short final groups.
            for p in model.parameters():
                if p.grad is not None:
                    p.grad.div_(group_denominator)
            nn.utils.clip_grad_norm_(model.parameters(), config.max_grad_norm)
            old_scale = scaler.get_scale()
            scaler.step(optimizer)
            scaler.update()
            if scaler.get_scale() >= old_scale:
                scheduler.step()  # Do not advance on AMP overflow/skipped update.
            optimizer.zero_grad(set_to_none=True)
            group_denominator = 0.
    return {'loss': loss_sum / denominator, 'accuracy': correct / rows}


@torch.no_grad()
def evaluate(model, loader, device, weights=None):
    model.eval()
    labels_all, predictions = [], []
    numerator, denominator = 0., 0.
    for batch in loader:
        batch = {key: value.to(device) for key, value in batch.items()}
        labels = batch.pop('labels')
        logits = model(**batch)
        numerator += nn.functional.cross_entropy(logits.float(), labels, weight=weights, reduction='sum').item()
        denominator += weights[labels].sum().item() if weights is not None else len(labels)
        labels_all.extend(labels.cpu().tolist())
        predictions.extend(logits.argmax(-1).cpu().tolist())
    return {'loss': numerator / denominator, **metrics(labels_all, predictions)}, predictions


class EarlyStopping:
    def __init__(self, metric='macro_f1', patience=2, min_delta=.0001):
        self.metric, self.patience, self.min_delta = metric, patience, min_delta
        self.best = None
        self.bad_epochs = 0

    def update(self, value):
        improvement = self.best is None or (value < self.best - self.min_delta if self.metric == 'loss' else value > self.best + self.min_delta)
        if improvement:
            self.best, self.bad_epochs = value, 0
        else:
            self.bad_epochs += 1
        return improvement, self.bad_epochs >= self.patience


def run(config, resume=False):
    config.validate()
    device = choose_device(config)
    seed_everything(config.seed)
    output = Path(config.output_dir)
    if output.exists() and any(output.iterdir()) and not resume:
        raise FileExistsError(f'{output} is not empty; choose a new run name or --resume')
    if resume and not (output / 'last_checkpoint.pt').exists():
        raise FileNotFoundError('No completed-epoch checkpoint to resume')
    train = load_processed(config.train_path, 'train')
    validation = load_processed(config.validation_path, 'validation')
    fingerprints = {'train': sha256(config.train_path), 'validation': sha256(config.validation_path)}
    code_hashes = {p.name: sha256(p) for p in Path(__file__).parent.glob('*.py')}
    checkpoint = torch.load(output / 'last_checkpoint.pt', map_location='cpu', weights_only=True) if resume else None
    if checkpoint:
        ignored = {'output_dir', 'train_path', 'validation_path', 'segmenter_dir', 'cache_dir', 'device'}
        for name, value in config.to_dict().items():
            if name not in ignored and checkpoint['config'][name] != value:
                raise ValueError(f'Cannot resume after changing {name}; start a new run')
        if checkpoint['data_hashes'] != fingerprints:
            raise ValueError('Dataset changed since checkpoint')
        if checkpoint['code_hashes'] != code_hashes:
            raise ValueError('Source code changed since checkpoint; use a new run')
    output.mkdir(parents=True, exist_ok=True)
    segmenter = Segmenter(config.segmenter_dir)
    if checkpoint and checkpoint['segmenter'] != segmenter.identity:
        raise ValueError('Segmenter assets changed since checkpoint')
    train_texts, train_key = segment_frame(train, segmenter, config.cache_dir)
    val_texts, val_key = segment_frame(validation, segmenter, config.cache_dir)
    if resume:
        tokenizer = AutoTokenizer.from_pretrained(output / 'tokenizer', use_fast=False, local_files_only=True)
        model = PhoBERTClassifier.from_config(AutoConfig.from_pretrained(output / 'encoder_config'), config.dropout)
        model.load_state_dict(checkpoint['model'])
        revision = checkpoint['resolved_revision']
    else:
        tokenizer = AutoTokenizer.from_pretrained(config.model_name, revision=config.revision, use_fast=False)
        model = PhoBERTClassifier.from_pretrained(config.model_name, config.revision, config.dropout)
        revision = getattr(model.encoder.config, '_commit_hash', None)
        if revision is not None:
            # Pin tokenizer to exactly the encoder revision, even if 'main' moved.
            tokenizer = AutoTokenizer.from_pretrained(config.model_name, revision=revision, use_fast=False)
        tokenizer.save_pretrained(output / 'tokenizer')
        model.encoder.config.save_pretrained(output / 'encoder_config')
    if config.gradient_checkpointing:
        model.encoder.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant': False})
    model.to(device)
    train_ds = ViHSDDataset(train_texts, train.label_id.tolist(), tokenizer, config.max_length)
    val_ds = ViHSDDataset(val_texts, validation.label_id.tolist(), tokenizer, config.max_length)
    train_loader, val_loader = make_loader(train_ds, tokenizer, config, True), make_loader(val_ds, tokenizer, config, False)
    weight_dict = class_weights(train.label_id)
    weights = torch.tensor(list(weight_dict.values()), dtype=torch.float32, device=device) if config.imbalance == 'weighted_loss' else None
    optimizer = torch.optim.AdamW(optimizer_groups(model, config.weight_decay), lr=config.learning_rate)
    total_steps = math.ceil(len(train_loader) / config.gradient_accumulation_steps) * config.epochs
    scheduler = get_cosine_schedule_with_warmup(optimizer, int(total_steps * config.warmup_ratio), total_steps)
    scaler = torch.amp.GradScaler('cuda', enabled=device.type == 'cuda' and config.precision == 'fp16')
    stopping = EarlyStopping(config.selection_metric, config.patience, config.min_delta)
    start, history, best_epoch = 0, [], None
    if checkpoint:
        optimizer.load_state_dict(checkpoint['optimizer'])
        scheduler.load_state_dict(checkpoint['scheduler'])
        scaler.load_state_dict(checkpoint['scaler'])
        stopping.best, stopping.bad_epochs = checkpoint['best'], checkpoint['bad_epochs']
        start, history, best_epoch = checkpoint['epoch'] + 1, checkpoint['history'], checkpoint['best_epoch']
        restore_rng(checkpoint['rng'], train_loader)
        del checkpoint
    write_json(output / 'config.json', config.to_dict())
    write_json(output / 'manifest.json', {
        'evaluation_split': 'validation', 'data_hashes': fingerprints, 'rows': {'train': len(train), 'validation': len(validation)},
        'class_weights': weight_dict, 'segmenter': segmenter.identity, 'segmentation_cache_keys': [train_key, val_key],
        'model_revision': revision, 'python': platform.python_version(), 'device': str(device),
        'gpu': torch.cuda.get_device_name(device) if device.type == 'cuda' else None,
        'packages': {name: version(name) for name in ['torch', 'transformers', 'numpy', 'pandas', 'py-vncorenlp']},
        'code_hashes': code_hashes,
        'empty_texts': {'train': int(train.text_clean.str.strip().eq('').sum()), 'validation': int(validation.text_clean.str.strip().eq('').sum())},
    })
    if not resume:
        write_json(output / 'token_lengths.json', {'train': token_length_report(train_texts, tokenizer), 'validation': token_length_report(val_texts, tokenizer)})
    for epoch in range(start, config.epochs):
        if stopping.bad_epochs >= config.patience:
            break
        model.freeze_encoder(epoch < config.freeze_epochs)
        began = time.monotonic()
        train_result = train_epoch(model, train_loader, optimizer, scheduler, scaler, device, config, weights)
        validation_result, _ = evaluate(model, val_loader, device, weights)
        improved, stop = stopping.update(validation_result[config.selection_metric])
        if improved:
            best_epoch = epoch + 1
            atomic_torch_save({'model': model.state_dict(), 'epoch': best_epoch,
                               'validation': validation_result}, output / 'best_model.pt')
        history.append({'epoch': epoch + 1, 'train_loss': train_result['loss'], 'train_accuracy': train_result['accuracy'],
                        'validation_loss': validation_result['loss'], 'validation_macro_f1': validation_result['macro_f1'],
                        'validation_accuracy': validation_result['accuracy'], 'validation_weighted_f1': validation_result['weighted_f1'],
                        'learning_rate': optimizer.param_groups[0]['lr'], 'seconds': time.monotonic() - began})
        atomic_torch_save({'model': model.state_dict(), 'optimizer': optimizer.state_dict(), 'scheduler': scheduler.state_dict(),
            'scaler': scaler.state_dict(), 'epoch': epoch, 'history': history, 'best': stopping.best,
            'best_epoch': best_epoch, 'bad_epochs': stopping.bad_epochs, 'rng': capture_rng(train_loader),
            'config': config.to_dict(), 'data_hashes': fingerprints, 'segmenter': segmenter.identity,
            'resolved_revision': revision, 'code_hashes': code_hashes}, output / 'last_checkpoint.pt')
        write_json(output / 'history.json', history)
        print(f'Epoch {epoch+1}: train_loss={train_result["loss"]:.4f}, val_macro_f1={validation_result["macro_f1"]:.4f}, saved to {output}', flush=True)
        if stop:
            break
    best = torch.load(output / 'best_model.pt', map_location='cpu', weights_only=True)
    model.load_state_dict(best['model'])
    final, predictions = evaluate(model, val_loader, device, weights)
    write_json(output / 'validation_metrics.json', {'best_epoch': best['epoch'], 'evaluation_split': 'validation', **final})
    pd.DataFrame({'row_id': validation.row_id, 'label': validation.label_id, 'prediction': predictions}).to_csv(output / 'validation_predictions.csv', index=False)
    return final


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    run(TrainConfig.from_json(args.config), args.resume)
