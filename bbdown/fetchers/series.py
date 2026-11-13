"""系列（列表）解析，对应 BBDown.Core/Fetcher/SeriesListFetcher.cs。

https://space.bilibili.com/{mid}/channel/seriesdetail?sid=340933
"""

from __future__ import annotations

import json

from ..entity import Page, VInfo
from ..net import HTTPUtil
from ._common import as_text, iter_list


class SeriesListFetcher:
    def fetch(self, id: str) -> VInfo:
        biz_id = id[12:]  # 去掉 "seriesBizId:"
        payload = json.loads(
            HTTPUtil.get_web_source(
                f"https://api.bilibili.com/x/v1/medialist/info?type=5&biz_id={biz_id}&tid=0"
            )
        )
        data = payload.get("data") or {}
        title = as_text(data, "title")
        intro = as_text(data, "intro")
        pub_time = int(data.get("ctime") or 0)

        pages_info: list[Page] = []
        has_more = True
        oid = ""
        index = 1
        while has_more:
            list_api = (
                "https://api.bilibili.com/x/v2/medialist/resource/list"
                f"?type=5&oid={oid}&otype=2&biz_id={biz_id}&bvid=&with_current=true"
                "&mobi_app=web&ps=20&direction=false&sort_field=1&tid=0&desc=true"
            )
            payload = json.loads(HTTPUtil.get_web_source(list_api))
            data = payload.get("data")
            if not isinstance(data, dict):
                code = payload.get("code", 0)
                message = payload.get("message", "未知错误")
                raise RuntimeError(f"获取系列视频列表失败(code={code}): {message}")

            has_more = bool(data.get("has_more"))
            for media in iter_list(data, "media_list"):
                if media.get("attr") is not None and int(media["attr"]) != 0:
                    continue

                page_count = int(media.get("page") or 0)
                desc = str(media.get("intro") or "")
                owner_name = as_text(media, "upper", "name")
                owner_mid = as_text(media, "upper", "mid")
                for page in iter_list(media, "pages"):
                    if page_count == 1:
                        page_title = str(media.get("title") or "")
                    else:
                        page_title = (
                            f"{media.get('title')}_P{page.get('page')}_{page.get('title')}"
                        )
                    dimension = page.get("dimension") or {}
                    item = Page(
                        index=index,
                        aid=str(media.get("id") or ""),
                        cid=str(page.get("id") or ""),
                        epid="",
                        title=page_title,
                        dur=int(page.get("duration") or 0),
                        res=f"{dimension.get('width', '')}x{dimension.get('height', '')}",
                        pub_time=int(media.get("pubtime") or 0),
                        cover=str(media.get("cover") or ""),
                        desc=desc,
                        owner_name=owner_name,
                        owner_mid=owner_mid,
                    )
                    if item not in pages_info:
                        pages_info.append(item)
                        index += 1
                oid = str(media.get("id") or "")

        return VInfo(
            title=title.strip(),
            desc=intro.strip(),
            pic="",
            pub_time=pub_time,
            pages_info=pages_info,
            is_bangumi=False,
        )
