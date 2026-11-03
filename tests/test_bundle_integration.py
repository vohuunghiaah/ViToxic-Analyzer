"""Opt-in real checkpoint test; no training, downloads or research output writes."""
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api import create_app
from src.serving import Predictor


@pytest.mark.integration
def test_real_bundle_http():
    bundle = os.environ.get('VITOXIC_TEST_BUNDLE')
    if not bundle:
        pytest.skip('Set VITOXIC_TEST_BUNDLE to a verified local deployment bundle')
    assert (Path(bundle) / 'bundle.json').is_file()
    with TestClient(create_app(lambda: Predictor(bundle))) as client:
        assert client.get('/ready').json()['status'] == 'ready'
        for path in ['/', '/workspace', '/static/storage.js', '/static/workspace.js']:
            assert client.get(path).status_code == 200
        single = client.post('/predict', json={'text': 'Xin chào bạn!'})
        batch = client.post('/predict/batch', json={'texts': ['Xin chào bạn!']})
        assert single.status_code == batch.status_code == 200
        assert batch.json()['predictions'] == [single.json()]
        assert abs(sum(single.json()['probabilities'].values()) - 1) < 1e-5
