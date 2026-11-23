"""Run a project-approved editor test command and record its new compiler output."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cwd", type=Path, required=True)
    parser.add_argument("--map-copy", type=Path, required=True, help="Map already open in the editor")
    parser.add_argument("--evidence", type=Path, required=True, help="New directory")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("launcher", nargs=argparse.REMAINDER)
    options = parser.parse_args()
    command = options.launcher
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("Specify the project-approved launcher after --")
    target = options.map_copy.resolve(strict=True)
    options.evidence.mkdir()
    started = datetime.now(timezone.utc).isoformat()
    output = options.evidence / "launcher-output.log"
    error = None
    status = None
    with output.open("wb") as log:
        try:
            result = subprocess.run(command, cwd=options.cwd, capture_output=False,
                                    stdout=log, stderr=subprocess.STDOUT, timeout=options.timeout)
            status = result.returncode
        except subprocess.TimeoutExpired:
            error = "Launcher timed out"
        except OSError as exc:
            error = str(exc)
    raw = output.read_text(encoding="utf-8", errors="replace")
    counters = [int(count) for count in re.findall(r"(?im)\bcompile_errors\s*=\s*(\d+)\b", raw)]
    if any(counters):
        state = "errors"
    elif counters and status == 0:
        state = "passed"
    else:
        state = "unverified"
    report = {
        "map": str(target), "started": started, "state": state,
        "launcherExitCode": status, "compileErrors": counters, "launcherError": error,
        "source": "launcher-output.log",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    (options.evidence / "compile-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"passed": 0, "errors": 1, "unverified": 2}[state]


if __name__ == "__main__":
    sys.exit(main())
