#!/usr/bin/env python3
"""Wait for report processing, independently of the project's quality gate."""

import json
import os
from pathlib import Path
import sys
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def main():
    module = sys.argv[1]
    if module not in {"backend", "frontend", "components", "microservices", "runtime"}:
        raise ValueError("Unknown analysis module")
    # Compose resolves dotenv quoting and environment overrides. Never print this input.
    services = json.load(sys.stdin)["services"]
    token = services["scanner"]["environment"].get("SONAR_TOKEN", "")
    port = services["sonarqube"]["ports"][0]["published"]
    root = Path(os.environ["SONAR_STATE_ROOT"])
    report = dict(line.split("=", 1) for line in
                  (root / "build/analysis/scanner" / module / "report-task.txt")
                  .read_text().splitlines() if "=" in line)
    url = f"http://127.0.0.1:{port}/api/ce/task?" + urlencode({"id": report["ceTaskId"]})
    headers = {"Authorization": "Bearer " + token} if token else {}
    deadline = time.monotonic() + 300
    print(f"Waiting for {module} report processing...", flush=True)
    while time.monotonic() < deadline:
        with urlopen(Request(url, headers=headers), timeout=15) as response:
            task = json.load(response)["task"]
        if task["status"] == "SUCCESS":
            print(f"{module}: server processing SUCCESS; analysis {task['analysisId']}", flush=True)
            if task.get("warningCount", 0):
                print(f"{module}: {task['warningCount']} analysis warning(s); see scanner log and SonarQube background tasks.", flush=True)
            return
        if task["status"] in {"FAILED", "CANCELED"}:
            raise ValueError(f"{module}: server processing {task['status']}: "
                             + (task.get("errorMessage") or "See SonarQube background tasks."))
        time.sleep(2)
    raise TimeoutError(f"{module}: report processing did not finish within 300 seconds")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError) as error:
        raise SystemExit(str(error))
