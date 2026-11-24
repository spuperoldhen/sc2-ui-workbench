"""Serve the local workbench and stage visual previews into one test map."""

import argparse
from functools import partial
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import tempfile
import threading
from threading import Lock
from types import SimpleNamespace
import time
import urllib.error
import urllib.request
from urllib.parse import parse_qs, urlparse
import webbrowser
from zipfile import BadZipFile
import sys

LOG_PATH = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "SC2WorkbenchPreview" / "launcher.log"
if sys.stdout is None or sys.stderr is None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _log_stream = open(LOG_PATH, "a", encoding="utf-8", buffering=1)
        if sys.stdout is None:
            sys.stdout = _log_stream
        if sys.stderr is None:
            sys.stderr = _log_stream
    except OSError:
        pass

from launch_test_game import editor_window, request_test_document

def resource_root():
    if getattr(sys, "frozen", False):
        local = Path(sys.executable).resolve().parent
        if (local / "index.html").is_file():
            return local
        return Path(getattr(sys, "_MEIPASS", local))
    return Path(__file__).resolve().parents[1]


WORKBENCH = resource_root()
SCRIPTS = WORKBENCH / "skills" / "sc2-galaxy-bridge" / "scripts"
if not SCRIPTS.is_dir() and getattr(sys, "frozen", False):
    SCRIPTS = Path(sys._MEIPASS) / "skills" / "sc2-galaxy-bridge" / "scripts"
sys.path.insert(0, str(SCRIPTS))
stage_module = importlib.import_module("stage")
LIMIT = stage_module.LIMIT
destination = stage_module.destination
stage = stage_module.stage

STATE = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "SC2WorkbenchPreview"
MAP_CONFIG = STATE / "map.txt"

OFFLINE = b'<meta name="sc2-preview-bridge" content="offline">'
PREVIEW_INCLUDE = 'include "Scripts/SC2WorkbenchPreview"'
PREVIEW_CALL = "SC2WorkbenchPreview_Init();"
VERSION = "2026-11-24.2"


def map_script(root):
    scripts = [destination(root, name) for name in ("MapScript.galaxy", "Base.SC2Data/MapScript.galaxy")]
    available = [path for path in scripts if path.is_file()]
    if len(available) != 1:
        raise ValueError("请在银河编辑器保存测试副本，确认已生成唯一的 MapScript.galaxy。")
    return available[0]


def read_map_script(path):
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16"), "utf-16"
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig"), "utf-8-sig"
    return raw.decode("utf-8"), "utf-8"


def ensure_wiring(root):
    """Add the preview include and InitMap call when the test copy lacks them."""
    path = map_script(root)
    script, encoding = read_map_script(path)
    changed = False
    if PREVIEW_INCLUDE not in script:
        lines = script.splitlines()
        index = max((i for i, line in enumerate(lines[:200]) if line.strip().startswith('include "')),
                    default=-1)
        if index < 0:
            raise ValueError("MapScript.galaxy 缺少 include 区。")
        lines.insert(index + 1, PREVIEW_INCLUDE)
        script = "\n".join(lines) + "\n"
        changed = True
    if PREVIEW_CALL not in script:
        start = script.find("void InitMap")
        if start < 0:
            raise ValueError("MapScript.galaxy 缺少 InitMap。")
        brace = script.find("{", start)
        depth = 0
        close = -1
        for position in range(brace, len(script)):
            if script[position] == "{":
                depth += 1
            elif script[position] == "}":
                depth -= 1
                if depth == 0:
                    close = position
                    break
        if close < 0:
            raise ValueError("InitMap 花括号不匹配。")
        script = script[:close].rstrip("\n") + "\n    " + PREVIEW_CALL + "\n" + script[close:]
        changed = True
    if changed:
        path.write_bytes(script.encode(encoding))
    return changed


def default_launcher():
    info = Path.home() / "Documents" / "StarCraft II" / "ExecuteInfo.txt"
    if not info.is_file():
        raise ValueError("找不到 Documents\\StarCraft II\\ExecuteInfo.txt，请用 --launcher 指定 SC2Switcher_x64.exe。")
    match = re.search(r"(?im)^\s*executable\s*=\s*(.+?)\s*$", info.read_text(encoding="utf-8", errors="replace"))
    if not match:
        raise ValueError("ExecuteInfo.txt 没有 executable 行，请用 --launcher 指定 SC2Switcher_x64.exe。")
    exe = Path(match.group(1))
    candidate = exe.parents[2] / "Support64" / "SC2Switcher_x64.exe"
    if not candidate.is_file():
        raise ValueError(f"找不到 {candidate}，请用 --launcher 指定 SC2Switcher_x64.exe。")
    return candidate


