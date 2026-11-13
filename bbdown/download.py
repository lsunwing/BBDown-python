"""文件下载：单线程 / 多线程分片 / aria2c，对应 BBDown/BBDownDownloadUtil.cs。"""

from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from . import aria2c
from .config import Config
from .console import ProgressBar, log_debug
from .entity import Clip
from .net import HTTPUtil

__all__ = [
    "DownloadConfig",
    "download_file",
    "multi_thread_download_file",
    "get_all_clips",
    "replace_url",
]

PER_CLIP_SIZE = 20 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024 // 4


@dataclass
class DownloadConfig:
    use_aria2c: bool = False
    aria2c_args: str = ""
    force_http: bool = False
    multi_thread: bool = False
    related_task: object | None = None


def replace_url(url: str) -> str:
    """把 https 换成 http（部分 CDN 走 http 更稳）。"""
    if ".mcdn.bilivideo.cn:" in url:
        log_debug("对[*.mcdn.bilivideo.cn:xxx]域名不做处理")
        return url
    log_debug("将https更改为http")
    return url.replace("https:", "http:")


def _download_headers(url: str) -> dict[str, str]:
    headers = {"User-Agent": "Mozilla/5.0", "Cookie": Config.COOKIE}
    if "platform=android_tv_yst" not in url and "platform=android" not in url:
        headers["Referer"] = "https://www.bilibili.com"
    return headers


def _range_download_to_tmp(
    clip_id: int,
    url: str,
    tmp_name: str,
    from_position: int,
    to_position: int | None,
    on_progress,
    fail_on_range_not_supported: bool = False,
) -> None:
    """下载 ``from_position``-``to_position`` 区间，续传写入 ``tmp_name``。"""
    last_write_time = None
    if os.path.exists(tmp_name):
        last_write_time = os.path.getmtime(tmp_name)

    os.makedirs(os.path.dirname(tmp_name) or ".", exist_ok=True)
    mode = "r+b" if os.path.exists(tmp_name) else "w+b"
    with open(tmp_name, mode) as handle:
        handle.seek(0, os.SEEK_END)
        position = handle.tell()
        if to_position is not None and to_position > 0 and position == to_position - from_position + 1:
            # 已下载完成，直接汇报进度
            on_progress(clip_id, position, position)
            return

        downloaded = from_position + position
        headers = _download_headers(url)
        headers["Range"] = f"bytes={downloaded}-" if to_position is None else f"bytes={downloaded}-{to_position}"
        if last_write_time is not None:
            import email.utils

            headers["If-Range"] = email.utils.formatdate(last_write_time, usegmt=True)

        response = HTTPUtil.session().get(
            url, headers=headers, timeout=HTTPUtil.TIMEOUT, stream=True, allow_redirects=True
        )
        try:
            response.raise_for_status()
            if response.status_code == 200:  # 服务端没理 Range，只能从头下
                if fail_on_range_not_supported and (downloaded > 0 or to_position is not None):
                    raise NotImplementedError("Range request is not supported.")
                downloaded = 0
                handle.seek(0)
                handle.truncate()

            content_length = response.headers.get("Content-Length")
            total_bytes = downloaded + (int(content_length) if content_length is not None else 0)
            received = 0

            for chunk in response.iter_content(CHUNK_SIZE):
                if not chunk:
                    continue
                handle.write(chunk)
                handle.flush()
                received += len(chunk)
                downloaded += len(chunk)
                on_progress(clip_id, downloaded - from_position, total_bytes)

            if content_length is not None and received != int(content_length):
                raise IOError("Retry...")
        finally:
            response.close()


def download_file(url: str, path: str, config: DownloadConfig) -> None:
    """单线程下载一个文件（带 3 次重试）。"""
    if not url:
        return
    if config.force_http:
        url = replace_url(url)
    log_debug("Start downloading: %s", url)

    des_dir = os.path.dirname(path) or "."
    os.makedirs(des_dir, exist_ok=True)

    if config.use_aria2c:
        aria2c.download_file_by_aria2c(url, path, config.aria2c_args)
        if os.path.exists(path + ".aria2") or not os.path.exists(path):
            raise RuntimeError("aria2下载可能存在错误")
        print()
        return

    tmp_name = os.path.join(des_dir, os.path.splitext(os.path.basename(path))[0] + ".tmp")
    last_error: Exception | None = None
    for _ in range(3):
        try:
            with ProgressBar(config.related_task) as progress:
                _range_download_to_tmp(
                    0,
                    url,
                    tmp_name,
                    0,
                    None,
                    lambda _, downloaded, total: progress.report(
                        downloaded / total if total else 0.0, downloaded
                    ),
                )
            os.replace(tmp_name, path)
            return
        except Exception as exc:  # 失败重试
            last_error = exc
    raise last_error if last_error else RuntimeError("下载失败")


