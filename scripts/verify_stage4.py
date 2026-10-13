"""Real HTTP smoke test and small CPU benchmark; never train or re-evaluate test."""
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
import socket
import subprocess
import sys
import time
import unicodedata

import httpx
import numpy as np
import pandas as pd
import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.experiment import sha256, write_json


def process_tree_rss_mb(process):
    processes = [process, *process.children(recursive=True)]
    return sum(p.memory_info().rss for p in processes if p.is_running()) / 1024**2


def stop_process_tree(process):
    # Windows venv python.exe can be a launcher with the real interpreter below it.
    try:
        parent = psutil.Process(process.pid)
        targets = [*reversed(parent.children(recursive=True)), parent]
    except psutil.NoSuchProcess:
        return
    for target in targets:
        try:
            target.terminate()
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs(targets, timeout=10)
    for target in alive:
        target.kill()
    psutil.wait_procs(alive, timeout=5)
    process.wait(timeout=5)


def main():
    output = ROOT / 'outputs/stage4'
    output.mkdir(parents=True, exist_ok=True)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    start = time.perf_counter()
    with (output / 'verification_server.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'src.api:app', '--host', '127.0.0.1',
                                    '--port', str(port), '--workers', '1', '--no-access-log'],
                                   cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        try:
            with httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=120, trust_env=False) as client:
                while True:
                    if process.poll() is not None:
                        raise RuntimeError('Server exited; see verification_server.log')
                    try:
                        if client.get('/ready').status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    if time.perf_counter() - start > 180:
                        raise TimeoutError('Server startup exceeded 180 seconds')
                    time.sleep(.5)
                startup = time.perf_counter() - start
                print(f'API ready after {startup:.1f}s', flush=True)
                metadata = client.get('/model').json()
                assert metadata['confidence_calibrated'] is False
                assert client.get('/health').status_code == 200
                assert client.get('/docs').status_code == 200
                assert '/predict/batch' in client.get('/openapi.json').json()['paths']
                run = ROOT / 'outputs/stage2/runs' / metadata['run']
                validation = pd.read_csv(ROOT / 'data/processed/validation.csv', keep_default_na=False)
                saved = pd.read_csv(run / 'validation_predictions.csv')
                sample = validation.groupby('label_id', sort=True).head(4)
                expected = saved.set_index('row_id').loc[sample.row_id, 'prediction'].tolist()
                response = client.post('/predict/batch', json={'texts': sample.free_text.tolist()})
                response.raise_for_status()
                actual = [row['label_id'] for row in response.json()['predictions']]
                assert actual == expected, 'API predictions differ from saved validation predictions'
                print('PASS: 12/12 validation predictions match through real HTTP + segmentation', flush=True)
                sentence = 'Chúc bạn một ngày vui vẻ 😊!'
                def predict(text):
                    result = client.post('/predict', json={'text': text})
                    result.raise_for_status()
                    return result.json()
                normal = predict(sentence)
                decomposed = predict(unicodedata.normalize('NFD', sentence))
                assert normal == decomposed
                batch = client.post('/predict/batch', json={'texts': [sentence]}).json()['predictions'][0]
                assert normal == batch
                long = predict('xin chào ' * 400)
                assert long['truncated'] and long['token_count'] > metadata['max_length']
                for text in ['', ' \n', '\u200b\ufeff', 'a' * 5001, 12, None]:
                    assert client.post('/predict', json={'text': text}).status_code == 422
                assert client.post('/predict/batch', json={'texts': []}).status_code == 422
                assert client.post('/predict/batch', json={'texts': ['a'] * 33}).status_code == 422
                assert client.post('/predict', content=b'a' * 131073).status_code == 413
                samples, memory = [], []
                proc = psutil.Process(process.pid)
                for batch_size, repetitions in [(1, 20), (8, 5)]:
                    durations = []
                    for _ in range(repetitions):
                        before = time.perf_counter()
                        result = client.post('/predict/batch', json={'texts': [sentence] * batch_size})
                        result.raise_for_status()
                        durations.append(time.perf_counter() - before)
                        memory.append(process_tree_rss_mb(proc))
                    samples.append({'batch_size': batch_size, 'requests': repetitions,
                                    'latency_p50_ms': float(np.quantile(durations, .5) * 1000),
                                    'latency_p95_ms': float(np.quantile(durations, .95) * 1000),
                                    'texts_per_second': float(batch_size / np.mean(durations))})
                report = {'passed': True, 'checked_at': datetime.now(timezone.utc).isoformat(),
                          'metadata': metadata, 'startup_seconds_including_warmup': startup,
                          'validation_rows': len(sample), 'validation_prediction_mismatches': 0,
                          'checks': ['real HTTP', 'health/readiness/OpenAPI', 'raw preprocessing + segmentation',
                                     'Unicode NFC/NFD equivalence', 'single/batch equivalence', 'long text truncation',
                                     'invalid input 422', 'oversized body 413'],
                          'benchmark': samples, 'max_observed_rss_mb': max(memory),
                          'benchmark_scope': 'Warm local HTTP, repeated short synthetic sentence; no concurrent load. Sum of process-tree RSS sampled after requests, not peak allocation; shared pages may be counted more than once.',
                          'source_sha256': {f: sha256(ROOT / f) for f in ['src/api.py', 'src/serving.py', 'scripts/verify_stage4.py']},
                          'packages': {p: version(p) for p in ['fastapi', 'uvicorn', 'pydantic', 'torch', 'transformers', 'py-vncorenlp']},
                          'docker_verified': False, 'public_deployment': False}
                write_json(output / 'verification.json', report)
                print(__import__('json').dumps(report, ensure_ascii=False, indent=2), flush=True)
        finally:
            stop_process_tree(process)


if __name__ == '__main__':
    main()
