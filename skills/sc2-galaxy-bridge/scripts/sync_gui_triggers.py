"""Plan or apply GUI Categories, Variables, Structures, and Member Variables to a SC2 map's Triggers, TriggerStrings.txt, and MapScript.galaxy."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import tempfile
import unicodedata
import xml.etree.ElementTree as ET


def strip_gv(name: str) -> str:
    return name[3:] if name.startswith("gv_") else name


def strip_gs(name: str) -> str:
    return name[3:] if name.startswith("gs_") else name


def strip_lv(name: str) -> str:
    return name[3:] if name.startswith("lv_") else name


# Mapping from GUI / Workbench types to SC2 Triggers <Type Value="..."/> and Galaxy type
TYPE_DEFS = {
    "int": {"triggers": "int", "galaxy": "int", "default_kind": "value", "default": "0"},
    "整数": {"triggers": "int", "galaxy": "int", "default_kind": "value", "default": "0"},
    "fixed": {"triggers": "fixed", "galaxy": "fixed", "default_kind": "value", "default": "0.0"},
    "实数": {"triggers": "fixed", "galaxy": "fixed", "default_kind": "value", "default": "0.0"},
    "bool": {"triggers": "bool", "galaxy": "bool", "default_kind": "value", "default": "false"},
    "布尔值": {"triggers": "bool", "galaxy": "bool", "default_kind": "value", "default": "false"},
    "string": {"triggers": "string", "galaxy": "string", "default_kind": "string", "default": ""},
    "字符串": {"triggers": "string", "galaxy": "string", "default_kind": "string", "default": ""},
    "text": {"triggers": "text", "galaxy": "text", "default_kind": "preset", "preset": "50BDC6EF", "galaxy_init": "null"},
    "文本": {"triggers": "text", "galaxy": "text", "default_kind": "preset", "preset": "50BDC6EF", "galaxy_init": "null"},
    "dialog": {"triggers": "dialog", "galaxy": "int", "default_kind": "preset", "preset": "B76A7F2A", "galaxy_init": "c_invalidDialogId"},
    "对话框": {"triggers": "dialog", "galaxy": "int", "default_kind": "preset", "preset": "B76A7F2A", "galaxy_init": "c_invalidDialogId"},
    "control": {"triggers": "control", "galaxy": "int", "default_kind": "preset", "preset": "FAC49C47", "galaxy_init": "c_invalidDialogControlId"},
    "dialogcontrol": {"triggers": "control", "galaxy": "int", "default_kind": "preset", "preset": "FAC49C47", "galaxy_init": "c_invalidDialogControlId"},
    "对话框项": {"triggers": "control", "galaxy": "int", "default_kind": "preset", "preset": "FAC49C47", "galaxy_init": "c_invalidDialogControlId"},
    "playergroup": {"triggers": "playergroup", "galaxy": "playergroup", "default_kind": "funccall", "func": "00000056", "galaxy_init": "PlayerGroupEmpty()"},
    "玩家组": {"triggers": "playergroup", "galaxy": "playergroup", "default_kind": "funccall", "func": "00000056", "galaxy_init": "PlayerGroupEmpty()"},
    "unit": {"triggers": "unit", "galaxy": "unit", "default_kind": "preset", "preset": "D6EA4D09", "galaxy_init": "null"},
    "单位": {"triggers": "unit", "galaxy": "unit", "default_kind": "preset", "preset": "D6EA4D09", "galaxy_init": "null"},
    "unitgroup": {"triggers": "unitgroup", "galaxy": "unitgroup", "default_kind": "funccall", "func": "00000104", "galaxy_init": "UnitGroupEmpty()"},
    "单位组": {"triggers": "unitgroup", "galaxy": "unitgroup", "default_kind": "funccall", "func": "00000104", "galaxy_init": "UnitGroupEmpty()"},
    "actor": {"triggers": "actor", "galaxy": "actor", "default_kind": "preset", "preset": "52D5A28A", "galaxy_init": "null"},
    "演算体": {"triggers": "actor", "galaxy": "actor", "default_kind": "preset", "preset": "52D5A28A", "galaxy_init": "null"},
    "point": {"triggers": "point", "galaxy": "point", "default_kind": "preset", "preset": "568CBBF1", "galaxy_init": "null"},
    "点": {"triggers": "point", "galaxy": "point", "default_kind": "preset", "preset": "568CBBF1", "galaxy_init": "null"},
    "region": {"triggers": "region", "galaxy": "region", "default_kind": "preset", "preset": "F5E3F3AD", "galaxy_init": "null"},
    "区域": {"triggers": "region", "galaxy": "region", "default_kind": "preset", "preset": "F5E3F3AD", "galaxy_init": "null"},
    "timer": {"triggers": "timer", "galaxy": "timer", "default_kind": "funccall", "func": "00000193", "galaxy_init": "TimerCreate()"},
    "计时器": {"triggers": "timer", "galaxy": "timer", "default_kind": "funccall", "func": "00000193", "galaxy_init": "TimerCreate()"},
    "sound": {"triggers": "sound", "galaxy": "sound", "default_kind": "preset", "preset": "7B90D057", "galaxy_init": "null"},
    "声音": {"triggers": "sound", "galaxy": "sound", "default_kind": "preset", "preset": "7B90D057", "galaxy_init": "null"},
    "color": {"triggers": "color", "galaxy": "color", "default_kind": "preset", "preset": "4A760179", "galaxy_init": "Color(0, 0, 0)"},
    "颜色": {"triggers": "color", "galaxy": "color", "default_kind": "preset", "preset": "4A760179", "galaxy_init": "Color(0, 0, 0)"},
    "bank": {"triggers": "bank", "galaxy": "bank", "default_kind": "preset", "preset": "BFF08621", "galaxy_init": "null"},
    "银行": {"triggers": "bank", "galaxy": "bank", "default_kind": "preset", "preset": "BFF08621", "galaxy_init": "null"},
    "trigger": {"triggers": "trigger", "galaxy": "trigger", "default_kind": "preset", "preset": "00000542", "galaxy_init": "null"},
    "触发器": {"triggers": "trigger", "galaxy": "trigger", "default_kind": "preset", "preset": "00000542", "galaxy_init": "null"},
    "gamelink": {"triggers": "gamelink", "galaxy": "string", "default_kind": "preset", "preset": "C9DCA6C0", "galaxy_init": None},
    "游戏链接": {"triggers": "gamelink", "galaxy": "string", "default_kind": "preset", "preset": "C9DCA6C0", "galaxy_init": None},
    "struct": {"triggers": "struct", "galaxy": None, "default_kind": "none"},
    "record": {"triggers": "struct", "galaxy": None, "default_kind": "none"},
    "结构体": {"triggers": "struct", "galaxy": None, "default_kind": "none"},
    "记录": {"triggers": "struct", "galaxy": None, "default_kind": "none"},
}


def resolve_type(raw_type: str) -> dict:
    if not raw_type:
        raise ValueError("Empty variable type")
    key = raw_type.strip()
    info = TYPE_DEFS.get(key) or TYPE_DEFS.get(key.lower())
    if not info:
        raise ValueError(f"Unsupported GUI type: {raw_type}")
    return dict(info)


def read_text_preserve(path: Path):
    raw = path.read_bytes()
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    crlf = b"\r\n" in raw
    text = raw.decode("utf-8-sig" if has_bom else "utf-8").replace("\r\n", "\n")
    return text, has_bom, crlf


def atomic_write_text(path: Path, text: str, has_bom: bool, crlf: bool):
    payload = (text.replace("\n", "\r\n") if crlf else text).encode("utf-8-sig" if has_bom else "utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
        try:
            tmp.write(payload)
            tmp.close()
            os.replace(tmp.name, path)
        finally:
            Path(tmp.name).unlink(missing_ok=True)


def xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def new_hex_id(used_ids: set[str]) -> str:
    while True:
        candidate = secrets.token_hex(4).upper()
        if candidate not in used_ids:
            used_ids.add(candidate)
            return candidate


def normalize_dimensions(entry: dict) -> list[int]:
    if "dimensions" in entry and entry["dimensions"] is not None:
        return [int(v) for v in entry["dimensions"]]
    if "maximumIndexes" in entry and entry["maximumIndexes"] is not None:
        return [int(v) for v in entry["maximumIndexes"]]
    if "arrayLengths" in entry and entry["arrayLengths"] is not None:
        return [max(0, int(v) - 1) for v in entry["arrayLengths"]]
    if "minimumArrayLengths" in entry and entry["minimumArrayLengths"] is not None:
        return [max(0, int(v) - 1) for v in entry["minimumArrayLengths"]]
    return []


def spec_from_manifest(manifest: dict, default_category: str | None = None) -> dict:
    variables = manifest.get("variables") or []
    cat_name = default_category or "SC2WorkbenchUI"
    structures: dict[str, dict] = {}
    top_vars: dict[str, dict] = {}

    def ensure_struct(struct_ident: str, display_name: str | None = None) -> dict:
        if struct_ident not in structures:
            structures[struct_ident] = {
                "identifier": struct_ident,
                "displayName": display_name or struct_ident,
                "category": cat_name,
                "members": [],
                "_member_map": {},
            }
        return structures[struct_ident]

    def merge_dims(existing: list[int], incoming: list[int], label: str) -> list[int]:
        if len(existing) != len(incoming):
            raise ValueError(f"Dimension count mismatch for {label}: {existing} vs {incoming}")
        return [max(a, b) for a, b in zip(existing, incoming)]

    for entry in variables:
        gui_type = entry["guiType"]
        max_indexes = normalize_dimensions(entry)
        storage = entry.get("storage")

        if storage == "structMember":
            parts = [strip_gv(strip_lv(p)) for p in entry["galaxyName"].split(".") if p]
            seg_dims = entry.get("segmentDimensions") or [0] * len(parts)
            if len(parts) < 2 or len(seg_dims) != len(parts):
                raise ValueError(f"Invalid structMember path/segmentDimensions: {entry}")
            dim_slices: list[list[int]] = []
            offset = 0
            for count in seg_dims:
                dim_slices.append(max_indexes[offset : offset + count])
                offset += count

            root_ident = parts[0]
            root_struct_ident = f"{root_ident}_Record"
            if root_ident in top_vars:
                if top_vars[root_ident]["type"] != "struct":
                    raise ValueError(f"Variable {root_ident} conflicts between scalar/array and struct")
                top_vars[root_ident]["dimensions"] = merge_dims(
                    top_vars[root_ident]["dimensions"], dim_slices[0], root_ident
                )
                root_struct_ident = top_vars[root_ident]["struct"]
            else:
                top_vars[root_ident] = {
                    "identifier": root_ident,
                    "displayName": root_ident,
                    "type": "struct",
                    "struct": root_struct_ident,
                    "dimensions": dim_slices[0],
                    "category": cat_name,
                }

            cur_struct_ident = root_struct_ident
            for idx in range(1, len(parts)):
                st = ensure_struct(cur_struct_ident)
                mem_ident = parts[idx]
                is_leaf = idx == len(parts) - 1
                mem_dims = dim_slices[idx]
                existing_mem = st["_member_map"].get(mem_ident)
                if is_leaf:
                    display = entry.get("displayName") or mem_ident
                    if existing_mem:
                        if existing_mem["type"] != gui_type:
                            raise ValueError(f"Struct member {cur_struct_ident}.{mem_ident} type mismatch")
                        existing_mem["dimensions"] = merge_dims(existing_mem["dimensions"], mem_dims, mem_ident)
                    else:
                        mem_obj = {
                            "identifier": mem_ident,
                            "displayName": display,
                            "type": gui_type,
                            "dimensions": mem_dims,
                        }
                        st["members"].append(mem_obj)
                        st["_member_map"][mem_ident] = mem_obj
                else:
                    child_struct = f"{cur_struct_ident}_{mem_ident}"
                    if existing_mem:
                        if existing_mem["type"] != "struct":
                            raise ValueError(f"Struct member {cur_struct_ident}.{mem_ident} must be struct")
                        existing_mem["dimensions"] = merge_dims(existing_mem["dimensions"], mem_dims, mem_ident)
                        child_struct = existing_mem["struct"]
                    else:
                        mem_obj = {
                            "identifier": mem_ident,
                            "displayName": mem_ident,
                            "type": "struct",
                            "struct": child_struct,
                            "dimensions": mem_dims,
                        }
                        st["members"].append(mem_obj)
                        st["_member_map"][mem_ident] = mem_obj
                    cur_struct_ident = child_struct
        else:
            ident = strip_gv(entry.get("guiIdentifier") or entry["galaxyName"])
            display = entry.get("displayName") or ident
            if ident in top_vars:
                if top_vars[ident]["type"] != gui_type:
                    raise ValueError(f"Variable {ident} type mismatch: {top_vars[ident]['type']} vs {gui_type}")
                top_vars[ident]["dimensions"] = merge_dims(top_vars[ident]["dimensions"], max_indexes, ident)
            else:
                top_vars[ident] = {
                    "identifier": ident,
                    "displayName": display,
                    "type": gui_type,
                    "dimensions": max_indexes,
                    "category": cat_name,
                }

    out_structs = []
    for st in structures.values():
        st.pop("_member_map", None)
        out_structs.append(st)

    return {
        "categories": [{"identifier": cat_name, "displayName": cat_name}],
        "structures": out_structs,
        "variables": list(top_vars.values()),
    }


def load_spec(spec_path: Path | None, manifest_path: Path | None, category_override: str | None) -> dict:
    if bool(spec_path) == bool(manifest_path):
        raise ValueError("Pass exactly one of --spec or --manifest")
    if manifest_path:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        return spec_from_manifest(manifest, category_override)

    raw = json.loads(spec_path.read_text(encoding="utf-8-sig"))
    categories = list(raw.get("categories") or [])
    if raw.get("category"):
        cat = raw["category"]
        if isinstance(cat, str):
            categories.append({"identifier": cat, "displayName": cat})
        else:
            categories.append(cat)
    if category_override:
        categories.append({"identifier": category_override, "displayName": category_override})
    return {
        "categories": categories,
        "structures": list(raw.get("structures") or []),
        "variables": list(raw.get("variables") or []),
    }


def build_default_param_elements(
    type_info: dict, used_ids: set[str], explicit_default: str | None = None
) -> tuple[str | None, list[str]]:
    """Return (param_id, [xml_snippets]) for a Variable's <Value> element."""
    dk = type_info["default_kind"]
    if dk == "none":
        return None, []

    param_id = new_hex_id(used_ids)
    tname = type_info["triggers"]

    if dk == "value":
        val = explicit_default if explicit_default is not None else type_info["default"]
        return param_id, [
            f'    <Element Type="Param" Id="{param_id}">\n'
            f'        <Value>{xml_escape(str(val))}</Value>\n'
            f'        <ValueType Type="{tname}"/>\n'
            f'    </Element>'
        ]
    if dk == "string":
        val = explicit_default if explicit_default is not None else ""
        val_line = f'        <Value>{xml_escape(str(val))}</Value>\n' if val != "" else ""
        return param_id, [
            f'    <Element Type="Param" Id="{param_id}">\n'
            f'{val_line}'
            f'        <ValueType Type="string"/>\n'
            f'    </Element>'
        ]
    if dk == "preset":
        if explicit_default is not None and tname == "gamelink":
            gt = type_info.get("game_type", "Sound")
            return param_id, [
                f'    <Element Type="Param" Id="{param_id}">\n'
                f'        <Value>{xml_escape(str(explicit_default))}</Value>\n'
                f'        <ValueType Type="gamelink"/>\n'
                f'        <ValueGameType Type="{xml_escape(gt)}"/>\n'
                f'    </Element>'
            ]
        preset_id = type_info["preset"]
        return param_id, [
            f'    <Element Type="Param" Id="{param_id}">\n'
            f'        <Preset Type="PresetValue" Library="Ntve" Id="{preset_id}"/>\n'
            f'    </Element>'
        ]
    if dk == "funccall":
        fc_id = new_hex_id(used_ids)
        func_id = type_info["func"]
        return param_id, [
            f'    <Element Type="Param" Id="{param_id}">\n'
            f'        <FunctionCall Type="FunctionCall" Id="{fc_id}"/>\n'
            f'    </Element>',
            f'    <Element Type="FunctionCall" Id="{fc_id}">\n'
            f'        <FunctionDef Type="FunctionDef" Library="Ntve" Id="{func_id}"/>\n'
            f'    </Element>',
        ]
    raise ValueError(f"Unknown default_kind: {dk}")


