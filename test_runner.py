"""Exercise shared-server routing and analysis isolation and the global scan lock without starting Docker."""

import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from project import MODULES


class RunnerTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.central = self.root / "central tool"
        self.central.mkdir()
        for name in ("run.sh", "project.py", "compose.yaml", "server.json"):
            shutil.copyfile(Path(__file__).with_name(name), self.central / name)
        (self.central / "wait-analysis.py").write_text("import sys; sys.stdin.read()\n")
        self.source = self.create_source("first")
        self.log = self.root / "docker-calls"
        binary = self.root / "bin"
        binary.mkdir()
        docker = binary / "docker"
        docker.write_text('#!/usr/bin/env python3\nimport json,os,sys\n'
                          'from pathlib import Path\n'
                          'with Path(os.environ["DOCKER_LOG"]).open("a") as log:\n'
                          ' log.write(json.dumps({\n'
                          '"args":sys.argv[1:],"source":os.environ["SONAR_SOURCE_ROOT"],\n'
                          '"state":os.environ["SONAR_STATE_ROOT"],\n'
                          '"project":os.environ["SONAR_COMPOSE_PROJECT"]}) + "\\n")\n')
        docker.chmod(0o700)
        self.environment = {**os.environ, "PATH": str(binary) + os.pathsep + os.environ["PATH"],
                            "DOCKER_LOG": str(self.log)}

    def create_source(self, identity):
        source = self.root / (identity + " source")
        configuration = source / "config" / "sonarqube"
        configuration.mkdir(parents=True)
        (configuration / "project.json").write_text(json.dumps({
            "id": identity, "composeProject": identity + "-sonarqube", "port": 9000,
            "modules": {name: name for name in MODULES}}))
        for module in MODULES:
            (configuration / (module + ".properties")).write_text("sonar.projectKey=" + module)
        return source

    def run_tool(self, source, *arguments):
        return subprocess.run(["bash", str(self.central / "run.sh"), str(source), *arguments],
                              cwd=self.root, env=self.environment, capture_output=True, text=True)

    def test_source_paths_with_spaces_use_only_the_selected_private_state(self):
        result = self.run_tool(self.source, "init")
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.run_tool(self.source, "check")
        self.assertEqual(result.returncode, 0, result.stderr)
        call = json.loads(self.log.read_text().splitlines()[-1])
        self.assertEqual(call["source"], str(self.source))
        self.assertEqual(call["state"], str(self.central / ".state/first"))
        self.assertEqual(call["project"], "myscoutee-sonarqube")
        self.assertIn(str(self.central / ".state/myscoutee/.env"), call["args"])
        self.assertFalse((self.source / "config/sonarqube/.env").exists())
        self.assertEqual((self.central / ".state/myscoutee/.env").stat().st_mode & 0o777, 0o600)

    def test_global_scan_lock_rejects_another_project_before_docker_or_preparation(self):
        second = self.create_source("second")
        (self.central / ".state").mkdir()
        with (self.central / ".state/scan.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            for source in (self.source, second):
                result = self.run_tool(source, "scan", "backend")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Another central Sonar scan is running", result.stderr)
        self.assertFalse(self.log.exists())

    def test_invalid_project_cannot_escape_private_state_or_reach_docker(self):
        path = self.source / "config/sonarqube/project.json"
        settings = json.loads(path.read_text())
        settings["id"] = "../outside"
        path.write_text(json.dumps(settings))
        result = self.run_tool(self.source, "check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Invalid project id", result.stderr)
        self.assertFalse(self.log.exists())
        self.assertFalse((self.central / ".state").exists())

    def test_private_runtime_directory_is_hidden_from_scanner(self):
        path = self.source / "config/sonarqube/project.json"
        settings = json.loads(path.read_text())
        settings["modules"] = {"runtime": "."}
        settings["privateDirectories"] = ["server/data"]
        path.write_text(json.dumps(settings))
        (self.source / "server/data").mkdir(parents=True)
        self.assertEqual(self.run_tool(self.source, "init").returncode, 0)
        result = self.run_tool(self.source, "scan", "runtime")
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        scanner = next(call for call in calls if "run" in call["args"])
        self.assertTrue(any(argument.endswith(":/workspace/server/data:ro") for argument in scanner["args"]))

    def test_private_directory_cannot_hide_a_sibling_or_entire_source(self):
        path = self.source / "config/sonarqube/project.json"
        for directory in ["../outside", "/absolute", ".", "server/.."]:
            settings = json.loads(path.read_text())
            settings["privateDirectories"] = [directory]
            path.write_text(json.dumps(settings))
            result = self.run_tool(self.source, "check")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Private directories must stay inside", result.stderr)

    def test_module_cannot_scan_a_sibling_repository(self):
        path = self.source / "config/sonarqube/project.json"
        settings = json.loads(path.read_text())
        settings["modules"]["backend"] = "../outside"
        path.write_text(json.dumps(settings))
        result = self.run_tool(self.source, "check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must stay inside", result.stderr)
        self.assertFalse(self.log.exists())

    def test_library_can_configure_only_its_owned_components_module(self):
        path = self.source / "config/sonarqube/project.json"
        settings = json.loads(path.read_text())
        settings["modules"] = {"components": "."}
        path.write_text(json.dumps(settings))
        self.assertEqual(self.run_tool(self.source, "init").returncode, 0)
        result = self.run_tool(self.source, "check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.log.exists())

    def test_runtime_sources_scan_without_backend_or_helm_preparation(self):
        path = self.source / "config/sonarqube/project.json"
        settings = json.loads(path.read_text())
        settings["modules"] = {"runtime": "."}
        path.write_text(json.dumps(settings))
        self.assertEqual(self.run_tool(self.source, "init").returncode, 0)
        result = self.run_tool(self.source, "scan", "runtime")
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        self.assertTrue(all("up" not in call["args"] for call in calls))
        scanner = next(call for call in calls if "run" in call["args"])
        self.assertIn("-Dproject.settings=/config/runtime.properties", scanner["args"])
        self.assertIn("-Dsonar.projectBaseDir=/workspace/.", scanner["args"])

    def test_unconfigured_module_is_rejected_before_docker(self):
        path = self.source / "config/sonarqube/project.json"
        settings = json.loads(path.read_text())
        settings["modules"] = {"frontend": "frontend"}
        path.write_text(json.dumps(settings))
        result = self.run_tool(self.source, "scan", "components")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not configured", result.stderr)
        self.assertFalse(self.log.exists())

    def test_two_sources_share_server_credentials_and_keep_separate_reports(self):
        second = self.create_source("second")
        self.assertEqual(self.run_tool(self.source, "init").returncode, 0)
        environment = self.central / ".state/myscoutee/.env"
        original = environment.read_bytes()
        self.assertEqual(self.run_tool(second, "init").returncode, 0)
        self.assertEqual(environment.read_bytes(), original)
        for source, identity in ((self.source, "first"), (second, "second")):
            result = self.run_tool(source, "scan", "frontend")
            self.assertEqual(result.returncode, 0, result.stderr)
            calls = [json.loads(line) for line in self.log.read_text().splitlines()]
            self.assertTrue(all(call["project"] == "myscoutee-sonarqube" for call in calls))
            self.assertTrue(all("up" not in call["args"] for call in calls))
            scanner = next(call for call in reversed(calls) if "run" in call["args"])
            self.assertIn("--no-deps", scanner["args"])
            self.assertEqual(scanner["state"], str(self.central / ".state" / identity))
        self.assertFalse((self.central / ".state/second/.env").exists())

    def test_unavailable_shared_server_does_not_start_another_instance(self):
        docker = self.root / "bin/docker"
        docker.write_text("#!/bin/sh\nexit 1\n")
        result = self.run_tool(self.source, "scan", "frontend")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Start the shared server explicitly", result.stderr)
