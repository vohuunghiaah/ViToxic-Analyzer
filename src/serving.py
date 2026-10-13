"""Offline inference from a checksummed deployment bundle; never fit a model."""
import json
import os
from pathlib import Path
import shutil
import tempfile

import torch
from transformers import AutoTokenizer

from .experiment import sha256
from .model import load_checkpoint_model
from .preprocessing import PreprocessingConfig, preprocess_text
from .segmentation import ASSETS, Segmenter

LABELS = ['CLEAN', 'OFFENSIVE', 'HATE']
MAX_TEXT_CHARS = 5000
MAX_BATCH_SIZE = 32
MAX_BATCH_CHARS = 20000


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def verify_bundle(directory):
    directory = Path(directory).resolve()
    info = read_json(directory / 'bundle.json')
    if info.get('schema_version') != 1 or info.get('labels') != LABELS:
        raise ValueError('Unsupported deployment bundle')
    required = {'model/best_model.pt', 'model/config.json', 'model/encoder_config/config.json',
                'model/tokenizer/tokenizer_config.json', 'model/tokenizer/vocab.txt',
                'model/tokenizer/bpe.codes', 'preprocessing.json',
                *('vncorenlp/' + name for name in ASSETS)}
    if not required.issubset(info['files']):
        raise ValueError('Incomplete deployment manifest')
    for name, digest in info['files'].items():
        path = (directory / name).resolve()
        if not path.is_relative_to(directory) or not path.is_file() or sha256(path) != digest:
            raise ValueError(f'Deployment integrity failure: {name}')
    if info['checkpoint_sha256'] != info['files']['model/best_model.pt']:
        raise ValueError('Checkpoint identity mismatch')
    return info


def clean_inputs(texts, config):
    if not isinstance(texts, list) or not 1 <= len(texts) <= MAX_BATCH_SIZE:
        raise ValueError(f'Provide 1–{MAX_BATCH_SIZE} texts')
    if any(not isinstance(text, str) or not 1 <= len(text) <= MAX_TEXT_CHARS for text in texts):
        raise ValueError(f'Each text must contain 1–{MAX_TEXT_CHARS} characters')
    if sum(map(len, texts)) > MAX_BATCH_CHARS:
        raise ValueError(f'Batch must not exceed {MAX_BATCH_CHARS} characters')
    if any(any(0xD800 <= ord(char) <= 0xDFFF for char in text) for text in texts):
        raise ValueError('Invalid Unicode surrogate in text')
    cleaned = [preprocess_text(text, config) for text in texts]
    if any(not text.strip() for text in cleaned):
        raise ValueError('Text must not be empty after normalization')
    return cleaned


class Predictor:
    """Create and call on one dedicated worker, including the Java segmenter."""
    def __init__(self, bundle, device='cpu', threads=4):
        self.bundle = Path(bundle).resolve()
        self.info = verify_bundle(self.bundle)
        if device not in {'cpu', 'cuda'} or (device == 'cuda' and not torch.cuda.is_available()):
            raise ValueError('Requested device is not available')
        if threads < 1:
            raise ValueError('threads must be positive')
        self.device = device
        torch.set_num_threads(threads)
        self.preprocessing = PreprocessingConfig(**read_json(self.bundle / 'preprocessing.json'))
        assets = self.bundle / 'vncorenlp'
        if os.name == 'nt' and not str(assets).isascii():
            assets = Path(tempfile.gettempdir()) / 'vitoxic-api-vncorenlp'
            for name in ASSETS:
                target = assets / name
                target.parent.mkdir(parents=True, exist_ok=True)
                digest = self.info['files']['vncorenlp/' + name]
                if not target.exists() or sha256(target) != digest:
                    shutil.copy2(self.bundle / 'vncorenlp' / name, target)
                if sha256(target) != digest:
                    raise ValueError('Temporary segmenter asset mismatch')
        self.segmenter = Segmenter(assets)
        self.model, self.config = load_checkpoint_model(self.bundle / 'model', device)
        self.tokenizer = AutoTokenizer.from_pretrained(self.bundle / 'model/tokenizer',
                                                       local_files_only=True, use_fast=False)
        self.predict(['Xin chào, chúc bạn một ngày tốt lành!'])

    def metadata(self):
        return {'run': self.info['run'], 'checkpoint_sha256': self.info['checkpoint_sha256'],
                'device': self.device, 'max_length': self.config.max_length,
                'labels': LABELS, 'confidence_calibrated': False,
                'limits': {'max_text_chars': MAX_TEXT_CHARS, 'max_batch_size': MAX_BATCH_SIZE,
                           'max_batch_chars': MAX_BATCH_CHARS}}

    def predict(self, texts):
        cleaned = clean_inputs(texts, self.preprocessing)
        segmented = [self.segmenter(text) for text in cleaned]
        lengths = [len(self.tokenizer.encode(text, truncation=False)) for text in segmented]
        inputs = self.tokenizer(segmented, padding=True, truncation=True,
                                max_length=self.config.max_length,
                                return_token_type_ids=False, return_tensors='pt')
        with torch.inference_mode():
            logits = self.model(**{name: value.to(self.device) for name, value in inputs.items()})
            if not torch.isfinite(logits).all():
                raise RuntimeError('Nonfinite model output')
            probs = logits.softmax(-1).cpu().numpy()
        output = []
        for i, prob in enumerate(probs):
            label = int(prob.argmax())
            output.append({'label_id': label, 'label': LABELS[label], 'confidence': float(prob[label]),
                           'probabilities': {name: float(prob[j]) for j, name in enumerate(LABELS)},
                           'token_count': lengths[i], 'truncated': lengths[i] > self.config.max_length})
        return output