def build_variable_xml(
    var_id: str,
    identifier: str,
    type_info: dict,
    dims: list[int],
    used_ids: set[str],
    struct_id: str | None = None,
    game_type: str | None = None,
    explicit_default: str | None = None,
) -> list[str]:
    tname = type_info["triggers"]
    lines = [
        f'    <Element Type="Variable" Id="{var_id}">',
        f'        <Identifier>{xml_escape(identifier)}</Identifier>',
        f'        <VariableType>',
        f'            <Type Value="{tname}"/>',
    ]
    if tname == "struct":
        if not struct_id:
            raise ValueError(f"Variable {identifier} has type struct without struct_id")
        lines.append(f'            <TypeElement Type="Structure" Id="{struct_id}"/>')
    elif tname == "gamelink" and game_type:
        lines.append(f'            <GameType Value="{xml_escape(game_type)}"/>')
    for d, max_idx in enumerate(dims):
        lines.append(f'            <ArraySize Dim="{d}" Value="{int(max_idx)}"/>')
    lines.append("        </VariableType>")

    if explicit_default is not None and tname == "gamelink" and game_type:
        type_info = dict(type_info, game_type=game_type)
    param_id, extra = build_default_param_elements(type_info, used_ids, explicit_default)
    if param_id is not None:
        lines.append(f'        <Value Type="Param" Id="{param_id}"/>')
    lines.append("    </Element>")
    return ["\n".join(lines)] + extra


