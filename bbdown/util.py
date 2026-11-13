"""通用工具函数，对应 BBDown/BBDownUtil.cs 与部分 Program.Methods.cs。"""

from __future__ import annotations

import hashlib
import os
import random
import re
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from .config import Config
from .console import format_file_size, log_debug, log_error, log_warn
from .entity import ViewPoint

__all__ = [
    "app_dir",
    "check_aid_from_file",
    "check_ffmpeg_dovi",
    "check_login",
    "combine_files",
    "dotnet_format",
    "fetch_points",
    "find_executable",
    "format_file_size",
    "format_time",
    "format_timestamp",
    "get_ffmpeg_meta_string",
    "get_files",
    "get_mixin_key",
    "get_mp4box_meta_string",
    "get_query_string",
    "get_random_string",
    "get_sign",
    "get_time_stamp",
    "get_tv_login_params",
    "get_valid_filename",
    "r_sub_string",
    "save_aid_to_file",
]

# ---------------------------------------------------------------------------
# 目录 / 文件
# ---------------------------------------------------------------------------

_APP_DIR: Path | None = None


def app_dir() -> Path:
    """程序数据目录（BBDown.data / BBDown.config / BBDown.archives 所在处）。

    优先级：``BBDOWN_HOME`` 环境变量 > 源码工程根目录 > 当前工作目录。
    对应 C# 的 ``Environment.ProcessPath`` 所在目录。
    """
    global _APP_DIR
    if _APP_DIR is not None:
        return _APP_DIR

    env = os.environ.get("BBDOWN_HOME")
    if env:
        _APP_DIR = Path(env).expanduser().resolve()
    else:
        package_dir = Path(__file__).resolve().parent
        parent = package_dir.parent
        lowered = str(package_dir).lower()
        if "site-packages" in lowered or "dist-packages" in lowered:
            _APP_DIR = Path.cwd()
        else:
            _APP_DIR = parent
    return _APP_DIR


_NAME_LOCKS = threading.Lock()


def get_valid_filename(text: str, re_placeholder: str = "_", filter_slash: bool = False) -> str:
    """把标题变成合法文件名；非法字符（含 ``: * ? " < > | \\ /`` 与控制符）替换掉。"""
    invalid = '"<>|' + "".join(chr(i) for i in range(32)) + ":*?\\/"
    result = text
    for ch in invalid:
        result = result.replace(ch, re_placeholder)
    if filter_slash:
        result = result.replace("/", re_placeholder).replace("\\", re_placeholder)
    return result


def combine_files(files: list[str], output_path: str) -> None:
    """按顺序拼接文件（对应 CombineMultipleFilesIntoSingleFile）。"""
    if not files:
        return
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if len(files) == 1:
        os.replace(files[0], out)
        return
    with open(out, "wb") as w:
        for name in files:
            if not name:
                continue
            with open(name, "rb") as r:
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    w.write(chunk)


def get_files(directory: str, ext: str) -> list[str]:
    """列出目录下指定后缀的文件，按路径排序（对应 GetFiles）。"""
    try:
        entries = os.listdir(directory)
    except OSError:
        return []
    wanted = ext.upper()
    result = [os.path.join(directory, name) for name in entries if os.path.splitext(name)[1].upper() == wanted]
    result.sort()
    return result


def find_executable(name: str) -> str | None:
    """在当前目录、程序目录、PATH 中查找可执行文件。"""
    file_ext = ".exe" if os.name == "nt" else ""
    search = [str(Path.cwd()), str(app_dir())]
    search.extend(os.environ.get("PATH", "").split(os.pathsep))
    for directory in search:
        if not directory:
            continue
        candidate = Path(directory) / (name + file_ext)
        if candidate.is_file():
            return str(candidate)
    return None


# ---------------------------------------------------------------------------
# 文本 / 时间格式化
# ---------------------------------------------------------------------------


def format_time(seconds: int, absolute: bool = False) -> str:
    """秒数 -> ``1h02m03s`` / ``02m03s`` / ``01:02:03``。"""
    total = int(seconds)
    total_hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if absolute:
        return f"{total_hours:02d}:{minutes:02d}:{secs:02d}"
    if total_hours == 0:
        return f"{minutes:02d}m{secs:02d}s"
    return f"{total_hours}h{minutes:02d}m{secs:02d}s"


_MONTH_ABBR = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_DAY_ABBR = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def dotnet_format(value: datetime, fmt: str) -> str:
    """把 .NET 自定义日期格式串翻译成实际文本（只支持常用 token）。"""
    out: list[str] = []
    i = 0
    length = len(fmt)
    while i < length:
        ch = fmt[i]
        run = 1
        while i + run < length and fmt[i + run] == ch:
            run += 1

        token = (ch, run)
        piece = _render_date_token(value, token)

        if piece is None:
            # 不认识的 token，原样输出一个字符，继续往后扫描
            out.append(ch)
            i += 1
        else:
            out.append(piece)
            i += run
    return "".join(out)


