#!/usr/bin/env python3
"""Stage explicitly pinned upstream packages in the offline installation mirror."""

import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def verify(path, package):
    if digest(path) != package["sha256"]:
        raise ValueError(f"SHA-256 mismatch for pinned package: {package['filename']}")
    # Read metadata only after authenticating the exact locked archive bytes.
    raw = subprocess.check_output(
        ["tar", "--zstd", "-xOf", str(path), ".PKGINFO"], text=True
    )
    metadata = {}
    for line in raw.splitlines():
        if line and not line.startswith("#"):
            key, separator, value = line.partition(" = ")
            if separator:
                metadata.setdefault(key, []).append(value)
    for key, expected in (("pkgname", package["name"]), ("pkgver", package["version"]), ("arch", package["arch"])):
        if metadata.get(key) != [expected]:
            raise ValueError(f"Unexpected {key} in pinned package: {package['filename']}")
    return metadata.get("depend", [])


def main():
    lock_path, mirror_path, record_path = map(Path, sys.argv[1:])
    lock = json.loads(lock_path.read_text())
    if lock.get("schema") != 1 or not isinstance(lock.get("packages"), list):
        raise ValueError("Unsupported pinned package lock")
    mirror_path.mkdir(parents=True, exist_ok=True)
    records, names = [], set()
    for package in lock["packages"]:
        name, filename = package["name"], package["filename"]
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9@._+-]*", name) or name in names:
            raise ValueError(f"Invalid or duplicate pinned package: {name}")
        if Path(filename).name != filename or not filename.endswith(".pkg.tar.zst"):
            raise ValueError(f"Invalid pinned package filename: {filename}")
        if not re.fullmatch(r"[0-9a-f]{64}", package["sha256"]) or not package["url"].startswith("https://"):
            raise ValueError(f"Pinned package requires HTTPS and a SHA-256: {name}")
        names.add(name)
        destination = mirror_path / filename
        if not destination.exists():
            with tempfile.TemporaryDirectory(prefix=".pinned-", dir=mirror_path) as temporary:
                downloaded = Path(temporary) / filename
                with urllib.request.urlopen(package["url"], timeout=30) as response, downloaded.open("wb") as output:
                    shutil.copyfileobj(response, output)
                dependencies = verify(downloaded, package)
                downloaded.replace(destination)
        else:
            dependencies = verify(destination, package)
        records.append({**package, "size_bytes": destination.stat().st_size, "runtime_dependencies": dependencies})
        print(f"Pinned offline package verified: {name} {package['version']} sha256={package['sha256']}", flush=True)
    record_path.write_text(json.dumps({"schema": 1, "packages": records}, indent=2) + "\n")


if __name__ == "__main__":
    main()
