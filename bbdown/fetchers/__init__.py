"""fetcher 工厂，对应 BBDown.Core/FetcherFactory.cs。"""

from __future__ import annotations

from ..entity import VInfo
from .bangumi import BangumiInfoFetcher
from .cheese import CheeseInfoFetcher
from .favlist import FavListFetcher
from .intl import IntlBangumiInfoFetcher
from .medialist import MediaListFetcher
from .normal import NormalInfoFetcher
from .series import SeriesListFetcher
from .space import SpaceVideoFetcher

__all__ = [
    "create_fetcher",
    "NormalInfoFetcher",
    "BangumiInfoFetcher",
    "CheeseInfoFetcher",
    "IntlBangumiInfoFetcher",
    "SpaceVideoFetcher",
    "MediaListFetcher",
    "SeriesListFetcher",
    "FavListFetcher",
]


def create_fetcher(aid_ori: str, use_intl_api: bool = False):
    """根据 aid 前缀挑选对应的解析器。"""
    if aid_ori.startswith("cheese"):
        return CheeseInfoFetcher()
    if aid_ori.startswith("ep"):
        return IntlBangumiInfoFetcher() if use_intl_api else BangumiInfoFetcher()
    if aid_ori.startswith("mid"):
        return SpaceVideoFetcher()
    if aid_ori.startswith("listBizId"):
        return MediaListFetcher()
    if aid_ori.startswith("seriesBizId"):
        return SeriesListFetcher()
    if aid_ori.startswith("favId"):
        return FavListFetcher()
    return NormalInfoFetcher()
