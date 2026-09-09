"""Regression coverage for release interruption and validation failures."""
import copy
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from check_release import release_notes, validate, version_tuple  # noqa: E402
import publish_release  # noqa: E402
from smoke_infer import check_probabilities  # noqa: E402


class MetadataTests(unittest.TestCase):
    def test_exact_changelog_section(self):
        text = "## [1.10] - 2026-09-09\nWrong\n## [1.1] - 2026-09-08\nCorrect\n## [1.0] - 2026-08-19\nOld\n"
        self.assertEqual(release_notes(text, "1.1"), "Correct\n")
        with self.assertRaises(ValueError):
            release_notes("## [1.10] - 2026-09-09\nWrong\n", "1.1")

    def test_missing_duplicate_empty_and_invalid_date(self):
        for text in ["", "## [1.1] - 2026-09-09\n", "## [1.1] - 2026-02-30\nNotes",
                     "## [1.1] - 2026-09-09\nA\n## [1.1] - 2026-09-09\nB"]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                release_notes(text, "1.1")

    def test_strict_version(self):
        self.assertGreater(version_tuple("1.10"), version_tuple("1.9"))
        for value in ("01.1", "1.01", "1.0.1", "1. 1", "1.1\n", "v1.1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                version_tuple(value)

    def test_probability_validation_is_language_independent(self):
        for label in ("Result:", "结论："):
            check_probabilities(f"  0.16s p=0.92 target\n 0.32s p=0.08 silence\n{label}\n", 2)

    def test_probability_validation_rejects_invalid_results(self):
        for output in ("", "0.16s p=nan", "0.16s p=inf", "0.16s p=1.2", "0.16s p=-0.1",
                       "0.32s p=0.5", "Result: target speaker detected"):
            with self.subTest(output=output), self.assertRaises(ValueError):
                check_probabilities(output, 1)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / "weights").mkdir()
        (self.root / "weights/nomo_pvad.pt").write_bytes(b"test weights")
        digest = hashlib.sha256(b"test weights").hexdigest()
        (self.root / "weights/CHECKSUMS.txt").write_text(f"{digest}  nomo_pvad.pt\n")
        (self.root / "VERSION").write_text("1.1\n")
        (self.root / "CHANGELOG.md").write_text("## [1.1] - 2026-09-09\nRelease notes\n")
        for name, other in [("README.md", "README.zh-CN.md"), ("README.zh-CN.md", "README.md")]:
            (self.root / name).write_text(f"`1.1` `release-1.1` [Language]({other})\n")
        self.tag_sha = "checked-sha"
        self.remote_sha = "checked-sha"
        self.release = None
        self.assets = {}
        self.commands = []
        self.fail_upload_once = False
        self.environment = patch.dict(os.environ, {"GITHUB_REF": "refs/heads/master"})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def run_command(self, *args):
        self.commands.append(args)
        if args[:3] == ("git", "rev-parse", "HEAD"):
            return "checked-sha"
        if args[:2] == ("git", "ls-remote"):
            return f"{self.remote_sha}\trefs/heads/master"
        if args[:3] == ("git", "tag", "--list"):
            return "release-1.1" if self.tag_sha else ""
        if args[:2] == ("git", "rev-parse"):
            return self.tag_sha
        if args[:3] == ("git", "tag", "-a"):
            self.tag_sha = args[-1]
        if args[:3] == ("gh", "release", "create"):
            self.release = {"draft": True, "assets": [], "tag_name": "release-1.1"}
        if args[:3] == ("gh", "release", "upload"):
            if self.fail_upload_once:
                self.fail_upload_once = False
                raise subprocess.CalledProcessError(1, args)
            source = Path(args[4])
            self.assets[source.name] = source.read_bytes()
            self.release["assets"].append({"name": source.name})
        if args[:3] == ("gh", "release", "download"):
            name = args[args.index("--pattern") + 1]
            target = Path(args[args.index("--dir") + 1]) / name
            target.write_bytes(self.assets[name])
        if args[:3] == ("gh", "release", "edit"):
            self.release["draft"] = False
        return ""

    def publish(self):
        with patch.object(publish_release, "run", side_effect=self.run_command), \
                patch.object(publish_release, "get_release", side_effect=lambda *args: copy.deepcopy(self.release)):
            publish_release.publish(self.root, "example/repo", "checked-sha")

    def test_tag_exists_release_missing(self):
        self.publish()
        self.assertFalse(self.release["draft"])
        self.assertEqual(set(self.assets), {"nomo_pvad.pt", "CHECKSUMS.txt"})
        self.assertFalse(any(cmd[:2] == ("git", "push") for cmd in self.commands))

    def test_first_release_creates_tag(self):
        self.tag_sha = None
        self.publish()
        self.assertIn(("git", "push", "origin", "refs/tags/release-1.1"), self.commands)

    def test_resume_after_upload_failure_and_repeat(self):
        self.fail_upload_once = True
        with self.assertRaises(subprocess.CalledProcessError):
            self.publish()
        self.assertTrue(self.release["draft"])
        self.publish()
        self.commands.clear()
        self.publish()
        self.assertFalse(any(cmd[:3] in [("gh", "release", "create"), ("gh", "release", "upload"),
                                        ("gh", "release", "edit")] for cmd in self.commands))

    def test_partial_draft_uploads_only_missing_asset(self):
        self.publish()
        self.release["draft"] = True
        self.release["assets"] = [{"name": "nomo_pvad.pt"}]
        del self.assets["CHECKSUMS.txt"]
        self.commands.clear()
        self.publish()
        uploads = [cmd for cmd in self.commands if cmd[:3] == ("gh", "release", "upload")]
        self.assertEqual(len(uploads), 1)
        self.assertTrue(uploads[0][4].endswith("CHECKSUMS.txt"))

    def test_tag_mismatch_is_never_moved(self):
        self.tag_sha = "old-release-sha"
        with self.assertRaisesRegex(ValueError, "another commit"):
            self.publish()
        self.assertFalse(any(cmd[:2] == ("git", "push") for cmd in self.commands))

    def test_asset_mismatch_is_never_overwritten(self):
        self.publish()
        self.assets["nomo_pvad.pt"] = b"wrong bytes"
        self.commands.clear()
        with self.assertRaisesRegex(ValueError, "asset differs"):
            self.publish()
        self.assertFalse(any(cmd[:3] == ("gh", "release", "upload") for cmd in self.commands))

    def test_stale_commit_or_wrong_branch_cannot_publish(self):
        self.remote_sha = "newer-master"
        with self.assertRaisesRegex(ValueError, "master advanced"):
            self.publish()
        with patch.dict(os.environ, {"GITHUB_REF": "refs/heads/dev"}), self.assertRaises(ValueError):
            self.publish()

    def test_metadata_rejects_checksum_and_readme_mismatch(self):
        (self.root / "README.zh-CN.md").write_text("`1.0`\n")
        with self.assertRaises(ValueError):
            validate(self.root)

    def test_api_failure_is_not_treated_as_missing_release(self):
        with patch.object(publish_release, "run", side_effect=subprocess.CalledProcessError(1, "gh")):
            with self.assertRaises(subprocess.CalledProcessError):
                publish_release.get_release("example/repo", "release-1.1")


if __name__ == "__main__":
    unittest.main()
