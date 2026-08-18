"""Helpers to normalize raw provider payloads into local catalog shapes."""

from __future__ import annotations

import json
import re
from typing import Any


def normalize_qty_values(raw: Any) -> dict:
    """Contract from docs:

    - null            -> qty must be 1                -> {"type": "unit"}
    - ["110","150"]   -> only these qtys allowed      -> {"type":"list","values":[...]}
    - {"min","max"}   -> qty within range             -> {"type":"range","min":n,"max":n}

    Returns a JSON-serializable dict.
    """
    if raw is None:
        return {"type": "unit"}
    if isinstance(raw, dict):
        mn = raw.get("min")
        mx = raw.get("max")
        return {
            "type": "range",
            "min": int(mn) if mn is not None else 1,
            "max": int(mx) if mx is not None else 2**31 - 1,
        }
    if isinstance(raw, list):
        values = [int(v) for v in raw]
        return {"type": "list", "values": values}
    return {"type": "unit"}


def is_qty_allowed(qty_values: dict, qty: int) -> bool:
    key = qty_values.get("type", "unit")
    if key == "unit":
        return qty == 1
    if key == "list":
        return qty in qty_values.get("values", [])
    if key == "range":
        return int(qty_values.get("min", 1)) <= qty <= int(qty_values.get("max", 2**31 - 1))
    return False


def sanitize_name(raw: str) -> str:
    """Clean raw provider names for display (noise, casing, artifacts)."""
    if not raw:
        return ""
    name = " ".join(raw.split())
    name = re.sub(r"[\x00-\x1f]", "", name)
    name = name.strip(" .-_،,")
    return name


def pretty_qty(qty_values: dict) -> str:
    """Human-readable quantity rule for product cards."""
    key = qty_values.get("type", "unit")
    if key == "unit":
        return "1"
    if key == "list":
        return " / ".join(str(v) for v in qty_values.get("values", []))
    return f"{qty_values.get('min')} – {qty_values.get('max')}"


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


def loads(raw: str | None, default: Any = None) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return default