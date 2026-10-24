#!/usr/bin/env python3
"""Read existing Spring Boot bytecode and libraries; never invoke a build."""

import os
import json
from pathlib import Path, PurePosixPath
import shutil
import sys
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile


def main():
    root = Path(os.environ["SONAR_SOURCE_ROOT"]).resolve()
    module = sys.argv[1] if len(sys.argv) > 1 else "backend"
    if module not in {"backend", "microservices"}:
        raise ValueError("Expected backend or microservices")
    output = Path(os.environ["SONAR_STATE_ROOT"]) / "build/analysis" / module
    source_roots = [root / "server/projects/profile/src/main/java"]
    business = source_roots[0]
    units = [*business.glob("com/raxim/myscoutee/domain/*/transport"),
             *business.glob("com/raxim/myscoutee/common/microservices/*")]
    optional_roots = [unit / "src/main/java" for unit in units]
    if module == "microservices":
        source_roots += optional_roots

    def sources(folders):
        for folder in folders:
            for source in folder.rglob("*.java"):
                if folder == business and any(unit in source.parents for unit in units):
                    continue
                yield source
    coverage_variable = "BACKEND_COVERAGE_REPORT" if module == "backend" else "MICROSERVICES_COVERAGE_REPORT"
    coverage = os.environ.get(coverage_variable)
    if coverage:
        coverage = Path(coverage)
        if not coverage.is_absolute():
            coverage = root / coverage
        if ElementTree.parse(coverage).getroot().tag != "report":
            raise ValueError(f"Expected a JaCoCo XML report: {coverage}")
        coverage_source_roots = source_roots if module == "backend" else source_roots[1:]
        newer = next((source for source in sources(coverage_source_roots)
                      if source.stat().st_mtime > coverage.stat().st_mtime), None)
        if newer is not None:
            raise ValueError(f"Java source is newer than coverage report: {newer.relative_to(root)}. "
                             "Generate matching coverage explicitly; no tests are run by the scanner.")
    settings = json.loads((root / "config/sonarqube/project.json").read_text())
    if settings.get("bytecode", {}).get(module) == "gradle-output":
        prepared = root / settings["modules"][module] / "build/sonar"
        marker = prepared / "prepared"
        source = root / settings["modules"][module] / "projects/profile/src/main/java"
        if not marker.is_file() or not any((prepared / "classes").rglob("*.class")):
            raise ValueError("No prepared library bytecode. Run server/gradlew -p server prepareSonar explicitly; no build is run by the scanner.")
        newer = next((path for path in source.rglob("*.java")
                      if path.stat().st_mtime > marker.stat().st_mtime), None)
        if newer is not None:
            raise ValueError(f"Java source is newer than prepared bytecode: {newer.relative_to(root)}. Run prepareSonar explicitly.")
        if output.exists():
            shutil.rmtree(output)
        shutil.copytree(prepared, output)
        if coverage:
            shutil.copyfile(coverage, output / "coverage.xml")
        print(f"{module} bytecode and dependencies: {prepared}; no build or tests run.", flush=True)
        return
    variable = "BACKEND_JAR" if module == "backend" else "MICROSERVICES_JAR"
    supplied = os.environ.get(variable)
    if supplied:
        jar = Path(supplied)
        if not jar.is_absolute():
            jar = root / jar
    elif module == "microservices":
        # This assembly includes all bootstrap/transport sources, including chat.
        jar = root / "server/build/microservices/communication/libs/myscoutee-communication.jar"
    else:
        candidates = list((root / "server/projects/profile/build/libs").glob("*.jar"))
        if not candidates:
            raise ValueError("No backend JAR. Supply an existing Spring Boot JAR with BACKEND_JAR; no build is run.")
        jar = max(candidates, key=lambda item: item.stat().st_mtime)

    jar_time = jar.stat().st_mtime
    newer = next((source for source in sources(source_roots)
                  if source.stat().st_mtime > jar_time), None)
    if newer is not None:
        raise ValueError(f"Java source is newer than {jar}: {newer.relative_to(root)}. "
                         f"Refresh the existing artifact manually or provide a matching {variable}; no build is run.")
    with ZipFile(jar) as archive:
        entries = []
        for entry in archive.infolist():
            path = PurePosixPath(entry.filename)
            if path.is_relative_to("BOOT-INF/classes") and path.suffix == ".class":
                relative = Path("classes") / path.relative_to("BOOT-INF/classes")
            elif path.is_relative_to("BOOT-INF/lib") and path.suffix == ".jar":
                relative = Path("lib") / path.relative_to("BOOT-INF/lib")
            else:
                continue
            if ".." in relative.parts:
                raise ValueError(f"Unsafe JAR entry: {entry.filename}")
            entries.append((entry, relative))
        if not any(relative.parts[0] == "classes" for _, relative in entries):
            raise ValueError(f"Not a Spring Boot JAR with compiled classes: {jar}")
        if output.exists():
            shutil.rmtree(output)
        for entry, relative in entries:
            target = output / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(entry) as source, target.open("wb") as destination:
                shutil.copyfileobj(source, destination)
    if coverage:
        shutil.copyfile(coverage, output / "coverage.xml")
    print(f"{module} bytecode and dependencies: {jar}", flush=True)
    print("Use a JAR built from the source revision being analyzed; no compilation or tests were run.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, BadZipFile, ElementTree.ParseError) as error:
        raise SystemExit(str(error))
