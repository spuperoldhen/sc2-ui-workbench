"""Apply a reviewed SC2 UI Workbench revision ZIP to a component test map."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shutil
import tempfile
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

MAP_LIMIT = 256 * 1024 * 1024
SCRIPT_PATTERN = r"scripts/sc2workbench(?!preview\.galaxy$)[a-z0-9_]*\.galaxy"
HASH_PATTERN = r"[0-9a-f]{64}"
RESOURCE_PATTERNS = {
    "texture": r"assets/textures/.+\.(?:dds|tga|png|webp|jpe?g|gif|bmp|avif)",
    "fontFile": r"(?:localizeddata|assets)/fonts/.+\.(?:ttf|otf|woff2?|ttc)",
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
    if path.is_absolute() or not path.parts or str(path) != value or any(part == ".." or part.endswith((" ", ".")) or PureWindowsPath(part).is_reserved() for part in path.parts):
        raise ValueError(f"路径超出测试副本或格式无效：{value!r}")
    return path


def map_path(target, value):
    path = target.joinpath(*relative_path(value).parts)
    for part in (path, *path.parents):
        if part == target:
            break
        if (part.is_symlink() or
                (part.exists() and getattr(part.lstat(), "st_file_attributes", 0) & 0x400)):
            raise ValueError(f"测试副本内含重定向路径：{part}")
    if not path.resolve().is_relative_to(target):
        raise ValueError(f"路径超出测试副本：{value}")
    return path


def integration_scripts(manifest):
    integration = manifest["integration"]
    script = integration["script"]
    scripts = integration.get("scripts", [script])
    if (not isinstance(scripts, list) or not scripts or scripts[0] != script or
            any(not re.fullmatch(SCRIPT_PATTERN, str(path).lower()) for path in scripts) or
            len({path.casefold() for path in scripts}) != len(scripts) or
            integration.get("include") != "\n".join(f'include "{path[:-7]}"' for path in scripts)):
        raise ValueError("清单中的 Galaxy 模块路径或引用无效。")
    return set(scripts)


def allow_map_path(kind, path, scripts, triggers):
    if kind == "galaxyScript":
        return path in scripts
    if kind == "triggerData":
        return bool(triggers and path.casefold() == triggers["path"].casefold())
    pattern = RESOURCE_PATTERNS.get(kind)
    return bool(pattern and re.fullmatch(r"(?:(?:base|[a-z]{4})\.sc2(?:data|assets)/)?" + pattern, path.lower()))


def bundle_manifest(archive):
    entries = archive.infolist()
    if len({entry.filename.casefold() for entry in entries}) != len(entries):
        raise ValueError("回导包含重复路径。")
    if sum(entry.file_size for entry in entries) > MAP_LIMIT:
        raise ValueError("回导包超过 256 MB。")
    info = archive.getinfo("ui_manifest.json")
    if info.file_size > 16 * 1024 * 1024:
        raise ValueError("回导清单过大。")
    manifest = json.loads(archive.read(info))
    if (manifest.get("format"), manifest.get("version")) != ("sc2-ui-workbench-handoff", 1) or manifest.get("preview"):
        raise ValueError("回导包格式不受支持。")
    return manifest


def verify_target(target, manifest, approval=None):
    review = manifest["collaboration"] if approval is not None else manifest["revision"]
    if not manifest.get("diagnostics", {}).get("ready"):
        raise ValueError("回导包未通过导出检查。")
    if approval is not None:
        if review.get("id") != approval or review.get("kind") not in {"existingIntegration", "agentIntegration"}:
            raise ValueError("回导包与当前定稿不匹配。")
        if Path(review["target"]).resolve(strict=True) != target:
            raise ValueError("回导包与当前定稿的目标路径不匹配。")
    elif target.name.casefold() != review.get("targetFolder", "").casefold():
        raise ValueError("目录名和增量包记录的测试副本不一致。")
    return review


def check_fingerprint(target, row, filename):
    path = relative_path(row["path"])
    checksum = row["sha256"]
    if path.name.casefold() != filename or not re.fullmatch(HASH_PATTERN, checksum):
        raise ValueError(f"目标 {path} 的校验记录无效。")
    if digest_file(map_path(target, str(path))) != checksum:
        raise ValueError(f"目标 {path} 已改变，请重新扫描和导出。")


def check_trigger_xml(data):
    # Check the bytes that will reach the editor, including their encoding and declaration.
    if re.search(rb"<!DOCTYPE|<!ENTITY", data.replace(b"\x00", b""), re.I):
        raise ValueError("Triggers 含有不支持的 XML 声明。")
    try:
        if ElementTree.fromstring(data).tag != "TriggerData":
            raise ValueError("Triggers 缺少 TriggerData 根节点。")
    except ElementTree.ParseError as error:
        raise ValueError(f"回导包的 Triggers 无法解析：{error}") from error


def plan_revision(archive, target, manifest, review, stage_assets=False):
    if not stage_assets and (review.get("kind") == "agentIntegration" or
            (review.get("kind") is None and not review.get("reuseInitialization"))):
        raise ValueError("此定稿需要 Agent 接入触发器。可用 --stage-assets 先部署已审核文件。")
    if not stage_assets and any(row.get("status") in {"新增", "冲突", "复核"} for row in review.get("guiBindings", [])):
        raise ValueError("清单仍有待处理的 GUI 绑定。")
    scripts = integration_scripts(manifest)
    triggers = review.get("targetTriggers")
    fingerprints = {}
    used = set()
    for row in review["files"]:
        name = row["path"]
        dest = map_path(target, name)
        status = row["status"]
        before, after = row["beforeSha256"], row["afterSha256"]
        if (name.casefold() in used or status not in {"新增", "更新", "相同"} or
                (before is None) != (status == "新增") or not re.fullmatch(HASH_PATTERN, after) or
                (before is not None and not re.fullmatch(HASH_PATTERN, before)) or
                (before == after) != (status == "相同")):
            raise ValueError(f"增量记录无效或仍有冲突：{name}")
        if digest_file(dest) != before:
            raise ValueError(f"目标文件已改变，请重新扫描和导出：{name}")
        used.add(name.casefold())
        fingerprints[name] = row
    result = []
    packed = set()
    for item in manifest["files"]:
        name = item["mapPath"]
        row = fingerprints.get(name)
        if (not row or name in packed or not allow_map_path(item["type"], name, scripts, triggers) or
                item["archivePath"] != "地图文件/" + name):
            raise ValueError(f"文件路径、类型或校验记录不一致：{name}")
        packed.add(name)
        entry = archive.getinfo(item["archivePath"])
        data = archive.read(entry)
        if digest_bytes(data) != row["afterSha256"]:
            raise ValueError(f"增量内容的哈希不一致：{entry.filename}")
        if item["type"] == "triggerData":
            check_trigger_xml(data)
        if row["status"] != "相同":
            result.append((map_path(target, name), entry, row["beforeSha256"], row["afterSha256"]))
    if any(name not in packed for name, row in fingerprints.items() if row["status"] != "相同"):
        raise ValueError("回导包缺少变更文件。")
    return result


def apply_revision(archive, changes, target, verify_context):
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
        verify_context()
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
                    restored = backup / "rollback.tmp"
                    shutil.copy2(backup / "原文件" / dest.relative_to(target), restored)
                    os.replace(restored, dest)
            except OSError as error:
                rollback_errors.append(str(error))
        if rollback_errors:
            raise RuntimeError(f"部分文件回滚失败。备份在 {backup}。{'；'.join(rollback_errors)}")
        raise
    return backup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zip_file", type=Path)
    parser.add_argument("test_map", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="核对后写入已完成接入的测试副本")
    mode.add_argument("--stage-assets", action="store_true", help="部署已审核资源、UI 模块和 GUI 变量文件，另行接入玩法触发器")
    parser.add_argument("--review-id", help="校验协作定稿编号、目标路径和文件哈希")
    args = parser.parse_args()
    try:
        supplied = args.test_map
        if supplied.is_symlink() or getattr(supplied.lstat(), "st_file_attributes", 0) & 0x400:
            raise ValueError("测试副本不能是链接或重解析点。")
        target = supplied.resolve(strict=True)
        writing = args.apply or args.stage_assets
        if not target.is_dir() or ((writing or not args.review_id) and
                not re.search(r"-UI-Test(?:\.SC2Map|\.SC2Components)?$", target.name, re.IGNORECASE)):
            raise ValueError("增量写入请选择以 -UI-Test 命名的组件地图副本。")
        if not any(path.name.lower() == "componentlist.sc2components" and path.is_file() for path in target.iterdir()):
            raise ValueError("测试副本缺少 ComponentList.SC2Components。")
        if args.stage_assets and not args.review_id:
            raise ValueError("--stage-assets 需要用户确认的 --review-id。")
        with ZipFile(args.zip_file) as archive:
            manifest = bundle_manifest(archive)
            review = verify_target(target, manifest, args.review_id)

            def verify_context():
                check_fingerprint(target, review["targetMapScript"], "mapscript.galaxy")
                if review.get("targetTriggers"):
                    check_fingerprint(target, review["targetTriggers"], "triggers")

            verify_context()
            changes = plan_revision(archive, target, manifest, review,
                                    stage_assets=args.stage_assets or (not writing and bool(args.review_id)))
            if args.review_id and not writing:
                print(review["kind"])
                return
            for dest, _, before, _ in changes:
                print(("更新" if before else "新增"), dest.relative_to(target))
            if writing and changes:
                print("已更新测试副本，备份位于", apply_revision(archive, changes, target, verify_context))
            elif not changes:
                print("测试副本无需更新。")
            else:
                print("核对通过。加上 --apply 可写入测试副本。")
    except (OSError, KeyError, ValueError, TypeError, RuntimeError, BadZipFile) as error:
        raise SystemExit(str(error)) from None


if __name__ == "__main__":
    main()
