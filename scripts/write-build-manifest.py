#!/usr/bin/env python3
"""Record the actual image, source and dependency identities after a real build."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def main():
    iso = Path(sys.argv[1]).resolve(strict=True)
    source_state = json.loads((ROOT / 'out/source-state.json').read_text())
    lock = json.loads((ROOT / 'config/sources.lock.json').read_text())
    repository_commit = subprocess.check_output(
        ['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True
    ).strip()
    manifest = {
        'schema': 1,
        'built_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'repository': os.environ.get('GITHUB_REPOSITORY', 'local-checkout'),
        'repository_commit': repository_commit,
        'run_id': os.environ.get('GITHUB_RUN_ID'),
        'run_attempt': os.environ.get('GITHUB_RUN_ATTEMPT'),
        'profile': 'custom-no-login',
        'authentication': json.loads((ROOT / 'sources/omarchy-iso/configs/airootfs/usr/share/omarchy-iso/custom-build-status.json').read_text()),
        'source_date_epoch': int(os.environ['SOURCE_DATE_EPOCH']),
        'locked_inputs': lock,
        'effective_sources': source_state,
        'iso': {'filename': iso.name, 'size_bytes': iso.stat().st_size, 'sha256': digest(iso)},
        'dependency_records': {},
        'verification': {'iso_created': True, 'el_torito_catalog_read': True, 'vm_boot_tested': False, 'usb_signer_tested': False},
        'reproducibility': 'Source/image/Node pins recorded; Arch/Omarchy mirrors and LazyVim plugin resolution remain network-resolved.',
    }
    for name in ('builder-image.json', 'offline-packages.txt', 'pinned-offline-packages.json', 'build-environment-packages.txt', 'node-dist.sha256', 'boot-catalog.txt', 'removed-login.json'):
        path = iso.parent / name
        if not path.is_file():
            raise FileNotFoundError(f'Missing build evidence: {path}')
        manifest['dependency_records'][name] = {'sha256': digest(path), 'size_bytes': path.stat().st_size}
    (iso.parent / 'build-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    main()

