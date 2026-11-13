"""HTTP 服务器模式，对应 BBDown/BBDownApiServer.cs。

接口文档见项目根目录的 json-api-doc.md（响应字段沿用 PascalCase）。
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

from . import PROJECT_NAME, __version__
from . import aid as aid_module
from . import workflow
from .config import Config
from .console import log, log_color, log_debug, log_error, log_warn
from .options import MyOption

__all__ = ["serve", "DownloadTask"]

_DEFAULT_LISTEN = "http://0.0.0.0:23333"


class DownloadTask:
    """服务器模式的下载任务状态。"""

    FIELDS = (
        "Aid",
        "Url",
        "TaskCreateTime",
        "Title",
        "Pic",
        "VideoPubTime",
        "TaskFinishTime",
        "Progress",
        "DownloadSpeed",
        "TotalDownloadedBytes",
        "IsSuccessful",
        "SavePaths",
    )

    def __init__(self, aid: str, url: str, task_create_time: int) -> None:
        self.Aid = aid
        self.Url = url
        self.TaskCreateTime = task_create_time
        self.Title: str | None = None
        self.Pic: str | None = None
        self.VideoPubTime: int | None = None
        self.TaskFinishTime: int | None = None
        self.Progress = 0.0
        self.DownloadSpeed = 0.0
        self.TotalDownloadedBytes = 0.0
        self.IsSuccessful = False
        self.SavePaths: list[str] = []

    def to_dict(self) -> dict:
        return {name: getattr(self, name) for name in self.FIELDS}


_OPTION_LOOKUP = {name.replace("_", "").lower(): name for name in MyOption.__dataclass_fields__}


def option_from_json(payload: dict) -> MyOption:
    """把请求体（大小写不敏感的 camelCase / PascalCase）转成 MyOption。"""
    option = MyOption()
    for key, value in payload.items():
        field = _OPTION_LOOKUP.get(str(key).replace("_", "").lower())
        if field is None:
            log_debug("忽略未知字段: %s", key)
            continue
        setattr(option, field, value)
    return option


class _ServerState:
    def __init__(self) -> None:
        self.running: list[DownloadTask] = []
        self.finished: list[DownloadTask] = []
        self.lock = threading.Lock()

    def find(self, aid: str) -> DownloadTask | None:
        with self.lock:
            for task in self.running:
                if task.Aid == aid:
                    return task
            for task in self.finished:
                if task.Aid == aid:
                    return task
        return None

    def add_running(self, task: DownloadTask) -> None:
        with self.lock:
            self.running.append(task)

    def move_to_finished(self, task: DownloadTask) -> None:
        with self.lock:
            if task in self.running:
                self.running.remove(task)
            self.finished.append(task)


STATE = _ServerState()


def _run_task(option: MyOption, task: DownloadTask, callback: str | None) -> DownloadTask:
    try:
        setup = workflow.set_up_work(option)
        fetched_aid, v_info, api_type = workflow.get_video_info(option, setup.aid_ori, setup.input)
        task.Title = v_info.title
        task.Pic = v_info.pic
        task.VideoPubTime = v_info.pub_time
        workflow.download_pages(
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
            task,
        )
        task.IsSuccessful = True
    except Exception as exc:
        log_error(f"{task.Aid}下载失败")
        message = str(exc)
        if Config.DEBUG_LOG:
            import traceback

            message = traceback.format_exc()
        log_error(message + " 请尝试升级到最新版本后重试!")

    task.TaskFinishTime = int(time.time())
    if task.IsSuccessful:
        task.Progress = 1.0
        elapsed = max(1, task.TaskFinishTime - task.TaskCreateTime)
        task.DownloadSpeed = task.TotalDownloadedBytes / elapsed

    STATE.move_to_finished(task)

    if callback:
        try:
            import urllib.request

            body = json.dumps(task.to_dict(), ensure_ascii=False).encode("utf-8")
            request = urllib.request.Request(
                callback, data=body, headers={"Content-Type": "application/json"}
            )
            urllib.request.urlopen(request, timeout=30).close()
        except Exception as exc:  # 回调失败不影响主流程
            log_debug("回调失败: %s", exc)
    return task


def _add_task(payload: dict) -> None:
    option = option_from_json(payload)
    if not option.url:
        raise ValueError("输入有误")

    try:
        aid = aid_module.get_av_id(option.url)
    except Exception as exc:
        log_error(f"解析任务地址失败: {exc}")
        return

    with STATE.lock:
        for task in STATE.running:
            if task.Aid == aid:
                return

    task = DownloadTask(aid, option.url, int(time.time()))
    STATE.add_running(task)
    threading.Thread(
        target=_run_task,
        args=(option, task, option.call_back_web_hook),
        name=f"task-{aid}",
        daemon=True,
    ).start()


class _Handler(BaseHTTPRequestHandler):
    server_version = f"{PROJECT_NAME}/{__version__}"
    protocol_version = "HTTP/1.1"

    # -- 基础设施 ---------------------------------------------------------
    def log_message(self, fmt: str, *args) -> None:  # 关掉默认的访问日志噪音
        log_debug("HTTP " + fmt, *args)

    def _send_json(self, status: int, payload) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, status: int, text: str) -> None:
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()
        self.wfile.write(body)

    # -- 路由 -------------------------------------------------------------
    def do_OPTIONS(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler 约定
        self._send_text(200, "")

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path.rstrip("/") or "/"
        parts = [unquote(part) for part in path.split("/") if part]

        if parts[:1] != ["get-tasks"] and parts[:1] != ["remove-finished"]:
            self._send_text(404, "Not Found")
            return

        if parts[0] == "get-tasks":
            if len(parts) == 1:
                with STATE.lock:
                    payload = {
                        "Running": [task.to_dict() for task in STATE.running],
                        "Finished": [task.to_dict() for task in STATE.finished],
                    }
                self._send_json(200, payload)
                return
            if parts[1] == "running":
                with STATE.lock:
                    self._send_json(200, [task.to_dict() for task in STATE.running])
                return
            if parts[1] == "finished":
                with STATE.lock:
                    self._send_json(200, [task.to_dict() for task in STATE.finished])
                return

            task = STATE.find(parts[1])
            if task is None:
                self._send_text(404, "Not Found")
                return
            self._send_json(200, task.to_dict())
            return

        # remove-finished
        with STATE.lock:
            if len(parts) == 1:
                STATE.finished.clear()
            elif parts[1] == "failed":
                STATE.finished = [task for task in STATE.finished if task.IsSuccessful]
            else:
                STATE.finished = [task for task in STATE.finished if task.Aid != parts[1]]
        self._send_text(200, "OK")

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path != "/add-task":
            self._send_text(404, "Not Found")
            return

        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            self._send_text(400, "输入有误")
            return

        if not isinstance(payload, dict) or not payload.get("Url") and not payload.get("url"):
            self._send_text(400, "输入有误")
            return

        try:
            _add_task(payload)
        except Exception:
            self._send_text(400, "输入有误")
            return
        self._send_text(200, "OK")


def serve(listen_url: str = _DEFAULT_LISTEN) -> int:
    """启动 HTTP 服务器（阻塞）。"""
    parsed = urlparse(listen_url)
    if parsed.scheme != "http" or not parsed.hostname:
        log_error(f"{listen_url}不是合法的http URL，url示例：http://0.0.0.0:5000")
        log_error("如果您需要https，请额外配置反向代理")
        return 1

    host = parsed.hostname
    port = parsed.port or 23333
    server = ThreadingHTTPServer((host, port), _Handler)
    server.daemon_threads = True

    log_color(f"服务器已启动: http://{host}:{port}")
    log("按 Ctrl+C 退出")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log_warn("Force Exit...")
    finally:
        server.server_close()
    return 0
