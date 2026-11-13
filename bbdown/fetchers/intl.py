"""国际版（东南亚）番剧解析，对应 BBDown.Core/Fetcher/IntlBangumiInfoFetcher.cs。"""

from __future__ import annotations

import json
import re

from ..config import Config
from ..entity import Page, VInfo
from ..net import HTTPUtil
from ._common import as_int, as_text, iter_list
from .bangumi import parse_pub_time

STATE_RE = re.compile(r"window\.__INITIAL_STATE__=([\s\S].*?);\(function\(\)")


class IntlBangumiInfoFetcher:
    def fetch(self, id: str) -> VInfo:
        ep_id = id[3:]  # 去掉 "ep:"
        index = ""

        host = "api.bilibili.tv" if Config.HOST == "api.bilibili.com" else Config.HOST
        api = (
            f"https://{host}/intl/gateway/v2/ogv/view/app/season?ep_id={ep_id}"
            "&platform=android&s_locale=zh_SG&mobi_app=bstar_a"
        )
        if Config.TOKEN != "":
            api += f"&access_key={Config.TOKEN}"

        payload = json.loads(HTTPUtil.get_web_source(api).replace("\\/", "/"))
        result = payload.get("result")
        if not isinstance(result, dict):
            # 与原版一致：拿不到 result 时抛出 KeyError，让上层回退到课程解析
            raise KeyError("Arg_KeyNotFound")

        season_id = as_text(result, "season_id")
        cover = as_text(result, "cover")
        title = as_text(result, "title")
        desc = as_text(result, "evaluate")

        if cover == "" and season_id:
            web = HTTPUtil.get_web_source(f"https://bangumi.bilibili.com/anime/{season_id}")
            if web:
                match = STATE_RE.search(web)
                if match:
                    try:
                        media = json.loads(match.group(1)).get("mediaInfo") or {}
                    except Exception:
                        media = {}
                    cover = as_text(media, "cover")
                    title = as_text(media, "title")
                    desc = as_text(media, "evaluate")

        pub_time = parse_pub_time(as_text(result, "publish", "pub_time"))

        pages = iter_list(result, "episodes")
        for section in iter_list(result, "modules"):
            if f"/{ep_id}" in json.dumps(section, ensure_ascii=False):
                pages = iter_list(section, "data", "episodes")
                break

        pages_info: list[Page] = []
        i = 1
        for page in pages:
            if as_text(page, "badge") == "预告":  # 跳过预告
                continue
            res = ""
            dimension = page.get("dimension")
            if isinstance(dimension, dict):
                res = f"{dimension.get('width', '')}x{dimension.get('height', '')}"
            title_text = f"{as_text(page, 'title')} {as_text(page, 'long_title')}".strip()
            item = Page(
                index=i,
                aid=as_text(page, "aid"),
                cid=as_text(page, "cid"),
                epid=as_text(page, "id"),
                title=title_text,
                dur=0,
                res=res,
                pub_time=as_int(page, "pub_time"),
            )
            i += 1
            if item.epid == ep_id:
                index = str(item.index)
            pages_info.append(item)

        return VInfo(
            title=title.strip(),
            desc=desc.strip(),
            pic=cover,
            pub_time=pub_time,
            pages_info=pages_info,
            is_bangumi=True,
            is_cheese=True,
            index=index,
        )
