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
from pathlib import Path
import sqlite3
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
        p.error("Backup directory must be separate from App_Data")
    if destination == source.parent or within(destination, source.parent):
        p.error("Backup directory must be outside the application tree")
    destination.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = destination / ("anka-" + stamp)
    target.mkdir(exist_ok=False)
    temporary = target / "anka.db.partial"
    try:
        with sqlite3.connect("file:" + database.as_posix() + "?mode=ro", uri=True, timeout=30) as src:
            with sqlite3.connect(str(temporary), timeout=30) as dst:
                src.backup(dst, pages=256, sleep=0.1)
        with sqlite3.connect("file:" + temporary.as_posix() + "?mode=ro", uri=True) as verify:
            result = verify.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise RuntimeError("SQLite backup integrity check failed: " + result)
        final = target / "anka.db"
        temporary.replace(final)
        manifest = {"created_utc": stamp, "database": {"name": final.name, "sha256": hashlib.sha256(final.read_bytes()).hexdigest()}, "epubs": []}
        epubs = source / "epubs"
        if epubs.exists():
            for path in sorted(epubs.rglob("*")):
                if path.is_symlink():
                    raise RuntimeError("Refusing symlink in EPUB tree: " + str(path))
                if not path.is_file():
                    continue
                digest = hashlib.sha256()
                with path.open("rb") as f:
                    for chunk in iter(lambda: f.read(1024 * 1024), b""):
                        digest.update(chunk)
                manifest["epubs"].append({"path": path.relative_to(source).as_posix(), "size": path.stat().st_size, "sha256": digest.hexdigest()})
        (target / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        print("Verified SQLite backup and EPUB inventory:", target)
        print("EPUBs are NOT copied. Back them up separately and verify against manifest.")
    except Exception:
        # A failed inventory must not leave a directory that resembles a usable backup.
        # Only remove files created in this newly allocated target; never touch source.
        for artifact in (target / "manifest.json", target / "anka.db", temporary):
            if artifact.exists():
                artifact.unlink()
        target.rmdir()
        raise

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("BACKUP FAILED:", exc, file=sys.stderr)
        sys.exit(1)
