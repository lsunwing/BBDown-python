"""全局运行时配置，对应 BBDown.Core/Config.cs。"""

from __future__ import annotations

__all__ = ["Config"]


class Config:
    """程序运行期共享的可变全局状态。

    直接以类属性方式读写（``Config.COOKIE = "..."``），与 C# 版的
    ``Config.COOKIE`` 用法保持一致。
    """

    #: 网页端鉴权用 cookie 字符串
    COOKIE: str = ""
    #: APP / TV 端鉴权用 access_token
    TOKEN: str = ""
    #: 是否输出调试日志
    DEBUG_LOG: bool = False
    #: BiliPlus host
    HOST: str = "api.bilibili.com"
    #: BiliPlus EP host
    EPHOST: str = "api.bilibili.com"
    #: TV 端接口 host
    TVHOST: str = "api.snm0516.aisee.tv"
    #: BiliPlus area (hk|tw|th)
    AREA: str = ""
    #: wbi 签名的 mixin key
    WBI: str = ""

    #: qn -> 清晰度名称。
    #:
    #: 顺序有意义：第一次键（``"127"``）是补解析时请求的最高清晰度。
    QUALITYS: dict[str, str] = {
        "127": "8K 超高清",
        "126": "杜比视界",
        "125": "HDR 真彩",
        "120": "4K 超清",
        "116": "1080P 高帧率",
        "112": "1080P 高码率",
        "100": "智能修复",
        "80": "1080P 高清",
        "74": "720P 高帧率",
        "64": "720P 高清",
        "48": "720P 高清",
        "32": "480P 清晰",
        "16": "360P 流畅",
        "5": "144P 流畅",
        "6": "240P 流畅",
    }

    @classmethod
    def quality_name(cls, qn: str) -> str:
        """把 qn 转成可读名称；未知 qn 原样返回而不是抛异常。"""
        return cls.QUALITYS.get(str(qn), str(qn))

    @classmethod
    def max_qn(cls) -> str:
        """最高清晰度对应的 qn（对应 C# 的 ``Config.qualitys.Keys.First()``）。"""
        return next(iter(cls.QUALITYS))
