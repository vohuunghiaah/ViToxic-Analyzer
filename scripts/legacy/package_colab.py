"""Package only Stage 2 source, tests, configs and train/validation (never test)."""
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
destination = ROOT / 'dist/vitoxic_stage2_colab.zip'
destination.parent.mkdir(exist_ok=True)
paths = []
for pattern in ['src/*.py', 'tests/test_stage2.py', 'configs/*.json', 'notebooks/02_training.ipynb',
                'reports/stage2/baseline/*.json', 'reports/stage2/baseline/*.csv']:
    paths.extend(ROOT.glob(pattern))
paths += [ROOT / name for name in ['requirements-stage2.txt', 'README.md', 'docs/STAGE2_COLAB.md',
           'data/processed/train_decontaminated.csv', 'data/processed/validation.csv']]
with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
    for path in paths:
        archive.write(path, 'ViToxic-Analyzer/' + path.relative_to(ROOT).as_posix())
print(f'{destination.name}: {destination.stat().st_size / 1024**2:.2f} MB; no test data')
