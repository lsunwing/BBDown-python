"""数据实体，对应 BBDown.Core/Entity/{Entity,VInfo,ParsedResult}.cs。"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import bv

__all__ = [
    "Page",
    "ViewPoint",
    "Video",
    "Audio",
    "Subtitle",
    "Clip",
    "AudioMaterial",
    "AudioMaterialInfo",
    "VInfo",
    "ParsedResult",
]


@dataclass(eq=False)
class Page:
    """一个分 P（或番剧的一集）。"""

    index: int
    aid: str
    cid: str
    epid: str
    title: str
    dur: int
    res: str
    pub_time: int
    cover: str | None = None
    desc: str | None = None
    owner_name: str | None = None
    owner_mid: str | None = None
    points: list["ViewPoint"] = field(default_factory=list)

    @property
    def bvid(self) -> str:
        try:
            return bv.encode(int(self.aid))
        except Exception:
            return ""

    # 与 C# 一致：以 (aid, cid, epid) 判等，用于去重
    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, Page)
            and self.aid == other.aid
            and self.cid == other.cid
            and self.epid == other.epid
        )

    def __hash__(self) -> int:
        return hash((self.aid, self.cid, self.epid))


@dataclass(eq=False)
class ViewPoint:
    """章节 / 看点。"""

    title: str
    start: int
    end: int


@dataclass(eq=False)
class Video:
    id: str
    dfn: str
    base_url: str
    codecs: str
    bandwith: int = 0
    res: str | None = None
    fps: str | None = None
    dur: int = 0
    size: float = 0.0

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, Video)
            and self.id == other.id
            and self.dfn == other.dfn
            and self.res == other.res
            and self.fps == other.fps
            and self.codecs == other.codecs
            and self.bandwith == other.bandwith
            and self.dur == other.dur
        )

    def __hash__(self) -> int:
        return hash((self.id, self.dfn, self.res, self.fps, self.codecs, self.bandwith, self.dur))


@dataclass(eq=False)
class Audio:
    id: str
    dfn: str
    base_url: str
    codecs: str
    bandwith: int = 0
    dur: int = 0

    @property
    def short_codecs(self) -> str:
        """E-AC-3 => EAC3，用于编码优先级匹配。"""
        return self.codecs.upper().replace("-", "")

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, Audio)
            and self.id == other.id
            and self.dfn == other.dfn
            and self.codecs == other.codecs
            and self.bandwith == other.bandwith
            and self.dur == other.dur
        )

    def __hash__(self) -> int:
        return hash((self.id, self.dfn, self.codecs, self.bandwith, self.dur))


@dataclass(eq=False)
class Subtitle:
    lan: str
    url: str
    path: str


@dataclass(eq=False)
class Clip:
    """多线程下载的一个分片。``to`` 为 -1 表示到文件末尾。"""

    index: int
    from_: int
    to: int


@dataclass(eq=False)
class AudioMaterial:
    """额外音轨（背景音 / 角色配音）。"""

    title: str
    person_name: str
    path: str


@dataclass(eq=False)
class AudioMaterialInfo:
    title: str
    person_name: str
    path: str
    audio: list[Audio] = field(default_factory=list)


@dataclass(eq=False)
class VInfo:
    """解析得到的视频元信息。"""

    title: str
    desc: str
    pic: str
    pub_time: int
    pages_info: list[Page]
    is_bangumi: bool = False
    is_cheese: bool = False
    is_bangumi_end: bool = False
    #: 番剧/课程当前选中的集数（字符串形式的 index）
    index: str | None = None
    is_stein_gate: bool = False


@dataclass(eq=False)
class ParsedResult:
    """playurl 解析结果。"""

    web_json_string: str = ""
    video_tracks: list[Video] = field(default_factory=list)
    audio_tracks: list[Audio] = field(default_factory=list)
    background_audio_tracks: list[Audio] = field(default_factory=list)
    role_audio_list: list[AudioMaterialInfo] = field(default_factory=list)
    extra_points: list[ViewPoint] = field(default_factory=list)
    #: FLV (durl) 模式下的分段地址
    clips: list[str] = field(default_factory=list)
    #: FLV 模式下可选的清晰度列表
    dfns: list[str] = field(default_factory=list)
