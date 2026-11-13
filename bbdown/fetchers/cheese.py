"""课程解析，对应 BBDown.Core/Fetcher/CheeseInfoFetcher.cs。"""

from __future__ import annotations

import json

from ..entity import Page, VInfo
from ..net import HTTPUtil
from ._common import as_int, as_text, iter_list


class CheeseInfoFetcher:
    def fetch(self, id: str) -> VInfo:
        ep_id = id[7:]  # 去掉 "cheese:"
        index = ""
        payload = json.loads(
            HTTPUtil.get_web_source(f"https://api.bilibili.com/pugv/view/web/season?ep_id={ep_id}")
        )
        data = payload.get("data") or {}

        cover = as_text(data, "cover")
        title = as_text(data, "title")
        desc = as_text(data, "subtitle")
        owner_name = as_text(data, "up_info", "uname")
        owner_mid = as_text(data, "up_info", "mid")

        pages_info: list[Page] = []
        for page in iter_list(data, "episodes"):
            item = Page(
                index=as_int(page, "index"),
                aid=as_text(page, "aid"),
                cid=as_text(page, "cid"),
                epid=as_text(page, "id"),
                title=as_text(page, "title").strip(),
                dur=as_int(page, "duration"),
                res="",
                pub_time=as_int(page, "release_date"),
                owner_name=owner_name,
                owner_mid=owner_mid,
            )
            if item.epid == ep_id:
                index = str(item.index)
            pages_info.append(item)

        pub_time = pages_info[0].pub_time if pages_info else 0

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