def parse_existing_triggers(triggers_text: str):
    root = ET.fromstring(triggers_text)
    used_ids = set(re.findall(r'Id="([0-9A-Fa-f]{6,12})"', triggers_text))
    used_ids = {i.upper() for i in used_ids}

    elems_by_id = {}
    categories_by_ident = {}
    all_category_ids = []
    structs_by_ident = {}
    top_vars_by_ident = {}
    member_ids = set()

    root_el = root.find("Root")
    root_item_ids = []
    if root_el is not None:
        for item in root_el.findall("Item"):
            if "Id" in item.attrib:
                root_item_ids.append((item.attrib.get("Type"), item.attrib["Id"]))

    for el in root.findall("Element"):
        eid = el.attrib.get("Id")
        etype = el.attrib.get("Type")
        if not eid:
            continue
        elems_by_id[eid] = el
        if etype == "Structure":
            ident = explicit_identifier(el)
            members = {}
            for m in el.findall("Variable"):
                mid = m.attrib.get("Id")
                if mid:
                    member_ids.add(mid)
                    members[mid] = m
            if ident:
                structs_by_ident[ident] = (eid, el, members)
        elif etype == "Category":
            all_category_ids.append(eid)
            ident = explicit_identifier(el)
            if ident:
                categories_by_ident[ident] = (eid, el)

    for eid, el in elems_by_id.items():
        if el.attrib.get("Type") == "Variable" and eid not in member_ids:
            ident = explicit_identifier(el)
            if ident:
                top_vars_by_ident[ident] = (eid, el)

    return root, used_ids, elems_by_id, all_category_ids, categories_by_ident, structs_by_ident, top_vars_by_ident


