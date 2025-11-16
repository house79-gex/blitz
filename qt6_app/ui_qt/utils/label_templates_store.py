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
        return {"templates": _DEFAULT_TEMPLATES.copy(), "associations": {}}
    try:
        with open(_STORE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"templates": _DEFAULT_TEMPLATES.copy(), "associations": {}}

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
    if qrcode:
        item["qrcode"] = dict(qrcode)
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
        for k in list(assoc.keys()):
            v = assoc[k]
            if isinstance(v, list):
                assoc[k] = [t for t in v if t != name]
                if not assoc[k]:
                    del assoc[k]
            elif v == name:
                del assoc[k]
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

def list_associations() -> Dict[str, Union[str, List[str]]]:
    data = _read_raw()
    return dict(data.get("associations", {}) or {})

def set_association(profile_name: str, template_name: str):
    """
    Aggiunge (accumula) il template all'associazione profilo.
    Il valore in JSON diventa una lista se si associano più template allo stesso profilo.
    """
    data = _read_raw()
    templates = data.get("templates", {}) or {}
    if template_name not in templates:
        raise ValueError("Template non esistente.")
    assoc = data.get("associations", {}) or {}
    cur = assoc.get(profile_name)
    if cur is None:
        assoc[profile_name] = [template_name]
    elif isinstance(cur, list):
        if template_name not in cur:
            cur.append(template_name)
            assoc[profile_name] = cur
    else:
        # string → lista
        if cur != template_name:
            assoc[profile_name] = [cur, template_name]
    data["associations"] = assoc
    _write_raw(data)

def remove_association(profile_name: str, template_name: str):
    data = _read_raw()
    assoc = data.get("associations", {}) or {}
    cur = assoc.get(profile_name)
    if isinstance(cur, list):
        cur = [t for t in cur if t != template_name]
        if cur:
            assoc[profile_name] = cur
        else:
            del assoc[profile_name]
    elif cur == template_name:
        del assoc[profile_name]
    data["associations"] = assoc
    _write_raw(data)

def clear_association(profile_name: str):
    data = _read_raw()
    assoc = data.get("associations", {}) or {}
    if profile_name in assoc:
        del assoc[profile_name]
        data["associations"] = assoc
        _write_raw(data)

def resolve_templates_for_profile(profile_name: str) -> List[Dict[str, Any]]:
    assoc = list_associations()
    v = assoc.get(profile_name)
    if isinstance(v, list):
        out: List[Dict[str, Any]] = []
        for n in v:
            t = get_template(n)
            if t:
                out.append(t)
        if out:
            return out
    elif isinstance(v, str):
        t = get_template(v)
        if t:
            return [t]
    # fallback default
    return [get_template("DEFAULT") or _DEFAULT_TEMPLATES["DEFAULT"]]

def resolve_template_for_profile(profile_name: str) -> Dict[str, Any]:
    # compat: primo della lista
    return resolve_templates_for_profile(profile_name)[0]
