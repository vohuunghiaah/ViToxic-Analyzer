"""Build a standalone, checksummed deployment ZIP using an explicit file allowlist."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.experiment import sha256, write_json
from src.serving import verify_bundle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--name', default='ViToxic-Analyzer-deploy-2026-10-16')
    args = parser.parse_args()
    if not args.name or Path(args.name).name != args.name or args.name in {'.', '..'}:
        raise ValueError('Use a plain directory name')
    source_bundle = ROOT / 'outputs/stage4/bundle'
    info = verify_bundle(source_bundle)
    destination = ROOT / 'dist' / args.name
    archive = destination.with_suffix('.zip')
    if destination.exists() or archive.exists():
        raise FileExistsError('Release already exists; choose a new --name')
    names = ['Dockerfile', 'compose.yaml', '.dockerignore', 'requirements/stage4.txt',
             'requirements/locks/windows-stage4-cpu.txt', 'docs/STAGE4_API.md', 'docs/DEPLOY_HANDOFF.md',
             'scripts/verify_handoff.py', 'scripts/smoke_deploy.py', 'tests/test_stage4.py',
             'AGENTS.md', 'AI_TRACKER.md', 'outputs/stage4/verification.json',
             'outputs/stage4/summary.md', 'outputs/stage4/openapi.json']
    names += [p.relative_to(ROOT).as_posix() for p in sorted((ROOT / 'src').glob('*.py'))]
    names += [p.relative_to(ROOT).as_posix() for p in sorted(source_bundle.rglob('*')) if p.is_file()]
    for name in names:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    shutil.copy2(ROOT / 'docs/DEPLOY_HANDOFF.md', destination / 'README.md')
    names.append('README.md')
    manifest = {'run': info['run'], 'checkpoint_sha256': info['checkpoint_sha256'],
                'docker_verified': False, 'files': {name: sha256(destination / name) for name in names}}
    write_json(destination / 'HANDOFF_MANIFEST.json', manifest)
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as output:
        for path in sorted(destination.rglob('*')):
            if path.is_file():
                output.write(path, args.name + '/' + path.relative_to(destination).as_posix())
    digest = sha256(archive)
    archive.with_suffix('.zip.sha256').write_text(f'{digest}  {archive.name}\n', encoding='ascii')
    print(json.dumps({'zip': str(archive), 'bytes': archive.stat().st_size, 'sha256': digest,
                      'files': len(names) + 1}, indent=2), flush=True)


if __name__ == '__main__':
    main()
