"""输入解析：URL / av / BV / ep / ss / md -> 内部使用的 aid 字符串。

对应 BBDown/BBDownUtil.cs 里的 GetAvIdAsync 及其辅助函数。
"""

from __future__ import annotations

import json
import re

from . import bv
from .config import Config
from .net import HTTPUtil
from .util import get_query_string

__all__ = ["get_av_id"]

AV_RE = re.compile(r"av(\d+)")
BV_RE = re.compile(r"[Bb][Vv]1(\w+)")
EP_RE = re.compile(r"/ep(\d+)")
SS_RE = re.compile(r"/ss(\d+)")
UID_RE = re.compile(r"space\.bilibili\.com/(\d+)")
GLOBAL_EP_RE = re.compile(r"\.bilibili\.tv/\w+/play/\d+/(\d+)")
BANGUMI_MD_RE = re.compile(r"bangumi/media/(md\d+)")
STATE_RE = re.compile(r"window\.__INITIAL_STATE__=([\s\S].*?);\(function\(\)")
MD_RE = re.compile(r"md(\d+)")

#: 用户从聊天软件/网页里粘过来的链接经常带各种引号和空白
_TRIM_CHARS = " \t\r\n\"'\u201c\u201d\u2018\u2019\u300c\u300d"
_SITE_MARKERS = ("bilibili.com", "b23.tv", "bili2233.cn", "biliintl.com")


def _normalize_input(raw: str) -> str:
    """去掉包裹的引号/空白；网址缺协议头时补上 ``https://``。"""
    text = raw.strip().strip(_TRIM_CHARS)
    lowered = text.lower()
    if not lowered.startswith(("http://", "https://")):
        if any(marker in lowered for marker in _SITE_MARKERS):
            return "https://" + text.lstrip("/")
    return text


def _search(pattern: re.Pattern[str], text: str, group: int = 1) -> str:
    match = pattern.search(text)
    return match.group(group) if match else ""


