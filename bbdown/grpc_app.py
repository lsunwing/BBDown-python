"""APP 端 gRPC 接口。

对应 BBDown.Core/AppHelper.cs 与 BBDown.Core/APP/**/*.proto：
请求体是 protobuf 二进制，外层套一层 gRPC 帧（1 字节压缩标志 + 4 字节大端长度），
响应同样解帧后反序列化，再把结果拼成和网页接口一致的 JSON，交给统一的解析逻辑。
"""

from __future__ import annotations

import base64
import gzip
import json

from .config import Config
from .console import log_debug, log_warn
from .net import HTTPUtil
from .pb import Field, Message

__all__ = [
    "do_req",
    "dm_view",
    "pack_message",
    "read_message",
    "PlayViewReply",
    "DmViewReply",
]

API = "https://grpc.biliapi.net/bilibili.app.playurl.v1.PlayURL/PlayView"
API2 = "https://app.bilibili.com/bilibili.pgc.gateway.player.v2.PlayURL/PlayView"
DM_API = "https://app.biliapi.net/bilibili.community.service.dm.v1.DM/DmView"

DALVIK_VER = "2.1.0"
OS_VER = "11"
BRAND = "M2012K11AC"
MODEL = "Build/RKQ1.200826.002"
APP_VER = "7.32.0"
BUILD = 7320200  # 新版才能抓到配音
CHANNEL = "xiaomi_cn_tv.danmaku.bili_zm20200902"
NETWORK_TYPE_WIFI = 1
NETWORK_OID = "46007"
CRONET = "1.36.1"
BUVID = ""
MOBI_APP = "android"
APP_KEY = "android64"
SESSION_ID = "dedf8669"
PLATFORM = "android"
ENV = "prod"
APP_ID = 1
REGION = "CN"
LANGUAGE = "zh"

CODE_NOCODE = 0
CODE_264 = 1
CODE_265 = 2
CODE_AV1 = 3


# ---------------------------------------------------------------------------
# message 定义（字段号与 .proto 一一对应）
# ---------------------------------------------------------------------------


class PlayViewReq(Message):
    FIELDS = (
        Field(1, "ep_id", "int"),
        Field(2, "cid", "int"),
        Field(3, "qn", "int"),
        Field(4, "fnver", "int"),
        Field(5, "fnval", "int"),
        Field(6, "download", "int"),
        Field(7, "force_host", "int"),
        Field(8, "fourk", "bool"),
        Field(9, "spmid", "str"),
        Field(10, "from_spmid", "str"),
        Field(11, "teenagers_mode", "int"),
        Field(12, "prefer_codec_type", "int"),
        Field(13, "is_preview", "bool"),
        Field(14, "room_id", "int"),
    )


class Device(Message):
    FIELDS = (
        Field(1, "app_id", "int"),
        Field(2, "build", "int"),
        Field(3, "buvid", "str"),
        Field(4, "mobi_app", "str"),
        Field(5, "platform", "str"),
        Field(6, "device", "str"),
        Field(7, "channel", "str"),
        Field(8, "brand", "str"),
        Field(9, "model", "str"),
        Field(10, "osver", "str"),
    )


class FawkesReq(Message):
    FIELDS = (
        Field(1, "appkey", "str"),
        Field(2, "env", "str"),
        Field(3, "session_id", "str"),
    )


class Metadata(Message):
    FIELDS = (
        Field(1, "access_key", "str"),
        Field(2, "mobi_app", "str"),
        Field(3, "device", "str"),
        Field(4, "build", "int"),
        Field(5, "channel", "str"),
        Field(6, "buvid", "str"),
        Field(7, "platform", "str"),
    )


class Network(Message):
    FIELDS = (
        Field(1, "type", "int"),
        Field(2, "tf", "int"),
        Field(3, "oid", "str"),
    )


class LocaleIds(Message):
    FIELDS = (
        Field(1, "language", "str"),
        Field(2, "script", "str"),
        Field(3, "region", "str"),
    )


class Locale(Message):
    FIELDS = (
        Field(1, "c_locale", "msg", LocaleIds),
        Field(2, "s_locale", "msg", LocaleIds),
    )


class DmViewReq(Message):
    FIELDS = (
        Field(1, "pid", "int"),
        Field(2, "oid", "int"),
        Field(3, "type", "int"),
        Field(4, "spmid", "str"),
        Field(5, "is_hard_boot", "int"),
    )


