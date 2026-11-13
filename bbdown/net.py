"""HTTP 请求封装，对应 BBDown.Core/Util/HTTPUtil.cs。"""

from __future__ import annotations

import random
import urllib.parse

import requests
import urllib3

from .config import Config
from .console import log_debug

__all__ = ["HTTPUtil", "REDIRECT_CODES"]

# 原项目同样关闭了证书校验，这里顺手压掉 urllib3 的告警，避免刷屏
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

REDIRECT_CODES = (301, 302, 303, 307, 308)

_PLATFORMS = ("Windows NT 10.0; Win64", "Macintosh; Intel Mac OS X 10_15", "X11; Linux x86_64")


def _random_version(low: float, high: float) -> str:
    return f"{random.uniform(low, high):.3f}"


def _random_user_agent() -> str:
    browsers = (
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/%s Safari/537.36" % _random_version(80, 110),
        "Gecko/20100101 Firefox/%s" % _random_version(80, 110),
    )
    return "Mozilla/5.0 (%s) %s" % (random.choice(_PLATFORMS), random.choice(browsers))


class HTTPUtil:
    """进程级共享的 HTTP 客户端。"""

    TIMEOUT = 120
    POOL_SIZE = 2048

    user_agent: str = _random_user_agent()

    _session: requests.Session | None = None

    @classmethod
    def session(cls) -> requests.Session:
        if cls._session is None:
            session = requests.Session()
            adapter = requests.adapters.HTTPAdapter(
                pool_connections=cls.POOL_SIZE,
                pool_maxsize=cls.POOL_SIZE,
                max_retries=0,
            )
            session.mount("http://", adapter)
            session.mount("https://", adapter)
            # 原项目关闭了证书校验（ServerCertificateCustomValidationCallback => true）
            session.verify = False
            session.headers.clear()
            cls._session = session
        return cls._session

    # -- 便捷方法 ---------------------------------------------------------
    @staticmethod
    def _cookie_for(url: str) -> str:
        cookie = Config.COOKIE or ""
        if "/ep" in url or "/ss" in url:
            return cookie + ";CURRENT_FNVAL=4048;"
        return cookie

    @classmethod
    def get_web_source(cls, url: str, user_agent: str | None = None) -> str:
        """GET 并返回文本内容。"""
        headers = {
            "User-Agent": user_agent or cls.user_agent,
            "Accept-Encoding": "gzip, deflate",
            "Cookie": cls._cookie_for(url),
            "Cache-Control": "no-cache",
        }
        if "api.bilibili.com" in url:
            headers["Referer"] = "https://www.bilibili.com/"
        if "api.bilibili.tv" in url:
            headers["sec-ch-ua"] = '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"'

        log_debug("获取网页内容: Url: %s, Headers: %s", url, headers)
        response = cls.session().get(url, headers=headers, timeout=cls.TIMEOUT)
        response.raise_for_status()
        text = response.content.decode("utf-8", "replace")
        log_debug("Response: %s", text)
        return text

    @classmethod
    def get_web_location(cls, url: str) -> str:
        """跟随重定向并返回最终地址。

        原实现用 HEAD；部分站点不支持 HEAD，这里退回 GET（只读响应头）。
        """
        headers = {
            "User-Agent": cls.user_agent,
            "Accept-Encoding": "gzip, deflate",
            "Cache-Control": "no-cache",
        }
        log_debug("获取网页重定向地址: Url: %s", url)
        session = cls.session()
        try:
            response = session.head(url, headers=headers, timeout=cls.TIMEOUT, allow_redirects=True)
            if response.status_code == 405 or response.status_code == 403:
                raise requests.HTTPError("HEAD not allowed")
            response.raise_for_status()
        except requests.RequestException:
            response = session.get(
                url, headers=headers, timeout=cls.TIMEOUT, allow_redirects=True, stream=True
            )
            response.raise_for_status()
            response.close()
        location = response.url
        log_debug("Location: %s", location)
        return location

    @classmethod
    def get_post_response(
        cls, url: str, post_data: bytes, headers: dict[str, str] | None = None
    ) -> bytes:
        """POST 二进制内容（gRPC），返回原始响应字节。"""
        import base64

        log_debug("Post to: %s, data: %s", url, base64.b64encode(post_data).decode("ascii"))

        request_headers: dict[str, str] = {"Content-Type": "application/grpc"}
        if headers:
            request_headers.update(headers)
        else:
            request_headers["User-Agent"] = (
                "Dalvik/2.1.0 (Linux; U; Android 6.0.1; oneplus a5010 Build/V417IR) 6.10.0 "
                "os/android model/oneplus a5010 mobi_app/android build/6100500 channel/bili "
                "innerVer/6100500 osVer/6.0.1 network/2"
            )
            request_headers["grpc-encoding"] = "gzip"

        response = cls.session().post(
            url, data=post_data, headers=request_headers, timeout=cls.TIMEOUT
        )
        response.raise_for_status()
        return response.content

    @classmethod
    def head_status(cls, url: str) -> int:
        """取 HTTP 状态码（用于探测 Range 支持）。"""
        response = cls.session().head(url, timeout=cls.TIMEOUT, allow_redirects=True)
        return response.status_code


def quote(value: str) -> str:
    return urllib.parse.quote(value, safe="")
