"""Tests for docs_check. Run with: python -m unittest -v"""
import tempfile
import unittest
from pathlib import Path

import docs_check

HERE = Path(__file__).parent


def rules(findings):
    return sorted(f.rule for f in findings)


class DocsCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.terms = docs_check.load_terms(HERE / "terms.txt")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, text):
        path = self.dir / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_clean_topic_has_no_findings(self):
        self.write("other.md", "---\ntitle: Other\ndescription: x\n---\n# Other\n## Setup steps\n")
        path = self.write("ok.md", "---\ntitle: OK\ndescription: A clean topic.\n---\n"
                                   "# OK\nRead [setup](other.md#setup-steps) first.\n")
        self.assertEqual(docs_check.check_file(path, self.terms), [])

    def test_missing_metadata(self):
        path = self.write("a.md", "---\ntitle: A\n---\n# A\n")
        self.assertEqual(rules(docs_check.check_file(path, self.terms)), ["metadata"])

    def test_broken_link_and_anchor(self):
        path = self.write("a.md", "---\ntitle: A\ndescription: d\n---\n# A\n"
                                  "[x](missing.md) and [y](#nowhere)\n")
        self.assertEqual(rules(docs_check.check_file(path, self.terms)), ["broken-anchor", "broken-link"])

    def test_terminology_is_case_aware(self):
        path = self.write("a.md", "---\ntitle: A\ndescription: d\n---\n# A\n"
                                  "Kubernetes is fine. kubernetes is not.\n")
        found = docs_check.check_file(path, self.terms)
        self.assertEqual(len(found), 1)
        self.assertIn("'Kubernetes' instead of 'kubernetes'", found[0].message)

    def test_code_is_ignored(self):
        path = self.write("a.md", "---\ntitle: A\ndescription: d\n---\n# A\n"
                                  "Run `kubectl get pods`.\n```\nclick on kubernetes\n```\n")
        self.assertEqual(docs_check.check_file(path, self.terms), [])

    def test_bad_example_flags_every_problem(self):
        found = docs_check.check_file(HERE / "examples" / "bad-topic.md", self.terms)
        for rule in ("metadata", "terminology", "filler", "long-sentence",
                     "heading-skip", "broken-link", "broken-anchor", "alt-text"):
            self.assertIn(rule, rules(found))


if __name__ == "__main__":
    unittest.main()
