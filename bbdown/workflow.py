"""主流程：解析参数 -> 取视频信息 -> 逐 P 下载混流。

对应 BBDown/Program.cs 与 BBDown/Program.Methods.cs。
"""

from __future__ import annotations

import os
import re
import shutil
import time
import traceback
from datetime import datetime
from pathlib import Path

from . import aid as aid_module
from . import aria2c, download, fetchers, muxer, playurl
from . import subtitle as subtitle_module
from .config import Config
from .console import log, log_banner, log_color, log_debug, log_error, log_warn
from .danmaku import parse_xml, save_as_ass
from .enums import ALL_FORMAT_NAMES, DEFAULT_FORMATS, DanmakuFormat, from_format_name
from .entity import Audio, AudioMaterial, Page, Subtitle, VInfo, Video
from .net import HTTPUtil
from .options import MyOption
from .util import (
    app_dir,
    check_aid_from_file,
    check_ffmpeg_dovi,
    check_login,
    combine_files,
    fetch_points,
    find_executable,
    format_file_size,
    format_time,
    format_timestamp,
    get_query_string,
    get_valid_filename,
    save_aid_to_file,
)

__all__ = ["do_work", "set_up_work", "get_video_info", "download_pages", "format_save_path"]

BACKUP_HOST = "upos-sz-mirrorcoso1.bilivideo.com"

SINGLE_PAGE_DEFAULT_SAVE_PATH = "<videoTitle>"
MULTI_PAGE_DEFAULT_SAVE_PATH = "<videoTitle>/[P<pageNumberWithZero>]<pageTitle>"

PCDN_RE = re.compile(r"://.*:\d+/")
AKAM_RE = re.compile(r"://.*akamaized\.net/")
UPOS_RE = re.compile(r"://[^/]+/")
INFO_RE = re.compile(r"<([\w:\-.]+?)>")


# ---------------------------------------------------------------------------
# 选项预处理
# ---------------------------------------------------------------------------


def handle_deprecated_options(option: MyOption) -> None:
    """兼容旧版本命令行参数并给出警告。"""
    global SINGLE_PAGE_DEFAULT_SAVE_PATH, MULTI_PAGE_DEFAULT_SAVE_PATH

    if option.add_dfn_subfix:
        log_warn("--add-dfn-subfix 已被弃用, 建议使用 --file-pattern/-F 或 --multi-file-pattern/-M 来自定义输出文件名格式")
        if not option.file_pattern and not option.multi_file_pattern:
            SINGLE_PAGE_DEFAULT_SAVE_PATH += "[<dfn>]"
            MULTI_PAGE_DEFAULT_SAVE_PATH += "[<dfn>]"
            log_warn(
                f'已切换至 -F "{SINGLE_PAGE_DEFAULT_SAVE_PATH}" -M "{MULTI_PAGE_DEFAULT_SAVE_PATH}"'
            )

    if option.aria2c_proxy:
        log_warn("--aria2c-proxy 已被弃用, 请使用 --aria2c-args 来设置aria2c代理, 本次执行已添加该代理")
        option.aria2c_args += f' --all-proxy="{option.aria2c_proxy}"'

    for flag, codec in (
        (option.only_hevc, "hevc"),
        (option.only_avc, "avc"),
        (option.only_av1, "av1"),
    ):
        if flag:
            log_warn(
                f"--only-{codec}/-{codec} 已被弃用, 请使用 --encoding-priority 来设置编码优先级, "
                f"本次执行已将{codec}设置为最高优先级"
            )
            option.encoding_priority = codec

    if option.no_padding_page_num:
        log_warn("--no-padding-page-num 已被弃用, 建议使用 --file-pattern/-F 或 --multi-file-pattern/-M 来自定义输出文件名格式")
        if not option.file_pattern and not option.multi_file_pattern:
            MULTI_PAGE_DEFAULT_SAVE_PATH = MULTI_PAGE_DEFAULT_SAVE_PATH.replace(
                "<pageNumberWithZero>", "<pageNumber>"
            )
            log_warn(f'已切换至 -M "{MULTI_PAGE_DEFAULT_SAVE_PATH}"')

    if option.bandwith_ascending:
        log_warn("--bandwith-ascending 已被弃用, 建议使用 --video-ascending 与 --audio-ascending 来指定视频或音频是否升序, 本次执行已将视频与音频均设为升序")
        option.video_ascending = True
        option.audio_ascending = True


def handle_conflicting_options(option: MyOption) -> None:
    # 手动选择时不能隐藏流
    if option.interactive:
        option.hide_streams = False
    # audio_only 和 video_only 同时开启则全部忽视
    if option.audio_only and option.video_only:
        option.audio_only = False
        option.video_only = False
    if option.skip_subtitle:
        option.sub_only = False


def parse_encoding_priority(option: MyOption) -> tuple[dict[str, int], str]:
    encoding_priority: dict[str, int] = {}
    first_encoding = ""
    if option.encoding_priority is not None:
        raw = option.encoding_priority.upper().replace("，", ",").replace("-", "").split(",")
        temp = [item.strip() for item in raw if item.strip()]
        if temp:
            first_encoding = temp[0]
            for index, encoding in enumerate(dict.fromkeys(temp)):
                encoding_priority[encoding] = index
    return encoding_priority, first_encoding


def parse_dfn_priority(option: MyOption) -> dict[str, int]:
    dfn_priority: dict[str, int] = {}
    if option.dfn_priority is not None:
        temp = [
            item.upper().strip()
            for item in option.dfn_priority.replace("，", ",").split(",")
            if item.strip()
        ]
        for index, dfn in enumerate(dict.fromkeys(temp)):
            dfn_priority[dfn] = index
    return dfn_priority