def parse_trigger_strings(text: str) -> dict[str, str]:
    entries = {}
    for line in text.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            entries[k.strip()] = v
    return entries


def global_variable_ids(root, elements):
    pending = [root.find("Root")]
    categories = set()
    variables = set()
    while pending:
        node = pending.pop()
        if node is None:
            continue
        for item in node.findall("Item"):
            identifier = item.get("Id")
            if item.get("Library") or identifier not in elements:
                continue
            if item.get("Type") == "Variable":
                variables.add(identifier)
            elif item.get("Type") == "Category" and identifier not in categories:
                categories.add(identifier)
                pending.append(elements[identifier])
    return variables


def automatic_identifiers(label):
    parts = []
    for char in unicodedata.normalize("NFC", label.strip()):
        if re.fullmatch(r"[A-Za-z0-9_]", char):
            parts.append(char)
        elif char.isspace() or unicodedata.category(char)[0] in "PSZC":
            parts.append("_")
        else:
            encoded = char.encode("utf-8").hex().upper()
            parts.append(encoded[0].lower() + encoded[1:] if not "".join(parts).strip("_") else encoded)
    stem = re.sub(r"_+", "_", "".join(parts)).strip("_")
    compact = "".join(char for char in label.strip() if char.isalnum() or char == "_")
    legacy = "".join(char if char.isascii() else char.encode("utf-8").hex() for char in compact)
    return {"_" + item if item[0].isdigit() else item for item in (stem, legacy) if item}


def explicit_identifier(element):
    node = element.find("Identifier")
    return (node.text or node.get("Value") or node.get("val") or "").strip() if node is not None else ""


