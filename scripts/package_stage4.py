"""Export only frozen inference artifacts; no datasets or optimizer checkpoints."""
import argparse
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.experiment import sha256, write_json
from src.serving import LABELS, read_json, verify_bundle


def package(root=ROOT, output=None):
    root = Path(root).resolve()
    output = Path(output).resolve() if output else root / 'outputs/stage4/bundle'
    lock = read_json(root / 'outputs/stage3/lock.json')
    selection = root / 'outputs/stage2/final_selection/selection.json'
    if sha256(selection) != lock['selection']:
        raise ValueError('Selection differs from Stage 3')
    selected = read_json(selection)
    if selected['selection_split'] != 'validation' or selected['selected']['run'] != lock['selected_run']:
        raise ValueError('Invalid model selection')
    run = root / 'outputs/stage2/runs' / lock['selected_run']
    for name, key in [('best_model.pt', 'checkpoint'), ('config.json', 'config')]:
        if sha256(run / name) != lock[key]:
            raise ValueError(f'Changed selected artifact: {name}')
    if (output / 'bundle.json').exists():
        info = verify_bundle(output)
        if info['checkpoint_sha256'] != lock['checkpoint']:
            raise ValueError('Existing bundle uses a different checkpoint')
        print(f'Existing bundle verified: {output}')
        return output
    if output.exists() and any(output.iterdir()):
        raise FileExistsError('Use an empty bundle directory')
    files = {f'model/{name}': run / name for name in ['best_model.pt', 'config.json']}
    for subdir in ['tokenizer', 'encoder_config']:
        for path in (run / subdir).rglob('*'):
            if path.is_file():
                files['model/' + path.relative_to(run).as_posix()] = path
    for name, digest in lock['segmenter'].items():
        source = root / 'resources/vncorenlp' / name
        if sha256(source) != digest:
            raise ValueError('Changed segmenter assets')
        files['vncorenlp/' + name] = source
    for name, source in files.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    preprocessing = read_json(root / 'outputs/stage1/audit.json')['preprocessing']
    write_json(output / 'preprocessing.json', preprocessing)
    digests = {name: sha256(output / name) for name in files}
    digests['preprocessing.json'] = sha256(output / 'preprocessing.json')
    write_json(output / 'bundle.json', {'schema_version': 1, 'run': lock['selected_run'],
               'checkpoint_sha256': lock['checkpoint'], 'labels': LABELS, 'files': digests,
               'selection_sha256': lock['selection'], 'confidence_calibrated': False})
    verify_bundle(output)
    print(f'Exported and verified {len(digests)} files: {output}')
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output')
    args = parser.parse_args()
    package(output=args.output)
