"""File-backed persistence for the local SC2 UI Workbench.

The browser's File System Access handles are per browser profile. This store
keeps project files, annotations, favorites and authorized asset-folder paths
beside the workbench executable so any browser served by the helper sees the
same data.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import threading
import time

MAX_PROJECT_BYTES = 24 * 1024 * 1024
MAX_SETTINGS_BYTES = 16 * 1024 * 1024
MAX_ASSET_FILES = 20000
PROJECT_SUFFIX = ".sc2ui.json"
ASSET_EXTENSIONS = {".dds", ".tga", ".png", ".webp", ".jpg", ".jpeg",
                    ".gif", ".bmp", ".avif", ".json"}
ICON_EXTENSIONS = {".js", ".json", ".webp"}


class StoreError(ValueError):
    pass


def _safe_project_name(value):
    if not isinstance(value, str):
        raise StoreError("项目名称无效。")
    name = value.strip()
    if not name or len(name) > 120 or re.search(r'[\\/:*?"<>|\x00-\x1f]', name):
        raise StoreError("项目名称包含无效字符。")
    if name in {".", ".."} or name.endswith(".") or name.endswith(" "):
        raise StoreError("项目名称无效。")
    if not name.lower().endswith(PROJECT_SUFFIX):
        name += PROJECT_SUFFIX
    return name


def _digest(value):
    return hashlib.sha256(os.fsencode(value)).hexdigest()[:20]


class LocalStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.projects = self.root / "projects"
        self.settings_file = self.root / "workbench.json"
        self.lock = threading.RLock()
        self.projects.mkdir(parents=True, exist_ok=True)
        self._settings = self._load_settings()

    def _default_settings(self):
        return {
            "version": 1,
            "annotations": {},
            "favorites": [],
            "preferFavorites": True,
            "projectFlags": {},
            "assetFolders": {"materials": "", "icons": ""},
        }

    def _load_settings(self):
        try:
            data = json.loads(self.settings_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return self._default_settings()
        if not isinstance(data, dict):
            return self._default_settings()
        result = self._default_settings()
        result.update(data)
        if not isinstance(result.get("annotations"), dict):
            result["annotations"] = {}
        if not isinstance(result.get("favorites"), list):
            result["favorites"] = []
        if not isinstance(result.get("projectFlags"), dict):
            result["projectFlags"] = {}
        if not isinstance(result.get("assetFolders"), dict):
            result["assetFolders"] = {"materials": "", "icons": ""}
        result["preferFavorites"] = result.get("preferFavorites") is not False
        return result

    def _write_json(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        payload = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
        temporary.write_bytes(payload)
        os.replace(temporary, path)

    def _save_settings(self):
        self._write_json(self.settings_file, self._settings)

    def settings(self):
        with self.lock:
            return json.loads(json.dumps(self._settings, ensure_ascii=False))

    def update_settings(self, patch):
        if not isinstance(patch, dict):
            raise StoreError("设置格式无效。")
        allowed = {"annotations", "favorites", "preferFavorites", "projectFlags", "assetFolders"}
        if set(patch) - allowed:
            raise StoreError("设置包含未知字段。")
        with self.lock:
            if "annotations" in patch:
                value = patch["annotations"]
                if not isinstance(value, dict) or len(value) > 20000:
                    raise StoreError("标注格式无效。")
                self._settings["annotations"] = value
            if "favorites" in patch:
                value = patch["favorites"]
                if not isinstance(value, list) or len(value) > 5000 or any(
                        not isinstance(item, str) or len(item) > 512 for item in value):
                    raise StoreError("收藏格式无效。")
                self._settings["favorites"] = value
            if "preferFavorites" in patch:
                self._settings["preferFavorites"] = patch["preferFavorites"] is not False
            if "projectFlags" in patch:
                value = patch["projectFlags"]
                if not isinstance(value, dict) or len(value) > 5000:
                    raise StoreError("项目收藏标记格式无效。")
                self._settings["projectFlags"] = value
            if "assetFolders" in patch:
                value = patch["assetFolders"]
                if not isinstance(value, dict) or set(value) - {"materials", "icons"}:
                    raise StoreError("素材目录格式无效。")
                for key, path in value.items():
                    if path == "":
                        self._settings["assetFolders"][key] = ""
                        continue
                    if not isinstance(path, str):
                        raise StoreError("素材目录格式无效。")
                    resolved = Path(path).expanduser().resolve(strict=True)
                    if not resolved.is_dir():
                        raise StoreError("素材目录不存在。")
                    self._settings["assetFolders"][key] = str(resolved)
            self._save_settings()
            return self.settings()

    def _project_path(self, name):
        return self.projects / _safe_project_name(name)

    def list_projects(self):
        rows = []
        with self.lock:
            for path in self.projects.glob("*" + PROJECT_SUFFIX):
                if not path.is_file():
                    continue
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    stat = path.stat()
                except (OSError, ValueError):
                    continue
                dialogs = data.get("dialogs")
                rows.append({
                    "name": path.name,
                    "title": data.get("projectName") or path.name.removesuffix(PROJECT_SUFFIX),
                    "count": len(dialogs) if isinstance(dialogs, list) else 0,
                    "size": stat.st_size,
                    "modified": int(stat.st_mtime * 1000),
                })
        rows.sort(key=lambda row: (-row["modified"], row["name"].casefold()))
        return rows

    def read_project(self, name):
        path = self._project_path(name)
        if not path.is_file():
            raise StoreError("项目不存在。")
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise StoreError("项目文件无法读取。") from error

    def save_project(self, name, data, create=False):
        if not isinstance(data, dict) or not isinstance(data.get("dialogs"), list):
            raise StoreError("项目数据格式无效。")
        payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
        if len(payload) > MAX_PROJECT_BYTES:
            raise StoreError("项目文件大于 24 MB。")
        path = self._project_path(name)
        with self.lock:
            if create and path.exists():
                raise StoreError("本地项目库已有同名项目，请换一个名称。")
            temporary = path.with_name(path.name + ".tmp")
            temporary.write_bytes(payload)
            os.replace(temporary, path)
            return {"name": path.name, "size": len(payload),
                    "modified": int(path.stat().st_mtime * 1000)}

    def rename_project(self, old_name, new_name):
        old_path = self._project_path(old_name)
        new_path = self._project_path(new_name)
        if not old_path.is_file():
            raise StoreError("项目不存在。")
        if old_path == new_path:
            return {"name": new_path.name}
        if new_path.exists():
            raise StoreError("同名项目已存在。")
        with self.lock:
            old_path.rename(new_path)
        return {"name": new_path.name}

    def delete_project(self, name):
        path = self._project_path(name)
        with self.lock:
            if path.is_file():
                path.unlink()
            else:
                raise StoreError("项目不存在。")
        return {"deleted": path.name}

    def _asset_root(self, source):
        if source not in {"materials", "icons"}:
            raise StoreError("素材来源无效。")
        raw = self._settings["assetFolders"].get(source) or ""
        if not raw:
            raise StoreError("尚未选择素材目录。")
        root = Path(raw).resolve(strict=True)
        if not root.is_dir():
            raise StoreError("素材目录不存在。")
        return root

    def asset_tree(self, source):
        root = self._asset_root(source)
        rows = []
        extensions = ICON_EXTENSIONS if source == "icons" else ASSET_EXTENSIONS
        with self.lock:
            for path in root.rglob("*"):
                if len(rows) >= MAX_ASSET_FILES:
                    break
                if not path.is_file() or path.suffix.lower() not in extensions:
                    continue
                if path.is_symlink():
                    continue
                try:
                    stat = path.stat()
                    relative = path.relative_to(root).as_posix()
                except (OSError, ValueError):
                    continue
                rows.append({"path": relative, "size": stat.st_size,
                             "modified": int(stat.st_mtime * 1000)})
        library_id = hashlib.sha256(os.fsencode(str(root).casefold())).hexdigest()[:20]
        return {"source": source, "name": root.name, "path": str(root),
                "libraryId": library_id, "files": rows}

    def asset_file(self, source, relative):
        root = self._asset_root(source)
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise StoreError("素材路径无效。")
        path = (root / candidate).resolve(strict=True)
        try:
            path.relative_to(root)
        except ValueError as error:
            raise StoreError("素材路径超出目录。") from error
        if not path.is_file() or path.is_symlink():
            raise StoreError("素材文件不存在。")
        return path

    def pick_folder(self, source):
        if source not in {"materials", "icons"}:
            raise StoreError("素材来源无效。")
        try:
            import tkinter as tk
            from tkinter import filedialog
        except ImportError as error:
            raise StoreError("当前环境没有 tkinter，无法打开目录选择器。") from error
        window = tk.Tk()
        window.withdraw()
        window.attributes("-topmost", True)
        try:
            path = filedialog.askdirectory(title="选择素材目录", mustexist=True)
        finally:
            window.destroy()
        if not path:
            return {"path": "", "cancelled": True}
        resolved = str(Path(path).resolve(strict=True))
        self.update_settings({"assetFolders": {source: resolved}})
        return {"path": resolved, "cancelled": False}
