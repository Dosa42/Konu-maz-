#!/usr/bin/env python3
"""Prepare pinned, editable source trees without resetting existing work."""

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parent.parent
SOURCE_NAMES = ("omarchy", "omarchy-iso", "omarchy-pkgs")


class PreparationError(RuntimeError):
    pass


def run(args, cwd=None, check=True, env=None):
    result = subprocess.run(
        [str(arg) for arg in args], cwd=cwd,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0", **(env or {})},
    )
    if check and result.returncode:
        details = result.stderr.decode("utf-8", "replace").strip()
        if not details:
            details = result.stdout.decode("utf-8", "replace").strip()
        raise PreparationError(
            f"Command failed ({result.returncode}): {' '.join(map(str, args))}\n{details}"
        )
    return result


def git(repository, *args, check=True, env=None):
    return run(["git", "-C", repository, *args], check=check, env=env)


def git_text(repository, *args):
    return git(repository, *args).stdout.decode("utf-8", "surrogateescape").strip()


def read_json(path):
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def safe_child(base, relative):
    """Reject traversal and symlink components, including an existing target."""
    value = PurePosixPath(relative)
    if not relative or value.is_absolute() or ".." in value.parts or ".git" in value.parts:
        raise PreparationError(f"Unsafe relative path: {relative!r}")
    if "\\" in relative:
        raise PreparationError(f"Use POSIX paths: {relative!r}")
    current = base
    if current.is_symlink():
        raise PreparationError(f"Symlink directory is not allowed: {current}")
    for part in value.parts:
        current = current / part
        if current.is_symlink():
            raise PreparationError(f"Symlink is not allowed: {current}")
    if not current.resolve().is_relative_to(base.resolve()):
        raise PreparationError(f"Path escapes its directory: {relative!r}")
    return current


def validate_source(name, spec):
    if not isinstance(spec, dict):
        raise PreparationError(f"Missing source specification: {name}")
    url = spec.get("url")
    commit = spec.get("commit")
    if not isinstance(url, str) or not url or url.startswith("-") or "\n" in url:
        raise PreparationError(f"Invalid source URL for {name}")
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise PreparationError(f"{name} must pin a complete 40-character commit SHA")


def prepare_repository(name, spec):
    repository = safe_child(ROOT / "sources", name)
    repository.parent.mkdir(parents=True, exist_ok=True)
    fresh = not repository.exists() or not any(repository.iterdir())
    if fresh:
        print(f"Cloning {name} from {spec['url']}", flush=True)
        run(["git", "clone", "--filter=blob:none", "--no-checkout", "--no-hardlinks", "--", spec["url"], repository])
    elif not (repository / ".git").is_dir() or (repository / ".git").is_symlink():
        raise PreparationError(
            f"{repository} must contain a standalone .git directory. "
            "An existing worktree/submodule .git file or nonempty unmanaged directory "
            "will not be replaced; preserve it and use an empty source directory."
        )

    actual_url = git_text(repository, "remote", "get-url", "origin")
    if actual_url != spec["url"]:
        raise PreparationError(f"{name}: origin differs from the lock: {actual_url}")
    commit = spec["commit"]
    if git(repository, "cat-file", "-e", f"{commit}^{{commit}}", check=False).returncode:
        git(repository, "fetch", "--no-tags", "origin", commit)

    if not fresh:
        actual_head = git_text(repository, "rev-parse", "HEAD")
        if actual_head != commit:
            raise PreparationError(
                f"{name}: HEAD is {actual_head}, expected {commit}. "
                "Existing source work is preserved; no reset or checkout was performed."
            )
    # Checking out the same commit only detaches HEAD; it preserves local changes.
    git(repository, "checkout", "--detach", commit)
    if git_text(repository, "rev-parse", "HEAD") != commit:
        raise PreparationError(f"{name}: checkout did not produce the pinned HEAD")
    print(f"Prepared {name} at {commit}", flush=True)
    return repository


