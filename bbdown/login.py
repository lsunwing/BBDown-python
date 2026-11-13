"""扫码登录，对应 BBDown/BBDownLoginUtil.cs。"""

from __future__ import annotations

import json
import time
from pathlib import Path

from .console import log, log_color, log_error
from .net import HTTPUtil
from .util import (
    app_dir,
    get_query_string,
    get_sign,
    get_time_stamp,
    get_tv_login_params,
    to_query_string,
)

__all__ = ["login_web", "login_tv"]

QR_PNG = "qrcode.png"


def _try_import_qrcode():
    try:
        import qrcode  # noqa: F401

        return qrcode
    except ImportError:
        return None


def _save_qr_png(text: str, path: str) -> bool:
    qrcode = _try_import_qrcode()
    if qrcode is None:
        return False
    image = qrcode.make(text, error_correction=qrcode.constants.ERROR_CORRECT_Q, box_size=7)
    image.save(path)
    return True


def _print_console_qr(text: str) -> None:
    """在终端里画出二维码；没有 qrcode 依赖时退化为打印链接。"""
    qrcode = _try_import_qrcode()
    if qrcode is None:
        log("未安装 qrcode 依赖，无法生成二维码；请手动打开下面的链接扫码：")
        print(text)
        return

    code = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_Q, border=1)
    code.add_data(text)
    code.make(fit=True)
    for row in code.get_matrix():
        print("".join("██" if cell else "  " for cell in row))


def _remove_quietly(path: str) -> None:
    try:
        Path(path).unlink()
    except OSError:
        pass


def _post_form(url: str, params: dict[str, str]) -> str:
    response = HTTPUtil.session().post(url, data=params, timeout=HTTPUtil.TIMEOUT)
    response.raise_for_status()
    return response.content.decode("utf-8", "replace")


def login_web() -> int:
    """扫码登录网页账号，成功后把 cookie 写入 BBDown.data。"""
    try:
        log("获取登录地址...")
        payload = json.loads(
            HTTPUtil.get_web_source(
                "https://passport.bilibili.com/x/passport-login/web/qrcode/generate?source=main-fe-header"
            )
        )
        url = (payload.get("data") or {}).get("url", "")
        qrcode_key = get_query_string("qrcode_key", url)
        if not url or not qrcode_key:
            log_error("获取登录二维码失败")
            return 1

        log("生成二维码...")
        if _save_qr_png(url, QR_PNG):
            log(f"生成二维码成功: {QR_PNG}, 请打开并扫描, 或扫描打印的二维码")
        else:
            log("生成二维码图片需要 qrcode 依赖, 可直接扫描下方的终端二维码")
        _print_console_qr(url)

        scanned = False
        while True:
            time.sleep(1)
            data = json.loads(
                HTTPUtil.get_web_source(
                    "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"
                    f"?qrcode_key={qrcode_key}&source=main-fe-header"
                )
            ).get("data") or {}
            code = data.get("code")
            if code == 86038:
                log_color("二维码已过期, 请重新执行登录指令.")
                break
            if code == 86101:  # 等待扫码
                continue
            if code == 86090:  # 等待确认
                if not scanned:
                    log("扫码成功, 请确认...")
                    scanned = True
                continue

            cookie_url = data.get("url", "")
            log("登录成功: SESSDATA=" + get_query_string("SESSDATA", cookie_url))
            # 导出 cookie, 转义英文逗号, 否则部分场景会出问题
            cookie = cookie_url[cookie_url.index("?") + 1 :].replace("&", ";").replace(",", "%2C")
            (app_dir() / "BBDown.data").write_text(cookie, encoding="utf-8")
            _remove_quietly(QR_PNG)
            break
    except Exception as exc:
        log_error(str(exc))
        return 1
    return 0


def login_tv() -> int:
    """扫码登录 TV 账号，成功后把 access_token 写入 BBDownTV.data。"""
    try:
        login_url = "https://passport.snm0516.aisee.tv/x/passport-tv-login/qrcode/auth_code"
        poll_url = "https://passport.bilibili.com/x/passport-tv-login/qrcode/poll"

        params = get_tv_login_params()
        log("获取登录地址...")
        payload = json.loads(_post_form(login_url, params))
        url = (payload.get("data") or {}).get("url", "")
        auth_code = str((payload.get("data") or {}).get("auth_code", ""))
        if not url or not auth_code:
            log_error("获取登录二维码失败")
            return 1

        log("生成二维码...")
        if _save_qr_png(url, QR_PNG):
            log(f"生成二维码成功: {QR_PNG}, 请打开并扫描, 或扫描打印的二维码")
        else:
            log("生成二维码图片需要 qrcode 依赖, 可直接扫描下方的终端二维码")
        _print_console_qr(url)

        params["auth_code"] = auth_code
        params["ts"] = get_time_stamp(True)
        params.pop("sign", None)
        params["sign"] = get_sign(to_query_string(params))

        while True:
            time.sleep(1)
            data = json.loads(_post_form(poll_url, params))
            code = str(data.get("code", ""))
            if code == "86038":
                log_color("二维码已过期, 请重新执行登录指令.")
                break
            if code == "86039":  # 等待扫码
                continue

            token = (data.get("data") or {}).get("access_token", "")
            log("登录成功: AccessToken=" + str(token))
            (app_dir() / "BBDownTV.data").write_text(f"access_token={token}", encoding="utf-8")
            _remove_quietly(QR_PNG)
            break
    except Exception as exc:
        log_error(str(exc))
        return 1
    return 0
