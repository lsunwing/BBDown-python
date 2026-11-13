"""弹幕下载格式枚举，对应 BBDown/BBDownEnums.cs。"""

from __future__ import annotations

import enum

__all__ = ["DanmakuFormat", "DEFAULT_FORMATS", "ALL_FORMAT_NAMES", "from_format_name"]


class DanmakuFormat(enum.Enum):
    XML = "xml"
    ASS = "ass"


#: 默认下载 xml + ass（与 C# 的 DefaultFormats 一致）
DEFAULT_FORMATS: tuple[DanmakuFormat, ...] = (DanmakuFormat.XML, DanmakuFormat.ASS)

#: 可选值列表
ALL_FORMAT_NAMES: tuple[str, ...] = tuple(f.value for f in DanmakuFormat)


def from_format_name(format_name: str) -> DanmakuFormat:
    """字符串 -> 枚举；未知值回退到 xml（与 C# 行为一致）。"""
    try:
        return DanmakuFormat(format_name.strip().lower())
    except ValueError:
        return DanmakuFormat.XML