def get_av_id(raw_input: str) -> str:
    """把各种输入形式统一成 ``aid`` / ``ep:xxx`` / ``cheese:xxx`` / ``listBizId:xxx`` 等。"""
    text = _normalize_input(raw_input)
    avid = text

    if text.startswith("http"):
        if "b23.tv" in text:
            tmp = HTTPUtil.get_web_location(text)
            if tmp == text:
                raise RuntimeError("无限重定向")
            text = tmp

        if "video/av" in text:
            avid = _search(AV_RE, text)
        elif "video/bv" in text.lower():
            avid = str(bv.decode(_search(BV_RE, text)))
        elif "/cheese/" in text:
            if "/ep" in text:
                ep_id = _search(EP_RE, text)
            elif "/ss" in text:
                ep_id = _get_epid_by_ss_id(_search(SS_RE, text))
            else:
                ep_id = ""
            avid = f"cheese:{ep_id}"
        elif "/ep" in text:
            avid = f"ep:{_search(EP_RE, text)}"
        elif "/ss" in text:
            avid = f"ep:{_get_ep_id_by_bangumi_ss_id(_search(SS_RE, text))}"
        elif (
            "/medialist/" in text
            and "business_id=" in text
            and "business=space_collection" in text
        ):
            avid = f"listBizId:{get_query_string('business_id', text)}"
        elif "/medialist/" in text and "business_id=" in text and "business=space_series" in text:
            avid = f"seriesBizId:{get_query_string('business_id', text)}"
        elif "/channel/collectiondetail?sid=" in text:
            avid = f"listBizId:{get_query_string('sid', text)}"
        elif "/channel/seriesdetail?sid=" in text:
            avid = f"seriesBizId:{get_query_string('sid', text)}"
        elif "space.bilibili.com/" in text and "/lists/" in text:
            # 新版个人空间合集/系列链接：
            #   https://space.bilibili.com/392959666/lists/1560264?type=season
            #   https://space.bilibili.com/392959666/lists/1560264?type=series
            list_type = get_query_string("type", text).lower()
            path = re.split(r"[?#]", text)[0]
            sid = path[path.rfind("/") + 1 :]
            if list_type == "series":
                avid = f"seriesBizId:{sid}"
            else:
                # season 或未知类型都按合集处理
                avid = f"listBizId:{sid}"
        elif "space.bilibili.com/" in text and "/favlist" in text:
            mid = _search(UID_RE, text)
            fav_id = get_query_string("fid", text)
            avid = f"favId:{fav_id}:{mid}"
        elif "space.bilibili.com/" in text:
            avid = f"mid:{_search(UID_RE, text)}"
        elif "ep_id=" in text:
            avid = f"ep:{get_query_string('ep_id', text)}"
        elif GLOBAL_EP_RE.search(text):
            avid = f"ep:{_search(GLOBAL_EP_RE, text)}"
        elif BANGUMI_MD_RE.search(text):
            avid = f"ep:{_get_ep_id_by_md(_search(BANGUMI_MD_RE, text))}"
        else:
            web = HTTPUtil.get_web_source(text)
            match = STATE_RE.search(web)
            payload = json.loads(match.group(1)) if match else {}
            episodes = payload.get("epList") or []
            if not episodes:
                raise RuntimeError("输入有误")
            avid = f"ep:{episodes[0].get('id')}"

    elif text.lower().startswith("bv"):
        avid = str(bv.decode(text[3:]))
    elif text.lower().startswith("av"):
        avid = text.lower()[2:]
    elif text.startswith("cheese/"):
        # ^cheese/(ep|ss)\d+ 格式
        if "/ep" in text:
            ep_id = _search(EP_RE, text)
        elif "/ss" in text:
            ep_id = _get_epid_by_ss_id(_search(SS_RE, text))
        else:
            ep_id = ""
        avid = f"cheese:{ep_id}"
    elif text.startswith("ep"):
        avid = f"ep:{text[2:]}"
    elif text.startswith("ss"):
        avid = f"ep:{_get_ep_id_by_bangumi_ss_id(text[2:])}"
    elif text.startswith("md"):
        avid = f"ep:{_get_ep_id_by_md(_search(MD_RE, text))}"
    else:
        raise RuntimeError("输入有误")

    return _fix_avid(avid)


def _fix_avid(avid: str) -> str:
    """纯数字 aid 若不是普通稿件（版权内容），改成 ``ep:xxx``。"""
    if not avid.isdigit():
        return avid
    location = HTTPUtil.get_web_location(f"https://www.bilibili.com/video/av{avid}/")
    if "/ep" in location:
        return f"ep:{_search(EP_RE, location)}"
    return avid


def _get_epid_by_ss_id(ssid: str) -> str:
    """课程 ss -> 第一个 ep。"""
    payload = json.loads(
        HTTPUtil.get_web_source(f"https://api.bilibili.com/pugv/view/web/season?season_id={ssid}")
    )
    episodes = (payload.get("data") or {}).get("episodes") or []
    return str(episodes[0].get("id")) if episodes else ""


def _get_ep_id_by_bangumi_ss_id(ss_id: str) -> str:
    """番剧 ss -> 第一个 ep。"""
    payload = json.loads(
        HTTPUtil.get_web_source(f"https://{Config.EPHOST}/pgc/view/web/season?season_id={ss_id}")
    )
    episodes = (payload.get("result") or {}).get("episodes") or []
    return str(episodes[0].get("id")) if episodes else ""


def _get_ep_id_by_md(md_id: str) -> str:
    """番剧 md -> 最新一集 ep。"""
    payload = json.loads(
        HTTPUtil.get_web_source(f"https://api.bilibili.com/pgc/review/user?media_id={md_id}")
    )
    return str(((payload.get("result") or {}).get("media") or {}).get("new_ep", {}).get("id") or "")
