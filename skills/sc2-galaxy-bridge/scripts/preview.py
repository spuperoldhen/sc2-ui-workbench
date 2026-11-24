"""Deploy a visual-preview handoff, wire it into a map copy, and launch it in game.

The handoff is the ZIP produced by the Workbench preview export. The script and
include names come from ui_manifest.json, so both SC2WorkbenchUI and
SC2WorkbenchPreview handoffs are handled the same way.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stage

MARKER = "// SC2 UI Workbench preview"
STYLE = re.compile(rb'<Style\s+name="([^"]+)"')


def ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def style_names(data):
    return {name.decode("utf-8", "ignore") for name in STYLE.findall(data)}


def deploy(bundle, root, evidence):
    manifest, init, rows = stage.load_bundle(bundle, root, preview=True)
    integration = manifest["integration"]
    if manifest.get("variables") and integration.get("triggerImplementation") != "visualPreview":
        raise SystemExit("Handoff needs GUI variables; use stage.py and the editor integration flow.")
    evidence.mkdir(parents=True, exist_ok=False)
    actions = []
    for item in manifest["files"]:
        relative = item["mapPath"]
        target, data = rows[relative]
        old = target.read_bytes() if target.is_file() else None
        if old == data:
            actions.append({"path": relative, "action": "unchanged"})
            continue
        if old is not None:
            if item["type"] == "fontStyles" and not style_names(old) <= style_names(data):
                raise SystemExit(f"Font styles need a merged copy: {relative}")
            backup = evidence / "backup" / relative
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_bytes(old)
            actions.append({"path": relative, "action": "replace", "backup": str(backup)})
        else:
            actions.append({"path": relative, "action": "create"})
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return manifest, init, actions


def insert_init(text, init):
    first = next((line.strip() for line in init.splitlines() if line.strip()), "")
    if first and first in text:
        return text, False
    start = text.find("void InitMap")
    if start < 0:
        raise SystemExit("MapScript.galaxy has no InitMap function")
    brace = text.find("{", start)
    depth = 0
    close = -1
    for index in range(brace, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                close = index
                break
    if close < 0:
        raise SystemExit("MapScript.galaxy InitMap is not balanced")
    block = "\n".join("    " + line if line.strip() else line for line in init.strip().splitlines())
    head = text[:close].rstrip("\n")
    return head + "\n" + MARKER + "\n" + block + "\n" + text[close:], True


def wire(root, include, init):
    script = root / "MapScript.galaxy"
    text = script.read_text(encoding="utf-8")
    wired = []
    if include not in text:
        lines = text.splitlines()
        index = max((i for i, line in enumerate(lines[:200]) if line.strip().startswith('include "')), default=-1)
        if index < 0:
            raise SystemExit("MapScript.galaxy has no include block")
        lines.insert(index + 1, include)
        text = "\n".join(lines) + "\n"
        wired.append(include)
    text, inserted = insert_init(text, init)
    if inserted:
        wired.append(init.strip().splitlines()[0])
    script.write_text(text, encoding="utf-8", newline="")
    return wired


def default_launcher():
    info = Path.home() / "Documents" / "StarCraft II" / "ExecuteInfo.txt"
    if not info.is_file():
        raise SystemExit("Pass --launcher; ExecuteInfo.txt is missing")
    match = re.search(r"(?im)^\s*executable\s*=\s*(.+?)\s*$", info.read_text(encoding="utf-8", errors="replace"))
    if not match:
        raise SystemExit("Pass --launcher; ExecuteInfo.txt has no executable line")
    exe = Path(match.group(1))
    candidate = exe.parents[2] / "Support64" / "SC2Switcher_x64.exe"
    if not candidate.is_file():
        raise SystemExit(f"Pass --launcher; {candidate} is missing")
    return candidate


def run_ps(source, evidence, name):
    script = evidence / name
    script.write_text(source, encoding="utf-8-sig")
    result = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or result.stdout.strip() or f"{name} failed")
    return result.stdout.strip()


def launch(launcher, root, evidence, previous_pid):
    if previous_pid:
        run_ps(
            "Get-Process -Id " + str(previous_pid) +
            " -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue\n"
            "'closed'\n", evidence, "stop.ps1")
    source = "\n".join([
        "$exe = " + ps_quote(launcher),
        "$map = " + ps_quote(root),
        "$before = @(Get-Process SC2_x64 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)",
        "Start-Process -FilePath $exe -WorkingDirectory " + ps_quote(launcher.parent) +
        " -ArgumentList ('-run \"{0}\" -displaymode 0' -f $map)",
        "$gamePid = 0",
        "for ($i = 0; $i -lt 24; $i++) {",
        "    Start-Sleep -Milliseconds 500",
        "    $new = @(Get-Process SC2_x64 -ErrorAction SilentlyContinue | Where-Object { $before -notcontains $_.Id })",
        "    if ($new.Count -gt 0) { $gamePid = $new[0].Id; break }",
        "}",
        "$gamePid",
    ]) + "\n"
    return run_ps(source, evidence, "launch.ps1").splitlines()[-1]


def screenshot(path, evidence):
    source = "\n".join([
        'Add-Type @"',
        "using System.Runtime.InteropServices;",
        "public class DpiAwareness { [DllImport(\"user32.dll\")] public static extern bool SetProcessDPIAware(); }",
        '"@',
        "[DpiAwareness]::SetProcessDPIAware() | Out-Null",
        "Add-Type -AssemblyName System.Windows.Forms",
        "Add-Type -AssemblyName System.Drawing",
        "$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds",
        "$bmp = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height",
        "$g = [System.Drawing.Graphics]::FromImage($bmp)",
        "$g.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)",
        "$bmp.Save(" + ps_quote(path) + ", [System.Drawing.Imaging.ImageFormat]::Png)",
        "$g.Dispose(); $bmp.Dispose()",
        "'ok'",
    ]) + "\n"
    run_ps(source, evidence, "shot.ps1")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--map-copy", type=Path, required=True)
    parser.add_argument("--launcher", type=Path)
    parser.add_argument("--shot", type=Path)
    parser.add_argument("--evidence", type=Path, help="New directory for the report and backups")
    parser.add_argument("--wait", type=int, default=15)
    parser.add_argument("--pid-file", type=Path)
    parser.add_argument("--deploy-only", action="store_true")
    parser.add_argument("--no-restart", action="store_true")
    options = parser.parse_args()

    root = options.map_copy.resolve(strict=True)
    if not (root / "ComponentList.SC2Components").is_file():
        parser.error("--map-copy must contain ComponentList.SC2Components")
    evidence = (options.evidence or Path(os.environ.get("TEMP", ".")) / "sc2-ui-preview" /
                time.strftime("run-%Y%m%d-%H%M%S")).resolve()
    manifest, init, actions = deploy(options.bundle, root, evidence)
    integration = manifest["integration"]
    wired = wire(root, integration["include"], init)
    report = {
        "map": str(root), "script": integration["script"], "include": integration["include"],
        "files": actions, "wired": wired, "evidence": str(evidence),
    }
    if not options.deploy_only:
        launcher = (options.launcher or default_launcher()).resolve(strict=True)
        pid_file = (options.pid_file or Path(os.environ.get("TEMP", ".")) / "sc2-ui-preview" /
                    (re.sub(r"[^A-Za-z0-9_.-]+", "_", root.name) + ".pid")).resolve()
        previous = None
        if pid_file.is_file() and not options.no_restart:
            try:
                previous = int(pid_file.read_text(encoding="utf-8").strip())
            except ValueError:
                previous = None
        game_pid = launch(launcher, root, evidence, previous)
        if game_pid.isdigit():
            pid_file.parent.mkdir(parents=True, exist_ok=True)
            pid_file.write_text(game_pid, encoding="utf-8")
        time.sleep(max(0, options.wait))
        shot = (options.shot or Path(os.environ.get("TEMP", ".")) / "sc2-ui-preview" /
                time.strftime("shot-%Y%m%d-%H%M%S.png")).resolve()
        screenshot(shot, evidence)
        report.update({"launcher": str(launcher), "gamePid": game_pid, "shot": str(shot)})
    print(json.dumps(report, ensure_ascii=False, indent=2))
    (evidence / "preview-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