def parse_download_danmaku_formats(option: MyOption) -> list[DanmakuFormat]:
    if not option.download_danmaku_formats:
        return list(DEFAULT_FORMATS)

    names = [
        item.strip().lower()
        for item in option.download_danmaku_formats.replace("，", ",").split(",")
        if item.strip()
    ]
    if any(name not in ALL_FORMAT_NAMES for name in names):
        log_error(f"包含不支持的下载弹幕格式：{option.download_danmaku_formats}")
        return list(DEFAULT_FORMATS)
    return [from_format_name(name) for name in names]


def find_binaries(option: MyOption) -> None:
    """定位 ffmpeg / mp4box / aria2c。"""
    if option.ffmpeg_path and os.path.isfile(option.ffmpeg_path):
        muxer.FFMPEG = option.ffmpeg_path
    if option.mp4box_path and os.path.isfile(option.mp4box_path):
        muxer.MP4BOX = option.mp4box_path
    if option.aria2c_path and os.path.isfile(option.aria2c_path):
        aria2c.ARIA2C = option.aria2c_path

    if not option.skip_mux:
        if option.use_mp4box:
            if not muxer.MP4BOX or not os.path.isfile(muxer.MP4BOX):
                found = find_executable("mp4box") or find_executable("MP4box")
                if not found:
                    raise RuntimeError("找不到可执行的mp4box文件")
                muxer.MP4BOX = found
        elif not muxer.FFMPEG or not os.path.isfile(muxer.FFMPEG):
            found = find_executable("ffmpeg")
            if not found:
                raise RuntimeError("找不到可执行的ffmpeg文件")
            muxer.FFMPEG = found

    if option.use_aria2c:
        if not aria2c.ARIA2C or not os.path.isfile(aria2c.ARIA2C):
            found = find_executable("aria2c")
            if not found:
                raise RuntimeError("找不到可执行的aria2c文件")
            aria2c.ARIA2C = found


def change_working_dir(option: MyOption) -> None:
    if option.work_dir:
        option.work_dir = os.path.expandvars(option.work_dir)
        target = os.path.abspath(option.work_dir)
        os.makedirs(target, exist_ok=True)
        os.chdir(target)
        log_debug("切换工作目录至：%s", target)


def load_credentials(option: MyOption) -> None:
    """从程序目录加载 cookie / token。"""
    base = app_dir()

    cookie_file = base / "BBDown.data"
    if not Config.COOKIE and cookie_file.is_file():
        log("加载本地cookie...")
        log_debug("文件路径：%s", cookie_file)
        Config.COOKIE = cookie_file.read_text(encoding="utf-8", errors="replace")

    tv_file = base / "BBDownTV.data"
    if not Config.TOKEN and tv_file.is_file() and option.use_tv_api:
        log("加载本地token...")
        log_debug("文件路径：%s", tv_file)
        Config.TOKEN = tv_file.read_text(encoding="utf-8", errors="replace").replace("access_token=", "")

    app_file = base / "BBDownApp.data"
    if not Config.TOKEN and app_file.is_file() and option.use_app_api:
        log("加载本地token...")
        log_debug("文件路径：%s", app_file)
        Config.TOKEN = app_file.read_text(encoding="utf-8", errors="replace").replace("access_token=", "")


# ---------------------------------------------------------------------------
# 分 P 选择
# ---------------------------------------------------------------------------


def get_selected_pages(option: MyOption, v_info: VInfo, input_url: str) -> list[str] | None:
    """返回需要下载的分 P 序号列表；None 表示全部。"""
    select_page = option.select_page.upper().strip().strip(",")

    if not select_page:
        # 用户没指定分P时，根据 epid 或 query param 判断要下哪一集
        if v_info.index:
            log("程序已自动选择你输入的集数, 如果要下载其他集数请自行指定分P(如可使用-p ALL代表全部)")
            return [v_info.index]
        query_page = get_query_string("p", input_url)
        if query_page:
            log("程序已自动选择你输入的集数, 如果要下载其他集数请自行指定分P(如可使用-p ALL代表全部)")
            return [query_page]
        return None

    if select_page == "ALL":
        return None

    selected: list[str] = []
    last_page = str(len(v_info.pages_info))
    for key in ("LAST", "NEW", "LATEST"):
        select_page = select_page.replace(key, last_page)

    try:
        if "-" in select_page:
            start_text, end_text = select_page.split("-")[:2]
            for number in range(int(start_text), int(end_text) + 1):
                selected.append(str(number))
        else:
            selected.extend(select_page.split(","))
    except ValueError:
        log_error("解析分P参数时失败了~")
        return None
    return selected


# ---------------------------------------------------------------------------
# 轨道排序 / 展示 / CDN 处理
# ---------------------------------------------------------------------------


def sort_video_tracks(
    video_tracks: list[Video],
    dfn_priority: dict[str, int],
    encoding_priority: dict[str, int],
    video_ascending: bool,
) -> list[Video]:
    def by_dfn(video: Video) -> tuple:
        return (
            dfn_priority.get(video.dfn, 100),
            encoding_priority.get(video.codecs, 100),
            -int(video.id) if str(video.id).isdigit() else 0,
            video.bandwith if video_ascending else -video.bandwith,
        )

    def by_encoding(video: Video) -> tuple:
        return (
            encoding_priority.get(video.codecs, 100),
            dfn_priority.get(video.dfn, 100),
            -int(video.id) if str(video.id).isdigit() else 0,
            video.bandwith if video_ascending else -video.bandwith,
        )

    # 同时给了自定义分辨率与编码优先级时，按命令行里出现的先后顺序决定主次
    if dfn_priority and encoding_priority:
        import sys

        command_line = " ".join(sys.argv)
        encoding_first = command_line.find("--encoding-priority")
        dfn_first = command_line.find("--dfn-priority")
        if -1 < encoding_first < dfn_first:
            return sorted(video_tracks, key=by_encoding)
    return sorted(video_tracks, key=by_dfn)


