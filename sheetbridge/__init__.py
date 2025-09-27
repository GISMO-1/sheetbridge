"""SheetBridge package initialization."""

from typing import TYPE_CHECKING

__version__ = "0.1.0"

if TYPE_CHECKING:  # pragma: no cover - import-time convenience for type checkers
    from .main import app as app

__all__ = ["app", "__version__"]


def __getattr__(name: str):
    if name == "app":
        from .main import app as _app
        return _app
    raise AttributeError(f"module 'sheetbridge' has no attribute {name!r}")
