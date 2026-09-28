import importlib.util
import tempfile
import unittest
from pathlib import Path


SPEC = importlib.util.spec_from_file_location("public_content", Path(__file__).with_name("check-public-content.py"))
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PublicContentGateTest(unittest.TestCase):
    def test_old_tree_and_personal_address_block_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "v0.3").mkdir()
            (root / "v0.3/README.md").write_text("old edition\n")
            (root / "v0.5").mkdir()
            (root / "v0.5/README.md").write_text("Contact owner@" + "personal.test\n")
            findings = MODULE.problems(root)
            self.assertTrue(any("old edition tree" in item for item in findings))
            self.assertTrue(any("non-placeholder email" in item for item in findings))

    def test_examples_and_git_transport_are_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("user@example.invalid and git@github.com\n")
            self.assertEqual(MODULE.problems(root), [])

    def test_public_guide_link_is_allowed_only_in_root_readme(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text(MODULE.PUBLIC_GUIDE_LINK)
            self.assertEqual(MODULE.problems(root), [])
            (root / "other.md").write_text(MODULE.PUBLIC_GUIDE_LINK)
            self.assertTrue(any("other.md" in item for item in MODULE.problems(root)))

    def test_public_link_does_not_hide_other_private_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for content in (
                MODULE.PUBLIC_GUIDE_LINK + " rudy" + "molt",
                MODULE.PUBLIC_GUIDE_LINK.replace("playbook)", "playbook-private)"),
                MODULE.PUBLIC_GUIDE_LINK + " owner@" + "personal.test",
            ):
                with self.subTest(content=content):
                    (root / "README.md").write_text(content)
                    self.assertTrue(MODULE.problems(root))

    def test_lowercase_private_fixture_identifiers_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "fixture.json").write_text(
                '{"project":"ru' + 'champs","run":"run-ru' + 'd-413",'
                '"env":"RU' + 'D409"}\n'
            )
            self.assertTrue(any("private marker" in item for item in MODULE.problems(root)))


if __name__ == "__main__":
    unittest.main()
