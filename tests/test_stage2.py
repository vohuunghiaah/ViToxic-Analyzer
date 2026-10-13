from dataclasses import replace
import json
from pathlib import Path
import pytest
import pandas as pd
import torch
from transformers import RobertaConfig, RobertaTokenizer

from src.config import TrainConfig
from src.dataset import ViHSDDataset, make_loader
from src.experiment import load_processed
from src.model import PhoBERTClassifier, load_checkpoint_model
from src.segmentation import segment_frame
from src.train import EarlyStopping, train_epoch, run


@pytest.fixture
def tokenizer(tmp_path):
    vocabulary = {'<s>': 0, '<pad>': 1, '</s>': 2, '<unk>': 3, '<mask>': 4, 'a': 5, 'b': 6, 'c': 7}
    (tmp_path / 'vocab.json').write_text(json.dumps(vocabulary), encoding='utf-8')
    (tmp_path / 'merges.txt').write_text('#version: 0.2\n', encoding='utf-8')
    return RobertaTokenizer(vocab_file=str(tmp_path / 'vocab.json'), merges_file=str(tmp_path / 'merges.txt'))


def tiny_model():
    config = RobertaConfig(vocab_size=8, hidden_size=8, num_hidden_layers=1,
                           num_attention_heads=2, intermediate_size=12, max_position_embeddings=260,
                           hidden_dropout_prob=0, attention_probs_dropout_prob=0)
    return PhoBERTClassifier.from_config(config, dropout=0)


def test_dynamic_padding_and_truncation(tokenizer):
    ds = ViHSDDataset(['a', 'a' * 100], [0, 2], tokenizer, max_length=16)
    batch = next(iter(make_loader(ds, tokenizer, TrainConfig(batch_size=2), False)))
    assert batch['input_ids'].shape == (2, 16)
    assert batch['attention_mask'][0].sum() == 3
    assert batch['labels'].tolist() == [0, 2]


def test_validation_split_guard(tmp_path):
    path = tmp_path / 'wrong.csv'
    pd.DataFrame({'row_id': ['test:0'], 'text_clean': ['a'], 'label_id': [0]}).to_csv(path, index=False)
    with pytest.raises(ValueError, match='test is not allowed'):
        load_processed(path, 'validation')


def test_early_stopping():
    stopping = EarlyStopping(patience=2)
    assert stopping.update(.4) == (True, False)
    assert stopping.update(.3) == (False, False)
    assert stopping.update(.39) == (False, True)
    assert EarlyStopping(metric='loss').update(1.0) == (True, False)


def test_cache_invalidated_by_text_and_assets(tmp_path):
    class FakeSegmenter:
        identity = {'version': '1'}
        calls = 0
        def __call__(self, text):
            self.calls += 1
            return text.replace(' ', '_')
    segmenter = FakeSegmenter()
    frame = pd.DataFrame({'row_id': ['train:0'], 'text_clean': ['học sinh']})
    assert segment_frame(frame, segmenter, tmp_path)[0] == ['học_sinh']
    segment_frame(frame, segmenter, tmp_path)
    assert segmenter.calls == 1
    frame['text_clean'] = ['giáo viên']
    segment_frame(frame, segmenter, tmp_path)
    segmenter.identity = {'version': '2'}
    segment_frame(frame, segmenter, tmp_path)
    assert segmenter.calls == 3


def test_weighted_accumulation_matches_large_batch(tokenizer):
    torch.manual_seed(7)
    first, second = tiny_model(), tiny_model()
    second.load_state_dict(first.state_dict())
    ds = ViHSDDataset(['a', 'ab', 'abc', 'b', 'bc'], [0, 1, 2, 0, 2], tokenizer)
    base = TrainConfig(precision='fp32', max_grad_norm=100, imbalance='weighted_loss')
    for model, batch, accumulation in [(first, 2, 3), (second, 5, 1)]:
        config = replace(base, batch_size=batch, gradient_accumulation_steps=accumulation)
        loader = make_loader(ds, tokenizer, config, True)
        optimizer = torch.optim.SGD(model.parameters(), lr=.001)
        scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lambda _: 1.)
        train_epoch(model, loader, optimizer, scheduler, torch.amp.GradScaler('cuda', enabled=False),
                    torch.device('cpu'), config, torch.tensor([.5, 2., 1.]))
    for a, b in zip(first.parameters(), second.parameters()):
        torch.testing.assert_close(a, b, atol=1e-6, rtol=1e-5)


def test_epoch_resume_matches_uninterrupted(tmp_path, tokenizer, monkeypatch):
    import src.train as training
    class FakeSegmenter:
        identity = {'fixture': 'only for test'}
        def __init__(self, *args): pass
        def __call__(self, text): return text
    monkeypatch.setattr(training, 'Segmenter', FakeSegmenter)
    original_tokenizer = training.AutoTokenizer.from_pretrained
    monkeypatch.setattr(training.AutoTokenizer, 'from_pretrained', lambda name, **kw:
                        tokenizer if str(name) == 'fixture' else original_tokenizer(name, **kw))
    monkeypatch.setattr(training.PhoBERTClassifier, 'from_pretrained', lambda *a, **kw: tiny_model())
    for split in ['train', 'validation']:
        pd.DataFrame({'row_id': [f'{split}:{i}' for i in range(6)],
                      'text_clean': ['a', 'ab', 'abc', 'b', 'bc', 'c'],
                      'label_id': [0, 1, 2, 0, 1, 2]}).to_csv(tmp_path / f'{split}.csv', index=False)
    config = TrainConfig(model_name='fixture', train_path=str(tmp_path / 'train.csv'),
                         validation_path=str(tmp_path / 'validation.csv'), cache_dir=str(tmp_path / 'cache'),
                         output_dir=str(tmp_path / 'full'), epochs=2, batch_size=2, eval_batch_size=3,
                         precision='fp32', device='cpu', gradient_checkpointing=False, dropout=0, patience=5)
    run(config)
    interrupted = replace(config, output_dir=str(tmp_path / 'interrupted'))
    original_epoch = training.train_epoch
    calls = 0
    def fail_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError('Simulated session disconnect')
        return original_epoch(*args, **kwargs)
    monkeypatch.setattr(training, 'train_epoch', fail_second)
    with pytest.raises(RuntimeError, match='disconnect'):
        run(interrupted)
    monkeypatch.setattr(training, 'train_epoch', original_epoch)
    run(interrupted, resume=True)
    full = torch.load(Path(config.output_dir) / 'last_checkpoint.pt', weights_only=True)
    resumed = torch.load(Path(interrupted.output_dir) / 'last_checkpoint.pt', weights_only=True)
    for key in full['model']:
        torch.testing.assert_close(full['model'][key], resumed['model'][key], rtol=0, atol=0)
    restored, _ = load_checkpoint_model(interrupted.output_dir)
    assert not restored.training
    with pytest.raises(ValueError, match='changing'):
        run(replace(interrupted, learning_rate=1e-4), resume=True)
