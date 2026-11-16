"""Regression checks for EPUB upload size guards.

These source-level tests complement (do not replace) authenticated upload
integration tests. They prevent a guard being accidentally commented out.
"""
from pathlib import Path
import re
import unittest

PROGRAM = Path(__file__).resolve().parents[1] / "Program.cs"


class EpubGuardRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = PROGRAM.read_text(encoding="utf-8")

    def test_mimetype_guard_is_executable(self):
        lines = self.source.splitlines()
        condition = re.compile(r"^\s*if\s*\(\s*mime\.Length\s*>\s*128\s*\)")
        matching = [i for i, line in enumerate(lines) if condition.search(line)]
        self.assertEqual(len(matching), 1, "Expected one executable mimetype size guard")
        i = matching[0]
        self.assertNotIn("//", lines[i].split("if", 1)[0])
        following = "\n".join(lines[i + 1:i + 4])
        self.assertIn("throw new InvalidDataException", following)
        self.assertLess(self.source.index("mime.Length > 128"), self.source.index("mime.Open()"))

    def test_xml_metadata_bounds_precede_parsing(self):
        for entry, limit, parse_call in (
            ("container", "1024 * 1024", "XDocument.Load(stream)"),
            ("opf", "4 * 1024 * 1024", "XDocument.Load(stream)"),
        ):
            guard = f"{entry}.Length > {limit}"
            self.assertIn(guard, self.source)
            start = self.source.index(guard)
            parse = self.source.index(parse_call, start)
            self.assertIn("throw new InvalidDataException", self.source[start:parse])

    def test_ci_discovers_security_regressions(self):
        workflow = (PROGRAM.parent / ".github/workflows/anka-deploy.yml").read_text(encoding="utf-8")
        self.assertIn("test_*backup*.py", workflow)
        self.assertIn("tests/**", workflow)


if __name__ == "__main__":
    unittest.main()