class DashItem(Message):
    FIELDS = (
        Field(1, "id", "int"),
        Field(2, "base_url", "str"),
        Field(3, "backup_url", "str", repeated=True),
        Field(4, "bandwidth", "int"),
        Field(5, "codecid", "int"),
        Field(6, "md5", "str"),
        Field(7, "size", "int"),
    )


class DolbyItem(Message):
    FIELDS = (
        Field(1, "type", "int"),
        Field(2, "audio", "msg", DashItem),
    )


class DashVideo(Message):
    FIELDS = (
        Field(1, "base_url", "str"),
        Field(2, "backup_url", "str", repeated=True),
        Field(3, "bandwidth", "int"),
        Field(4, "codecid", "int"),
        Field(5, "md5", "str"),
        Field(6, "size", "int"),
        Field(7, "audio_id", "int"),
        Field(8, "no_rexcode", "bool"),
    )


class ResponseUrl(Message):
    FIELDS = (
        Field(1, "order", "int"),
        Field(2, "length", "int"),
        Field(3, "size", "int"),
        Field(4, "url", "str"),
        Field(5, "backup_url", "str", repeated=True),
        Field(6, "md5", "str"),
    )


class SegmentVideo(Message):
    FIELDS = (Field(1, "segment", "msg", ResponseUrl, repeated=True),)


class StreamLimit(Message):
    FIELDS = (
        Field(1, "title", "str"),
        Field(2, "uri", "str"),
        Field(3, "msg", "str"),
    )


class StreamInfo(Message):
    FIELDS = (
        Field(1, "quality", "int"),
        Field(2, "format", "str"),
        Field(3, "description", "str"),
        Field(4, "err_code", "int"),
        Field(5, "limit", "msg", StreamLimit),
        Field(6, "need_vip", "bool"),
        Field(7, "need_login", "bool"),
        Field(8, "intact", "bool"),
        Field(9, "no_rexcode", "bool"),
        Field(10, "attribute", "int"),
    )


class StreamItem(Message):
    FIELDS = (
        Field(1, "stream_info", "msg", StreamInfo),
        Field(2, "dash_video", "msg", DashVideo),
        Field(3, "segment_video", "msg", SegmentVideo),
    )


class VideoInfo(Message):
    FIELDS = (
        Field(1, "quality", "int"),
        Field(2, "format", "str"),
        Field(3, "timelength", "int"),
        Field(4, "video_codecid", "int"),
        Field(5, "stream_list", "msg", StreamItem, repeated=True),
        Field(6, "dash_audio", "msg", DashItem, repeated=True),
        Field(7, "dolby", "msg", DolbyItem),
        Field(9, "flac", "msg", DolbyItem),
    )


class ClipInfo(Message):
    FIELDS = (
        Field(2, "start", "int"),
        Field(3, "end", "int"),
        Field(5, "toast_text", "str"),
    )


class BusinessInfo(Message):
    FIELDS = (
        Field(1, "is_preview", "bool"),
        Field(2, "bp", "bool"),
        Field(3, "marlin_token", "str"),
        Field(6, "clip_info", "msg", ClipInfo, repeated=True),
    )


class AudioMaterialProto(Message):
    FIELDS = (
        Field(1, "audio_id", "str"),
        Field(2, "title", "str"),
        Field(3, "edition", "str"),
        Field(5, "person_name", "str"),
        Field(7, "audio", "msg", DashItem, repeated=True),
    )


class RoleAudioProto(Message):
    FIELDS = (Field(4, "audio_material_list", "msg", AudioMaterialProto, repeated=True),)


class PlayDubbingInfo(Message):
    FIELDS = (
        Field(1, "background_audio", "msg", AudioMaterialProto),
        Field(2, "role_audio_list", "msg", RoleAudioProto, repeated=True),
    )


class PlayExtInfo(Message):
    FIELDS = (Field(1, "play_dubbing_info", "msg", PlayDubbingInfo),)


class PlayViewReply(Message):
    FIELDS = (
        Field(1, "video_info", "msg", VideoInfo),
        Field(3, "business", "msg", BusinessInfo),
        Field(7, "play_ext_info", "msg", PlayExtInfo),
    )


class SubtitleItem(Message):
    FIELDS = (
        Field(1, "id_str", "str"),
        Field(2, "id", "int"),
        Field(3, "lan", "str"),
        Field(4, "lan_doc", "str"),
        Field(5, "subtitle_url", "str"),
    )


