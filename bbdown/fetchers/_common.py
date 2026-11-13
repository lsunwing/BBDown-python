"""fetcher 公共小工具。"""

from __future__ import annotations

from typing import Any

__all__ = ["dig", "as_text", "as_int", "as_float", "iter_list", "PageSource"]


def dig(node: Any, *keys: str, default: Any = None) -> Any:
    """安全地按层级取 JSON 字段，任一层缺失都返回 default。"""
    current = node
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current


def as_text(node: Any, *keys: str, default: str = "") -> str:
    value = dig(node, *keys)
    if value is None:
        return default
    return str(value)


def as_int(node: Any, *keys: str, default: int = 0) -> int:
    value = dig(node, *keys)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def as_float(node: Any, *keys: str, default: float = 0.0) -> float:
    value = dig(node, *keys)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def iter_list(node: Any, *keys: str) -> list:
    value = dig(node, *keys)
    return value if isinstance(value, list) else []


#: 类型提示占位（各 fetcher 都实现 fetch(id) -> VInfo）
PageSource = Any
