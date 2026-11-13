"""混流（ffmpeg / mp4box）与 FLV 分段合并，对应 BBDown/BBDownMuxer.cs。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from .config import Config
from .console import log, log_debug
from .entity import AudioMaterial, Subtitle, ViewPoint
from .subtitle import get_subtitle_code
from .util import (
    combine_files,
    get_ffmpeg_meta_string,
    get_files,
    get_mp4box_meta_string,
)

__all__ = ["FFMPEG", "MP4BOX", "mux_av", "merge_flv", "run_exe"]

#: 可通过命令行覆盖的可执行文件路径
FFMPEG = "ffmpeg"
MP4BOX = "mp4box"


def run_exe(app: str, args: list[str]) -> int:
    """运行外部程序，把 stderr 逐行转发到日志。"""
    log_debug("%s %s", app, " ".join(args))
    try:
        process = subprocess.Popen(
            [app, *args],
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"找不到可执行文件: {app}") from exc

    assert process.stderr is not None
    for line in process.stderr:
        line = line.strip()
        if line:
            log(line)
    return process.wait()


def _escape(value: str) -> str:
    """元数据里的双引号换成单引号，避免破坏 ffmpeg/mp4box 的参数解析。"""
    if not value:
        return value
    return value.replace('"', "'")


def _chapters_path(video_path: str, audio_path: str) -> Path:
    base = video_path if video_path else audio_path
    return Path(base).parent / "chapters"


def mux_av(
    use_mp4box: bool,
    bvid: str,
    video_path: str,
    audio_path: str,
    audio_material: list[AudioMaterial],
    out_path: str,
    desc: str = "",
    title: str = "",
    author: str = "",
    episode_id: str = "",
    pic: str = "",
    lang: str = "",
    subs: list[Subtitle] | None = None,
    audio_only: bool = False,
    video_only: bool = False,
    points: list[ViewPoint] | None = None,
    pub_time: int = 0,
    simply_mux: bool = False,
    is_hevc: bool = False,
) -> int:
    """把音视频（+字幕+封面+章节）混流成 mp4，返回退出码。"""
    if audio_only and audio_path != "":
        video_path = ""
    if video_only:
        audio_path = ""

    desc = _escape(desc)
    title = _escape(title)
    episode_id = _escape(episode_id)
    url = f"https://www.bilibili.com/video/{bvid}/"

    if use_mp4box:
        return _mux_by_mp4box(
            url, video_path, audio_path, out_path, desc, title, author, episode_id, pic, lang, subs,
            audio_only, video_only, points,
        )

    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    args: list[str] = []
    meta: list[str] = []
    input_count = 0

    for path in (video_path, audio_path):
        if path:
            input_count += 1
            args.extend(["-i", path])

    if audio_material:
        audio_count = 0
        meta.extend(["-metadata:s:a:0", "title=原音频"])
        for item in audio_material:
            input_count += 1
            audio_count += 1
            args.extend(["-i", item.path])
            if item.title:
                meta.extend([f"-metadata:s:a:{audio_count}", f"title={item.title}"])
            if item.person_name:
                meta.extend([f"-metadata:s:a:{audio_count}", f"artist={item.person_name}"])

    if pic:
        input_count += 1
        args.extend(["-i", pic])

    subtitle_index = 0
    for sub in subs or []:
        if Path(sub.path).is_file() and Path(sub.path).stat().st_size > 0:
            input_count += 1
            args.extend(["-i", sub.path])
            code, name = get_subtitle_code(sub.lan)
            meta.extend([f"-metadata:s:s:{subtitle_index}", f"title={name}"])
            meta.extend([f"-metadata:s:s:{subtitle_index}", f"language={code}"])
            subtitle_index += 1

    if pic:
        meta.extend([f"-disposition:v:{0 if audio_only else 1}", "attached_pic"])

    if points:
        meta_file = _chapters_path(video_path, audio_path)
        meta_file.parent.mkdir(parents=True, exist_ok=True)
        meta_file.write_text(get_ffmpeg_meta_string(points), encoding="utf-8")
        args.extend(["-i", str(meta_file), "-map_chapters", str(input_count)])

    for i in range(input_count):
        args.extend(["-map", str(i)])

    final: list[str] = ["-loglevel", "verbose" if Config.DEBUG_LOG else "warning", "-y"]
    final.extend(args)
    final.extend(meta)

    if not simply_mux:
        final.extend(["-metadata", f"title={episode_id if episode_id else title}"])
        final.extend(["-metadata", f"comment={url}"])
        if lang:
            final.extend(["-metadata:s:a:0", f"language={lang}"])
        if desc:
            final.extend(["-metadata", f"description={desc}"])
        if author:
            final.extend(["-metadata", f"artist={author}"])
        if episode_id:
            final.extend(["-metadata", f"album={title}"])
        if pub_time:
            from datetime import datetime, timezone

            created = datetime.fromtimestamp(pub_time, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
            final.extend(["-metadata", f"creation_time={created}.000000Z"])

    final.extend(["-c:v", "copy", "-c:a", "copy"])
    if audio_only and audio_path == "":
        final.append("-vn")
    if subs is not None:
        final.extend(["-c:s", "mov_text"])
    # 修 macOS hev1 兼容性，见 https://discussions.apple.com/thread/253081863
    if sys.platform == "darwin" and is_hevc:
        final.extend(["-tag:v:0", "hvc1"])
    final.extend(["-movflags", "faststart", "-strict", "unofficial", "-strict", "-2", "-f", "mp4"])
    final.append(out_path)

    return run_exe(FFMPEG, final)


def _mux_by_mp4box(
    url: str,
    video_path: str,
    audio_path: str,
    out_path: str,
    desc: str,
    title: str,
    author: str,
    episode_id: str,
    pic: str,
    lang: str,
    subs: list[Subtitle] | None,
    audio_only: bool,
    video_only: bool,
    points: list[ViewPoint] | None,
) -> int:
    args: list[str] = ["-inter", "500", "-noprog"]
    meta_arg = ""
    now_id = 0

    if video_path:
        track_id = "2" if (audio_only and audio_path == "") else "1"
        args.extend(["-add", f'{video_path}#trackID={track_id}:name=" '])
        now_id += 1

    if audio_path:
        args.extend(["-add", f"{audio_path}:lang={lang or 'und'}"])
        now_id += 1

    if points:
        meta_file = _chapters_path(video_path, audio_path)
        meta_file.parent.mkdir(parents=True, exist_ok=True)
        meta_file.write_text(get_mp4box_meta_string(points), encoding="utf-8")
        args.extend(["-chap", str(meta_file)])

    if pic:
        meta_arg += f':cover="{pic}"'
    if episode_id:
        meta_arg += f':album="{title}":title="{episode_id}"'
    else:
        meta_arg += f':title="{title}"'
    meta_arg += f':sdesc="{desc}"'
    meta_arg += f':comment="{url}"'
    meta_arg += f':artist="{author}"'

    for sub in subs or []:
        if Path(sub.path).is_file() and Path(sub.path).stat().st_size > 0:
            now_id += 1
            code, name = get_subtitle_code(sub.lan)
            args.extend(["-add", f'{sub.path}#trackID=1:name=:hdlr=sbtl:lang={code}'])
            args.extend(["-udta", f'{now_id}:type=name:str="{name}"'])

    if Config.DEBUG_LOG:
        args.append("-v")
    if meta_arg:
        args.extend(["-itags", "tool=" + meta_arg])
    args.extend(["-new", "--", out_path])
    return run_exe(MP4BOX, args)


def merge_flv(files: list[str], out_path: str) -> None:
    """把 FLV 分段转成 ts 再拼接。"""
    if len(files) == 1:
        os.replace(files[0], out_path)
        return

    for file in files:
        tmp_file = str(Path(file).parent / (Path(file).stem + ".ts"))
        args = [
            "-loglevel", "warning", "-y", "-i", file, "-map", "0",
            "-c", "copy", "-f", "mpegts", "-bsf:v", "h264_mp4toannexb", tmp_file,
        ]
        log_debug("ffmpeg命令: %s", " ".join(args))
        run_exe(FFMPEG, args)
        try:
            os.remove(file)
        except OSError:
            pass

    ts_files = get_files(str(Path(files[0]).parent), ".ts")
    combine_files(ts_files, out_path)
    for name in ts_files:
        try:
            os.remove(name)
        except OSError:
            pass