def prepare_archiso(iso, spec):
    path = safe_child(iso, "archiso")
    expected = spec["commit"]
    recorded = git_text(iso, "rev-parse", "HEAD:archiso")
    if recorded != expected:
        raise PreparationError(
            f"archiso lock {expected} differs from the ISO commit's gitlink {recorded}"
        )
    if (path / ".git").exists():
        actual = git_text(path, "rev-parse", "HEAD")
        if actual != expected:
            raise PreparationError(
                f"archiso HEAD is {actual}, expected {expected}; existing work is preserved"
            )
        git(path, "config", "remote.origin.url", spec["url"])
    elif path.exists() and any(path.iterdir()):
        raise PreparationError(f"Unmanaged, nonempty archiso directory: {path}")

    # Do not run submodule sync: it would restore the URL from .gitmodules.
    git(iso, "config", "submodule.archiso.url", spec["url"])
    git(iso, "submodule", "update", "--init", "--checkout", "--", "archiso")
    if git_text(path, "rev-parse", "HEAD") != expected:
        raise PreparationError("archiso submodule does not match its locked commit")
    print(f"Prepared archiso at {expected}", flush=True)
    return path


def patch_series_is_applied(repository, patches):
    """Reverse the whole series in an isolated index, leaving source work intact.

    A later patch may change the context or result of an earlier one. Checking
    each earlier patch in isolation therefore cannot recognize the completed
    series. Reverse-order application reconstructs its intermediate states.
    """
    if not patches:
        return True
    with tempfile.TemporaryDirectory(prefix="omarchy-patch-index-") as temporary:
        env = {"GIT_INDEX_FILE": str(Path(temporary) / "index")}
        git(repository, "read-tree", "HEAD", env=env)
        # Include new patch/overlay files as well as tracked modifications and
        # deletions. This writes only the disposable index, never the real index.
        git(repository, "add", "--all", "--", ".", env=env)
        for patch in reversed(patches):
            result = git(
                repository, "apply", "--cached", "--reverse", "--", patch,
                env=env, check=False,
            )
            if result.returncode:
                return False
    return True


def apply_patches(name, repository, series):
    applied = []
    base = safe_child(ROOT / "patches", name)
    patches = []
    for relative in series:
        if not isinstance(relative, str):
            raise PreparationError(f"{name}: patch filenames must be strings")
        patch = safe_child(base, relative)
        if not patch.is_file():
            raise PreparationError(f"Missing patch file: {patch}")
        patches.append(patch)
    # Recognize a prepared prefix too: a later patch within that prefix may
    # already have changed an earlier patch's result/context.
    applied_prefix = next(
        (count for count in range(len(patches), 0, -1)
         if patch_series_is_applied(repository, patches[:count])),
        0,
    )
    for index, (relative, patch) in enumerate(zip(series, patches)):
        if index < applied_prefix:
            print(f"{name}: {relative}: already-applied", flush=True)
            applied.append({"path": f"patches/{name}/{relative}", "sha256": digest(patch), "state": "already-applied"})
            continue
        forward = git(repository, "apply", "--check", "--", patch, check=False)
        if forward.returncode == 0:
            git(repository, "apply", "--", patch)
            state = "applied"
        else:
            reverse = git(repository, "apply", "--reverse", "--check", "--", patch, check=False)
            if reverse.returncode:
                raise PreparationError(
                    f"{name}: patch cannot apply and is not already applied: {relative}\n"
                    + forward.stderr.decode("utf-8", "replace")
                    + reverse.stderr.decode("utf-8", "replace")
                )
            state = "already-applied"
        print(f"{name}: {relative}: {state}", flush=True)
        applied.append({"path": f"patches/{name}/{relative}", "sha256": digest(patch), "state": state})
    return applied


