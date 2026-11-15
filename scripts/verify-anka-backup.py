#!/usr/bin/env python3
"""Read-only verification of an ANKA backup before any isolated restore.

Usage: python scripts/verify-anka-backup.py --backup-dir D:\\AnkaBackups\\anka-YYYYMMDDTHHMMSSZ
This script NEVER writes into App_Data or a live IIS deployment.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import sqlite3
import sys


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def checked_file(root, name):
    if not isinstance(name, str) or not name or "\\" in name:
        raise ValueError("Invalid manifest path")
    posix = PurePosixPath(name)
    if posix.is_absolute() or any(part in (".", "..") for part in name.split("/")):
        raise ValueError("Unsafe manifest path: " + name)
    candidate = root
    for part in posix.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            raise ValueError("Symlink in backup path: " + name)
    if not candidate.is_file():
        raise ValueError("Missing or redirected backup file: " + name)
    if not candidate.resolve().is_relative_to(root.resolve()):
        raise ValueError("Backup path escapes root: " + name)
    return candidate


def verify(root):
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Backup must be a real directory")
    manifest_path = checked_file(root, "manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    database = manifest["database"]
    if database["name"] != "anka.db":
        raise ValueError("Unexpected SQLite filename")
    db = checked_file(root, database["name"])
    if digest(db) != database["sha256"]:
        raise ValueError("SQLite SHA-256 mismatch")
    with sqlite3.connect("file:" + db.resolve().as_posix() + "?mode=ro", uri=True) as conn:
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("SQLite integrity check failed")
    seen = set()
    for entry in manifest["epubs"]:
        name = entry["path"]
        if not isinstance(name, str) or not name.startswith("epubs/") or name in seen:
            raise ValueError("Invalid or duplicate EPUB entry")
        seen.add(name)
        file = checked_file(root, name)
        if file.stat().st_size != entry["size"] or digest(file) != entry["sha256"]:
            raise ValueError("EPUB size/hash mismatch: " + name)
    epub_root = root / "epubs"
    if epub_root.is_symlink():
        raise ValueError("EPUB backup directory is redirected")
    if epub_root.exists() and not epub_root.is_dir():
        raise ValueError("EPUB backup path is not a directory")
    if epub_root.is_dir():
        for item in epub_root.rglob("*"):
            if item.is_symlink():
                raise ValueError("Symlink inside EPUB backup: " + str(item))
    actual = {p.relative_to(root).as_posix() for p in epub_root.rglob("*") if p.is_file()} if epub_root.is_dir() else set()
    if actual != seen:
        raise ValueError("EPUB inventory does not match backup files")
    return len(seen)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup-dir", required=True, type=Path)
    args = parser.parse_args()
    count = verify(args.backup_dir)
    print("Verified SQLite integrity and", count, "EPUB files. No restore was performed.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("BACKUP VERIFICATION FAILED:", exc, file=sys.stderr)
        sys.exit(1)
