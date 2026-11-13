"""普通投稿视频解析，对应 BBDown.Core/Fetcher/NormalInfoFetcher.cs。"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET

from ..entity import Page, VInfo
from ..net import HTTPUtil
from ._common import as_int, as_text, iter_list

EP_ID_RE = re.compile(r"ep(\d+)")


class NormalInfoFetcher:
    def fetch(self, id: str) -> VInfo:
        api = f"https://api.bilibili.com/x/web-interface/view?aid={id}"
        payload = json.loads(HTTPUtil.get_web_source(api))
        if payload.get("code", 0) != 0:
            raise RuntimeError(
                f"获取视频信息失败(code={payload.get('code')}): {payload.get('message', '未知错误')}"
            )
        data = payload.get("data") or {}

        title = as_text(data, "title")
        desc = as_text(data, "desc")
        pic = as_text(data, "pic")
        owner_mid = as_text(data, "owner", "mid")
        owner_name = as_text(data, "owner", "name")
        pub_time = as_int(data, "pubdate")
        bvid = as_text(data, "bvid")
        cid = as_text(data, "cid")
        is_stein_gate = as_int(data, "rights", "is_stein_gate")

        pages_raw = iter_list(data, "pages")
        pages_info: list[Page] = []
        for page in pages_raw:
            pages_info.append(
                Page(
                    index=as_int(page, "page"),
                    aid=str(id),
                    cid=as_text(page, "cid"),
                    epid="",
                    title=as_text(page, "part").strip(),
                    dur=as_int(page, "duration"),
                    res=f"{as_int(page, 'dimension', 'width')}x{as_int(page, 'dimension', 'height')}",
                    pub_time=pub_time,  # 分P视频没有独立发布时间
                    owner_name=owner_name,
                    owner_mid=owner_mid,
                )
            )

        if is_stein_gate == 1 and bvid:
            pages_info.extend(self._fetch_interactive_pages(id, bvid, cid, pub_time, owner_name, owner_mid))

        bangumi = False
        try:
            redirect_url = as_text(data, "redirect_url")
            if "bangumi" in redirect_url:
                bangumi = True
                match = EP_ID_RE.search(redirect_url)
                ep_id = match.group(1) if match else ""
                # 番剧内容通常不会有分P，如果有分P则不需要 epId
                if len(pages_raw) == 1 and ep_id:
                    for page in pages_info:
                        page.epid = ep_id
        except Exception:
            pass

        return VInfo(
            title=title.strip(),
            desc=desc.strip(),
            pic=pic,
            pub_time=pub_time,
            pages_info=pages_info,
            is_bangumi=bangumi,
            is_stein_gate=is_stein_gate == 1,
        )

    @staticmethod
    def _fetch_interactive_pages(
        id: str, bvid: str, cid: str, pub_time: int, owner_name: str, owner_mid: str
    ) -> list[Page]:
        """互动视频：从 player.so 拿到 graph_version，再取选项作为分P。"""
        player_so = HTTPUtil.get_web_source(
            f"https://api.bilibili.com/x/player.so?bvid={bvid}&id=cid:{cid}"
        )
        try:
            root = ET.fromstring(f"<root>{player_so}</root>")
        except ET.ParseError as exc:
            raise RuntimeError("互动视频获取分P信息失败") from exc

        interaction = root.find(".//interaction")
        text = (interaction.text or "") if interaction is not None else ""
        if not text:
            raise RuntimeError("互动视频获取分P信息失败")

        graph_version = as_int(json.loads(text), "graph_version")
        edge_json = json.loads(
            HTTPUtil.get_web_source(
                f"https://api.bilibili.com/x/stein/edgeinfo_v2?graph_version={graph_version}&bvid={bvid}"
            )
        )
        questions = iter_list(edge_json, "data", "edges", "questions")

        pages: list[Page] = []
        index = 2  # 互动视频分P索引从2开始
        for question in questions:
            for choice in iter_list(question, "choices"):
                pages.append(
                    Page(
                        index=index,
                        aid=str(id),
                        cid=as_text(choice, "cid"),
                        epid="",
                        title=as_text(choice, "option").strip(),
                        dur=0,
                        res="",
                        pub_time=pub_time,
                        owner_name=owner_name,
                        owner_mid=owner_mid,
                    )
                )
                index += 1
        return pages
