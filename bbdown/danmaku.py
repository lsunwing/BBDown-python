"""弹幕解析与 ASS 字幕生成，对应 BBDown.Core/DanmakuUtil.cs。"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from .console import log, log_debug

__all__ = ["parse_xml", "save_as_ass", "DanmakuItem"]

MONITOR_WIDTH = 1920
MONITOR_HEIGHT = 1080
FONT_SIZE = 40
MOVE_SPEND_TIME = 8.00  # 滚动弹幕停留时间
TOP_SPEND_TIME = 4.00  # 顶部/底部弹幕停留时间
PROTECT_LENGTH = 50  # 滚动弹幕屏占百分比

POS_MOVE = 1  # 滚动弹幕
POS_TOP = 2  # 顶部弹幕
POS_BOTTOM = 3  # 底部弹幕


class DanmakuItem:
    """单条弹幕。"""

    def __init__(self, attrs: list[str], content: str) -> None:
        self.out_of_range = False
        self.content = content
        self.start_time = ""
        self.second = 0.0
        self.end_time = ""
        self.font_size = ""
        self.color = ""
        self.timestamp = ""

        mode = attrs[1] if len(attrs) > 1 else ""
        self.danmaku_mode = {"4": POS_BOTTOM, "5": POS_TOP}.get(mode, POS_MOVE)

        try:
            second = float(attrs[0])
            self.second = second
            self.start_time = self._compute_time(second)
            extra = MOVE_SPEND_TIME if self.danmaku_mode == POS_MOVE else TOP_SPEND_TIME
            self.end_time = self._compute_time(second + extra)
        except (ValueError, IndexError) as exc:
            log(str(exc))

        self.font_size = attrs[2] if len(attrs) > 2 else ""
        try:
            self.color = "%06X" % int(attrs[3])
        except (ValueError, IndexError) as exc:
            log(str(exc))
        self.timestamp = attrs[4] if len(attrs) > 4 else ""

    @staticmethod
    def _compute_time(second: float) -> str:
        hour = int(second) // 3600
        minute = int(second - hour * 3600) // 60
        second -= hour * 3600 + minute * 60
        return f"{hour}:{minute:02d}:{second:05.2f}"


class _PositionController:
    """按行分配弹幕位置，避免重叠。"""

    def __init__(self) -> None:
        self.max_line = MONITOR_HEIGHT * PROTECT_LENGTH // FONT_SIZE // 100
        self.move_queue = [0.0] * self.max_line
        self.top_queue = [0.0] * self.max_line
        self.bottom_queue = [0.0] * self.max_line

    def update_position(self, danmaku_type: int, time: float, length: int) -> int:
        display_time = TOP_SPEND_TIME
        if danmaku_type == POS_BOTTOM:
            queue = self.bottom_queue
        elif danmaku_type == POS_TOP:
            queue = self.top_queue
        else:
            queue = self.move_queue
            display_time = (
                MOVE_SPEND_TIME
                * (length + 5)
                * FONT_SIZE
                / (MONITOR_WIDTH + (length * MOVE_SPEND_TIME))
            )

        for i in range(self.max_line):
            if time >= queue[i]:
                queue[i] = time + display_time
                return i * FONT_SIZE
        return -1


def parse_xml(xml_path: str) -> list[DanmakuItem] | None:
    """解析弹幕 XML；解析失败返回 None。"""
    items: list[DanmakuItem] = []
    try:
        root = ET.parse(xml_path).getroot()
    except Exception as exc:
        log_debug("解析字幕xml时出现异常: %s", exc)
        return None

    for node in root.findall("d"):
        attr = node.get("p")
        if not attr:
            continue
        parts = attr.split(",")
        if len(parts) >= 8:
            items.append(DanmakuItem(parts, node.text or ""))
    return items


def save_as_ass(danmakus: list[DanmakuItem], output_path: str) -> None:
    """保存为 ASS 字幕文件。"""
    lines: list[str] = []
    lines.append("[Script Info]")
    lines.append("Script Updated By: BBDown(https://github.com/nilaoda/BBDown)")
    lines.append("ScriptType: v4.00+")
    lines.append(f"PlayResX: {MONITOR_WIDTH}")
    lines.append(f"PlayResY: {MONITOR_HEIGHT}")
    lines.append(f"Aspect Ratio: {MONITOR_WIDTH}:{MONITOR_HEIGHT}")
    lines.append("Collisions: Normal")
    lines.append("WrapStyle: 2")
    lines.append("ScaledBorderAndShadow: yes")
    lines.append("YCbCr Matrix: TV.601")
    lines.append("[V4+ Styles]")
    lines.append(
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding"
    )
    lines.append(
        "Style: BBDOWN_Style, 黑体, %d, &H00FFFFFF, &H00FFFFFF, &H00000000, &H00000000, "
        "0, 0, 0, 0, 100, 100, 0.00, 0.00, 1, 2, 0, 7, 0, 0, 0, 0" % FONT_SIZE
    )
    lines.append("[Events]")
    lines.append("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text")

    controller = _PositionController()
    for danmaku in sorted(danmakus, key=lambda d: d.second):
        height = controller.update_position(
            danmaku.danmaku_mode, danmaku.second, len(danmaku.content)
        )
        if height == -1:
            continue

        if danmaku.danmaku_mode == POS_BOTTOM:
            effect = f"\\an8\\pos({MONITOR_WIDTH // 2}, {MONITOR_HEIGHT - FONT_SIZE - height})"
        elif danmaku.danmaku_mode == POS_TOP:
            effect = f"\\an8\\pos({MONITOR_WIDTH // 2}, {height})"
        else:
            effect = (
                f"\\move({MONITOR_WIDTH}, {height}, "
                f"{-len(danmaku.content) * FONT_SIZE}, {height})"
            )
        if danmaku.color != "FFFFFF":
            effect += f"\\c&{danmaku.color}&"

        lines.append(
            f"Dialogue: 2,{danmaku.start_time},{danmaku.end_time},BBDOWN_Style,,"
            f"0000,0000,0000,,{{{effect}}}{danmaku.content}"
        )

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    # 用 "\n" 拼接，写文件时由 Python 按平台换成 \r\n / \n
    Path(output_path).write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
