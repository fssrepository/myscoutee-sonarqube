#!/usr/bin/env python3
"""Read the application-owned analysis configuration without opening credentials."""

import json
from pathlib import Path
import re
import sys

MODULES = ("backend", "frontend", "components", "microservices", "runtime")


def load_project(source):
    root = Path(source).resolve(strict=True)
    configuration = root / "config" / "sonarqube"
    settings = json.loads((configuration / "project.json").read_text())
    for key in ("id",):
        value = settings.get(key)
        if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", value):
            raise ValueError(f"Invalid project {key}")
    configured = settings.get("modules", {})
    if not isinstance(configured, dict) or not configured or not set(configured).issubset(MODULES):
        raise ValueError("Configure at least one known analysis module")
    for module in configured:
        path = settings["modules"][module]
        if not isinstance(path, str) or not path or "\n" in path or "\r" in path:
            raise ValueError(f"Invalid {module} base directory")
        relative = Path(path)
        if relative.is_absolute() or not (root / relative).resolve().is_relative_to(root):
            raise ValueError(f"The {module} base directory must stay inside the source repository")
        if not (configuration / f"{module}.properties").is_file():
            raise ValueError(f"Missing {module} analysis properties")
    bytecode = settings.get("bytecode", {})
    private = settings.get("privateDirectories", [])
    if not isinstance(private, list) or any(
            not isinstance(path, str) or not path or "\n" in path or "\r" in path
            or Path(path).is_absolute() or (root / path).resolve() == root
            or not (root / path).resolve().is_relative_to(root) for path in private):
        raise ValueError("Private directories must stay inside the source repository")
    if not isinstance(bytecode, dict) or any(
            key not in configured or key not in {"backend", "microservices"}
            or value != "gradle-output" for key, value in bytecode.items()):
        raise ValueError("Invalid bytecode preparation configuration")
    return root, settings


if __name__ == "__main__":
    try:
        _, settings = load_project(sys.argv[1])
        server = json.loads(Path(__file__).with_name("server.json").read_text())
        for key in ("id", "composeProject"):
            if not isinstance(server.get(key), str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", server[key]):
                raise ValueError(f"Invalid server {key}")
        if type(server.get("port")) is not int or not 1 <= server["port"] <= 65535:
            raise ValueError("Invalid server port")
        print(settings["id"], server["composeProject"], server["port"],
              *(settings["modules"].get(module, "") for module in MODULES), sep="\n")
        print(server["id"])
        for path in settings.get("privateDirectories", []):
            print(path)
    except (OSError, ValueError, KeyError, IndexError) as error:
        raise SystemExit(str(error)) from None