def _render_date_token(value: datetime, token: tuple[str, int]) -> str | None:
    ch, run = token
    if ch == "y":
        if run <= 2:
            return f"{value.year % 100:02d}"
        return f"{value.year:04d}"
    if ch == "M":
        if run == 1:
            return str(value.month)
        if run == 2:
            return f"{value.month:02d}"
        if run == 3:
            return _MONTH_ABBR[value.month - 1]
        if run >= 4:
            return _MONTH_FULL[value.month - 1]
    if ch == "d":
        if run == 1:
            return str(value.day)
        if run == 2:
            return f"{value.day:02d}"
        if run == 3:
            return _DAY_ABBR[value.weekday()]
        if run >= 4:
            return _DAY_FULL[value.weekday()]
    if ch == "H":
        return str(value.hour) if run == 1 else f"{value.hour:02d}"
    if ch == "h":
        hour12 = value.hour % 12 or 12
        return str(hour12) if run == 1 else f"{hour12:02d}"
    if ch == "m":
        return str(value.minute) if run == 1 else f"{value.minute:02d}"
    if ch == "s":
        return str(value.second) if run == 1 else f"{value.second:02d}"
    if ch == "f":
        fraction = f"{value.microsecond:06d}" + "0" * 7
        clamped = min(run, 7)
        return fraction[:clamped]
    if ch == "z":
        offset = value.utcoffset()
        total_minutes = int(offset.total_seconds() // 60) if offset else 0
        sign = "+" if total_minutes >= 0 else "-"
        total_minutes = abs(total_minutes)
        hours, minutes = divmod(total_minutes, 60)
        if run == 1:
            return f"{sign}{hours}"
        if run == 2:
            return f"{sign}{hours:02d}"
        return f"{sign}{hours:02d}:{minutes:02d}"
    if ch == "t":
        marker = "AM" if value.hour < 12 else "PM"
        return marker[0] if run == 1 else marker
    return None


_MONTH_FULL = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
_DAY_FULL = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def format_timestamp(ts: int, fmt: str) -> str:
    """Unix 时间戳按 .NET 格式串格式化；0 输出 ``null``。"""
    if ts == 0:
        return "null"
    try:
        return dotnet_format(datetime.fromtimestamp(ts).astimezone(), fmt)
    except Exception as exc:  # pragma: no cover - 极端输入
        log_error(f"格式化日期出错: {exc}")
        return str(ts)


# ---------------------------------------------------------------------------
# URL / 签名 / 随机
# ---------------------------------------------------------------------------

_QUERY_RE = re.compile(r"(^|&)?(\w+)=([^&]+)(&|$)?")


def get_query_string(name: str, url: str) -> str:
    """取 URL 查询串中的参数值，找不到返回空串。"""
    for match in _QUERY_RE.finditer(url):
        if match.group(2) == name:
            return match.group(3)
    return ""


def get_sign(parms: str) -> str:
    """TV 端接口签名。"""
    return hashlib.md5((parms + "59b43e04ad6965f34319062b478f83dd").encode("utf-8")).hexdigest()


def get_time_stamp(seconds: bool = False) -> str:
    now = time.time()
    return str(int(now)) if seconds else str(int(now * 1000))


_RANDOM_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_0123456789"


def get_random_string(length: int) -> str:
    return "".join(random.choice(_RANDOM_CHARS) for _ in range(length))


def get_tv_login_params() -> dict[str, str]:
    """TV 端扫码登录的公共参数（含 sign）。"""
    now = datetime.now()
    device_id = get_random_string(20)
    buvid = get_random_string(37)
    fingerprint = now.strftime("%Y%m%d%H%M%S") + f"{now.microsecond // 1000:03d}" + get_random_string(45)

    params: dict[str, str] = {}
    params["appkey"] = "4409e2ce8ffd12b8"
    params["auth_code"] = ""
    params["bili_local_id"] = device_id
    params["build"] = "102801"
    params["buvid"] = buvid
    params["channel"] = "master"
    params["device"] = "OnePlus"
    params["device_id"] = device_id
    params["device_name"] = "OnePlus7TPro"
    params["device_platform"] = "Android10OnePlusHD1910"
    params["fingerprint"] = fingerprint
    params["guid"] = buvid
    params["local_fingerprint"] = fingerprint
    params["local_id"] = buvid
    params["mobi_app"] = "android_tv_yst"
    params["networkstate"] = "wifi"
    params["platform"] = "android"
    params["sys_ver"] = "29"
    params["ts"] = get_time_stamp(True)
    params["sign"] = get_sign(to_query_string(params))
    return params


def to_query_string(params: dict[str, str]) -> str:
    """按插入顺序拼查询串（对应 NameValueCollection.ToString）。"""
    from urllib.parse import quote

    parts = []
    for key, value in params.items():
        encoded = quote(str(value), safe="-_.!~*'()")
        parts.append(f"{key}={encoded}")
    return "&".join(parts)


def r_sub_string(sub: str) -> str:
    """取 URL 最后一段去掉扩展名后的名字（wbi 图片名）。"""
    sub = sub[sub.rfind("/") + 1 :]
    return sub[: sub.rfind(".")]


_MIXIN_KEY_ENC_TAB = (
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
)


def get_mixin_key(orig: str) -> str:
    return "".join(orig[index] for index in _MIXIN_KEY_ENC_TAB)


# ---------------------------------------------------------------------------
# 外部程序 / 网络辅助
# ---------------------------------------------------------------------------

_LIBAVUTIL_RE = re.compile(r"libavutil\s+(\d+)\.\s+(\d+)\.")


def check_ffmpeg_dovi(ffmpeg_path: str) -> bool:
    """检测 ffmpeg 是否具备杜比视界处理能力（libavutil >= 57，即 ffmpeg 5.0+）。"""
    try:
        proc = subprocess.run(
            [ffmpeg_path, "-version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        info = (proc.stdout or "") + "\n" + (proc.stderr or "")
        match = _LIBAVUTIL_RE.search(info)
        if not match:
            return False
        return int(match.group(1)) >= 57
    except Exception:
        return False


def fetch_points(cid: str, aid: str) -> list[ViewPoint]:
    """获取章节信息（看点）。"""
    from .net import HTTPUtil

    points: list[ViewPoint] = []
    try:
        api = f"https://api.bilibili.com/x/player/wbi/v2?cid={cid}&aid={aid}"
        data = _json_object(HTTPUtil.get_web_source(api)).get("data") or {}
        for point in data.get("view_points") or []:
            points.append(
                ViewPoint(
                    title=str(point.get("content", "")),
                    start=int(point.get("from", 0)),
                    end=int(point.get("to", 0)),
                )
            )
    except Exception:
        pass
    return points


def get_ffmpeg_meta_string(points: list[ViewPoint]) -> str:
    """生成 ffmpeg 章节元数据（FFMETADATA）。"""
    lines = [";FFMETADATA"]
    for point in points:
        time_base = 1000
        lines.append("[CHAPTER]")
        lines.append(f"TIMEBASE=1/{time_base}")
        lines.append(f"START={point.start * time_base}")
        lines.append(f"END={point.end * time_base}")
        lines.append(f"title={point.title}")
        lines.append("")
    return "\n".join(lines) + "\n"


def get_mp4box_meta_string(points: list[ViewPoint]) -> str:
    """生成 mp4box 章节元数据。"""
    return "\n".join(f"{format_time(p.start, True)} {p.title}" for p in points) + "\n"


def check_login(cookie: str) -> bool:
    """检测登录状态，顺便刷新 wbi key。"""
    from . import net

    try:
        source = net.HTTPUtil.get_web_source("https://api.bilibili.com/x/web-interface/nav")
        data = _json_object(source).get("data") or {}
        is_login = bool(data.get("isLogin"))
        wbi_img = data.get("wbi_img") or {}
        Config.WBI = get_mixin_key(
            r_sub_string(str(wbi_img.get("img_url", ""))) + r_sub_string(str(wbi_img.get("sub_url", "")))
        )
        log_debug("wbi: %s", Config.WBI)
        return is_login
    except Exception:
        return False


def _json_object(text: str) -> dict:
    import json

    try:
        value = json.loads(text)
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


# ---------------------------------------------------------------------------
# 断点续传记录（BBDown.archives）
# ---------------------------------------------------------------------------

_ARCHIVE_LOCK = threading.Lock()


def save_aid_to_file(aid: str) -> None:
    with _ARCHIVE_LOCK:
        path = app_dir() / "BBDown.archives"
        log_debug("文件路径：%s", path)
        try:
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(f"{aid}|")
        except OSError as exc:  # pragma: no cover - 磁盘异常
            log_warn(f"写入下载记录失败: {exc}")


def check_aid_from_file(aid: str) -> bool:
    with _ARCHIVE_LOCK:
        path = app_dir() / "BBDown.archives"
        if not path.is_file():
            return False
        log_debug("文件路径：%s", path)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return False
        return aid in text.split("|")
