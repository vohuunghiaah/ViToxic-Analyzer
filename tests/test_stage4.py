from concurrent.futures import ThreadPoolExecutor
import asyncio
import json
import threading

from fastapi.testclient import TestClient
import httpx
import numpy as np
import pytest
import torch

from src.api import create_app
from src.experiment import sha256, write_json
from src.preprocessing import PreprocessingConfig
from src.serving import Predictor, clean_inputs, verify_bundle


class FakePredictor:
    def metadata(self):
        return {'run': 'fixture', 'confidence_calibrated': False}

    def predict(self, texts):
        cleaned = clean_inputs(texts, PreprocessingConfig())
        return [{'label': 'CLEAN', 'label_id': 0, 'confidence': .7,
                 'probabilities': {'CLEAN': .7, 'OFFENSIVE': .2, 'HATE': .1},
                 'token_count': len(t.split()) + 2, 'truncated': False} for t in cleaned]


def test_routes_and_load_once():
    calls = []
    def factory():
        calls.append(1)
        return FakePredictor()
    with TestClient(create_app(factory)) as client:
        assert client.get('/health').status_code == 200
        assert client.get('/ready').json()['status'] == 'ready'
        assert client.get('/model').json()['confidence_calibrated'] is False
        single = client.post('/predict', json={'text': 'Xin chào 😊'}).json()
        batch = client.post('/predict/batch', json={'texts': ['Xin chào 😊']}).json()
        assert batch['predictions'] == [single]
        assert batch['count'] == 1
        assert client.get('/openapi.json').status_code == 200
        assert len(calls) == 1


@pytest.mark.parametrize('payload', [{}, {'text': ''}, {'text': ' \n'}, {'text': '\u200b\ufeff'},
                                    {'text': 123}, {'text': None}, {'text': 'a' * 5001},
                                    {'text': 'ok', 'extra': True}, {'text': '\ud800'}])
def test_invalid_single(payload):
    with TestClient(create_app(FakePredictor)) as client:
        response = client.post('/predict', content=json.dumps(payload),
                               headers={'content-type': 'application/json'})
        assert response.status_code == 422
        detail = response.json()['detail']
        if isinstance(detail, list):
            assert all('input' not in error for error in detail)


@pytest.mark.parametrize('texts', [[], ['a'] * 33, ['a' * 5000] * 5, ['ok', ' '], 'text'])
def test_invalid_batch(texts):
    with TestClient(create_app(FakePredictor)) as client:
        assert client.post('/predict/batch', json={'texts': texts}).status_code == 422


def test_body_limit_and_malformed_json():
    with TestClient(create_app(FakePredictor)) as client:
        assert client.post('/predict', content=b'x' * 131073).status_code == 413
        assert client.post('/predict', content=b'{bad', headers={'content-type': 'application/json'}).status_code == 422


def test_busy_does_not_block_health_and_releases_after_failure():
    entered, release = threading.Event(), threading.Event()
    class Blocking(FakePredictor):
        def predict(self, texts):
            entered.set()
            assert release.wait(10)
            raise RuntimeError('private details')
    with TestClient(create_app(Blocking)) as client, ThreadPoolExecutor() as pool:
        first = pool.submit(client.post, '/predict', json={'text': 'one'})
        assert entered.wait(5)
        try:
            assert client.get('/health').status_code == 200
            second = client.post('/predict', json={'text': 'two'})
            assert second.status_code == 503
            assert second.headers['retry-after'] == '1'
        finally:
            release.set()
        assert first.result().status_code == 500
        assert 'private' not in first.result().text
        assert client.get('/ready').json()['busy'] is False


def test_startup_failure_and_not_ready():
    def fail():
        raise ValueError('bad checksum')
    app = create_app(fail)
    with pytest.raises(ValueError, match='bad checksum'), TestClient(app):
        pass
    assert app.state.ready is False


def test_cancelled_client_does_not_release_running_inference():
    entered, release = threading.Event(), threading.Event()
    class Blocking(FakePredictor):
        def predict(self, texts):
            entered.set()
            assert release.wait(10)
            return super().predict(texts)
    async def scenario():
        app = create_app(Blocking)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                first = asyncio.create_task(client.post('/predict', json={'text': 'hello'}))
                try:
                    assert await asyncio.to_thread(entered.wait, 5)
                    first.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await first
                    assert (await client.post('/predict', json={'text': 'next'})).status_code == 503
                finally:
                    release.set()
                for _ in range(100):
                    if not app.state.busy:
                        break
                    await asyncio.sleep(.01)
                assert (await client.post('/predict', json={'text': 'next'})).status_code == 200
    asyncio.run(scenario())


def test_preprocessing_truncation_and_probabilities():
    predictor = Predictor.__new__(Predictor)
    predictor.preprocessing = PreprocessingConfig()
    predictor.device = 'cpu'
    predictor.config = type('Config', (), {'max_length': 128})()
    seen = []
    predictor.segmenter = lambda text: seen.append(text) or text
    class Tokenizer:
        def encode(self, text, **kwargs):
            return list(range(len(text.split()) + 2))
        def __call__(self, texts, **kwargs):
            assert kwargs['truncation'] and kwargs['max_length'] == 128
            return {'input_ids': torch.zeros((len(texts), 128), dtype=torch.long),
                    'attention_mask': torch.ones((len(texts), 128), dtype=torch.long)}
    predictor.tokenizer = Tokenizer()
    predictor.model = lambda **kwargs: torch.tensor([[1., 2., 3.]]).repeat(len(kwargs['input_ids']), 1)
    output = predictor.predict(['  cha\u0300o 😊 ', 'xin ' * 200])
    assert seen[0] == 'chào 😊'
    assert output[1]['truncated'] and output[1]['token_count'] == 202
    assert output[0]['label'] == 'HATE'
    assert np.isclose(sum(output[0]['probabilities'].values()), 1)


def test_bundle_integrity_and_path_escape(tmp_path):
    names = ['model/best_model.pt', 'model/config.json', 'model/encoder_config/config.json',
             'model/tokenizer/tokenizer_config.json', 'model/tokenizer/vocab.txt',
             'model/tokenizer/bpe.codes', 'preprocessing.json', 'vncorenlp/VnCoreNLP-1.2.jar',
             'vncorenlp/models/wordsegmenter/vi-vocab', 'vncorenlp/models/wordsegmenter/wordsegmenter.rdr']
    for name in names:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'fixture')
    files = {name: sha256(tmp_path / name) for name in names}
    info = {'schema_version': 1, 'labels': ['CLEAN', 'OFFENSIVE', 'HATE'], 'files': files,
            'checkpoint_sha256': files['model/best_model.pt']}
    write_json(tmp_path / 'bundle.json', info)
    assert verify_bundle(tmp_path) == info
    (tmp_path / names[0]).write_bytes(b'corrupt')
    with pytest.raises(ValueError, match='integrity'):
        verify_bundle(tmp_path)
    (tmp_path / names[0]).write_bytes(b'fixture')
    info['files']['../escape'] = 'invalid'
    write_json(tmp_path / 'bundle.json', info)
    with pytest.raises(ValueError, match='integrity'):
        verify_bundle(tmp_path)
