"""Apply a reviewed SC2 UI Workbench revision ZIP to a component test map."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
from zipfile import ZipFile

MAP_LIMIT = 256 * 1024 * 1024
SCRIPT = "scripts/sc2workbenchui.galaxy"
RESOURCE_PATTERNS = {
    "texture": r"assets/textures/.+\.(?:dds|tga|png|webp|jpe?g|gif|bmp|avif)",
    "fontFile": r"localizeddata/fonts/.+\.(?:ttf|otf|woff2?|ttc)",
    "fontStyles": r"ui/fontstyles\.sc2style",
    "layoutFile": r"ui/layout/.+\.sc2layout",
    "localizedTextFile": r"localizeddata/(?:gamestrings|triggerstrings|objectstrings)\.txt",
}


def digest_bytes(data):
    return hashlib.sha256(data).hexdigest()


def digest_file(path):
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative_path(value):
    if not isinstance(value, str) or re.search(r'[\\:\x00-\x1f<>|"*?]', value):
        raise ValueError(f"路径格式无效：{value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or str(path) != value or ".." in path.parts:
        raise ValueError(f"路径超出测试副本或格式无效：{value!r}")
    return path


def map_path(target, value):
    path = target.joinpath(*relative_path(value).parts)
    for part in (path, *path.parents):
        if part == target:
            break
        if part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction()):
            raise ValueError(f"测试副本内含重定向路径：{part}")
    if not path.resolve().is_relative_to(target):
        raise ValueError(f"路径超出测试副本：{value}")
    return path


def allow_map_path(kind, path):
    path = path.lower()
    if kind == "galaxyScript":
        return path == SCRIPT
    pattern = RESOURCE_PATTERNS.get(kind)
    return bool(pattern and re.fullmatch(r"(?:(?:base|[a-z]{4})\.sc2(?:data|assets)/)?" + pattern, path))


def plan_revision(archive, target):
    entries = archive.infolist()
    if len({entry.filename for entry in entries}) != len(entries):
        raise ValueError("增量包存在重复的文件名。")
    manifest_entry = archive.getinfo("ui_manifest.json")
    if manifest_entry.file_size > 4 * 1024 * 1024:
        raise ValueError("清单超过 4 MB。")
    manifest = json.loads(archive.read(manifest_entry))
    revision = manifest.get("revision", {})
    if (manifest.get("format"), manifest.get("version")) != ("sc2-ui-workbench-handoff", 1):
        raise ValueError("回导包格式不受支持。")
    if not manifest.get("diagnostics", {}).get("ready") or not revision.get("reuseInitialization"):
        raise ValueError("该副本需要先完成或复核 GUI 初始化接入。请查看包内回导说明。")
    if target.name.casefold() != revision.get("targetFolder", "").casefold():
        raise ValueError("目录名和增量包记录的测试副本不一致。")
    map_script = revision.get("targetMapScript", {})
    path = relative_path(map_script.get("path"))
    map_hash = map_script.get("sha256", "")
    if path.name.casefold() != "mapscript.galaxy" or not isinstance(map_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", map_hash):
        raise ValueError("清单缺少原 MapScript.galaxy 的校验记录。")
    if digest_file(map_path(target, str(path))) != map_hash:
        raise ValueError("MapScript.galaxy 已修改，请在工作台重新核对差异。")
    if any(row.get("status") in {"新增", "冲突"} for row in revision.get("guiBindings", [])):
        raise ValueError("清单仍有待新增或冲突的 GUI 绑定。")
    changes = {row["path"]: row for row in revision.get("files", []) if row["status"] in {"新增", "更新"}}
    if any(row.get("status") == "冲突" for row in revision.get("files", [])):
        raise ValueError("增量包仍有文件冲突。")
    if len(changes) != len(manifest.get("files", [])):
        raise ValueError("文件清单和增量记录不一致。")
    result = []
    used = set()
    total = 0
    for file in manifest["files"]:
        name = file["mapPath"]
        row = changes.get(name)
        raw_path = relative_path(name)
        if (not row or name.casefold() in used or not allow_map_path(file["type"], name) or
                file["archivePath"] != "地图文件/" + str(raw_path)):
            raise ValueError(f"文件路径、类型或增量记录不一致：{name}")
        used.add(name.casefold())
        entry = archive.getinfo(file["archivePath"])
        total += entry.file_size
        if total > MAP_LIMIT:
            raise ValueError("增量文件超过 256 MB。")
        dest = map_path(target, name)
        before = row.get("beforeSha256")
        after = row.get("afterSha256")
        if (row["status"] == "新增") != (before is None) or not isinstance(after, str) or not re.fullmatch(r"[0-9a-f]{64}", after):
            raise ValueError(f"增量状态或内容哈希无效：{name}")
        if digest_file(dest) != before:
            raise ValueError(f"{name} 已改变，请重新导出增量包。")
        result.append((dest, entry, before, after))
    return result


def apply_revision(archive, changes, target):
    backup = Path(tempfile.mkdtemp(prefix=target.name + "-ui-backup-", dir=target.parent))
    applied = []
    try:
        for index, (dest, entry, before, after) in enumerate(changes):
            data = archive.read(entry)
            if digest_bytes(data) != after:
                raise ValueError(f"增量内容的哈希不一致：{entry.filename}")
            (backup / f"{index}.new").write_bytes(data)
            if before is not None:
                original = backup / "原文件" / dest.relative_to(target)
                original.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(dest, original)
                if digest_file(original) != before:
                    raise ValueError(f"备份时发现文件已改变：{dest}")
        for dest, _, before, _ in changes:
            if digest_file(dest) != before:
                raise ValueError(f"写入前发现文件已改变：{dest}")
        for index, (dest, _, before, _) in enumerate(changes):
            if digest_file(dest) != before:
                raise ValueError(f"写入前发现文件已改变：{dest}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.replace(backup / f"{index}.new", dest)
            applied.append((dest, before))
    except Exception:
        rollback_errors = []
        for dest, before in reversed(applied):
            try:
                if before is None:
                    dest.unlink()
                else:
                    shutil.copy2(backup / "原文件" / dest.relative_to(target), dest)
            except OSError as error:
                rollback_errors.append(str(error))
        if rollback_errors:
            raise RuntimeError(f"部分文件回滚失败。备份在 {backup}。{'；'.join(rollback_errors)}")
        raise
    return backup


def verify_agent_package(archive, target, approval):
    names = archive.namelist()
    if len(names) != len(set(names)):
        raise ValueError("回导包含重复路径。")
    info = archive.getinfo("ui_manifest.json")
    if info.file_size > 16 * 1024 * 1024:
        raise ValueError("回导清单过大。")
    manifest = json.loads(archive.read(info))
    review = manifest.get("collaboration", {})
    if (manifest.get("format"), manifest.get("version")) != ("sc2-ui-workbench-handoff", 1):
        raise ValueError("回导包格式不受支持。")
    if review.get("id") != approval or not manifest.get("diagnostics", {}).get("ready"):
        raise ValueError("回导包与当前定稿不匹配。")
    if Path(review["target"]).resolve(strict=True) != target:
        raise ValueError("回导包与当前定稿的目标路径不匹配。")
    script = review["targetMapScript"]
    if Path(script["path"]).name.casefold() != "mapscript.galaxy" or digest_file(map_path(target, script["path"])) != script["sha256"]:
        raise ValueError("目标 MapScript.galaxy 已改变，请重新读取目标地图和定稿。")
    triggers = review.get("targetTriggers")
    if triggers and digest_file(map_path(target, triggers["path"])) != triggers["sha256"]:
        raise ValueError("目标 Triggers 已改变，请重新读取目标地图和定稿。")
    fingerprints = {row["path"]: row for row in review["files"]}
    for row in review["files"]:
        if row["status"] == "冲突" or digest_file(map_path(target, row["path"])) != row["beforeSha256"]:
            raise ValueError(f"目标文件已改变，请重新读取目标地图和定稿：{row['path']}")
    for item in manifest["files"]:
        path = item["mapPath"]
        name = "地图文件/" + path
        if item["archivePath"] != name or path not in fingerprints:
            raise ValueError(f"回导包路径与定稿不符：{path}")
        if archive.getinfo(name).file_size > MAP_LIMIT or digest_bytes(archive.read(name)) != fingerprints[path]["afterSha256"]:
            raise ValueError(f"回导包内容与定稿不符：{path}")
    return review["kind"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zip_file", type=Path)
    parser.add_argument("test_map", type=Path)
    parser.add_argument("--apply", action="store_true", help="核对后实际写入测试副本并保留备份")
    parser.add_argument("--review-id", help="校验协作定稿编号、目标路径和文件哈希")
    args = parser.parse_args()
    target = args.test_map.resolve(strict=True)
    if not target.is_dir() or ((args.apply or not args.review_id) and
            not re.search(r"-UI-Test(?:\.SC2Map|\.SC2Components)?$", target.name, re.IGNORECASE)):
        raise SystemExit("增量写入请选择以 -UI-Test 命名的组件地图副本。")
    if not any(path.name.lower() == "componentlist.sc2components" and path.is_file() for path in target.iterdir()):
        raise SystemExit("测试副本缺少 ComponentList.SC2Components。")
    try:
        with ZipFile(args.zip_file) as archive:
            if args.review_id:
                kind = verify_agent_package(archive, target, args.review_id)
                if not args.apply:
                    print(kind)
                    return
                if kind != "existingIntegration":
                    raise ValueError("此定稿需要 Agent 接入触发器，无法直接增量写入。")
            changes = plan_revision(archive, target)
            for dest, entry, before, after in changes:
                if digest_bytes(archive.read(entry)) != after:
                    raise ValueError(f"增量内容的哈希不一致：{entry.filename}")
                print(("更新" if before else "新增"), dest.relative_to(target))
            if args.apply and changes:
                print("已更新测试副本，备份位于", apply_revision(archive, changes, target))
            elif not changes:
                print("测试副本无需更新。")
            else:
                print("核对通过。加上 --apply 可写入测试副本。")
    except (OSError, KeyError, ValueError, TypeError, RuntimeError) as error:
        raise SystemExit(str(error)) from None


if __name__ == "__main__":
    main()
