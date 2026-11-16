"""Source-level regression guards for hostile EPUB upload limits.

These checks complement, but do not replace, runtime ZIP-bomb tests.
"""
from pathlib import Path
import unittest

SOURCE = (Path(__file__).resolve().parents[1] / "Program.cs").read_text(encoding="utf-8")


class EpubUploadBoundsTests(unittest.TestCase):
    def test_archive_limits_precede_metadata_extraction(self):
        start = SOURCE.index('app.MapPost("/api/books"')
        end = SOURCE.index('app.MapRazorComponents<App>()', start)
        upload = SOURCE[start:end]
        checks = [
            'file.Length > 50L * 1024 * 1024',
            'archive.Entries.Count > 15000',
            'archive.Entries.Sum(e => e.Length) > 200L * 1024 * 1024',
            'mime.Length > 128',
            'container.Length > 1024 * 1024',
            'opf.Length > 4 * 1024 * 1024',
        ]
        for check in checks:
            with self.subTest(check=check):
                self.assertIn(check, upload)
        self.assertLess(upload.index('archive.Entries.Count > 15000'), upload.index('mime.Open()'))
        self.assertLess(upload.index('container.Length > 1024 * 1024'), upload.index('container.Open()'))
        self.assertLess(upload.index('opf.Length > 4 * 1024 * 1024'), upload.index('opf.Open()'))

    def test_rejected_upload_deletes_uncommitted_file(self):
        upload = SOURCE[SOURCE.index('app.MapPost("/api/books"'):SOURCE.index('app.MapRazorComponents<App>()')]
        self.assertIn('catch (InvalidDataException e) { File.Delete(path);', upload)
        self.assertIn('catch (System.Xml.XmlException) { File.Delete(path);', upload)
        self.assertIn('catch { File.Delete(path); throw; }', upload)


if __name__ == "__main__":
    unittest.main()
