"""Verify generated-input provenance without altering the source repository."""

import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


spec = importlib.util.spec_from_file_location("prepare_helm", Path(__file__).with_name("prepare-helm.py"))
prepare_helm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare_helm)


class HelmMetadataTest(unittest.TestCase):
    def test_generated_values_have_provenance_and_source_state_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "source"
            root.mkdir()
            environment = {**os.environ, "GIT_AUTHOR_NAME": "Original author",
                           "GIT_COMMITTER_NAME": "Original author",
                           "GIT_AUTHOR_EMAIL": "original@example.invalid",
                           "GIT_COMMITTER_EMAIL": "original@example.invalid"}

            def git(*arguments):
                return subprocess.run(["git", "-C", str(root), *arguments], env=environment,
                                      capture_output=True, text=True, check=True).stdout.strip()

            git("init", "--template=", "--initial-branch=main")
            chart = root / "config/microservices/chart"
            chart.mkdir(parents=True)
            (chart / "values.yaml").write_text("images: {}\n")
            source = root / "microservices/source.py"
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("original = True\n")
            git("add", ".")
            git("commit", "-m", "Original source")
            git("update-index", "--add", "--cacheinfo", "160000", git("rev-parse", "HEAD"), "frontend")
            (root / ".gitmodules").write_text('[submodule "frontend"]\n\tpath = frontend\n\turl = ../frontend\n')
            git("add", ".gitmodules")
            git("commit", "-m", "Frontend submodule")
            (root / "frontend").mkdir()
            (root / "frontend/.git").write_text("gitdir: ../.git/modules/frontend\n")
            revision = git("rev-parse", "HEAD")
            source.write_text("original = False\n")
            git("add", str(source))
            index_before = (root / ".git/index").read_bytes()
            config_before = (root / ".git/config").read_bytes()
            status_before = git("-c", "diff.ignoreSubmodules=all", "status", "--porcelain=v1")

            private = Path(temporary) / "analysis"
            private.mkdir()
            values = private / "values.json"
            values.write_text('{"images": {"example": "placeholder"}}\n')
            prepare_helm.prepare_git_metadata(root, private, values)
            metadata = private / "git"
            self.assertEqual((metadata / "objects/info/alternates").read_text(), "/scm-objects\n")
            self.assertEqual((private / "source-revision").read_text().strip(), revision)
            self.assertEqual((private / "origin-objects.path").read_text().strip(), str(root / ".git/objects"))

            # Resolve the scanner's read-only object mount at its host path for these checks.
            (metadata / "objects/info/alternates").write_text(str(root / ".git/objects") + "\n")

            def snapshot(*arguments):
                return git("--git-dir", str(metadata), "--work-tree", str(root), *arguments)

            self.assertEqual(snapshot("rev-parse", "HEAD^"), revision)
            self.assertEqual(snapshot("diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"),
                             "config/microservices/chart/values.yaml")
            self.assertEqual(snapshot("show", "HEAD:config/microservices/chart/values.yaml"),
                             values.read_text().strip())
            self.assertEqual(snapshot("show", "HEAD:microservices/source.py"), "original = True")
            self.assertEqual(snapshot("show", "-s", "--format=%an"), "SonarQube analysis")
            self.assertIn("Original author", snapshot("blame", "HEAD", "--", "microservices/source.py"))
            self.assertIn("microservices/source.py", snapshot("status", "--porcelain=v1"))
            self.assertEqual(git("rev-parse", "HEAD"), revision)
            self.assertEqual((root / ".git/index").read_bytes(), index_before)
            self.assertEqual((root / ".git/config").read_bytes(), config_before)
            self.assertEqual(git("-c", "diff.ignoreSubmodules=all", "status", "--porcelain=v1"), status_before)
            self.assertEqual((chart / "values.yaml").read_text(), "images: {}\n")


if __name__ == "__main__":
    unittest.main()