def read_var_shape(el: ET.Element, elems_by_id: dict[str, ET.Element]):
    vt = el.find("VariableType")
    t_el = vt.find("Type") if vt is not None else None
    tname = t_el.attrib.get("Value", "") if t_el is not None else ""
    te = vt.find("TypeElement") if vt is not None else None
    struct_ident = None
    if te is not None and te.attrib.get("Type") == "Structure":
        sid = te.attrib.get("Id")
        if sid in elems_by_id:
            id_el = elems_by_id[sid].find("Identifier")
            if id_el is not None and id_el.text:
                struct_ident = id_el.text.strip()
    dims = {}
    if vt is not None:
        for arr in vt.findall("ArraySize"):
            d = int(arr.attrib.get("Dim", "0"))
            val = arr.attrib.get("Value")
            if val is not None and val.isdigit():
                dims[d] = int(val)
    dim_list = [dims[d] for d in sorted(dims)] if dims else []
    return tname, dim_list, struct_ident


def widen_variable_arrays_in_text(triggers_text: str, var_id: str, new_dims: list[int]) -> str:
    pattern = re.compile(
        rf'(<Element\s+Type="Variable"\s+Id="{re.escape(var_id)}">[\s\S]*?</VariableType>)'
    )
    m = pattern.search(triggers_text)
    if not m:
        raise ValueError(f"Could not locate Variable {var_id} to widen ArraySize")
    block = m.group(1)
    for d, val in enumerate(new_dims):
        arr_pat = re.compile(rf'(<ArraySize\s+Dim="{d}"\s+Value=")(\d+)("/>)')
        if arr_pat.search(block):
            block = arr_pat.sub(rf"\g<1>{val}\g<3>", block, count=1)
        else:
            block = block.replace(
                "        </VariableType>",
                f'            <ArraySize Dim="{d}" Value="{val}"/>\n        </VariableType>',
                1,
            )
    return triggers_text[: m.start(1)] + block + triggers_text[m.end(1) :]


def insert_items_into_root_or_category(triggers_text: str, category_id: str | None, items_xml: list[str]) -> str:
    if not items_xml:
        return triggers_text
    if category_id:
        pat = re.compile(rf'(<Element\s+Type="Category"\s+Id="{re.escape(category_id)}">[\s\S]*?)(\n\s*</Element>)')
        m = pat.search(triggers_text)
        if m:
            joined = "\n".join("        " + it for it in items_xml)
            return triggers_text[: m.end(1)] + "\n" + joined + triggers_text[m.end(1) :]
    joined = "\n".join("        " + it for it in items_xml)
    assert "    </Root>" in triggers_text, "Missing </Root> in Triggers"
    return triggers_text.replace("    </Root>", joined + "\n    </Root>", 1)


def append_members_to_structure(triggers_text: str, struct_id: str, member_refs: list[str]) -> str:
    if not member_refs:
        return triggers_text
    pat = re.compile(rf'(<Element\s+Type="Structure"\s+Id="{re.escape(struct_id)}">[\s\S]*?)(\n\s*</Element>)')
    m = pat.search(triggers_text)
    if not m:
        raise ValueError(f"Missing Structure {struct_id} in Triggers")
    joined = "\n".join(f'        <Variable Type="Variable" Id="{mid}"/>' for mid in member_refs)
    return triggers_text[: m.end(1)] + "\n" + joined + triggers_text[m.end(1) :]


def sync_map_script(
    ms_text: str,
    spec_structs: list[dict],
    spec_vars: list[dict],
) -> tuple[str, list[str]]:
    notes = []

    def galaxy_type_for(v: dict) -> str:
        tinfo = resolve_type(v["type"])
        if tinfo["triggers"] == "struct":
            return f"gs_{strip_gs(v['struct'])}"
        return tinfo["galaxy"]

    def galaxy_decl(prefix: str, ident: str, v: dict) -> str:
        gtype = galaxy_type_for(v)
        dims = normalize_dimensions(v)
        arr = "".join(f"[{d + 1}]" for d in dims)
        return f"{gtype}{arr} {prefix}{ident};"

    # 1. Struct declarations
    struct_blocks = []
    for st in spec_structs:
        sident = strip_gs(st["identifier"])
        gstruct = f"gs_{sident}"
        if re.search(rf"(?m)^\s*struct\s+{re.escape(gstruct)}\b", ms_text):
            continue
        body = []
        for m in st.get("members") or []:
            body.append("    " + galaxy_decl("lv_", strip_lv(m["identifier"]), m))
        struct_blocks.append(f"struct {gstruct} {{\n" + "\n".join(body) + "\n};")
        notes.append(f"MapScript: add struct {gstruct}")

    if struct_blocks:
        gv_banner = "// Global Variables"
        idx = ms_text.find(gv_banner)
        if idx < 0:
            raise ValueError("MapScript.galaxy missing '// Global Variables' banner")
        # Insert right before Global Variables banner
        insert_pos = ms_text.rfind("//--", 0, idx)
        if insert_pos < 0:
            insert_pos = idx
        block_txt = (
            "//--------------------------------------------------------------------------------------------------\n"
            "// Structures\n"
            "//--------------------------------------------------------------------------------------------------\n"
            + "\n".join(struct_blocks)
            + "\n\n"
        )
        ms_text = ms_text[:insert_pos] + block_txt + ms_text[insert_pos:]

    # 2. Global variable declarations (must be BEFORE include lines)
    var_decls = []
    init_lines = []
    for v in spec_vars:
        ident = strip_gv(v["identifier"])
        gvar = f"gv_{ident}"
        if re.search(rf"(?m)\b{re.escape(gvar)}\s*;", ms_text):
            continue
        var_decls.append(galaxy_decl("gv_", ident, v))
        notes.append(f"MapScript: add global {gvar}")
        tinfo = resolve_type(v["type"])
        dims = normalize_dimensions(v)
        ginit = v.get("defaultValue") or tinfo.get("galaxy_init")
        if ginit is not None and not dims and tinfo["triggers"] != "struct":
            init_lines.append(f"    {gvar} = {ginit};")

    if var_decls:
        m_init = re.search(r"(?m)^void InitGlobals\s*\(\)\s*\{", ms_text)
        if not m_init:
            raise ValueError("MapScript.galaxy missing InitGlobals()")
        pos = m_init.start()
        ms_text = ms_text[:pos] + "\n".join(var_decls) + "\n\n" + ms_text[pos:]

    if init_lines:
        m_init = re.search(r"(?m)^void InitGlobals\s*\(\)\s*\{", ms_text)
        brace = ms_text.find("{", m_init.start())
        depth = 0
        close = -1
        for i in range(brace, len(ms_text)):
            if ms_text[i] == "{":
                depth += 1
            elif ms_text[i] == "}":
                depth -= 1
                if depth == 0:
                    close = i
                    break
        if close < 0:
            raise ValueError("MapScript.galaxy InitGlobals() unbalanced")
        ms_text = ms_text[:close].rstrip("\n") + "\n" + "\n".join(init_lines) + "\n" + ms_text[close:]

    # Sanity check: custom include lines should not precede gv_ declarations
    gv_pos = ms_text.find("gv_")
    for m_inc in re.finditer(r'(?m)^include\s+"([^"]+)"', ms_text):
        if m_inc.group(1).startswith("TriggerLibs/"):
            continue
        if gv_pos >= 0 and m_inc.start() < gv_pos:
            notes.append(f'WARNING: include "{m_inc.group(1)}" appears before gv_ declarations in MapScript.galaxy')

    return ms_text, notes


