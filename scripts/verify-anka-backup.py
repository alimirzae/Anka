#!/usr/bin/env python3
"""Read-only verification of an ANKA backup before any isolated restore.

Usage: python scripts/verify-anka-backup.py --backup-dir D:\\AnkaBackups\\anka-YYYYMMDDTHHMMSSZ
This script NEVER writes into App_Data or a live IIS deployment.
"""
import argparse
from contextlib import closing
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


def valid_sha256(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


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
    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate manifest JSON key: " + key)
            result[key] = value
        return result

    def reject_nonfinite(value):
        raise ValueError("Non-standard JSON numeric value: " + value)

    # Bound untrusted manifest input before parsing to avoid memory exhaustion.
    # 16 MiB accommodates large EPUB inventories without allowing arbitrary JSON.
    if manifest_path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("Backup manifest exceeds 16 MiB limit")
    manifest = json.loads(
        manifest_path.read_text(encoding="utf-8"),
        object_pairs_hook=unique_keys,
        parse_constant=reject_nonfinite,
    )
    if not isinstance(manifest, dict) or not isinstance(manifest.get("database"), dict) or not isinstance(manifest.get("epubs"), list):
        raise ValueError("Invalid backup manifest structure")
    database = manifest["database"]
    if not valid_sha256(database.get("sha256")):
        raise ValueError("Invalid SQLite SHA-256 field")
    if database["name"] != "anka.db":
        raise ValueError("Unexpected SQLite filename")
    # A restored SQLite snapshot must be self-contained. Untracked WAL/journal
    # sidecars could change the restored state despite a valid main-file hash.
    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = root / (database["name"] + suffix)
        if sidecar.exists() or sidecar.is_symlink():
            raise ValueError("Unexpected SQLite sidecar in backup: " + sidecar.name)
    db = checked_file(root, database["name"])
    if digest(db) != database["sha256"]:
        raise ValueError("SQLite SHA-256 mismatch")
    # Immutable read-only mode prevents SQLite from creating journal/SHM files
    # or consulting an external WAL while inspecting this self-contained snapshot.
    # sqlite3.Connection.__exit__ commits/rolls back but does not close the handle.
    # Explicit closure is essential for restoring/removing fixtures on Windows.
    # Path.as_uri() percent-encodes spaces, # and ? in Windows/POSIX paths.
    # Concatenating a raw filesystem path into a SQLite URI can inspect the
    # wrong file (or fail) when a backup directory contains URI delimiters.
    db_uri = db.resolve().as_uri() + "?mode=ro&immutable=1"
    with closing(sqlite3.connect(db_uri, uri=True)) as conn:
        results = [row[0] for row in conn.execute("PRAGMA integrity_check")]
        if results != ["ok"]:
            raise ValueError("SQLite integrity check failed: " + str(results[:3]))
    seen = set()
    for entry in manifest["epubs"]:
        if not isinstance(entry, dict) or not valid_sha256(entry.get("sha256")) or type(entry.get("size")) is not int or entry["size"] < 0:
            raise ValueError("Invalid EPUB manifest metadata")
        name = entry.get("path")
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
