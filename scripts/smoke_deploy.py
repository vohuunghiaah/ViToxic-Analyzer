"""Smoke-test a running deployment. No training data or third-party packages needed."""
import argparse
import json
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8000')
    args = parser.parse_args()
    base = args.url.rstrip('/')
    def call(path, payload=None):
        data = None if payload is None else json.dumps(payload).encode('utf-8')
        request = Request(base + path, data=data, headers={'Content-Type': 'application/json'})
        with urlopen(request, timeout=120) as response:
            return json.load(response)
    assert call('/ready')['status'] == 'ready'
    metadata = call('/model')
    assert metadata['confidence_calibrated'] is False
    prediction = call('/predict', {'text': 'Xin chào, chúc bạn một ngày vui vẻ!'})
    assert prediction['label'] in metadata['labels']
    assert abs(sum(prediction['probabilities'].values()) - 1) < 1e-5
    batch = call('/predict/batch', {'texts': ['Xin chào!', 'Cảm ơn bạn.']})
    assert batch['count'] == len(batch['predictions']) == 2
    print(json.dumps({'status': 'PASS', 'run': metadata['run'], 'prediction': prediction}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
