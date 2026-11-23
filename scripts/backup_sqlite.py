#!/usr/bin/env python3
"""Create a consistent, verified online SQLite backup without touching source or EPUB files.

Usage: python scripts/backup_sqlite.py --source App_Data/anka.db --destination D:/AnkaBackups/anka-2026-11-23.db
Run on the IIS host with read access to the source and write access to a separate backup directory.
This tool does NOT back up EPUBs or DataProtection keys; back those up separately.
"""
import argparse
from contextlib import closing
import os
import sqlite3
import sys
import tempfile
from pathlib import Path


def backup(source: Path, destination: Path) -> None:
    source = source.resolve(strict=True)
    destination = destination.resolve(strict=False)
    if not source.is_file() or source.stat().st_size == 0:
        raise ValueError("Source must be a non-empty SQLite database file")
    if source == destination:
        raise ValueError("Source and destination must differ")
    if destination.exists():
        raise FileExistsError("Refusing to overwrite an existing backup")
    if not destination.parent.is_dir():
        raise FileNotFoundError("Destination directory must already exist")
    # Prevent accidental backup into the application data directory.
    if destination.is_relative_to(source.parent):
        raise ValueError("Backups must be stored outside the live database directory")
    fd, temp_name = tempfile.mkstemp(prefix=".anka-backup-", suffix=".sqlite", dir=destination.parent)
    os.close(fd)
    temporary = Path(temp_name)
    try:
        # mode=ro prevents creating or mutating the source database.
        source_uri = source.as_uri() + "?mode=ro"
        with closing(sqlite3.connect(source_uri, uri=True, timeout=30)) as live:
            with closing(sqlite3.connect(temporary, timeout=30)) as snapshot:
                live.backup(snapshot, pages=256, sleep=0.1)
                if snapshot.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise RuntimeError("Backup integrity check failed")
                if snapshot.execute("PRAGMA foreign_key_check").fetchall():
                    raise RuntimeError("Backup contains foreign-key violations")
        # Publish only after verification, without replacing an existing destination.
        os.link(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()
    try:
        backup(args.source, args.destination)
    except (OSError, sqlite3.Error, RuntimeError, ValueError) as exc:
        print(f"Backup failed: {exc}", file=sys.stderr)
        return 1
    print(f"Verified SQLite backup: {args.destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
