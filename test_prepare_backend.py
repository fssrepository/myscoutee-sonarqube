"""Artifact freshness checks without Gradle, Java compilation or running services."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from zipfile import ZipFile


class ArtifactFreshnessTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.sonar = self.root / "sonarqube"
        self.sonar.mkdir()
        shutil.copyfile(Path(__file__).with_name("prepare-backend.py"), self.sonar / "prepare-backend.py")
        self.source = self.root / "server/projects/profile/src/main/java/Example.java"
        self.source.parent.mkdir(parents=True)
        self.source.write_text("class Example {}\n")
        self.configuration = self.root / "config/sonarqube/project.json"
        self.configuration.parent.mkdir(parents=True)
        self.configuration.write_text(json.dumps({"modules": {"backend": "server/projects/profile"}}))
        self.jar = self.root / "profile.jar"
        with ZipFile(self.jar, "w") as archive:
            archive.writestr("BOOT-INF/classes/Example.class", b"\xca\xfe\xba\xbe")
        os.utime(self.jar, (200, 200))

    def prepare(self, **variables):
        return subprocess.run(["python3", str(self.sonar / "prepare-backend.py")],
                              env={**os.environ, "BACKEND_JAR": str(self.jar),
                                   "SONAR_SOURCE_ROOT": str(self.root),
                                   "SONAR_STATE_ROOT": str(self.sonar), **variables},
                              text=True, capture_output=True)

    def test_current_artifact_is_extracted(self):
        os.utime(self.source, (100, 100))
        result = self.prepare()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.sonar / "build/analysis/backend/classes/Example.class").read_bytes(),
                         b"\xca\xfe\xba\xbe")

    def test_stale_artifact_is_rejected_before_replacing_analysis(self):
        os.utime(self.source, (300, 300))
        marker = self.sonar / "build/analysis/backend/previous-analysis"
        marker.parent.mkdir(parents=True)
        marker.write_text("keep")
        result = self.prepare()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Java source is newer", result.stderr)
        self.assertEqual(marker.read_text(), "keep")

    def test_explicit_current_coverage_is_copied_without_executing_tests(self):
        os.utime(self.source, (100, 100))
        report = self.root / "coverage.xml"
        report.write_text('<report name="tests"/>')
        result = self.prepare(BACKEND_COVERAGE_REPORT=str(report))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.sonar / "build/analysis/backend/coverage.xml").read_text(), report.read_text())

    def test_stale_coverage_is_rejected_before_replacing_analysis(self):
        os.utime(self.source, (100, 100))
        report = self.root / "coverage.xml"
        report.write_text('<report name="tests"/>')
        os.utime(report, (50, 50))
        marker = self.sonar / "build/analysis/backend/previous-analysis"
        marker.parent.mkdir(parents=True)
        marker.write_text("keep")
        result = self.prepare(BACKEND_COVERAGE_REPORT=str(report))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("newer than coverage report", result.stderr)
        self.assertEqual(marker.read_text(), "keep")

    def test_coverage_is_not_imported_implicitly(self):
        os.utime(self.source, (100, 100))
        (self.root / "coverage.xml").write_text('<report name="tests"/>')
        result = self.prepare()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.sonar / "build/analysis/backend/coverage.xml").exists())

    def test_library_bytecode_is_imported_without_boot_jar_or_build(self):
        self.configuration.write_text(json.dumps({"modules": {"backend": "server"},
                                                  "bytecode": {"backend": "gradle-output"}}))
        prepared = self.root / "server/build/sonar"
        (prepared / "classes").mkdir(parents=True)
        (prepared / "lib").mkdir()
        (prepared / "classes/Example.class").write_bytes(b"library")
        (prepared / "prepared").write_text("version")
        os.utime(self.source, (100, 100))
        result = self.prepare()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.sonar / "build/analysis/backend/classes/Example.class").read_bytes(), b"library")
        os.utime(prepared / "prepared", (50, 50))
        result = self.prepare()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("newer than prepared bytecode", result.stderr)
        self.assertEqual((self.sonar / "build/analysis/backend/classes/Example.class").read_bytes(), b"library")
