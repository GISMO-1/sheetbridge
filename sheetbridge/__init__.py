"""SheetBridge package initialization."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - import-time convenience for type checkers
    from .main import app as app

__all__ = ["app"]


def __getattr__(name: str):
    if name == "app":
        from .main import app as _app
        return _app
    raise AttributeError(f"module 'sheetbridge' has no attribute {name!r}")