def get_all_clips(url: str, file_size: int) -> list[Clip]:
    """把文件切成 20MB 左右的分片（对应 GetAllClips）。"""
    clips: list[Clip] = []
    index = 0
    counter = 0
    remaining = file_size
    while remaining > 0:
        clip = Clip(index=index, from_=counter, to=counter + PER_CLIP_SIZE)
        if remaining - PER_CLIP_SIZE > 0:
            remaining -= PER_CLIP_SIZE
            counter += PER_CLIP_SIZE + 1
            index += 1
            clips.append(clip)
        else:
            clip.to = -1
            clips.append(clip)
            break
    return clips


def get_file_size(url: str) -> int:
    response = HTTPUtil.session().get(
        url,
        headers=_download_headers(url),
        timeout=HTTPUtil.TIMEOUT,
        stream=True,
        allow_redirects=True,
    )
    try:
        response.raise_for_status()
        return int(response.headers.get("Content-Length") or 0)
    finally:
        response.close()


def _clip_path(path: str, index: int) -> str:
    extension = ".vclip" if path.endswith(".mp4") else ".aclip"
    return os.path.join(
        os.path.dirname(path) or ".",
        f"{index:05d}_" + os.path.splitext(os.path.basename(path))[0] + extension,
    )


def multi_thread_download_file(url: str, path: str, config: DownloadConfig) -> list[str]:
    """多线程分片下载，返回各分片临时文件路径（按顺序）。"""
    if config.force_http:
        url = replace_url(url)
    log_debug("Start downloading: %s", url)

    if config.use_aria2c:
        aria2c.download_file_by_aria2c(url, path, config.aria2c_args)
        if os.path.exists(path + ".aria2") or not os.path.exists(path):
            raise RuntimeError("aria2下载可能存在错误")
        print()
        return []

    file_size = get_file_size(url)
    log_debug("文件大小：%s bytes", file_size)
    if file_size <= 0:
        raise RuntimeError(f"无法获取文件大小: {url}")

    if os.path.exists(path) and os.path.getsize(path) == file_size:
        log_debug("文件已下载过, 跳过下载")
        return []

    clips = get_all_clips(url, file_size)
    log_debug("分段数量：%s", len(clips))

    progress_lock = threading.Lock()
    clip_progress: dict[int, int] = {clip.index: 0 for clip in clips}
    tmp_names = {clip.index: _clip_path(path, clip.index) for clip in clips}

    with ProgressBar(config.related_task) as progress:
        progress.report(0.0, 0)

        def report(clip_id: int, downloaded: int, _total: int) -> None:
            with progress_lock:
                clip_progress[clip_id] = downloaded
                done = sum(clip_progress.values())
            progress.report(done / file_size if file_size else 0.0, done)

        def run_clip(clip: Clip) -> None:
            attempt = 0
            while True:
                try:
                    _range_download_to_tmp(
                        clip.index,
                        url,
                        tmp_names[clip.index],
                        clip.from_,
                        None if clip.to == -1 else clip.to,
                        report,
                        True,
                    )
                    return
                except NotImplementedError as exc:
                    attempt += 1
                    if attempt == 3:
                        raise RuntimeError(
                            "服务器可能并不支持多线程下载, 请使用 --multi-thread false 关闭多线程"
                        ) from exc
                except Exception as exc:
                    attempt += 1
                    if attempt == 3:
                        raise RuntimeError(f"Failed to download clip {clip.index}") from exc

        workers = min(16, max(4, os.cpu_count() or 4))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="clip") as pool:
            futures = [pool.submit(run_clip, clip) for clip in clips]
            for future in futures:
                future.result()

    return [tmp_names[clip.index] for clip in clips]
