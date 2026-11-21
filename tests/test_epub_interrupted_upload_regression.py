"""Regression guard for interrupted EPUB uploads.

Source-level checks only: these do not simulate a network disconnect or
prove IIS storage cleanup. Keep a separate integration test for that.
"""
from pathlib import Path
import unittest

SOURCE = (Path(__file__).resolve().parents[1] / "Program.cs").read_text(encoding="utf-8")


class InterruptedUploadCleanupTests(unittest.TestCase):
    def test_copy_and_validation_are_inside_cleanup_try(self):
        start = SOURCE.index('app.MapPost("/api/books"')
        end = SOURCE.index('app.MapRazorComponents<App>()', start)
        handler = SOURCE[start:end]
        path = handler.index('var path = Path.Combine(storage, name);')
        protected = handler.index('    try\n    {', path)
        copy = handler.index('await file.CopyToAsync(dest);', protected)
        validation = handler.index('using var archive = ZipFile.OpenRead(path);', copy)
        first_catch = handler.index('catch (InvalidDataException e)', validation)
        self.assertLess(path, protected)
        self.assertLess(protected, copy)
        self.assertLess(copy, validation)
        self.assertLess(validation, first_catch)

    def test_every_failure_handler_removes_partial_file(self):
        start = SOURCE.index('app.MapPost("/api/books"')
        end = SOURCE.index('app.MapRazorComponents<App>()', start)
        handler = SOURCE[start:end]
        for failure in (
            'catch (InvalidDataException e)',
            'catch (System.Xml.XmlException)',
            'catch {',
        ):
            with self.subTest(failure=failure):
                position = handler.index(failure)
                self.assertIn('File.Delete(path);', handler[position:position + 160])

    def test_database_commit_precedes_success_response(self):
        start = SOURCE.index('app.MapPost("/api/books"')
        end = SOURCE.index('app.MapRazorComponents<App>()', start)
        handler = SOURCE[start:end]
        self.assertLess(handler.index('await transaction.CommitAsync();'),
                        handler.index('return Results.Created('))


if __name__ == "__main__":
    unittest.main()
