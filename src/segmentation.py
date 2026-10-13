"""RDRSegmenter cache keyed by full input text, row IDs and model hashes."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import re
import urllib.request
from .experiment import sha256, write_json

ASSETS = ['VnCoreNLP-1.2.jar', 'models/wordsegmenter/vi-vocab', 'models/wordsegmenter/wordsegmenter.rdr']
ASSET_REVISION = '62bbc58fe5d113c898eae112656be97dcf50b3a0'


def prepare_segmenter(directory, download=False):
    directory = Path(directory).resolve()
    if not shutil.which('java'):
        raise RuntimeError('Java 8+ required; on Colab install default-jre-headless')
    if download:
        directory.mkdir(parents=True, exist_ok=True)
        for name in ASSETS:
            target = directory / name
            if target.is_file() and target.stat().st_size > 0:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            temp = target.with_suffix(target.suffix + '.download')
            url = f'https://raw.githubusercontent.com/vncorenlp/VnCoreNLP/{ASSET_REVISION}/{name}'
            with urllib.request.urlopen(url, timeout=120) as response, temp.open('wb') as stream:
                shutil.copyfileobj(response, stream)
            os.replace(temp, target)
    missing = [name for name in ASSETS if not (directory / name).is_file()]
    if missing:
        raise FileNotFoundError(f'Missing VnCoreNLP assets {missing}; run python -m src.segmentation --download')
    return directory


class Segmenter:
    def __init__(self, directory):
        directory = prepare_segmenter(directory)
        if not os.environ.get('JAVA_HOME'):
            settings = subprocess.run(['java', '-XshowSettings:properties', '-version'],
                                      capture_output=True, text=True, check=True)
            match = re.search(r'^\s*java.home\s*=\s*(.+)$', settings.stderr, re.MULTILINE)
            if match:
                os.environ['JAVA_HOME'] = match.group(1).strip()
        import py_vncorenlp
        self.identity = {name: sha256(directory / name) for name in ASSETS}
        previous = Path.cwd()
        try:
            self.engine = py_vncorenlp.VnCoreNLP(annotators=['wseg'], save_dir=str(directory))
        finally:
            # Wrapper changes cwd; never let it affect project-relative paths.
            os.chdir(previous)

    def __call__(self, text):
        return ' '.join(self.engine.word_segment(text)) if text.strip() else ''


def segment_frame(frame, segmenter, cache_dir):
    from tqdm.auto import tqdm
    payload = {'version': 1, 'segmenter': segmenter.identity,
               'rows': list(zip(frame.row_id.tolist(), frame.text_clean.tolist()))}
    key = hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode('utf-8')).hexdigest()
    path = Path(cache_dir) / (key + '.json')
    if path.exists():
        texts = json.loads(path.read_text(encoding='utf-8'))
        if len(texts) != len(frame) or not all(isinstance(text, str) for text in texts):
            raise ValueError('Invalid segmentation cache')
        return texts, key
    texts = [segmenter(text) for text in tqdm(frame.text_clean, desc='RDRSegmenter')]
    write_json(path, texts)
    return texts, key


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', default='resources/vncorenlp')
    parser.add_argument('--download', action='store_true')
    args = parser.parse_args()
    print(prepare_segmenter(args.directory, args.download))
