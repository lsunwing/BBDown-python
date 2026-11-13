"""番剧解析，对应 BBDown.Core/Fetcher/BangumiInfoFetcher.cs。"""

from __future__ import annotations

import json
from datetime import datetime

from ..config import Config
from ..entity import Page, VInfo
from ..net import HTTPUtil
from ._common import as_int, as_text, iter_list


def parse_pub_time(value: str) -> int:
    if not value:
        return 0
    try:
        return int(datetime.strptime(value, "%Y-%m-%d %H:%M:%S").timestamp())
    except ValueError:
        return 0


class BangumiInfoFetcher:
    def fetch(self, id: str) -> VInfo:
        ep_id = id[3:]  # 去掉 "ep:"
        index = ""
        payload = json.loads(
            HTTPUtil.get_web_source(f"https://{Config.EPHOST}/pgc/view/web/season?ep_id={ep_id}")
        )
        result = payload.get("result")
        if not isinstance(result, dict):
            # 与原版一致：拿不到 result 时抛出 KeyError，让上层回退到课程解析
            raise KeyError("Arg_KeyNotFound")

        cover = as_text(result, "cover")
        title = as_text(result, "title")
        desc = as_text(result, "evaluate")
        pub_time = parse_pub_time(as_text(result, "publish", "pub_time"))

        episodes = iter_list(result, "episodes")

        # episodes 为空，或未包含对应 epId（番外/花絮之类）
        if not (episodes and f"/ep{ep_id}" in json.dumps(result.get("episodes"), ensure_ascii=False)):
            for section in iter_list(result, "section"):
                if f"/ep{ep_id}" in json.dumps(section, ensure_ascii=False):
                    title += "[" + as_text(section, "title") + "]"
                    episodes = iter_list(section, "episodes")
                    break

        pages_info: list[Page] = []
        i = 1
        for page in episodes:
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
