#!/usr/bin/env python3
"""Consistent, read-only ANKA SQLite backup and EPUB manifest.

Run on the IIS host with Python 3.9+:
  py -3 scripts/backup-anka.py --data-dir C:\\inetpub\\anka.iyashil.com\\App_Data --output-dir D:\\AnkaBackups
Never put backups under the IIS site or wwwroot.
"""
import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path
import sqlite3
from contextlib import closing
import sys
import tempfile
from datetime import datetime, timezone

def within(child, parent):
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-dir", required=True, type=Path)
    p.add_argument("--output-dir", required=True, type=Path)
    args = p.parse_args()
    source = args.data_dir.resolve(strict=True)
    database = source / "anka.db"
    if not database.is_file() or database.is_symlink():
        p.error("Existing regular anka.db required; never create an empty production DB")
    destination = args.output_dir.resolve()
    if within(destination, source) or within(source, destination):
        p.error("Backup directory must be outside the application tree and separate from App_Data")
    if destination == source.parent or within(destination, source.parent):
        p.error("Backup directory must be outside the application tree")
    destination.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = destination / ("anka-" + stamp)
    target.mkdir(exist_ok=False)
    temporary = target / "anka.db.partial"
    try:
        with closing(sqlite3.connect("file:" + database.as_posix() + "?mode=ro", uri=True, timeout=30)) as src:
            with closing(sqlite3.connect(str(temporary), timeout=30)) as dst:
                src.backup(dst, pages=256, sleep=0.1)
        with closing(sqlite3.connect("file:" + temporary.as_posix() + "?mode=ro&immutable=1", uri=True)) as verify:
            result = verify.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise RuntimeError("SQLite backup integrity check failed: " + result)
        final = target / "anka.db"
        temporary.replace(final)
        manifest = {"created_utc": stamp, "database": {"name": final.name, "sha256": hashlib.sha256(final.read_bytes()).hexdigest()}, "epubs": []}
        epubs = source / "epubs"
        # Reject a redirected EPUB root, not just symlinks found below it.
        # Otherwise a symlinked root can silently produce an incomplete inventory.
        if epubs.is_symlink():
            raise RuntimeError("Refusing symlinked EPUB root: " + str(epubs))
        if epubs.exists() and not epubs.is_dir():
            raise RuntimeError("EPUB root must be a directory: " + str(epubs))
        if epubs.is_dir():
            for path in sorted(epubs.rglob("*")):
                if path.is_symlink():
                    raise RuntimeError("Refusing symlink in EPUB tree: " + str(path))
                if not path.is_file():
                    continue
                digest = hashlib.sha256()
                with path.open("rb") as f:
                    for chunk in iter(lambda: f.read(1024 * 1024), b""):
                        digest.update(chunk)
                relative = path.relative_to(source)
                copied = target / relative
                copied.parent.mkdir(parents=True, exist_ok=True)
                # Copy into the new backup tree; never modify the source EPUB.
                with path.open("rb") as src, copied.open("xb") as dst:
                    shutil.copyfileobj(src, dst, length=1024 * 1024)
                copied_digest = hashlib.sha256()
                with copied.open("rb") as check:
                    for chunk in iter(lambda: check.read(1024 * 1024), b""):
                        copied_digest.update(chunk)
                if copied_digest.hexdigest() != digest.hexdigest():
                    raise RuntimeError("EPUB changed during backup: " + str(path))
                manifest["epubs"].append({"path": relative.as_posix(), "size": copied.stat().st_size, "sha256": copied_digest.hexdigest()})
        (target / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        print("Verified SQLite backup and EPUB copies:", target)
        print("Verify restoration in an isolated environment before relying on this backup.")
    except Exception:
        # A failed inventory must not leave a directory that resembles a usable backup.
        # Only remove files created in this newly allocated target; never touch source.
        shutil.rmtree(target)
        raise

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("BACKUP FAILED:", exc, file=sys.stderr)
        sys.exit(1)