class VideoSubtitle(Message):
    FIELDS = (
        Field(1, "lan", "str"),
        Field(2, "lan_doc", "str"),
        Field(3, "subtitles", "msg", SubtitleItem, repeated=True),
    )


class DmViewReply(Message):
    FIELDS = (
        Field(1, "closed", "bool"),
        Field(3, "subtitle", "msg", VideoSubtitle),
    )


# ---------------------------------------------------------------------------
# gRPC 帧
# ---------------------------------------------------------------------------


def pack_message(data: bytes) -> bytes:
    """压缩并按 gRPC 帧格式打包。"""
    compressed = gzip.compress(data)
    return bytes([1]) + len(compressed).to_bytes(4, "big") + compressed


def read_message(data: bytes) -> bytes:
    """解 gRPC 帧，返回反序列化前的 protobuf 字节。"""
    if len(data) < 5:
        raise ValueError("gRPC response too short")
    first = data[0]
    size = int.from_bytes(data[1:5], "big")
    if first == 1:
        return gzip.decompress(data[5:])
    return data[5 : 5 + size]


# ---------------------------------------------------------------------------
# 请求构造
# ---------------------------------------------------------------------------


def _video_code_type(codec: str) -> int:
    return {"AVC": CODE_264, "HEVC": CODE_265, "AV1": CODE_AV1}.get(codec, CODE_265)


def _b64(message: Message) -> str:
    return base64.b64encode(message.serialize()).decode("ascii")


def _get_header(appkey: str) -> dict[str, str]:
    return {
        "Host": "grpc.biliapi.net",
        "user-agent": (
            f"Dalvik/{DALVIK_VER} (Linux; U; Android {OS_VER}; {BRAND} {MODEL}) {APP_VER} "
            f"os/android model/{BRAND} mobi_app/android build/{BUILD} channel/{CHANNEL} "
            f"innerVer/{BUILD} osVer/{OS_VER} network/2 grpc-java-cronet/{CRONET}"
        ),
        "te": "trailers",
        "x-bili-fawkes-req-bin": _b64(FawkesReq(appkey=APP_KEY, env=ENV, session_id=SESSION_ID)),
        "x-bili-metadata-bin": _b64(
            Metadata(
                access_key=appkey,
                mobi_app=MOBI_APP,
                build=BUILD,
                channel=CHANNEL,
                buvid=BUVID,
                platform=PLATFORM,
            )
        ),
        "authorization": f"identify_v1 {Config.TOKEN}",
        "x-bili-device-bin": _b64(
            Device(
                app_id=APP_ID,
                build=BUILD,
                buvid=BUVID,
                mobi_app=MOBI_APP,
                platform=PLATFORM,
                channel=CHANNEL,
                brand=BRAND,
                model=MODEL,
                osver=OS_VER,
            )
        ),
        "x-bili-network-bin": _b64(Network(type=NETWORK_TYPE_WIFI, oid=NETWORK_OID)),
        "x-bili-restriction-bin": "",
        "x-bili-locale-bin": _b64(
            Locale(c_locale=LocaleIds(language=LANGUAGE, region=REGION))
        ),
        "x-bili-exps-bin": "",
        "grpc-encoding": "gzip",
        "grpc-accept-encoding": "identity,gzip",
        "grpc-timeout": "17996161u",
    }


def _playview_payload(target_id: int, cid: int, qn: int, codec: int) -> bytes:
    """target_id：UGC 是 aid，番剧是 ep_id（对应原始实现的 EpId 字段）。"""
    obj = PlayViewReq(
        ep_id=target_id,
        cid=cid,
        qn=127,  # 原实现固定请求最高清晰度
        fnval=4048,
        fourk=True,
        spmid="main.ugc-video-detail.0.0",
        from_spmid="main.my-history.0.0",
        prefer_codec_type=codec,
        download=0,  # 0:播放 1:flv下载 2:dash下载
        force_host=2,  # 0:允许使用ip 1:使用http 2:使用https
    )
    log_debug("PayLoadPlain: %s", _dump(obj))
    return pack_message(obj.serialize())


def _dump(message: Message) -> str:
    return json.dumps(
        {f.name: getattr(message, f.name) for f in message.FIELDS},
        ensure_ascii=False,
        default=str,
    )


# ---------------------------------------------------------------------------
# 响应 -> 网页版 JSON
# ---------------------------------------------------------------------------


