"""个人空间投稿解析，对应 BBDown.Core/Fetcher/SpaceVideoFetcher.cs。

原项目并不直接下载 UP 主的全部投稿，而是抓出全部地址写进 txt，让用户自行批处理。
这里保持同样的行为。
"""

from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path

from .. import playurl
from ..console import log
from ..net import HTTPUtil
from ..util import get_valid_filename
from ._common import as_int, as_text, iter_list

PAGE_SIZE = 50


class SpaceVideoFetcher:
    def fetch(self, id: str):  # noqa: ANN201 - 保持与其它 fetcher 相同的签名
        mid = id[4:]  # 去掉 "mid:"
        user_info = json.loads(
            HTTPUtil.get_web_source(f"https://api.live.bilibili.com/live_user/v1/Master/info?uid={mid}")
        )
        user_name = get_valid_filename(
            as_text(user_info, "data", "info", "uname"), ".", filter_slash=True
        )

        urls: list[str] = []
        page_number = 1
        first = json.loads(HTTPUtil.get_web_source(self._api(mid, page_number)))
        urls.extend(self._collect(first))

        total_count = as_int(first, "data", "page", "count")
        total_page = math.ceil(total_count / PAGE_SIZE)
        while page_number < total_page:
            page_number += 1
            urls.extend(self._collect(json.loads(HTTPUtil.get_web_source(self._api(mid, page_number)))))

        out_path = Path(f"{user_name}的投稿视频.txt")
        out_path.write_text(os.linesep.join(urls), encoding="utf-8")

        log("目前下载器不支持下载用户的全部投稿视频，不过程序已经获取到了该用户的全部投稿视频地址，"
            "你可以自行使用批处理脚本等手段调用本程序进行批量下载。如在Windows系统你可以使用如下代码：")
        print()
        print("@echo Off")
        print('For /F %%a in (urls.txt) Do (bbdown "%%a")')
        print("pause")
        print()
        raise RuntimeError("暂不支持该功能")

    @staticmethod
    def _api(mid: str, page_number: int) -> str:
        query = playurl.wbi_sign(
            f"mid={mid}&order=pubdate&pn={page_number}&ps={PAGE_SIZE}&tid=0&wts={int(time.time())}"
        )
        return f"https://api.bilibili.com/x/space/wbi/arc/search?{query}"

    @staticmethod
    def _collect(payload: dict) -> list[str]:
        return [
            f"https://www.bilibili.com/video/av{as_text(item, 'aid')}"
            for item in iter_list(payload, "data", "list", "vlist")
        ]