def apply_overlay(name, repository):
    base = safe_child(ROOT / "overlays", name)
    entries = []
    if not base.exists():
        return entries
    if not base.is_dir():
        raise PreparationError(f"Overlay must be a directory: {base}")
    for directory, directories, files in os.walk(base, followlinks=False):
        directories.sort()
        for child in directories:
            safe_child(base, (Path(directory) / child).relative_to(base).as_posix())
        for filename in sorted(files):
            relative = (Path(directory) / filename).relative_to(base).as_posix()
            source = safe_child(base, relative)
            destination = safe_child(repository, relative)
            if not source.is_file():
                raise PreparationError(f"Overlay entry must be a regular file: {source}")
            if destination.exists() and not destination.is_file():
                raise PreparationError(f"Overlay file conflicts with a directory: {destination}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            entries.append({
                "path": relative, "sha256": digest(source),
                "mode": oct(source.stat().st_mode & 0o777),
            })
    print(f"{name}: copied {len(entries)} overlay files", flush=True)
    return entries


def source_state(name, repository, spec, output):
    diff = git(repository, "diff", "--binary", "HEAD", "--").stdout
    relative = f"source-diffs/{name}.patch"
    diff_path = safe_child(output, relative)
    diff_path.parent.mkdir(parents=True, exist_ok=True)
    diff_path.write_bytes(diff)
    return {
        "url": spec["url"], "locked_commit": spec["commit"],
        "head": git_text(repository, "rev-parse", "HEAD"),
        "status": git_text(repository, "status", "--short", "--untracked-files=all"),
        "tracked_diff": relative, "tracked_diff_sha256": hashlib.sha256(diff).hexdigest(),
    }


def main():
    if len(sys.argv) != 1:
        raise PreparationError("Usage: scripts/prepare-sources.py (configuration comes from config/sources.lock.json)")
    lock = read_json(ROOT / "config/sources.lock.json")
    series = read_json(ROOT / "patches/series.json")
    if lock.get("schema") != 1 or not isinstance(lock.get("sources"), dict):
        raise PreparationError("Unsupported sources.lock.json schema")
    if set(lock["sources"]) != set(SOURCE_NAMES):
        raise PreparationError("Lock must specify exactly omarchy, omarchy-iso and omarchy-pkgs")
    if not isinstance(series, dict) or set(series) != set(SOURCE_NAMES):
        raise PreparationError("patches/series.json must list all three source names")
    for name in SOURCE_NAMES:
        validate_source(name, lock["sources"][name])
        if (not isinstance(series[name], list)
                or not all(isinstance(item, str) for item in series[name])
                or len(set(series[name])) != len(series[name])):
            raise PreparationError(f"{name}: patch series must be a list of strings without duplicates")
    validate_source("archiso", lock.get("archiso"))
    if not isinstance(lock.get("builder_image"), str) or not re.fullmatch(r"[^\s@]+@sha256:[0-9a-f]{64}", lock["builder_image"]):
        raise PreparationError("builder_image must pin an immutable sha256 image digest")

    repositories = {name: prepare_repository(name, lock["sources"][name]) for name in SOURCE_NAMES}
    archiso = prepare_archiso(repositories["omarchy-iso"], lock["archiso"])
    patches = {}
    overlays = {}
    for name, repository in repositories.items():
        patches[name] = apply_patches(name, repository, series[name])
        overlays[name] = apply_overlay(name, repository)

    output = safe_child(ROOT, "out")
    output.mkdir(parents=True, exist_ok=True)
    state = {
        "schema": 1,
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "builder_image": lock["builder_image"],
        "sources_lock_sha256": digest(ROOT / "config/sources.lock.json"),
        "sources": {},
        "archiso": source_state("archiso", archiso, lock["archiso"], output),
        "untracked_note": "Git status records untracked paths; tracked diffs do not contain their contents. Archive the prepared sources with the build.",
    }
    for name, repository in repositories.items():
        item = source_state(name, repository, lock["sources"][name], output)
        item["patches"] = patches[name]
        item["overlays"] = overlays[name]
        state["sources"][name] = item
    safe_child(output, "source-state.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    print("Source state written to out/source-state.json", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (PreparationError, OSError, ValueError, TypeError) as error:
        print(f"prepare-sources: {error}", file=sys.stderr)
        sys.exit(1)