def do_req(aid: str, cid: str, ep_id: str, qn: str, bangumi: bool, encoding: str, appkey: str = "") -> str:
    """请求 APP 接口，返回与网页接口同构的 dash JSON 字符串。"""
    headers = _get_header(appkey)
    log_debug("App-Req-Headers: %s", json.dumps(headers, ensure_ascii=False))

    qn_value = int(qn) if str(qn).isdigit() else 0
    if bangumi:
        if encoding not in ("", "HEVC"):
            log_warn("APP的番剧不支持 HEVC 以外的编码")
        body = _playview_payload(int(ep_id or 0), int(cid), qn_value, CODE_265)
        data = HTTPUtil.get_post_response(API2, body, headers)
    else:
        body = _playview_payload(int(aid or 0), int(cid), qn_value, _video_code_type(encoding))
        data = HTTPUtil.get_post_response(API, body, headers)

    reply = PlayViewReply.parse(read_message(data))
    log_debug("PlayViewReply: %s", _dump(reply))
    return _convert_to_dash_json(reply)


def _convert_to_dash_json(resp: PlayViewReply) -> str:
    video_info = resp.video_info
    videos: list[dict] = []
    audios: list[dict] = []
    clips: list[dict] = []
    background_audios: list[dict] = []
    roles: list[dict] = []

    timelength = video_info.timelength if video_info is not None else 0
    seconds = timelength // 1000

    if video_info is not None:
        for item in video_info.stream_list:
            dash_video = item.dash_video
            if dash_video is None:
                continue
            quality = item.stream_info.quality if item.stream_info is not None else 0
            bandwidth = 0
            if seconds > 0:
                bandwidth = int(dash_video.size * 8 // seconds)
            videos.append(
                {
                    "id": quality,
                    "base_url": dash_video.base_url or "",
                    "backup_url": list(dash_video.backup_url),
                    "bandwidth": bandwidth,
                    "codecid": dash_video.codecid or 0,
                }
            )

        for item in video_info.dash_audio:
            audios.append(_audio_json(item, "M4A"))

        if video_info.flac is not None and video_info.flac.audio is not None:
            audios.append(_audio_json(video_info.flac.audio, "FLAC"))

        if video_info.dolby is not None and video_info.dolby.audio is not None:
            audios.append(_audio_json(video_info.dolby.audio, "E-AC-3"))

    if resp.business is not None:
        for clip in resp.business.clip_info:
            clips.append(
                {"start": clip.start or 0, "end": clip.end or 0, "toastText": clip.toast_text or ""}
            )

    ext = resp.play_ext_info
    dubbing = ext.play_dubbing_info if ext is not None else None
    if dubbing is not None and dubbing.background_audio is not None:
        for item in dubbing.background_audio.audio:
            background_audios.append(_audio_json(item, "M4A"))

        for role_group in dubbing.role_audio_list:
            for role in role_group.audio_material_list:
                roles.append(
                    {
                        "audio_id": role.audio_id or "",
                        "title": role.title or role.audio_id or "",
                        "person_name": role.person_name or role.edition or "",
                        "audio": [_audio_json(item, "M4A") for item in role.audio],
                    }
                )

    payload = {
        "code": 0,
        "message": "0",
        "ttl": 1,
        "data": {
            "timelength": timelength,
            "dash": {"video": videos, "audio": audios},
            "clip_info_list": clips,
        },
        "dubbing_info": {
            "background_audio": background_audios,
            "role_audio_list": roles,
        },
    }
    # 紧凑输出，保持和网页接口一致的形态（解析端会做字符串特征判断）
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _audio_json(item: DashItem, codecs: str) -> dict:
    return {
        "id": item.id or 0,
        "base_url": item.base_url or "",
        "backup_url": list(item.backup_url),
        "bandwidth": item.bandwidth or 0,
        "codecs": codecs,
    }


# ---------------------------------------------------------------------------
# 弹幕接口（用于未登录时取字幕）
# ---------------------------------------------------------------------------


def dm_view(aid: str, cid: str) -> DmViewReply | None:
    """调用 DM/DmView 接口取字幕信息。"""
    try:
        payload = DmViewReq(
            pid=int(aid),
            oid=int(cid),
            type=1,
            spmid="main.ugc-video-detail.0.0",
        )
        data = HTTPUtil.get_post_response(DM_API, pack_message(payload.serialize()))
        return DmViewReply.parse(read_message(data))
    except Exception:
        return None
