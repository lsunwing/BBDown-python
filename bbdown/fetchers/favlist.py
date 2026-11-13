"""收藏夹解析，对应 BBDown.Core/Fetcher/FavListFetcher.cs。"""

from __future__ import annotations

import json
import math

from ..entity import Page, VInfo
from ..net import HTTPUtil
from ._common import as_text, iter_list
from .normal import NormalInfoFetcher

PAGE_SIZE = 20


class FavListFetcher:
    def fetch(self, id: str) -> VInfo:
        spec = id[6:]  # 去掉 "favId:"
        parts = spec.split(":")
        fav_id = parts[0]
        mid = parts[1] if len(parts) > 1 else ""

        if fav_id == "":
            payload = json.loads(
                HTTPUtil.get_web_source(
                    f"https://api.bilibili.com/x/v3/fav/folder/created/list-all?up_mid={mid}"
                )
            )
            folders = iter_list(payload, "data", "list")
            fav_id = str(folders[0].get("id")) if folders else ""

        url = (
            f"https://api.bilibili.com/x/v3/fav/resource/list?media_id={fav_id}&pn=1"
            f"&ps={PAGE_SIZE}&order=mtime&type=2&tid=0&platform=web"
        )
        payload = json.loads(HTTPUtil.get_web_source(url))
        data = payload.get("data") or {}
        total_count = int((data.get("info") or {}).get("media_count") or 0)
        total_page = math.ceil(total_count / PAGE_SIZE)
        info = data.get("info") or {}
        title = as_text(info, "title")
        intro = as_text(info, "intro")
        pub_time = int(info.get("ctime") or 0)

        medias = list(iter_list(data, "medias"))
        for page in range(2, total_page + 1):
            url = (
                f"https://api.bilibili.com/x/v3/fav/resource/list?media_id={fav_id}&pn={page}"
                f"&ps={PAGE_SIZE}&order=mtime&type=2&tid=0&platform=web"
            )
            payload = json.loads(HTTPUtil.get_web_source(url))
            medias.extend(iter_list(payload, "data", "medias"))

        pages_info: list[Page] = []
        index = 1
        normal_fetcher = NormalInfoFetcher()
        for media in medias:
            if int(media.get("attr") or 0) != 0:  # 只处理未失效的视频
                continue

            page_count = int(media.get("page") or 0)
            if page_count > 1:
                tmp_info = normal_fetcher.fetch(str(media.get("id") or ""))
                for sub in tmp_info.pages_info:
                    item = Page(
                        index=index,
                        aid=sub.aid,
                        cid=sub.cid,
                        epid=sub.epid,
                        title=f"{media.get('title')}_P{sub.index}_{sub.title}",
                        dur=sub.dur,
                        res=sub.res,
                        pub_time=sub.pub_time,
                        cover=tmp_info.pic,
                        desc=str(media.get("intro") or ""),
                        owner_name=sub.owner_name,
                        owner_mid=sub.owner_mid,
                    )
                    if item not in pages_info:
                        pages_info.append(item)
                    index += 1
            else:
                item = Page(
                    index=index,
                    aid=str(media.get("id") or ""),
                    cid=as_text(media, "ugc", "first_cid"),
                    epid="",
                    title=str(media.get("title") or ""),
                    dur=int(media.get("duration") or 0),
                    res="",
                    pub_time=int(media.get("pubtime") or 0),
                    cover=str(media.get("cover") or ""),
                    desc=str(media.get("intro") or ""),
                    owner_name=as_text(media, "upper", "name"),
                    owner_mid=as_text(media, "upper", "mid"),
                )
                if item not in pages_info:
                    pages_info.append(item)
                index += 1

        return VInfo(
            title=title.strip(),
            desc=intro.strip(),
            pic="",
            pub_time=pub_time,
            pages_info=pages_info,
            is_bangumi=False,
        )
