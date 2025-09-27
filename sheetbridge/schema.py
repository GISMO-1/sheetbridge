from __future__ import annotations

import os
from typing import Dict, Literal, Optional

from pydantic import BaseModel, Field

JsonType = Literal["string", "number", "integer", "boolean", "datetime", "date"]


class Column(BaseModel):
    type: JsonType = "string"
    required: bool = False


class Contract(BaseModel):
    columns: Dict[str, Column] = Field(default_factory=dict)


_contract: Contract | None = None
_path: str | None = None


def load(path: str) -> Contract | None:
    global _contract, _path
    if not os.path.exists(path):
        _contract, _path = None, path
        return None
    with open(path, "r", encoding="utf-8") as handle:
        data = handle.read()
    _contract = Contract.model_validate_json(data)
    _path = path
    return _contract


def get() -> Contract | None:
    return _contract


def save(contract: Contract, path: Optional[str] = None) -> str:
    p = path or _path or "schema.json"
    with open(p, "w", encoding="utf-8") as handle:
        handle.write(contract.model_dump_json(indent=2))
    return p
