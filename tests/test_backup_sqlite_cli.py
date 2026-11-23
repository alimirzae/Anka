"""End-to-end safety checks for scripts/backup_sqlite.py using disposable fixtures."""
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'backup_sqlite.py'


class BackupCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.live_dir = root / 'live'
        self.backups = root / 'backups'
        self.live_dir.mkdir()
        self.backups.mkdir()
        self.source = self.live_dir / 'anka.db'
        self.target = self.backups / 'snapshot.db'
        with sqlite3.connect(self.source) as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE editions(id INTEGER PRIMARY KEY, title TEXT NOT NULL)')
            db.execute("INSERT INTO editions VALUES (1, 'approved')")

    def run_backup(self, destination=None):
        return subprocess.run(
            [sys.executable, str(SCRIPT), '--source', str(self.source),
             '--destination', str(destination or self.target)],
            capture_output=True, text=True, timeout=30,
        )

    def test_snapshot_roundtrip_and_no_overwrite(self):
        result = self.run_backup()
        self.assertEqual(result.returncode, 0, result.stderr)
        with sqlite3.connect(self.target) as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(db.execute('SELECT title FROM editions').fetchone()[0], 'approved')
        original = self.target.read_bytes()
        result = self.run_backup()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.target.read_bytes(), original)

    def test_rejects_backup_inside_live_directory(self):
        result = self.run_backup(self.live_dir / 'unsafe.db')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.live_dir / 'unsafe.db').exists())

    def test_rejects_source_as_destination(self):
        before = self.source.read_bytes()
        result = self.run_backup(self.source)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.source.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