def plan_and_apply(args):
    root = args.map_copy.resolve(strict=True)
    triggers_path = root / "Triggers"
    if not triggers_path.is_file():
        raise ValueError(f"Missing Triggers file in {root}")

    spec = load_spec(args.spec, args.manifest, args.category)
    triggers_text, t_bom, t_crlf = read_text_preserve(triggers_path)
    (
        trigger_root,
        used_ids,
        elems_by_id,
        all_category_ids,
        categories_by_ident,
        structs_by_ident,
        top_vars_by_ident,
    ) = parse_existing_triggers(triggers_text)

    # Locate TriggerStrings files
    tstr_paths = sorted(root.glob("*.SC2Data/LocalizedData/TriggerStrings.txt"))
    if not tstr_paths:
        default_ts = root / "zhCN.SC2Data/LocalizedData/TriggerStrings.txt"
        tstr_paths = [default_ts]

    primary_ts_entries = {}
    if tstr_paths[0].is_file():
        ts_txt, _, _ = read_text_preserve(tstr_paths[0])
        primary_ts_entries = parse_trigger_strings(ts_txt)

    # Map category displayName -> category_id as well
    categories_by_display = {}
    for cid in all_category_ids:
        dname = primary_ts_entries.get(f"Category/Name/{cid}")
        if dname:
            categories_by_display[dname] = cid

    globals_in_tree = global_variable_ids(trigger_root, elems_by_id)
    top_vars_by_ident = {}
    explicit_variables = set()
    for eid in globals_in_tree:
        element = elems_by_id[eid]
        ident = explicit_identifier(element)
        if not ident:
            continue
        if ident in top_vars_by_ident:
            raise ValueError(f"Duplicate GUI identifier gv_{ident}; verify the map variables.")
        explicit_variables.add(eid)
        top_vars_by_ident[ident] = (eid, element)
    implicit_by_identifier = {}
    for path in tstr_paths:
        if not path.is_file():
            continue
        labels = {key.casefold(): value for key, value in parse_trigger_strings(read_text_preserve(path)[0]).items()}
        for eid in globals_in_tree - explicit_variables:
            label = labels.get(f"variable/name/{eid.casefold()}", "")
            for alias in automatic_identifiers(label):
                implicit_by_identifier.setdefault(alias, set()).add(eid)
    ms_path = next((path for path in (root / "MapScript.galaxy", root / "Base.SC2Data/MapScript.galaxy")
                    if path.is_file()), root / "MapScript.galaxy")
    ms_text, ms_bom, ms_crlf = read_text_preserve(ms_path) if ms_path.is_file() else ("", False, False)
    compiled_variables = set(re.findall(r"(?m)^\s*\w+(?:\s*\[[^\]\r\n]+\])*\s+(gv_\w+)\s*[;=]", ms_text))

    report = {
        "map": str(root),
        "mode": "apply" if args.apply else "dry-run",
        "categories": [],
        "structures": [],
        "variables": [],
        "triggerStrings": [],
        "mapScript": [],
        "warnings": [],
    }

    new_root_items: list[str] = []
    new_cat_items: dict[str, list[str]] = {}
    new_elements: list[str] = []
    new_strings: dict[str, str] = {}

    def ensure_category(cat_ident: str, display_name: str | None = None) -> str:
        dname = display_name or cat_ident
        if cat_ident in categories_by_ident:
            cid = categories_by_ident[cat_ident][0]
            return cid
        if dname in categories_by_display:
            return categories_by_display[dname]
        cid = new_hex_id(used_ids)
        categories_by_ident[cat_ident] = (cid, None)
        categories_by_display[dname] = cid
        new_root_items.append(f'<Item Type="Category" Id="{cid}"/>')
        new_elements.append(f'    <Element Type="Category" Id="{cid}">\n    </Element>')
        new_strings[f"Category/Name/{cid}"] = dname
        report["categories"].append({"action": "create", "id": cid, "identifier": cat_ident, "displayName": dname})
        return cid

    for cat in spec["categories"]:
        ensure_category(cat.get("identifier") or cat["displayName"], cat.get("displayName"))

    # Resolve/Create Structures & Members
    struct_id_map: dict[str, str] = {ident: sid for ident, (sid, _, _) in structs_by_ident.items()}
    struct_append_members: dict[str, list[str]] = {}
    widened_vars: list[tuple[str, list[int]]] = []

    for st in spec["structures"]:
        sident = strip_gs(st["identifier"])
        dname = st.get("displayName") or sident
        cat_name = st.get("category")
        cid = ensure_category(cat_name, cat_name) if cat_name else None

        if sident in structs_by_ident:
            sid, sel, member_ref_map = structs_by_ident[sident]
            existing_members_by_ident = {}
            for mid in member_ref_map:
                mel = elems_by_id.get(mid)
                if mel is not None:
                    id_el = mel.find("Identifier")
                    m_ident = id_el.text.strip() if id_el is not None and id_el.text else ""
                    if m_ident:
                        existing_members_by_ident[m_ident] = (mid, mel)
            st_action = "reuse"
        else:
            sid = new_hex_id(used_ids)
            struct_id_map[sident] = sid
            existing_members_by_ident = {}
            st_action = "create"
            item_xml = f'<Item Type="Structure" Id="{sid}"/>'
            if cid:
                new_cat_items.setdefault(cid, []).append(item_xml)
            else:
                new_root_items.append(item_xml)
            new_strings[f"Structure/Name/{sid}"] = dname

        added_member_ids = []
        member_reports = []
        for mem in st.get("members") or []:
            mident = strip_lv(mem["identifier"])
            mdname = mem.get("displayName") or mident
            tinfo = resolve_type(mem["type"])
            dims = normalize_dimensions(mem)
            m_struct_id = struct_id_map.get(strip_gs(mem["struct"])) if tinfo["triggers"] == "struct" else None

            if mident in existing_members_by_ident:
                mid, mel = existing_members_by_ident[mident]
                old_type, old_dims, old_struct = read_var_shape(mel, elems_by_id)
                if old_type != tinfo["triggers"]:
                    raise ValueError(
                        f"Existing struct member {sident}.{mident} has type '{old_type}', expected '{tinfo['triggers']}'"
                    )
                if len(old_dims) != len(dims):
                    raise ValueError(
                        f"Existing struct member {sident}.{mident} has dims {old_dims}, expected {dims}"
                    )
                merged = [max(a, b) for a, b in zip(old_dims, dims)]
                if merged != old_dims:
                    widened_vars.append((mid, merged))
                    member_reports.append({"action": "widen", "id": mid, "identifier": mident, "dimensions": merged})
                else:
                    member_reports.append({"action": "reuse", "id": mid, "identifier": mident, "dimensions": old_dims})
            else:
                mid = new_hex_id(used_ids)
                added_member_ids.append(mid)
                new_elements.extend(
                    build_variable_xml(
                        mid,
                        mident,
                        tinfo,
                        dims,
                        used_ids,
                        struct_id=m_struct_id,
                        game_type=mem.get("gameType"),
                        explicit_default=mem.get("defaultValue"),
                    )
                )
                new_strings[f"Variable/Name/{mid}"] = mdname
                member_reports.append(
                    {"action": "create", "id": mid, "identifier": mident, "type": tinfo["triggers"], "dimensions": dims}
                )

        if st_action == "create":
            m_refs = "\n".join(f'        <Variable Type="Variable" Id="{mid}"/>' for mid in added_member_ids)
            body = f"\n{m_refs}" if m_refs else ""
            new_elements.append(
                f'    <Element Type="Structure" Id="{sid}">\n'
                f'        <Identifier>{xml_escape(sident)}</Identifier>{body}\n'
                f'    </Element>'
            )
        elif added_member_ids:
            struct_append_members[sid] = added_member_ids

        report["structures"].append(
            {"action": st_action, "id": sid, "identifier": sident, "displayName": dname, "members": member_reports}
        )

    # Resolve/Create Top-level Global Variables
    for var in spec["variables"]:
        ident = strip_gv(var["identifier"])
        dname = var.get("displayName") or ident
        tinfo = resolve_type(var["type"])
        dims = normalize_dimensions(var)
        cat_name = var.get("category")
        cid = ensure_category(cat_name, cat_name) if cat_name else None
        v_struct_ident = strip_gs(var["struct"]) if tinfo["triggers"] == "struct" else None
        v_struct_id = struct_id_map.get(v_struct_ident) if v_struct_ident else None
        if tinfo["triggers"] == "struct" and not v_struct_id:
            raise ValueError(f"Global variable {ident} references unknown struct {v_struct_ident}")

        found = top_vars_by_ident.get(ident)
        if not found:
            matches = implicit_by_identifier.get(ident, set())
            if len(matches) > 1:
                raise ValueError(f"Ambiguous editor-generated identifier gv_{ident}; verify the GUI variable ID.")
            if matches:
                eid = next(iter(matches))
                found = (eid, elems_by_id[eid])
        if not found and f"gv_{ident}" in compiled_variables:
            raise ValueError(f"Compiled global gv_{ident} exists, but its GUI variable could not be identified.")
        if found:
            vid, vel = found
            old_type, old_dims, old_struct = read_var_shape(vel, elems_by_id)
            if old_type != tinfo["triggers"]:
                raise ValueError(f"Existing global variable {ident} has type '{old_type}', expected '{tinfo['triggers']}'")
            if old_type == "struct" and old_struct != v_struct_ident:
                raise ValueError(f"Existing struct variable {ident} has struct '{old_struct}', expected '{v_struct_ident}'")
            if len(old_dims) != len(dims):
                raise ValueError(f"Existing global variable {ident} has dims {old_dims}, expected {dims}")
            merged = [max(a, b) for a, b in zip(old_dims, dims)]
            if merged != old_dims:
                widened_vars.append((vid, merged))
                report["variables"].append({"action": "widen", "id": vid, "identifier": ident, "dimensions": merged})
            else:
                report["variables"].append({"action": "reuse", "id": vid, "identifier": ident, "dimensions": old_dims})
        else:
            vid = new_hex_id(used_ids)
            item_xml = f'<Item Type="Variable" Id="{vid}"/>'
            if cid:
                new_cat_items.setdefault(cid, []).append(item_xml)
            else:
                new_root_items.append(item_xml)
            new_elements.extend(
                build_variable_xml(
                    vid,
                    ident,
                    tinfo,
                    dims,
                    used_ids,
                    struct_id=v_struct_id,
                    game_type=var.get("gameType"),
                    explicit_default=var.get("defaultValue"),
                )
            )
            new_strings[f"Variable/Name/{vid}"] = dname
            report["variables"].append(
                {
                    "action": "create",
                    "id": vid,
                    "identifier": ident,
                    "galaxyName": f"gv_{ident}",
                    "displayName": dname,
                    "type": tinfo["triggers"],
                    "dimensions": dims,
                }
            )

    # Build updated Triggers text
    updated_triggers = triggers_text
    for vid, new_dims in widened_vars:
        updated_triggers = widen_variable_arrays_in_text(updated_triggers, vid, new_dims)
    # New categories must be inserted before adding items into them
    if new_elements:
        assert "</TriggerData>" in updated_triggers, "Missing </TriggerData> in Triggers"
        updated_triggers = updated_triggers.replace(
            "</TriggerData>", "\n".join(new_elements) + "\n</TriggerData>", 1
        )
    if new_root_items:
        updated_triggers = insert_items_into_root_or_category(updated_triggers, None, new_root_items)
    for cid, items in new_cat_items.items():
        updated_triggers = insert_items_into_root_or_category(updated_triggers, cid, items)
    for sid, mids in struct_append_members.items():
        updated_triggers = append_members_to_structure(updated_triggers, sid, mids)

    ET.fromstring(updated_triggers)

    # TriggerStrings updates
    for k, v in sorted(new_strings.items()):
        report["triggerStrings"].append(f"{k}={v}")

    # Optional MapScript.galaxy sync
    updated_ms = None
    if not args.no_map_script and ms_path.is_file():
        updated_ms, ms_notes = sync_map_script(ms_text, spec["structures"], spec["variables"])
        for n in ms_notes:
            if n.startswith("WARNING:"):
                report["warnings"].append(n)
            else:
                report["mapScript"].append(n)

    if args.apply:
        backup_root = args.backup_dir
        if not backup_root:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_root = root.parent / f".sc2_gui_sync_bak_{root.stem}_{stamp}"
        backup_root.mkdir(parents=True, exist_ok=True)
        report["backupDir"] = str(backup_root)

        shutil.copy2(triggers_path, backup_root / "Triggers")
        atomic_write_text(triggers_path, updated_triggers, t_bom, t_crlf)

        for tsp in tstr_paths:
            if tsp.is_file():
                ts_bak = backup_root / tsp.relative_to(root)
                ts_bak.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(tsp, ts_bak)
                ts_text, ts_bom, ts_crlf = read_text_preserve(tsp)
            else:
                ts_text, ts_bom, ts_crlf = "", True, True
            existing_map = parse_trigger_strings(ts_text)
            lines = [ln for ln in ts_text.rstrip("\n").splitlines() if ln.strip() != ""]
            for k, v in new_strings.items():
                if k not in existing_map:
                    lines.append(f"{k}={v}")
            atomic_write_text(tsp, "\n".join(lines) + "\n", ts_bom, ts_crlf)

        if updated_ms is not None and ms_path.is_file():
            backup = backup_root / ms_path.relative_to(root)
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ms_path, backup)
            atomic_write_text(ms_path, updated_ms, ms_bom, ms_crlf)

    print(json.dumps(report, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map-copy", type=Path, required=True, help="SC2 map component directory")
    parser.add_argument("--spec", type=Path, help="JSON spec describing categories, structures, and variables")
    parser.add_argument("--manifest", type=Path, help="ui_manifest.json from sc2-ui-workbench handoff")
    parser.add_argument("--category", help="Default GUI category name for newly created items")
    parser.add_argument("--backup-dir", type=Path, help="Backup directory outside the map copy")
    parser.add_argument("--no-map-script", action="store_true", help="Do not update MapScript.galaxy")
    parser.add_argument("--apply", action="store_true", help="Write changes after verifying the dry-run plan")
    args = parser.parse_args()
    plan_and_apply(args)


if __name__ == "__main__":
    main()