def sort_audio_tracks(
    audio_tracks: list[Audio], encoding_priority: dict[str, int], audio_ascending: bool
) -> list[Audio]:
    return sorted(
        audio_tracks,
        key=lambda audio: (
            encoding_priority.get(audio.short_codecs, 100),
            audio.bandwith if audio_ascending else -audio.bandwith,
        ),
    )


def _track_size(bandwith: int, duration: int) -> str:
    return format_file_size(duration * bandwith * 1024 / 8)


def print_all_tracks_info(parsed, page_dur: int, only_show_info: bool) -> None:
    if parsed.background_audio_tracks and parsed.role_audio_list:
        log(f"共计{len(parsed.background_audio_tracks)}条背景音频流.")
        for index, audio in enumerate(parsed.background_audio_tracks):
            dur = page_dur or audio.dur
            log_color(f"{index}. [{audio.codecs}] [{audio.bandwith} kbps] [~{_track_size(audio.bandwith, dur)}]", False)
        log(f"共计{len(parsed.role_audio_list)}条配音, 每条包含{len(parsed.role_audio_list[0].audio)}条配音流.")
        for index, audio in enumerate(parsed.role_audio_list[0].audio):
            dur = page_dur or audio.dur
            log_color(f"{index}. [{audio.codecs}] [{audio.bandwith} kbps] [~{_track_size(audio.bandwith, dur)}]", False)

    if parsed.video_tracks:
        log(f"共计{len(parsed.video_tracks)}条视频流.")
        for index, video in enumerate(parsed.video_tracks):
            dur = page_dur or video.dur
            size = video.size if video.size > 0 else dur * video.bandwith * 1024 / 8
            text = (
                f"{index}. [{video.dfn}] [{video.res or ''}] [{video.codecs}] [{video.fps or ''}] "
                f"[{video.bandwith} kbps] [~{format_file_size(size)}]"
            ).replace("[] ", "")
            log_color(text, False)
            if only_show_info:
                print(video.base_url)

    if parsed.audio_tracks:
        log(f"共计{len(parsed.audio_tracks)}条音频流.")
        for index, audio in enumerate(parsed.audio_tracks):
            dur = page_dur or audio.dur
            log_color(
                f"{index}. [{audio.codecs}] [{audio.bandwith} kbps] [~{_track_size(audio.bandwith, dur)}]",
                False,
            )
            if only_show_info:
                print(audio.base_url)


def print_selected_track_info(
    selected_video: Video | None, selected_audio: Audio | None, page_dur: int
) -> None:
    if selected_video is not None:
        dur = page_dur or selected_video.dur
        size = (
            selected_video.size
            if selected_video.size > 0
            else dur * selected_video.bandwith * 1024 / 8
        )
        text = (
            f"[视频] [{selected_video.dfn}] [{selected_video.res or ''}] [{selected_video.codecs}] "
            f"[{selected_video.fps or ''}] [{selected_video.bandwith} kbps] [~{format_file_size(size)}]"
        ).replace("[] ", "")
        log_color(text, False)

    if selected_audio is not None:
        dur = page_dur or selected_audio.dur
        log_color(
            f"[音频] [{selected_audio.codecs}] [{selected_audio.bandwith} kbps] "
            f"[~{_track_size(selected_audio.bandwith, dur)}]",
            False,
        )


def _read_int() -> int:
    try:
        return int(input())
    except (ValueError, EOFError):
        return 0


def select_track_manually(parsed) -> tuple[int, int]:
    v_index = 0
    a_index = 0
    if parsed.video_tracks:
        log("请选择一条视频流(输入序号): ", False)
        v_index = _read_int()
        if v_index > len(parsed.video_tracks) or v_index < 0:
            v_index = 0
    if parsed.audio_tracks:
        log("请选择一条音频流(输入序号): ", False)
        a_index = _read_int()
        if a_index > len(parsed.audio_tracks) or a_index < 0:
            a_index = 0
    return v_index, a_index


def handle_pcdn(option: MyOption, selected_video: Video | None, selected_audio: Audio | None) -> None:
    """处理 PCDN / 海外源 / 自定义 upos。"""
    if option.upos_host == "":
        if not option.allow_pcdn:
            if selected_video is not None and PCDN_RE.search(selected_video.base_url):
                log_warn(f"检测到视频流为PCDN, 尝试强制替换为{BACKUP_HOST}……")
                selected_video.base_url = PCDN_RE.sub(f"://{BACKUP_HOST}/", selected_video.base_url)
            if selected_audio is not None and PCDN_RE.search(selected_audio.base_url):
                log_warn(f"检测到音频流为PCDN, 尝试强制替换为{BACKUP_HOST}……")
                selected_audio.base_url = PCDN_RE.sub(f"://{BACKUP_HOST}/", selected_audio.base_url)

        if selected_video is not None and Config.AREA != "" and "akamaized.net" in selected_video.base_url:
            log_warn(f"检测到视频流为外国源, 尝试强制替换为{BACKUP_HOST}……")
            selected_video.base_url = AKAM_RE.sub(f"://{BACKUP_HOST}/", selected_video.base_url)
        if selected_audio is not None and Config.AREA != "" and "akamaized.net" in selected_audio.base_url:
            log_warn(f"检测到音频流为外国源, 尝试强制替换为{BACKUP_HOST}……")
            selected_audio.base_url = AKAM_RE.sub(f"://{BACKUP_HOST}/", selected_audio.base_url)
    else:
        if selected_video is not None:
            log_warn(f"尝试将视频流强制替换为{option.upos_host}……")
            selected_video.base_url = UPOS_RE.sub(f"://{option.upos_host}/", selected_video.base_url)
        if selected_audio is not None:
            log_warn(f"尝试将音频流强制替换为{option.upos_host}……")
            selected_audio.base_url = UPOS_RE.sub(f"://{option.upos_host}/", selected_audio.base_url)


