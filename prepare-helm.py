#!/usr/bin/env python3
"""Provide complete Helm inputs for analysis without contacting the lab VM."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def prepare_git_metadata(root, private, values):
    """Give only the generated input its own provenance; never commit user edits."""
    def source_git(*arguments):
        return subprocess.run(["git", "-C", str(root), *arguments],
                              capture_output=True, text=True, check=True).stdout.strip()

    revision = source_git("rev-parse", "HEAD")
    objects = source_git("rev-parse", "--path-format=absolute", "--git-path", "objects")
    timestamp = source_git("show", "-s", "--format=%cI", revision)
    metadata = private / "git"
    if metadata.exists():
        shutil.rmtree(metadata)
    environment = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
                   "GIT_AUTHOR_NAME": "SonarQube analysis", "GIT_COMMITTER_NAME": "SonarQube analysis",
                   "GIT_AUTHOR_EMAIL": "sonarqube-analysis@invalid",
                   "GIT_COMMITTER_EMAIL": "sonarqube-analysis@invalid",
                   "GIT_AUTHOR_DATE": timestamp, "GIT_COMMITTER_DATE": timestamp}

    def analysis_git(*arguments, input=None):
        return subprocess.run(["git", "--git-dir", str(metadata), *arguments], env=environment,
                              input=input, capture_output=True, text=True, check=True).stdout.strip()

    analysis_git("init", "--bare", "--template=", "--initial-branch=sonar-analysis")
    alternates = metadata / "objects/info/alternates"
    # Share read-only source objects instead of copying the repository's history.
    alternates.write_text(objects + "\n")
    analysis_git("read-tree", revision)
    blob = analysis_git("hash-object", "-w", "--stdin", input=values.read_text())
    analysis_git("update-index", "--add", "--cacheinfo", "100644", blob,
                 "config/microservices/chart/values.yaml")
    tree = analysis_git("write-tree")
    commit = analysis_git("commit-tree", tree, "-p", revision,
                          input="Generated Helm analysis inputs; application source history preserved.\n")
    analysis_git("update-ref", "HEAD", commit)
    analysis_git("config", "core.bare", "false")
    analysis_git("config", "core.worktree", "/workspace")
    # This scan covers microservices only. Git status must not descend into the
    # frontend submodules, whose private Git directories are outside this metadata.
    analysis_git("config", "diff.ignoreSubmodules", "all")
    # Scanner-only paths; the original .git, refs and index are never written.
    alternates.write_text("/scm-objects\n")
    (private / "origin-objects.path").write_text(objects + "\n")
    (private / "source-revision").write_text(revision + "\n")


def main():
    root = Path(os.environ["SONAR_SOURCE_ROOT"]).resolve()
    state = Path(os.environ["SONAR_STATE_ROOT"]).resolve()
    support = Path(os.environ.get("MYSCOUTEE_MICROSERVICES_SOURCE", root.parent / "myscoutee-microservices"))
    os.environ["MYSCOUTEE_BACKEND_SOURCE"] = str(root)
    sys.path.insert(0, str(support / "tools"))
    import workloads

    private = state / "build/helm"
    workloads.vm.private_directory(private)
    # This imported module instance belongs only to this process. Never open lab credentials.
    workloads.SECRET_FILE = private / "analysis-credentials.json"
    credentials = {key: "sonar-analysis-placeholder" for key in workloads.secrets_data()}
    values = workloads.chart_values(credentials=credentials, cluster_dns="192.0.2.53",
                                    release_certificate="")
    overlay = private / "overlay.json"
    overlay.write_text(json.dumps(values) + "\n")
    overlay.chmod(0o600)

    # Let the existing pinned Helm merge the real chart defaults. No YAML parser
    # or duplicate copy of deployment defaults is maintained in the Sonar tool.
    with tempfile.TemporaryDirectory(dir=private) as temporary:
        chart = Path(temporary)
        shutil.copyfile(root / "config/microservices/chart/Chart.yaml", chart / "Chart.yaml")
        shutil.copyfile(root / "config/microservices/chart/values.yaml", chart / "values.yaml")
        (chart / "templates").mkdir()
        (chart / "templates/analysis-values.yaml").write_text("{{ .Values | toJson }}\n")
        rendered = subprocess.run([str(support / "tools/helm.sh"), "template", "sonar-analysis",
                                   str(chart), "-f", str(overlay)],
                                  capture_output=True, text=True, check=True)
        merged = json.loads(next(line for line in rendered.stdout.splitlines() if line.startswith("{")))
    target = private / "values.json"
    target.write_text(json.dumps(merged, indent=2) + "\n")
    target.chmod(0o600)
    prepare_git_metadata(root, private, target)
    print("Helm analysis values prepared from the canonical deployment owner and chart defaults.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        raise SystemExit(f"Helm analysis preparation failed: {error.stderr.strip()}")
    except (OSError, ValueError) as error:
        raise SystemExit(str(error))
