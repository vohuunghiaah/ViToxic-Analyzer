"""PhoBERT encoder with a two-layer classification head."""
import torch
from torch import nn
from transformers import AutoConfig, AutoModel


class PhoBERTClassifier(nn.Module):
    def __init__(self, encoder, dropout=.1):
        super().__init__()
        self.encoder = encoder
        hidden = encoder.config.hidden_size
        self.classifier = nn.Sequential(nn.Dropout(dropout), nn.Linear(hidden, hidden),
                                        nn.Tanh(), nn.Dropout(dropout), nn.Linear(hidden, 3))

    @classmethod
    def from_pretrained(cls, name, revision='main', dropout=.1):
        encoder = AutoModel.from_pretrained(name, revision=revision, add_pooling_layer=False)
        return cls(encoder, dropout)

    @classmethod
    def from_config(cls, config, dropout=.1):
        return cls(AutoModel.from_config(config, add_pooling_layer=False), dropout)

    def freeze_encoder(self, frozen):
        for parameter in self.encoder.parameters():
            parameter.requires_grad = not frozen

    def forward(self, input_ids, attention_mask):
        encoded = self.encoder(input_ids=input_ids, attention_mask=attention_mask)
        return self.classifier(encoded.last_hidden_state[:, 0])


def load_checkpoint_model(directory, device='cpu'):
    """Offline inference restore; weights-only checkpoint (no Python objects)."""
    from pathlib import Path
    from .config import TrainConfig
    directory = Path(directory)
    config = TrainConfig.from_json(directory / 'config.json')
    encoder_config = AutoConfig.from_pretrained(directory / 'encoder_config', local_files_only=True)
    model = PhoBERTClassifier.from_config(encoder_config, config.dropout)
    checkpoint = torch.load(directory / 'best_model.pt', map_location='cpu', weights_only=True)
    model.load_state_dict(checkpoint['model'])
    return model.to(device).eval(), config