# ---------------------------------------------------------------------------
# 输出路径
# ---------------------------------------------------------------------------


def format_save_path(
    pattern: str,
    title: str,
    video_track: Video | None,
    audio_track: Audio | None,
    page: Page,
    pages_count: int,
    api_type: str,
    pub_time: int,
) -> str:
    """按用户模板生成保存路径（变量见 README）。"""
    result = pattern.replace("\\", "/")
    for match in list(INFO_RE.finditer(result)):
        key = match.group(1)

        # 解析自定义日期格式，如 <publishDate:yyyy-MM-dd>
        default_date_format = "yyyy-MM-dd_HH-mm-ss"
        for prefix in ("publishDate:", "videoDate:"):
            if key.startswith(prefix):
                default_date_format = key[key.index(":") + 1 :]
                key = prefix.replace(":", "")
                break

        if key == "videoTitle":
            value = get_valid_filename(title, filter_slash=True).strip().rstrip(".").strip()
        elif key == "pageNumber":
            value = str(page.index)
        elif key == "pageNumberWithZero":
            value = str(page.index).zfill(len(str(pages_count)))
        elif key == "pageTitle":
            value = get_valid_filename(page.title, filter_slash=True).strip().rstrip(".").strip()
        elif key == "bvid":
            value = page.bvid
        elif key in ("aid", "cid"):
            value = getattr(page, key)
        elif key == "ownerName":
            value = (
                ""
                if page.owner_name is None
                else get_valid_filename(page.owner_name, filter_slash=True).strip().rstrip(".").strip()
            )
        elif key == "ownerMid":
            value = page.owner_mid or ""
        elif key == "dfn":
            value = "" if video_track is None else video_track.dfn
        elif key == "res":
            value = "" if video_track is None else (video_track.res or "")
        elif key == "fps":
            value = "" if video_track is None else (video_track.fps or "")
        elif key == "videoCodecs":
            value = "" if video_track is None else video_track.codecs
        elif key == "videoBandwidth":
            value = "" if video_track is None else str(video_track.bandwith)
        elif key == "audioCodecs":
            value = "" if audio_track is None else audio_track.codecs
        elif key == "audioBandwidth":
            value = "" if audio_track is None else str(audio_track.bandwith)
        elif key == "publishDate":
            value = format_timestamp(pub_time, default_date_format)
        elif key == "videoDate":
            value = format_timestamp(page.pub_time, default_date_format)
        elif key == "apiType":
            value = api_type
        else:
            value = f"<{key}>"

        result = result.replace(match.group(0), value)

    if not result.endswith(".mp4"):
        result += ".mp4"
    return result


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------


def download_track(url: str, dest_path: str, config: download.DownloadConfig, video: bool) -> None:
    """下载一条轨道（多线程分片或单线程）。"""
    kind = "视频" if video else "音频"
    if config.multi_thread and "-cmcc-" not in url:
        clips = download.multi_thread_download_file(url, dest_path, config)
        log(f"合并{kind}分片...")
        if clips:
            combine_files(clips, dest_path)
        log("清理分片...")
        for leftover in Path(dest_path).parent.glob("*.?clip"):
            try:
                leftover.unlink()
            except OSError:
                pass
    else:
        if config.multi_thread and "-cmcc-" in url:
            log_warn("检测到cmcc域名cdn, 已经禁用多线程")
            config.force_http = False
        download.download_file(url, dest_path, config)


def _cleanup_dir(directory: str) -> None:
    try:
        if os.path.isdir(directory) and not os.listdir(directory):
            os.rmdir(directory)
    except OSError:
        pass


