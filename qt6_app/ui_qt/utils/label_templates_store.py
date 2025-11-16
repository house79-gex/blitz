from __future__ import annotations
import json, os, time
from typing import Dict, Any, List, Optional, Union

_STORE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "label_templates.json")

_DEFAULT_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "DEFAULT": {
        "name": "DEFAULT",
        "paper": "DK-11201",
        "rotate": 0,
        "font_size": 32,
        "cut": True,
        "lines": [
            "{profile}",
            "{element}",
            "L={length_mm:.2f} AX={ang_sx:.1f} AD={ang_dx:.1f}",
            "SEQ:{seq_id}"
        ],
        # Opzionale: QR
        # "qrcode": {"data": "{commessa}|{element_id}", "module_size": 4}
        "updated_at": None
    }
}

def _ensure_dir():
    os.makedirs(os.path.dirname(_STORE_FILE), exist_ok=True)

def _read_raw() -> Dict[str, Any]:
    if not os.path.exists(_STORE_FILE):
        return {"templates": _DEFAULT_TEMPLATES.copy(), "associations": {"by_profile": {}, "by_element": {}}}
    try:
        with open(_STORE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {"templates": _DEFAULT_TEMPLATES.copy(), "associations": {}}
    # Normalizza struttura associazioni
    assoc = data.get("associations") or {}
    if not isinstance(assoc, dict):
        assoc = {}
    assoc.setdefault("by_profile", {})
    assoc.setdefault("by_element", {})
    data["associations"] = assoc
    return data

def _write_raw(data: Dict[str, Any]):
    _ensure_dir()
    with open(_STORE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def list_templates() -> List[Dict[str, Any]]:
    data = _read_raw()
    templates = data.get("templates", {}) or {}
    if "DEFAULT" not in templates:
        templates["DEFAULT"] = _DEFAULT_TEMPLATES["DEFAULT"]
    return sorted([dict(v) for v in templates.values()], key=lambda x: x.get("name","").lower())

def get_template(name: str) -> Optional[Dict[str, Any]]:
    for t in list_templates():
        if t.get("name") == name:
            return t
    return None

def upsert_template(name: str, paper: str, rotate: int, font_size: int, cut: bool, lines: List[str], qrcode: Optional[Dict[str, Any]] = None):
    data = _read_raw()
    templates = data.get("templates", {}) or {}
    item = {
        "name": name,
        "paper": paper,
        "rotate": int(rotate),
        "font_size": int(font_size),
        "cut": bool(cut),
        "lines": list(lines),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }
    if qrcode and isinstance(qrcode, dict) and (qrcode.get("data") or "").strip():
        item["qrcode"] = {"data": str(qrcode.get("data")), "module_size": int(qrcode.get("module_size", 4))}
    templates[name] = item
    data["templates"] = templates
    _write_raw(data)

def delete_template(name: str) -> bool:
    if name == "DEFAULT":
        return False
    data = _read_raw()
    templates = data.get("templates", {}) or {}
    if name in templates:
        del templates[name]
        assoc = data.get("associations", {}) or {}
        # Pulisci in by_profile
        bp = assoc.get("by_profile", {}) or {}
        for k in list(bp.keys()):
            v = bp[k]
            if isinstance(v, list):
                bp[k] = [t for t in v if t != name]
                if not bp[k]:
                    del bp[k]
            elif v == name:
                del bp[k]
        assoc["by_profile"] = bp
        # Pulisci in by_element
        be = assoc.get("by_element", {}) or {}
        for prof, emap in list(be.items()):
            if not isinstance(emap, dict):
                del be[prof]; continue
            for el, lst in list(emap.items()):
                if isinstance(lst, list):
                    new = [t for t in lst if t != name]
                    if new:
                        emap[el] = new
                    else:
                        del emap[el]
            if not emap:
                del be[prof]
        assoc["by_element"] = be
        data["associations"] = assoc
        data["templates"] = templates
        _write_raw(data)
        return True
    return False

def duplicate_template(src_name: str, new_name: str) -> bool:
    src = get_template(src_name)
    if not src:
        return False
    upsert_template(new_name,
                    paper=src.get("paper","DK-11201"),
                    rotate=int(src.get("rotate",0)),
                    font_size=int(src.get("font_size",32)),
                    cut=bool(src.get("cut",True)),
                    lines=list(src.get("lines",[])),
                    qrcode=src.get("qrcode"))
    return True

def list_associations() -> Dict[str, Any]:
    data = _read_raw()
    return dict(data.get("associations", {}) or {"by_profile": {}, "by_element": {}})

# Associazioni per profilo (multi-template)
def set_profile_association(profile_name: str, template_name: str):
    data = _read_raw()
    templates = data.get("templates", {}) or {}
    if template_name not in templates:
        raise ValueError("Template non esistente.")
    assoc = data.get("associations", {}) or {}
    bp = assoc.get("by_profile", {}) or {}
    cur = bp.get(profile_name)
    if cur is None:
        bp[profile_name] = [template_name]
    elif isinstance(cur, list):
        if template_name not in cur:
            cur.append(template_name)
            bp[profile_name] = cur
    else:
        if cur != template_name:
            bp[profile_name] = [cur, template_name]
    assoc["by_profile"] = bp
    data["associations"] = assoc
    _write_raw(data)

def remove_profile_association(profile_name: str, template_name: str):
    data = _read_raw()
    assoc = data.get("associations", {}) or {}
    bp = assoc.get("by_profile", {}) or {}
    cur = bp.get(profile_name)
    if isinstance(cur, list):
        cur = [t for t in cur if t != template_name]
        if cur:
            bp[profile_name] = cur
        else:
            del bp[profile_name]
    elif cur == template_name:
        del bp[profile_name]
    assoc["by_profile"] = bp
    data["associations"] = assoc
    _write_raw(data)

def clear_profile_association(profile_name: str):
    data = _read_raw()
    assoc = data.get("associations", {}) or {}
    bp = assoc.get("by_profile", {}) or {}
    if profile_name in bp:
        del bp[profile_name]
    assoc["by_profile"] = bp
    data["associations"] = assoc
    _write_raw(data)

# Associazioni per elemento (scopo: profilo + nome elemento) — multi-template
def set_element_association(profile_name: str, element_name: str, template_name: str):
    data = _read_raw()
    templates = data.get("templates", {}) or {}
    if template_name not in templates:
        raise ValueError("Template non esistente.")
    assoc = data.get("associations", {}) or {}
    be = assoc.get("by_element", {}) or {}
    emap = be.get(profile_name) or {}
    lst = emap.get(element_name)
    if lst is None:
        emap[element_name] = [template_name]
    elif isinstance(lst, list):
        if template_name not in lst:
            lst.append(template_name)
            emap[element_name] = lst
    else:
        if lst != template_name:
            emap[element_name] = [lst, template_name]
    be[profile_name] = emap
    assoc["by_element"] = be
    data["associations"] = assoc
    _write_raw(data)

def remove_element_association(profile_name: str, element_name: str, template_name: str):
    data = _read_raw()
    assoc = data.get("associations", {}) or {}
    be = assoc.get("by_element", {}) or {}
    emap = be.get(profile_name) or {}
    lst = emap.get(element_name)
    if isinstance(lst, list):
        lst = [t for t in lst if t != template_name]
        if lst:
            emap[element_name] = lst
        else:
            del emap[element_name]
    elif lst == template_name:
        del emap[element_name]
    if emap:
        be[profile_name] = emap
    else:
        if profile_name in be:
            del be[profile_name]
    assoc["by_element"] = be
    data["associations"] = assoc
    _write_raw(data)

def clear_element_association(profile_name: str, element_name: str):
    data = _read_raw()
    assoc = data.get("associations", {}) or {}
    be = assoc.get("by_element", {}) or {}
    emap = be.get(profile_name) or {}
    if element_name in emap:
        del emap[element_name]
    if emap:
        be[profile_name] = emap
    else:
        if profile_name in be:
            del be[profile_name]
    assoc["by_element"] = be
    data["associations"] = assoc
    _write_raw(data)

# Resolver: per elemento → per profilo → default
def resolve_templates(profile_name: str, element_name: Optional[str] = None) -> List[Dict[str, Any]]:
    assoc = list_associations()
    out: List[Dict[str, Any]] = []

    if element_name:
        be = assoc.get("by_element", {}) or {}
        emap = be.get(profile_name) or {}
        lst = emap.get(element_name)
        if isinstance(lst, list):
            for n in lst:
                t = get_template(n)
                if t:
                    out.append(t)
    if not out:
        bp = assoc.get("by_profile", {}) or {}
        lst = bp.get(profile_name)
        if isinstance(lst, list):
            for n in lst:
                t = get_template(n)
                if t:
                    out.append(t)
    if not out:
        t = get_template("DEFAULT") or _DEFAULT_TEMPLATES["DEFAULT"]
        out = [t]
    return out

# Compat vecchie funzioni
def resolve_templates_for_profile(profile_name: str) -> List[Dict[str, Any]]:
    return resolve_templates(profile_name, None)

def resolve_template_for_profile(profile_name: str) -> Dict[str, Any]:
    return resolve_templates(profile_name, None)[0]
