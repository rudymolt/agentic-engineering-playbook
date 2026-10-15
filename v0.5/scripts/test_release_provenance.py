import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import release_provenance


class ReleaseProvenanceTest(unittest.TestCase):
    def checkout(self, root: Path) -> tuple[Path, str, str]:
        root.mkdir()
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.name", "Fixture"], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.email", "fixture@example.invalid"], check=True)
        (root / "v0.5").mkdir()
        (root / "v0.5" / "README.md").write_text("release fixture\n")
        subprocess.run(["git", "-C", str(root), "add", "."], check=True)
        subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture"], check=True)
        subprocess.run(["git", "-C", str(root), "tag", "-a", "v0.5.2", "-m", "release"], check=True)
        head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
        tag = subprocess.check_output(["git", "-C", str(root), "rev-parse", "refs/tags/v0.5.2"], text=True).strip()
        return root, head, tag

    def test_exact_published_clean_tag_is_a_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, head, tag = self.checkout(Path(tmp) / "checkout")
            with patch.object(release_provenance, "published_tag_refs", return_value=(tag, head)):
                self.assertEqual(
                    release_provenance.verified_release_evidence(root), ("v0.5.2", tag, head)
                )
                self.assertEqual(release_provenance.verified_release(root), "v0.5.2")

    def test_changed_checkout_or_unverified_tag_is_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, head, tag = self.checkout(Path(tmp) / "checkout")
            with patch.object(release_provenance, "published_tag_refs", return_value=None):
                self.assertIsNone(release_provenance.verified_release(root))
            with patch.object(release_provenance, "published_tag_refs", return_value=(tag, head)):
                (root / "v0.5" / "README.md").write_text("modified\n")
                self.assertIsNone(release_provenance.verified_release(root))

    def test_local_tag_must_match_the_public_tag_object(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, head, _ = self.checkout(Path(tmp) / "checkout")
            with patch.object(release_provenance, "published_tag_refs", return_value=("0" * 40, head)):
                self.assertIsNone(release_provenance.verified_release(root))

    def test_warm_check_detects_a_checkout_advanced_in_place_without_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, head, tag = self.checkout(Path(tmp) / "checkout")
            with patch.object(release_provenance, "published_tag_refs", side_effect=AssertionError("network used")):
                self.assertTrue(release_provenance.local_checkout_matches_release(root, "v0.5.2", tag, head))
                with redirect_stdout(StringIO()):
                    self.assertEqual(release_provenance.main([
                        str(root), "--local-check", "v0.5.2", "--tag-object", tag,
                        "--commit", head,
                    ]), 0)
                (root / "v0.5" / "README.md").write_text("next release\n")
                subprocess.run(["git", "-C", str(root), "add", "."], check=True)
                subprocess.run(["git", "-C", str(root), "commit", "-qm", "advance"], check=True)
                subprocess.run(["git", "-C", str(root), "tag", "-fa", "v0.5.2", "-m", "moved"],
                               check=True, capture_output=True)
                self.assertFalse(release_provenance.local_checkout_matches_release(root, "v0.5.2", tag, head))
                self.assertFalse(release_provenance.local_checkout_matches_release(root, None, tag, head))
                with redirect_stdout(StringIO()):
                    self.assertEqual(release_provenance.main([
                        str(root), "--local-check", "v0.5.2", "--tag-object", tag,
                        "--commit", head,
                    ]), 2)

    def test_directory_name_and_changelog_do_not_prove_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "v0.5.2"
            root.mkdir()
            (root / "v0.5").mkdir()
            (root / "v0.5" / "CHANGELOG.md").write_text("## V0.5.2\n")
            self.assertIsNone(release_provenance.verified_release(root))


if __name__ == "__main__":
    unittest.main()