def _remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def _read_text(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _tail_cover(selected_pages_info: list[Page], page: Page, cover_path: str) -> None:
    """只在最后一集/最后一个分P 时删封面。"""
    last = selected_pages_info[-1]
    if len(selected_pages_info) == 1 or page.index == last.index or page.aid != last.aid:
        _remove(cover_path)


# ---------------------------------------------------------------------------
# 单个分 P
# ---------------------------------------------------------------------------


def download_page(
    page: Page,
    option: MyOption,
    v_info: VInfo,
    selected_pages_info: list[Page],
    encoding_priority: dict[str, int],
    dfn_priority: dict[str, int],
    first_encoding: str,
    download_danmaku_flag: bool,
    danmaku_formats: list[DanmakuFormat],
    input_url: str,
    save_path_format: str,
    lang: str,
    aid_ori: str,
    api_type: str,
    related_task=None,
) -> None:
    """下载并混流单个分 P（失败自动重试 2 次）。"""
    desc = page.desc if page.desc else v_info.desc
    bangumi = v_info.is_bangumi
    pages_count = len(selected_pages_info)
    subtitle_info: list[Subtitle] = []
    title = v_info.title
    pic = v_info.pic
    pub_time = v_info.pub_time
    selected = False
    v_index = 0
    a_index = 0
    retry_count = 0

    while True:
        try:
            log_debug("尝试获取章节信息...")
            page.points = fetch_points(page.cid, page.aid)

            video_path = f"{page.aid}/{page.aid}.P{page.index}.{page.cid}.mp4"
            audio_path = f"{page.aid}/{page.aid}.P{page.index}.{page.cid}.m4a"
            cover_path = f"{page.aid}/{page.aid}.jpg"

            # 处理文件夹以 . 开头 / 结尾导致的异常
            if title.endswith("."):
                title += "_fix"
            if title.startswith("."):
                title = "_" + title

            # ---- 封面与字幕 -------------------------------------------------
            if not option.only_show_info:
                os.makedirs(page.aid, exist_ok=True)

                if (
                    not option.skip_cover
                    and not option.sub_only
                    and not os.path.exists(cover_path)
                    and not option.danmaku_only
                    and not option.cover_only
                ):
                    download.download_file(
                        pic or page.cover or "", cover_path, download.DownloadConfig()
                    )

                if not option.skip_subtitle and not option.danmaku_only and not option.cover_only:
                    log_debug("获取字幕...")
                    subtitle_info = subtitle_module.get_subtitles(
                        page.aid, page.cid, page.epid, page.index, option.use_intl_api
                    )
                    if option.skip_ai and subtitle_info:
                        log("跳过下载AI字幕")
                        subtitle_info = [s for s in subtitle_info if not s.lan.startswith("ai-")]

                    for item in subtitle_info:
                        log(f"下载字幕 {item.lan} => {subtitle_module.get_subtitle_code(item.lan)[1]}...")
                        log_debug("下载：%s", item.url)
                        subtitle_module.save_subtitle(item.url, item.path)
                        if option.sub_only and os.path.exists(item.path) and _read_text(item.path) != "":
                            out_path = format_save_path(
                                save_path_format, title, None, None, page, pages_count, api_type, pub_time
                            )
                            if "/" in out_path:
                                os.makedirs(out_path.split("/")[0], exist_ok=True)
                            out_path = os.path.splitext(out_path)[0] + f".{item.lan}.srt"
                            os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
                            if os.path.exists(out_path):
                                os.remove(out_path)
                            shutil.move(item.path, out_path)

                if option.sub_only:
                    _cleanup_dir(page.aid)
                    return

            # ---- 解析 -------------------------------------------------------
            parsed = playurl.extract_tracks(
                aid_ori,
                page.aid,
                page.cid,
                page.epid,
                option.use_tv_api,
                option.use_intl_api,
                option.use_app_api,
                first_encoding,
            )
            audio_material: list[AudioMaterial] = []
            if not page.points:
                page.points = parsed.extra_points

            if Config.DEBUG_LOG:
                debug_name = datetime.now().strftime("debug_%Y%m%d%H%M%S%f") + ".json"
                Path(debug_name).write_text(parsed.web_json_string, encoding="utf-8")

            save_path = ""
            download_config = download.DownloadConfig(
                use_aria2c=option.use_aria2c,
                aria2c_args=option.aria2c_args,
                force_http=option.force_http,
                multi_thread=option.multi_thread,
                related_task=related_task,
            )

            if (parsed.video_tracks or parsed.audio_tracks) and not parsed.clips:
                # ================= DASH =====================================
                if not parsed.video_tracks:
                    log_warn("没有找到符合要求的视频流")
                    if option.video_only:
                        return
                if not parsed.audio_tracks:
                    log_warn("没有找到符合要求的音频流")
                    if option.audio_only:
                        return

                if option.audio_only:
                    parsed.video_tracks.clear()
                if option.video_only:
                    parsed.audio_tracks.clear()
                    parsed.background_audio_tracks.clear()
                    parsed.role_audio_list.clear()

                parsed.video_tracks = sort_video_tracks(
                    parsed.video_tracks, dfn_priority, encoding_priority, option.video_ascending
                )
                parsed.audio_tracks = sort_audio_tracks(
                    parsed.audio_tracks, encoding_priority, option.audio_ascending
                )
                parsed.background_audio_tracks = sort_audio_tracks(
                    parsed.background_audio_tracks, encoding_priority, option.audio_ascending
                )
                for role in parsed.role_audio_list:
                    role.audio = sort_audio_tracks(role.audio, encoding_priority, option.audio_ascending)

                if not option.hide_streams:
                    print_all_tracks_info(parsed, page.dur, option.only_show_info)

                if option.only_show_info:
                    return

                if option.interactive and not selected:
                    v_index, a_index = select_track_manually(parsed)
                    selected = True

                selected_video = (
                    parsed.video_tracks[v_index] if v_index < len(parsed.video_tracks) else None
                )
                selected_audio = (
                    parsed.audio_tracks[a_index] if a_index < len(parsed.audio_tracks) else None
                )
                selected_background_audio = (
                    parsed.background_audio_tracks[a_index]
                    if a_index < len(parsed.background_audio_tracks)
                    else None
                )

                log_debug("Format Before: %s", save_path_format)
                save_path = format_save_path(
                    save_path_format,
                    title,
                    selected_video,
                    selected_audio,
                    page,
                    pages_count,
                    api_type,
                    pub_time,
                )
                log_debug("Format After: %s", save_path)

                # 弹幕
                if download_danmaku_flag:
                    danmaku_xml_path = os.path.splitext(save_path)[0] + ".xml"
                    danmaku_ass_path = os.path.splitext(save_path)[0] + ".ass"
                    log("正在下载弹幕Xml文件")
                    download.download_file(
                        f"https://comment.bilibili.com/{page.cid}.xml", danmaku_xml_path, download_config
                    )
                    danmakus = parse_xml(danmaku_xml_path)
                    if danmakus is None:
                        log("弹幕Xml解析失败, 删除Xml...")
                        _remove(danmaku_xml_path)
                    elif not danmakus:
                        log("当前视频没有弹幕, 删除Xml...")
                        _remove(danmaku_xml_path)
                    elif DanmakuFormat.ASS in danmaku_formats:
                        log("正在保存弹幕Ass文件...")
                        save_as_ass(danmakus, danmaku_ass_path)

                    if DanmakuFormat.XML not in danmaku_formats:
                        _remove(danmaku_xml_path)

                    if option.danmaku_only:
                        _cleanup_dir(page.aid)
                        return

                # 仅封面
                if option.cover_only:
                    cover_url = pic or page.cover or ""
                    new_cover_path = os.path.splitext(save_path)[0] + os.path.splitext(cover_url)[1]
                    download.download_file(cover_url, new_cover_path, download_config)
                    _cleanup_dir(page.aid)
                    if related_task is not None:
                        related_task.SavePaths.append(new_cover_path)

                log("已选择的流:")
                print_selected_track_info(selected_video, selected_audio, page.dur)

                # 用户开启了强制替换
                if option.force_replace_host and not option.upos_host:
                    option.upos_host = BACKUP_HOST

                handle_pcdn(option, selected_video, selected_audio)

                if (
                    not option.only_show_info
                    and os.path.exists(save_path)
                    and os.path.getsize(save_path) != 0
                ):
                    log(f"{save_path}已存在, 跳过下载...")
                    if related_task is not None:
                        related_task.SavePaths.append(save_path)
                    _remove(cover_path)
                    _cleanup_dir(page.aid)
                    return

                if selected_video is not None:
                    # 杜比视界：ffmpeg 版本过低时改用 mp4box
                    if (
                        selected_video.dfn == Config.QUALITYS["126"]
                        and not option.use_mp4box
                        and not check_ffmpeg_dovi(muxer.FFMPEG)
                    ):
                        log_warn("检测到杜比视界清晰度且您的ffmpeg版本小于5.0,将使用mp4box混流...")
                        option.use_mp4box = True
                    log(f"开始下载P{page.index}视频...")
                    download_track(selected_video.base_url, video_path, download_config, True)

                if selected_audio is not None:
                    log(f"开始下载P{page.index}音频...")
                    download_track(selected_audio.base_url, audio_path, download_config, False)

                if selected_background_audio is not None:
                    background_path = f"{page.aid}/{page.aid}.{page.cid}.P{page.index}.back_ground.m4a"
                    log(f"开始下载P{page.index}背景配音...")
                    download_track(
                        selected_background_audio.base_url, background_path, download_config, False
                    )
                    audio_material.append(AudioMaterial("背景音频", "", background_path))

                if parsed.role_audio_list:
                    for role in parsed.role_audio_list:
                        log(f"开始下载P{page.index}配音[{role.title}]...")
                        if a_index < len(role.audio):
                            download_track(role.audio[a_index].base_url, role.path, download_config, False)
                            audio_material.append(AudioMaterial(role.title, role.person_name, role.path))

                log(f"下载P{page.index}完毕")
                if not parsed.video_tracks:
                    video_path = ""
                if not parsed.audio_tracks:
                    audio_path = ""
                if option.skip_mux:
                    return

                log(f"开始合并音视频{'和字幕' if subtitle_info else ''}...")
                if option.audio_only:
                    save_path = save_path[:-4] + ".m4a"

                is_hevc = selected_video is not None and selected_video.codecs == "HEVC"
                code = muxer.mux_av(
                    option.use_mp4box,
                    page.bvid,
                    video_path,
                    audio_path,
                    audio_material,
                    save_path,
                    desc,
                    title,
                    page.owner_name or "",
                    page.title if (pages_count > 1 or (bangumi and not v_info.is_bangumi_end)) else "",
                    cover_path if os.path.exists(cover_path) else "",
                    lang,
                    subtitle_info,
                    option.audio_only,
                    option.video_only,
                    page.points,
                    page.pub_time,
                    option.simply_mux,
                    is_hevc,
                )
                if code != 0 or not os.path.exists(save_path) or os.path.getsize(save_path) == 0:
                    log_error("合并失败")
                    return

                log("清理临时文件...")
                time.sleep(0.2)
                if parsed.video_tracks:
                    _remove(video_path)
                if parsed.audio_tracks:
                    _remove(audio_path)
                if page.points:
                    _remove(os.path.join(os.path.dirname(video_path or audio_path), "chapters"))
                for item in subtitle_info:
                    _remove(item.path)
                for material in audio_material:
                    _remove(material.path)
                _tail_cover(selected_pages_info, page, cover_path)
                _cleanup_dir(page.aid)

            elif parsed.clips and parsed.dfns:
                # ================= FLV (durl) ===============================
                flag = False
                clips = parsed.clips
                dfns = parsed.dfns
                reparse = True
                while reparse:
                    reparse = False
                    parsed.video_tracks = sort_video_tracks(
                        parsed.video_tracks, dfn_priority, encoding_priority, option.video_ascending
                    )
                    if option.interactive and not flag and not selected:
                        for index, key in enumerate(dfns):
                            log_color(f"{index}.{Config.quality_name(key)}")
                        log("请选择最想要的清晰度(输入序号): ", False)
                        v_index = _read_int()
                        if v_index > len(dfns) or v_index < 0:
                            v_index = 0
                        # 重新解析
                        parsed.video_tracks.clear()
                        parsed = playurl.extract_tracks(
                            aid_ori,
                            page.aid,
                            page.cid,
                            page.epid,
                            option.use_tv_api,
                            option.use_intl_api,
                            option.use_app_api,
                            first_encoding,
                            dfns[v_index],
                        )
                        if not page.points:
                            page.points = parsed.extra_points
                        flag = True
                        selected = True
                        reparse = True
                        continue

                log(f"共计{len(parsed.video_tracks)}条流(共有{len(clips)}个分段).")
                for index, video in enumerate(parsed.video_tracks):
                    text = (
                        f"{index}. [{video.dfn}] [{video.res or ''}] [{video.codecs}] "
                        f"[{video.fps or ''}] "
                        f"[~{video.size / 1024 / video.dur * 8:0.0f} kbps] [{format_file_size(video.size)}]"
                        if video.dur
                        else f"{index}. [{video.dfn}] [{video.res or ''}] [{video.codecs}] "
                        f"[{video.fps or ''}] [{format_file_size(video.size)}]"
                    ).replace("[] ", "")
                    log_color(text, False)
                    if option.only_show_info:
                        for clip in clips:
                            print(clip)
                if option.only_show_info:
                    return

                selected_video = (
                    parsed.video_tracks[v_index] if v_index < len(parsed.video_tracks) else None
                )
                save_path = format_save_path(
                    save_path_format,
                    title,
                    selected_video,
                    None,
                    page,
                    pages_count,
                    api_type,
                    pub_time,
                )
                if os.path.exists(save_path) and os.path.getsize(save_path) != 0:
                    log(f"{save_path}已存在, 跳过下载...")
                    if related_task is not None:
                        related_task.SavePaths.append(save_path)
                    if len(selected_pages_info) == 1:
                        _cleanup_dir(page.aid)
                    return

                padding = len(str(len(clips)))
                segment_paths: list[str] = []
                for index, link in enumerate(clips):
                    segment_path = (
                        f"{page.aid}/{page.aid}.P{page.index}.{page.cid}.{index:0{padding}d}.mp4"
                    )
                    log(f"开始下载P{page.index}视频, 片段({index + 1:0{padding}d}/{len(clips)})...")
                    download_track(link, segment_path, download_config, True)
                    segment_paths.append(segment_path)

                log(f"下载P{page.index}完毕")
                log("开始合并分段...")
                video_path = f"{page.aid}/{page.aid}.P{page.index}.{page.cid}.mp4"
                muxer.merge_flv(segment_paths, video_path)

                if option.skip_mux:
                    return

                log(f"开始混流视频{'和字幕' if subtitle_info else ''}...")
                if option.audio_only:
                    save_path = save_path[:-4] + ".m4a"

                code = muxer.mux_av(
                    False,
                    page.bvid,
                    video_path,
                    "",
                    audio_material,
                    save_path,
                    desc,
                    title,
                    page.owner_name or "",
                    page.title if (pages_count > 1 or (bangumi and not v_info.is_bangumi_end)) else "",
                    cover_path if os.path.exists(cover_path) else "",
                    lang,
                    subtitle_info,
                    option.audio_only,
                    option.video_only,
                    page.points,
                    page.pub_time,
                    option.simply_mux,
                )
                if code != 0 or not os.path.exists(save_path) or os.path.getsize(save_path) == 0:
                    log_error("合并失败")
                    return

                log("清理临时文件...")
                time.sleep(0.2)
                if parsed.video_tracks:
                    _remove(video_path)
                for item in subtitle_info:
                    _remove(item.path)
                for material in audio_material:
                    _remove(material.path)
                if page.points:
                    _remove(os.path.join(os.path.dirname(video_path or audio_path), "chapters"))
                _tail_cover(selected_pages_info, page, cover_path)
                _cleanup_dir(page.aid)

            else:
                log_error("解析此分P失败(建议--debug查看详细信息)")
                if len(parsed.web_json_string) < 100:
                    log_error(parsed.web_json_string)
                log_debug("%s", parsed.web_json_string)

            if save_path and save_path.strip() and related_task is not None:
                related_task.SavePaths.append(save_path)
            return

        except Exception as exc:
            retry_count += 1
            if retry_count > 2:
                raise
            log_error(str(exc))
            log_warn("下载出现异常, 3秒后将进行自动重试...")
            time.sleep(3)


# ---------------------------------------------------------------------------
# 多个分 P
# ---------------------------------------------------------------------------


def download_pages(
    option: MyOption,
    v_info: VInfo,
    encoding_priority: dict[str, int],
    dfn_priority: dict[str, int],
    first_encoding: str,
    download_danmaku_flag: bool,
    danmaku_formats: list[DanmakuFormat],
    input_url: str,
    save_path_format: str,
    lang: str,
    aid_ori: str,
    delay: int,
    api_type: str,
    related_task=None,
) -> None:
    pages_info = list(v_info.pages_info)
    bangumi = v_info.is_bangumi
    selected_pages = get_selected_pages(option, v_info, input_url)

    log(
        f"共计 {len(pages_info)} 个分P, 已选择："
        + ("ALL" if selected_pages is None else ",".join(selected_pages))
    )
    pages_count = len(pages_info)

    if selected_pages is not None:
        pages_info = [page for page in pages_info if str(page.index) in selected_pages]

    # 根据 P 数选择存储路径：多 P，或只有 1P 但番剧尚未完结，都按多 P 处理
    save_path_format = option.file_pattern or SINGLE_PAGE_DEFAULT_SAVE_PATH
    if pages_count > 1 or (bangumi and not v_info.is_bangumi_end):
        save_path_format = option.multi_file_pattern or MULTI_PAGE_DEFAULT_SAVE_PATH

    for position, page in enumerate(pages_info):
        if len(pages_info) > 1 and delay > 0:
            log(f"停顿{delay}秒...")
            time.sleep(delay)

        log(f"开始解析P{page.index}: {page.aid}... ({position + 1} of {len(pages_info)})")

        if option.save_archives_to_file and check_aid_from_file(page.aid):
            log(f"aid: {page.aid}已下载过, 跳过下载...")
            continue

        download_page(
            page,
            option,
            v_info,
            pages_info,
            encoding_priority,
            dfn_priority,
            first_encoding,
            download_danmaku_flag,
            danmaku_formats,
            input_url,
            save_path_format,
            lang,
            aid_ori,
            api_type,
            related_task,
        )

        if option.save_archives_to_file:
            save_aid_to_file(page.aid)

    log("任务完成")


# ---------------------------------------------------------------------------
# 顶层流程
# ---------------------------------------------------------------------------


class SetupResult:
    """set_up_work 的返回值。"""

    __slots__ = (
        "encoding_priority",
        "dfn_priority",
        "first_encoding",
        "download_danmaku",
        "danmaku_formats",
        "input",
        "save_path_format",
        "lang",
        "aid_ori",
        "delay",
    )

    def __init__(self, **kwargs) -> None:
        for name in self.__slots__:
            setattr(self, name, kwargs[name])


def set_up_work(option: MyOption) -> SetupResult:
    handle_deprecated_options(option)
    handle_conflicting_options(option)
    find_binaries(option)
    change_working_dir(option)

    encoding_priority, first_encoding = parse_encoding_priority(option)
    dfn_priority = parse_dfn_priority(option)

    if option.user_agent:
        HTTPUtil.user_agent = option.user_agent

    download_danmaku = option.download_danmaku or option.danmaku_only
    danmaku_formats = parse_download_danmaku_formats(option)

    try:
        delay = int(option.delay_per_page or 0)
    except ValueError:
        log_warn(f"无法解析 --delay-per-page 的取值: {option.delay_per_page}, 按 0 处理")
        delay = 0

    Config.DEBUG_LOG = option.debug
    Config.HOST = option.host
    Config.EPHOST = option.ep_host
    Config.TVHOST = option.tv_host
    Config.AREA = option.area
    Config.COOKIE = option.cookie
    Config.TOKEN = option.access_token.replace("access_token=", "")

    log_debug("AppDirectory: %s", app_dir())
    log_debug("运行参数：%s", option.to_camel_dict())

    return SetupResult(
        encoding_priority=encoding_priority,
        dfn_priority=dfn_priority,
        first_encoding=first_encoding,
        download_danmaku=download_danmaku,
        danmaku_formats=danmaku_formats,
        input=option.url,
        save_path_format=option.file_pattern,
        lang=option.language,
        aid_ori="",
        delay=delay,
    )


def get_video_info(option: MyOption, aid_ori: str, input_url: str) -> tuple[str, VInfo, str]:
    load_credentials(option)

    # 检测是否登录了账号
    if not option.use_intl_api and not option.use_tv_api and Config.AREA == "":
        log("检测账号登录...")
        if not check_login(Config.COOKIE):
            log_warn("你尚未登录B站账号, 解析可能受到限制")

    log("获取aid...")
    aid_ori = aid_module.get_av_id(input_url)
    log(f"获取aid结束: {aid_ori}")

    if not aid_ori:
        raise RuntimeError("输入有误")

    log("获取视频信息...")
    fetcher = fetchers.create_fetcher(aid_ori, option.use_intl_api)
    try:
        v_info = fetcher.fetch(aid_ori)
    except KeyError:
        # 只输入 EP/SS 时优先按番剧查找，找不到再尝试按课程查找
        if aid_ori.startswith("cheese:"):
            raise
        log_warn("未找到此 EP/SS 对应番剧信息, 正在尝试按课程查找。")
        aid_ori = aid_ori.replace("ep", "cheese")
        log("新的 aid: " + aid_ori)
        if not aid_ori:
            raise RuntimeError("输入有误") from None
        log("获取视频信息...")
        fetcher = fetchers.create_fetcher(aid_ori, option.use_intl_api)
        v_info = fetcher.fetch(aid_ori)

    title = v_info.title
    pub_time = v_info.pub_time
    log_color("视频标题: " + title)
    if pub_time:
        log("发布时间: " + format_timestamp(pub_time, "yyyy-MM-dd HH:mm:ss zzz"))

    bvid = v_info.pages_info[0].bvid if v_info.pages_info else ""
    if bvid and not option.use_intl_api:
        log(f"视频URL: https://www.bilibili.com/video/{bvid}/")

    mid = next(
        (page.owner_mid for page in v_info.pages_info if page.owner_mid), None
    )
    if mid:
        log(f"UP主页: https://space.bilibili.com/{mid}")

    if v_info.is_stein_gate and option.use_tv_api:
        log("视频为互动视频，暂时不支持tv下载，修改为默认下载")
        option.use_tv_api = False

    api_type = (
        "TV"
        if option.use_tv_api
        else ("APP" if option.use_app_api else ("INTL" if option.use_intl_api else "WEB"))
    )

    # 打印分P信息
    pages_info = v_info.pages_info
    more = False
    for page in pages_info:
        if not option.show_all:
            if more and page.index != len(pages_info):
                continue
            if not more and page.index > 5:
                log("......")
                more = True
                continue
        log(f"P{page.index}: [{page.cid}] [{page.title}] [{format_time(page.dur)}]")

    return aid_ori, v_info, api_type


def do_work(option: MyOption) -> int:
    """执行一次完整下载任务，返回进程退出码。"""
    try:
        setup = set_up_work(option)
        fetched_aid, v_info, api_type = get_video_info(option, setup.aid_ori, setup.input)
        download_pages(
            option,
            v_info,
            setup.encoding_priority,
            setup.dfn_priority,
            setup.first_encoding,
            setup.download_danmaku,
            setup.danmaku_formats,
            setup.input,
            setup.save_path_format,
            setup.lang,
            fetched_aid,
            setup.delay,
            api_type,
        )
        return 0
    except Exception as exc:
        message = traceback.format_exc() if Config.DEBUG_LOG else str(exc)
        log_banner(message + os.linesep + "请尝试升级到最新版本后重试!")
        return 1