def sc2_pids():
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", "(Get-Process SC2_x64 -ErrorAction SilentlyContinue).Id"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    return {int(value) for value in result.stdout.split() if value.isdigit()}


def launch_direct(root, launcher, previous):
    if previous and previous in sc2_pids():
        subprocess.run(["taskkill", "/PID", str(previous), "/F"], capture_output=True)
    before = sc2_pids()
    subprocess.Popen([str(launcher), "-run", str(root), "-displaymode", "0"], cwd=str(launcher.parent))
    deadline = time.time() + 15
    while time.time() < deadline:
        time.sleep(0.5)
        new = sc2_pids() - before
        if new:
            return min(new)
    return None


def test_map(path):
    path = Path(path)
    try:
        info = path.lstat()
    except OSError as error:
        raise ValueError("测试副本目录不存在。") from error
    if path.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
        raise ValueError("测试副本不能是链接或重解析点。")
    root = path.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("请选择目录形态的地图副本，而不是打包地图文件。")
    if (root.suffix.lower() not in {".sc2map", ".sc2components"}
            or not root.stem.lower().endswith("-ui-test")
            or not destination(root, "ComponentList.SC2Components").is_file()):
        raise ValueError("请选择名称以 -UI-Test 结尾并包含 ComponentList.SC2Components 的地图副本。")
    return root


def save_map(path):
    MAP_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    temp = MAP_CONFIG.with_name(MAP_CONFIG.name + ".tmp")
    temp.write_text(str(path), encoding="utf-8")
    os.replace(temp, MAP_CONFIG)


def service_state(port):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/preview/version", timeout=1) as response:
            return True, json.loads(response.read()).get("version")
    except urllib.error.HTTPError:
        return True, None
    except (OSError, ValueError):
        return False, None


def show_message(kind, message):
    try:
        import tkinter as tk
        from tkinter import messagebox
        window = tk.Tk()
        window.withdraw()
        getattr(messagebox, kind)("SC2 UI 工作台", message)
        window.destroy()
    except Exception:
        print(message, file=sys.stderr)


def watch(session, server):
    while True:
        time.sleep(2)
        with session.lock:
            clients = session.clients
            seen = session.seen_client
            last = session.last_client
        now = time.time()
        if seen and clients == 0 and now - last > 8:
            server.shutdown()
            return
        if not seen and now - last > 120:
            server.shutdown()
            return


def verify_initialization(root):
    script, _ = read_map_script(map_script(root))
    # Strip comments without changing quoted Galaxy strings or include paths.
    script = re.sub(r'"(?:[^"\\]|\\.)*"|//[^\n]*|/\*[\s\S]*?\*/',
                    lambda match: match[0] if match[0].startswith('"') else "\n", script)
    includes = re.findall(r'^\s*include\s+"Scripts[/\\]SC2WorkbenchPreview"\s*;?\s*$', script, re.M)
    calls = re.findall(r"^\s*SC2WorkbenchPreview_Init\(\s*\)\s*;", script, re.M)
    if len(includes) != 1 or len(calls) != 1:
        raise ValueError("请在测试副本配置唯一的预览 include 和初始化调用，保存后重试。")


class PreviewError(Exception):
    def __init__(self, code, message, status=409, report_path=None, conflicts=None):
        super().__init__(message)
        self.code = code
        self.status = status
        self.report_path = report_path
        self.conflicts = conflicts or []


