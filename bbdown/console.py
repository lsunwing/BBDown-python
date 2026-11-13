"""控制台输出：彩色日志 + 下载进度条。

对应 BBDown.Core/Logger.cs 与 BBDown/ProgressBar.cs。
"""

from __future__ import annotations

import os
import sys
import threading
import time

__all__ = [
    "log",
    "log_error",
    "log_color",
    "log_warn",
    "log_debug",
    "ProgressBar",
    "format_file_size",
]

_RESET = "\x1b[0m"
_RED = "\x1b[31m"
_DARK_YELLOW = "\x1b[33m"
_CYAN = "\x1b[36m"
_DARK_GRAY = "\x1b[90m"
_WHITE_ON_DARK_BLUE = "\x1b[37;44m"

#: 时间戳格式与 C# 的 ``[yyyy-MM-dd HH:mm:ss.fff]`` 一致
_TS_PREFIX = "                            "  # 28 空格，与 C# LogColor 的对齐一致


def _enable_vt() -> bool:
    """尽力打开 Windows 控制台的 ANSI 转义支持。"""
    if os.name != "nt":
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))
    except Exception:
        return False


def _setup_stdio() -> None:
    """把控制台切到 UTF-8，避免中文输出乱码。"""
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            ctypes.windll.kernel32.SetConsoleCP(65001)
        except Exception:
            pass
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _is_tty() -> bool:
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


_setup_stdio()
_USE_COLOR = _is_tty() and _enable_vt()


def _colorize(text: str, color: str) -> str:
    if not _USE_COLOR:
        return text
    return color + text + _RESET


def _timestamp() -> str:
    now = time.time()
    return "[" + time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)) + (".%03d]" % int((now % 1) * 1000))


def format_file_size(file_size: float) -> str:
    """对应 BBDownUtil.FormatFileSize。"""
    if file_size < 0:
        raise ValueError("file_size must be non-negative")
    if file_size >= 1024 * 1024 * 1024:
        return f"{file_size / (1024 ** 3):.2f} GB"
    if file_size >= 1024 * 1024:
        return f"{file_size / (1024 ** 2):.2f} MB"
    if file_size >= 1024:
        return f"{file_size / 1024:.2f} KB"
    if float(file_size).is_integer():
        return f"{int(file_size)} bytes"
    return f"{file_size} bytes"


def set_console_title(title: str) -> None:
    """设置窗口标题（非 Windows 平台忽略）。"""
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.kernel32.SetConsoleTitleW(title)
        except Exception:
            pass


def log(text: object, enter: bool = True) -> None:
    sys.stdout.write(_timestamp() + " - " + str(text))
    if enter:
        sys.stdout.write("\n")
    sys.stdout.flush()


def log_error(text: object) -> None:
    sys.stdout.write(_timestamp() + " - ")
    sys.stdout.write(_colorize(str(text), _RED))
    sys.stdout.write("\n")
    sys.stdout.flush()


def log_color(text: object, time_prefix: bool = True) -> None:
    if time_prefix:
        sys.stdout.write(_timestamp() + " - ")
    sys.stdout.write(_colorize(str(text), _CYAN))
    sys.stdout.write("\n")
    sys.stdout.flush()


def log_warn(text: object, time_prefix: bool = True) -> None:
    if time_prefix:
        sys.stdout.write(_timestamp() + " - ")
    sys.stdout.write(_colorize(str(text), _DARK_YELLOW))
    sys.stdout.write("\n")
    sys.stdout.flush()


def log_banner(text: str) -> None:
    """白字深蓝底输出（对应 Console.BackgroundColor 用法）。"""
    sys.stdout.write(_colorize(text, _WHITE_ON_DARK_BLUE) if _USE_COLOR else text)
    sys.stdout.write("\n")
    sys.stdout.flush()


def log_debug(to_format: str, *args: object) -> None:
    from .config import Config

    if not Config.DEBUG_LOG:
        return
    message = to_format % args if args else to_format
    sys.stdout.write(_timestamp() + " - ")
    sys.stdout.write(_colorize(message.strip(), _DARK_GRAY))
    sys.stdout.write("\n")
    sys.stdout.flush()


class ProgressBar:
    """单行刷新的进度条。

    只在终端里绘制；当关联了服务器模式的 ``DownloadTask`` 时，即使输出被重定向
    也继续统计进度，只是不往屏幕上写（与 C# 版行为一致）。
    """

    BLOCK_COUNT = 40
    ANIMATION = "|/-\\"
    _INTERVAL = 1.0 / 8.0
    _SPEED_INTERVAL = 1.0

    def __init__(self, task: object | None = None) -> None:
        self._task = task
        self._progress = 0.0
        self._downloaded = 0
        self._last_downloaded = 0
        self._speed_string = ""
        self._current_text = ""
        self._animation_index = 0
        self._disposed = True
        self._lock = threading.Lock()
        self._tick = 0
        self._thread: threading.Thread | None = None
        self._draw = _is_tty()
        if self._draw or task is not None:
            self._disposed = False
            self._thread = threading.Thread(target=self._run, name="progress-bar", daemon=True)
            self._thread.start()

    # -- 对外接口 ---------------------------------------------------------
    def report(self, value: float, bytes_count: int | None = None) -> None:
        value = max(0.0, min(1.0, value))
        with self._lock:
            self._progress = value
            if bytes_count is not None:
                self._downloaded = bytes_count

    def close(self) -> None:
        self._disposed = True
        thread = self._thread
        if thread is not None:
            thread.join(timeout=1.0)
            self._thread = None
        if self._draw:
            self._write("\r\x1b[K")

    def __enter__(self) -> "ProgressBar":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # -- 内部实现 ---------------------------------------------------------
    def _run(self) -> None:
        speed_mark = time.monotonic()
        while not self._disposed:
            time.sleep(self._INTERVAL)
            if self._disposed:
                break
            self._tick += 1
            if self._tick % int(round(self._SPEED_INTERVAL / self._INTERVAL)) == 0:
                now = time.monotonic()
                if self._update_speed(now - speed_mark):
                    speed_mark = now
            self._render()

    def _update_speed(self, elapsed: float) -> bool:
        with self._lock:
            delta = self._downloaded - self._last_downloaded
            self._last_downloaded = self._downloaded
            if delta <= 0:
                return False
            self._speed_string = " - " + format_file_size(delta) + "/s"
        task = self._task
        if task is not None:
            try:
                task.DownloadSpeed = delta
                task.TotalDownloadedBytes += delta
            except Exception:
                pass
        return True

    def _render(self) -> None:
        with self._lock:
            progress = self._progress
            speed = self._speed_string
        filled = int(progress * self.BLOCK_COUNT)
        anim = self.ANIMATION[self._animation_index % len(self.ANIMATION)]
        self._animation_index += 1
        text = "{prefix}[{bar}] {percent:3.2f}% {anim}{speed}".format(
            prefix=_TS_PREFIX,
            bar="#" * filled + "-" * (self.BLOCK_COUNT - filled),
            percent=progress * 100,
            anim=anim,
            speed=speed,
        )
        task = self._task
        if task is not None:
            try:
                task.Progress = progress
            except Exception:
                pass
        if self._draw:
            self._write("\r\x1b[K" + text)

    def _write(self, text: str) -> None:
        try:
            sys.stdout.write(text)
            sys.stdout.flush()
        except Exception:
            pass
