from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Tuple

from .schema import get


def _coerce(val: Any, typ: str):
    if val is None:
        return None
    if typ == "string":
        return str(val)
    if typ == "integer":
        return int(val)
    if typ == "number":
        return float(val)
    if typ == "boolean":
        if isinstance(val, bool):
            return val
        s = str(val).strip().lower()
        return s in {"1", "true", "yes", "y"}
    if typ == "datetime":
        coerced = datetime.fromisoformat(str(val))
        return coerced.isoformat()
    if typ == "date":
        coerced = datetime.fromisoformat(str(val)).date()
        return coerced.isoformat()
    return val


def validate_row(row: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], str | None]:
    contract = get()
    if not contract:
        return True, row, None

    clean: Dict[str, Any] = {}
    for name, column in contract.columns.items():
        value = row.get(name)
        if value is None:
            if column.required:
                return False, row, f"missing_required:{name}"
            clean[name] = None
            continue
        try:
            clean[name] = _coerce(value, column.type)
        except Exception:
            return False, row, f"type_error:{name}:{column.type}"

    for key, value in row.items():
        if key not in clean:
            clean[key] = value
    return True, clean, None