class PreviewSession:
    def __init__(self, state, replace_font_styles, launch="direct", launcher=None, initial_map=None):
        self.state_root = state
        self.replace_font_styles = replace_font_styles
        self.launch = launch
        self.launcher = launcher or (default_launcher() if launch == "direct" else None)
        if self.launcher is not None:
            self.launcher = self.launcher.resolve(strict=True)
        self.lock = Lock()
        self.token = secrets.token_urlsafe(32)
        self.targets = {}
        self.root = None
        self.state = None
        self.game_pid = None
        self.revision = secrets.token_urlsafe(18)
        self.clients = 0
        self.seen_client = False
        self.last_client = time.time()
        if initial_map is not None:
            self._activate(initial_map)

    @staticmethod
    def _key(path):
        return os.path.normcase(str(path))

    def _target_state(self, root):
        key = sha256(os.fsencode(self._key(root))).hexdigest()[:20]
        target_state = self.state_root / key
        if not target_state.exists():
            legacy = self.state_root / sha256(os.fsencode(str(root))).hexdigest()[:20]
            if legacy.is_dir():
                legacy.rename(target_state)
            else:
                target_state.mkdir(parents=True)
        return target_state

    def _activate(self, path):
        path = test_map(path)
        key = self._key(path)
        entry = self.targets.get(key)
        if entry is None:
            entry = {"state": self._target_state(path), "game_pid": None}
            self.targets[key] = entry
        if self.root is not None:
            self.targets[self._key(self.root)]["game_pid"] = self.game_pid
        self.root = path
        self.state = entry["state"]
        self.game_pid = entry.get("game_pid")
        return path

    def current_info(self):
        return {"map": str(self.root) if self.root else "",
                "capabilities": {"selectTarget": True},
                "targetRevision": self.revision}

    def select_target(self, map_value, expected_revision):
        with self.lock:
            if expected_revision != self.revision:
                raise PreviewError("PREVIEW_TARGET_CHANGED", "测试副本已切换，请重新打开预览并核对。")
            if not isinstance(map_value, str) or not map_value.strip():
                raise ValueError("请填写测试副本的完整目录路径。")
            path = self._activate(map_value.strip())
            self.revision = secrets.token_urlsafe(18)
            save_map(path)
            return {"map": str(self.root), "targetRevision": self.revision,
                    "message": "已切换测试副本。"}

    def client_open(self):
        with self.lock:
            self.clients += 1
            self.seen_client = True
            self.last_client = time.time()

    def client_close(self):
        with self.lock:
            self.clients = max(0, self.clients - 1)
            self.last_client = time.time()

    def page_html(self):
        source = (WORKBENCH / "index.html").read_bytes()
        if source.count(OFFLINE) != 1:
            raise ValueError("工作台页面缺少预览入口。")
        token = self.token.encode("ascii")
        marker = OFFLINE.replace(b'offline', token)
        if b"/api/preview/events" in source:
            return source.replace(OFFLINE, marker, 1)
        keepalive = b"""<script>
(function(){
  var meta=document.querySelector('meta[name="sc2-preview-bridge"]');
  var token=meta?meta.content:"";
  if(location.hostname==="127.0.0.1"&&token&&token!=="offline"){
    window.sc2PreviewEvents=new EventSource("/api/preview/events?token="+encodeURIComponent(token));
  }
})();
</script>"""
        return source.replace(OFFLINE, marker + keepalive, 1)

    def _conflicts(self, report):
        try:
            data = json.loads(report.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        kinds = {}
        try:
            manifest = json.loads((report.parent / "ui_manifest.json").read_text(encoding="utf-8"))
            kinds = {item.get("mapPath"): item.get("type", "file")
                     for item in manifest.get("files", []) if isinstance(item, dict)}
        except (OSError, ValueError):
            pass
        rows = []
        for row in data.get("files", []):
            if row.get("action") == "conflict" and isinstance(row.get("path"), str):
                item = {"path": row["path"], "kind": kinds.get(row["path"], "file"),
                        "reason": "与已有文件或上次写入记录不一致"}
                for field in ("sha256", "existingSha256", "previousSha256"):
                    if isinstance(row.get(field), str):
                        item[field] = row[field]
                rows.append(item)
        return rows

    def stage_preview(self, source, size, run, revision):
        with self.lock:
            if revision != self.revision:
                raise PreviewError("PREVIEW_TARGET_CHANGED", "测试副本已切换，请重新打开预览并核对。")
            if self.root is None or self.state is None:
                raise PreviewError("PREVIEW_TARGET_CHANGED", "尚未选择测试副本，请先在实机预览中设置目标。")
            window = None
            if run and self.launch == "editor":
                window = editor_window(self.root.stem)
                verify_initialization(self.root)
            prior = sorted(self.state.glob("run-*/staged/stage-report.json"), key=lambda p: p.stat().st_mtime_ns)
            previous = None
            for report_path in reversed(prior):
                try:
                    receipt = json.loads(report_path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if receipt.get("state") == "staged":
                    previous = report_path
                    break
            work = Path(tempfile.mkdtemp(prefix="run-", dir=self.state))
            bundle = work / "preview.zip"
            try:
                with bundle.open("wb") as output:
                    while size:
                        data = source.read(min(size, 1024 * 1024))
                        if not data:
                            raise ValueError("预览包传输中断。")
                        output.write(data)
                        size -= len(data)
                try:
                    stage(SimpleNamespace(bundle=bundle, map_copy=self.root, evidence=work/"staged",
                                          previous=previous, apply=True, preview=True,
                                          replace_font_styles=self.replace_font_styles))
                except ValueError as error:
                    report = work / "staged" / "stage-report.json"
                    conflicts = self._conflicts(report)
                    if conflicts:
                        raise PreviewError("MAP_FILE_CONFLICT",
                                           "现有地图文件需要合并。没有地图文件被修改。",
                                           report_path=str(report), conflicts=conflicts) from error
                    raise
            finally:
                bundle.unlink(missing_ok=True)
            if run:
                try:
                    if self.launch == "direct":
                        ensure_wiring(self.root)
                    verify_initialization(self.root)
                    if self.launch == "editor":
                        request_test_document(self.root.stem, window)
                        message = "已写入并发出「测试文档」命令。请在银河编辑器查看编译结果，并在游戏中确认画面。"
                    else:
                        self.game_pid = launch_direct(self.root, self.launcher, self.game_pid)
                        message = "已写入并启动游戏。若上一局仍在运行，启动器已尝试先结束它；切到游戏窗口确认画面。"
                except (OSError, ValueError) as error:
                    raise ValueError(f"已写入测试副本。启动失败：{error}") from error
                self.targets[self._key(self.root)]["game_pid"] = self.game_pid
                return message
            return "已写入测试副本。点击「写入并测试」可直启游戏。"


class PreviewHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(self, *args, session, **kwargs):
        self.session = session
        super().__init__(*args, **kwargs)

    def send_content(self, status, content_type, payload):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(payload)

    def json_response(self, status, value):
        self.send_content(status, "application/json; charset=utf-8", json.dumps(value, ensure_ascii=False).encode())

    def local_host(self):
        return self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"

    def do_GET(self):
        if not self.local_host():
            self.json_response(403, {"message":"请通过「启动SC2 UI 工作台」提供的地址访问。"})
        elif self.path.startswith("/api/preview/events"):
            token = parse_qs(urlparse(self.path).query).get("token", [""])[0]
            if not secrets.compare_digest(token.encode("utf-8"), self.session.token.encode("ascii")):
                self.json_response(403, {"message":"请通过「启动SC2 UI 工作台」打开页面后重试。"})
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            self.session.client_open()
            try:
                while True:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    time.sleep(5)
            except (OSError, ValueError, ConnectionError):
                pass
            finally:
                self.session.client_close()
        elif self.path == "/":
            try:
                html = self.session.page_html()
            except (OSError, ValueError) as error:
                self.send_content(500, "text/plain; charset=utf-8", str(error).encode())
            else:
                self.send_content(200, "text/html; charset=utf-8", html)
        elif self.path == "/api/preview":
            self.json_response(200, self.session.current_info())
        elif self.path == "/api/preview/version":
            self.json_response(200, {"version": VERSION})
        else:
            self.json_response(404, {"message":"找不到此入口。"})

    def do_POST(self):
        origin = f"http://127.0.0.1:{self.server.server_port}"
        if not self.local_host() or self.headers.get("Origin") != origin:
            self.json_response(403, {"message":"请通过「启动SC2 UI 工作台」打开页面后重试。"})
            return
        token = self.headers.get("X-SC2-Preview-Token", "")
        if not secrets.compare_digest(token.encode("utf-8"), self.session.token.encode("ascii")):
            self.json_response(403, {"message":"请通过「启动SC2 UI 工作台」打开页面后重试。"})
            return
        if self.path == "/api/preview/target":
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if self.headers.get_content_type() != "application/json" or not 0 < size <= 16 * 1024:
                    raise ValueError("请提交 JSON 格式的目标请求。")
                body = json.loads(self.rfile.read(size).decode("utf-8"))
                if not isinstance(body, dict) or set(body) - {"map", "targetRevision"}:
                    raise ValueError("目标请求只能包含 map 和 targetRevision。")
                result = self.session.select_target(body.get("map"), body.get("targetRevision"))
            except PreviewError as error:
                self.preview_error(error)
                return
            except (OSError, ValueError) as error:
                self.json_response(409, {"message": str(error)})
                return
            self.json_response(200, result)
            return
        if self.path not in {"/api/preview/stage", "/api/preview/run"}:
            self.json_response(404, {"message":"找不到此入口。"})
            return
        revision = self.headers.get("X-SC2-Preview-Target-Revision", "")
        size = 0
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if self.headers.get_content_type() != "application/zip" or not 0 < size <= LIMIT + 2*1024**2:
                raise ValueError("请提交工作台生成的 ZIP 预览包。")
            self.connection.settimeout(30)
            message = self.session.stage_preview(self.rfile, size, self.path.endswith("/run"), revision)
        except PreviewError as error:
            if error.code == "PREVIEW_TARGET_CHANGED":
                self.drain_request(size)
            self.preview_error(error)
        except (BadZipFile, OSError, ValueError, KeyError, TypeError, AttributeError, RuntimeError) as error:
            self.json_response(409, {"message": str(error)})
        else:
            self.json_response(200, {"message":message})

    def drain_request(self, size):
        """Finish reading a rejected upload so the 409 response survives HTTP/1.1."""
        remaining = size
        try:
            while remaining > 0:
                chunk = self.rfile.read(min(remaining, 64 * 1024))
                if not chunk:
                    break
                remaining -= len(chunk)
        except OSError:
            pass

    def preview_error(self, error):
        payload = {"code": error.code, "message": str(error)}
        if error.report_path:
            payload["reportPath"] = error.report_path
        if error.conflicts:
            payload["conflicts"] = error.conflicts
        self.json_response(error.status, payload)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map-copy", type=Path, help="Component map copy ending in -UI-Test")
    parser.add_argument("--port", type=int, default=8765, help="Local workbench port")
    parser.add_argument("--no-browser", action="store_true", help="Print URL instead of opening a browser")
    parser.add_argument("--launch", choices=("direct", "editor"), default="direct",
                        help="direct starts SC2 with SC2Switcher; editor sends Test Document to an open editor")
    parser.add_argument("--launcher", type=Path, help="SC2Switcher_x64.exe path for direct launch")
    parser.add_argument("--replace-font-styles", action="store_true",
                        help="Allow the first replacement of the test copy FontStyles.SC2Style and keep a backup")
    args = parser.parse_args()
    state = STATE
    state.mkdir(parents=True, exist_ok=True)
    existing = f"http://127.0.0.1:{args.port}/"
    alive, running_version = service_state(args.port)
    if alive:
        if running_version == VERSION:
            if not args.no_browser:
                webbrowser.open(existing)
            return
        show_message("showinfo",
                     "检测到另一个工作台服务仍在运行。请关闭工作台标签页，约 10 秒后它会自动退出，再重新双击启动。\n"
                     "如果 10 秒后仍未退出，请在任务管理器结束「启动SC2 UI 工作台」。")
        return
    try:
        initial = None
        if args.map_copy:
            initial = test_map(args.map_copy)
            save_map(initial)
        else:
            saved = None
            try:
                saved = MAP_CONFIG.read_text(encoding="utf-8").strip()
            except OSError:
                pass
            if saved:
                try:
                    initial = test_map(Path(saved))
                except (OSError, ValueError):
                    initial = None
        session = PreviewSession(state, args.replace_font_styles,
                                 args.launch, args.launcher, initial_map=initial)
        with ThreadingHTTPServer(("127.0.0.1", args.port), partial(PreviewHandler,session=session)) as server:
            url = f"http://127.0.0.1:{server.server_port}/"
            target = str(session.root) if session.root else "未选择（请在网页实机预览中设置）"
            print(f"{url}\n测试副本：{target}", flush=True)
            threading.Thread(target=watch, args=(session, server), daemon=True).start()
            if not args.no_browser:
                webbrowser.open(url)
            server.serve_forever()
    except (OSError, ValueError) as error:
        if getattr(sys, "frozen", False):
            show_message("showerror", str(error))
        else:
            parser.exit(1, f"{error}\n")
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
