"""playurl 解析，对应 BBDown.Core/Parser.cs。"""

from __future__ import annotations

import hashlib
import json
import re
import time

from . import grpc_app
from .config import Config
from .console import log, log_debug
from .entity import Audio, AudioMaterialInfo, ParsedResult, Video, ViewPoint
from .net import HTTPUtil

__all__ = ["wbi_sign", "get_play_json", "extract_tracks", "get_video_codec", "get_max_qn"]

PLAYER_JSON_RE = re.compile(r"window\.__playinfo__=([\s\S]*?)</script>")
BASE_URL_RE = re.compile(r"http.*:\d+")


def wbi_sign(api: str) -> str:
    return f"{api}&w_rid=" + hashlib.md5((api + Config.WBI).encode("utf-8")).hexdigest()


def get_max_qn() -> str:
    return Config.max_qn()


def get_time_stamp(seconds: bool = False) -> str:
    now = time.time()
    return str(int(now)) if seconds else str(int(now * 1000))


def get_sign(parms: str, is_bili_plus: bool) -> str:
    salt = "acd495b248ec528c2eed1e862d393126" if is_bili_plus else "59b43e04ad6965f34319062b478f83dd"
    return hashlib.md5((parms + salt).encode("utf-8")).hexdigest()


def get_video_codec(code: str) -> str:
    return {"13": "AV1", "12": "HEVC", "7": "AVC"}.get(str(code), "UNKNOWN")


# ---------------------------------------------------------------------------
# 请求 playurl
# ---------------------------------------------------------------------------


def get_play_json(
    encoding: str,
    aid_ori: str,
    aid: str,
    cid: str,
    ep_id: str,
    tv_api: bool,
    intl: bool,
    app_api: bool,
    qn: str = "0",
) -> str:
    log_debug(
        "aid=%s,cid=%s,epId=%s,tvApi=%s,IntlApi=%s,appApi=%s,qn=%s",
        aid,
        cid,
        ep_id,
        tv_api,
        intl,
        app_api,
        qn,
    )

    if intl:
        return _get_intl_play_json(aid, cid, ep_id, qn)

    cheese = aid_ori.startswith("cheese:")
    bangumi = cheese or aid_ori.startswith("ep:")
    log_debug("bangumi=%s,cheese=%s", bangumi, cheese)

    if app_api:
        return grpc_app.do_req(aid, cid, ep_id, qn, bangumi, encoding, Config.TOKEN)

    if tv_api:
        host = f"{Config.TVHOST}/pgc/player/api/playurltv" if bangumi else f"{Config.TVHOST}/x/tv/playurl"
    else:
        host = f"{Config.HOST}/pgc/player/web/v2/playurl" if bangumi else "api.bilibili.com/x/player/wbi/playurl"
    prefix = f"https://{host}?"

    if tv_api:
        builder = []
        if Config.TOKEN != "":
            builder.append(f"access_key={Config.TOKEN}&")
        builder.append(f"appkey=4409e2ce8ffd12b8&build=106500&cid={cid}&device=android")
        if bangumi:
            builder.append(f"&ep_id={ep_id}&expire=0")
        builder.append("&fnval=4048&fnver=0&fourk=1&mid=0&mobi_app=android_tv_yst")
        builder.append(f"&object_id={aid}&platform=android&playurl_type=1&qn={qn}&ts={get_time_stamp(True)}")
        params = "".join(builder)
        api = f"{prefix}{params}&sign={get_sign(params, False)}"
    else:
        builder = [
            f"support_multi_audio=true&from_client=BROWSER&avid={aid}&cid={cid}&fnval=4048&fnver=0&fourk=1"
        ]
        if Config.AREA != "":
            builder.append(f"&access_key={Config.TOKEN}&area={Config.AREA}")
        builder.append(f"&otype=json&qn={qn}")
        if bangumi:
            builder.append(f"&module=bangumi&ep_id={ep_id}&session=")
        if Config.COOKIE == "":
            builder.append("&try_look=1")
        builder.append(f"&wts={get_time_stamp(True)}")
        params = "".join(builder)
        api = prefix + (params if bangumi else wbi_sign(params))

    if cheese:
        api = api.replace("/pgc/", "/pugv/")

    web_json = HTTPUtil.get_web_source(api)
    if '"大会员专享限制"' in web_json:
        log("此视频需要大会员，您大概率需要登录一个有大会员的账号才可以下载，尝试从网页源码解析")
        web_source = HTTPUtil.get_web_source(f"https://www.bilibili.com/bangumi/play/ep{ep_id}")
        match = PLAYER_JSON_RE.search(web_source)
        web_json = match.group(1) if match else web_json
    return web_json


def _get_intl_play_json(aid: str, cid: str, ep_id: str, qn: str, code: str = "0") -> str:
    is_bili_plus = Config.HOST != "api.bilibili.com"
    api = f"https://{Config.HOST if is_bili_plus else 'api.biliintl.com'}/intl/gateway/v2/ogv/playurl?"

    builder = []
    if Config.TOKEN != "":
        builder.append(f"access_key={Config.TOKEN}&")
    builder.append(f"aid={aid}")
    if is_bili_plus:
        builder.append(f"&appkey=7d089525d3611b1c&area={Config.AREA or 'th'}")
    builder.append(f"&cid={cid}&ep_id={ep_id}&platform=android&prefer_code_type={code}&qn={qn}")
    if is_bili_plus:
        builder.append(f"&ts={get_time_stamp(True)}")
    builder.append("&s_locale=zh_SG")

    params = "".join(builder)
    api += f"{params}&sign={get_sign(params, True)}" if is_bili_plus else params
    return HTTPUtil.get_web_source(api)


# ---------------------------------------------------------------------------
# 解析 playurl 响应
# ---------------------------------------------------------------------------


def _select_root(data: dict) -> dict:
    """对应 Parser 里根据响应形态挑选数据根节点。"""
    if not isinstance(data, dict):
        return {}
    result = data.get("result")
    if isinstance(result, dict):
        video_info = result.get("video_info")
        if isinstance(video_info, dict):
            return video_info
        return result
    inner = data.get("data")
    if isinstance(inner, dict):
        return inner
    return data


def _first_usable_url(url_list: list[str]) -> str:
    for item in url_list:
        if not BASE_URL_RE.search(item):
            return item
    return url_list[0] if url_list else ""


def extract_tracks(
    aid_ori: str,
    aid: str,
    cid: str,
    ep_id: str,
    tv_api: bool,
    intl_api: bool,
    app_api: bool,
    encoding: str,
    qn: str = "0",
) -> ParsedResult:
    """解析指定分 P 的音视频流。"""
    parsed = ParsedResult()
    parsed.web_json_string = get_play_json(
        encoding, aid_ori, aid, cid, ep_id, tv_api, intl_api, app_api, qn
    )
    log_debug(parsed.web_json_string)

    if '"stream_list"' in parsed.web_json_string:
        _parse_intl(parsed, aid, cid, ep_id, qn)
        return parsed

    root = _select_root(_loads(parsed.web_json_string))
    bangumi = aid_ori.startswith("ep:")

    if '"dash":' in parsed.web_json_string:
        _parse_dash(parsed, root, aid, aid_ori, cid, ep_id, tv_api, intl_api, app_api, encoding, bangumi)
    elif '"durl":' in parsed.web_json_string:
        _parse_flv(parsed, aid_ori, aid, cid, ep_id, tv_api, intl_api, app_api, encoding)

    if bangumi:
        _parse_clip_info(parsed, root)

    return parsed


def _loads(text: str) -> dict:
    try:
        value = json.loads(text)
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _parse_intl(parsed: ParsedResult, aid: str, cid: str, ep_id: str, qn: str) -> None:
    """国际版接口：stream_list / dash_audio，需要请求两次（code 0 和 1）。"""
    for code in ("0", "1"):
        parsed.web_json_string = _get_intl_play_json(aid, cid, ep_id, qn, code)
        root = _loads(parsed.web_json_string).get("data") or {}
        video_info = root.get("video_info") or {}
        p_dur = int(video_info.get("timelength", 0)) // 1000

        for stream in video_info.get("stream_list") or []:
            dash_video = stream.get("dash_video")
            if not dash_video or not dash_video.get("base_url"):
                continue
            video_id = str((stream.get("stream_info") or {}).get("quality", ""))
            url_list = [dash_video.get("base_url", "")]
            url_list.extend(dash_video.get("backup_url") or [])
            video = Video(
                id=video_id,
                dfn=Config.quality_name(video_id),
                base_url=_first_usable_url(url_list),
                codecs=get_video_codec(str(dash_video.get("codecid", ""))),
                bandwith=int(dash_video.get("bandwidth", 0)) // 1000,
                dur=p_dur,
                size=float(dash_video.get("size") or 0),
            )
            if video not in parsed.video_tracks:
                parsed.video_tracks.append(video)

        for node in video_info.get("dash_audio") or []:
            url_list = [node.get("base_url", "")]
            url_list.extend(node.get("backup_url") or [])
            audio_id = str(node.get("id", ""))
            audio = Audio(
                id=audio_id,
                dfn=audio_id,
                base_url=_first_usable_url(url_list),
                codecs="M4A",
                bandwith=int(node.get("bandwidth", 0)) // 1000,
                dur=p_dur,
            )
            if audio not in parsed.audio_tracks:
                parsed.audio_tracks.append(audio)


def _parse_dash(
    parsed: ParsedResult,
    root: dict,
    aid: str,
    aid_ori: str,
    cid: str,
    ep_id: str,
    tv_api: bool,
    intl_api: bool,
    app_api: bool,
    encoding: str,
    bangumi: bool,
) -> None:
    dash = root.get("dash") or {}
    p_dur = int(dash.get("duration") or 0)
    if not p_dur:
        p_dur = int(root.get("timelength") or 0) // 1000

    if app_api and bangumi:
        dubbing = _loads(parsed.web_json_string).get("dubbing_info") or {}
        _parse_dubbing(parsed, root, dubbing, aid, cid)

    _add_videos(parsed, dash, p_dur, tv_api, app_api)

    # 原实现会先按默认 qn 解析一次，再用最高 qn 补解析一次（拿免二压片源）
    if not app_api:
        parsed.web_json_string = get_play_json(
            encoding, aid_ori, aid, cid, ep_id, tv_api, intl_api, app_api, get_max_qn()
        )
        root = _select_root(_loads(parsed.web_json_string))
        dash = root.get("dash") or {}
        _add_videos(parsed, dash, p_dur, tv_api, app_api)

    _add_audios(parsed, dash, p_dur, tv_api)


def _add_videos(
    parsed: ParsedResult, dash: dict, p_dur: int, tv_api: bool, app_api: bool
) -> None:
    for node in dash.get("video") or []:
        url_list = [node.get("base_url", "")]
        backup = node.get("backup_url")
        if isinstance(backup, list):
            url_list.extend(backup)
        video_id = str(node.get("id", ""))
        video = Video(
            id=video_id,
            dfn=Config.quality_name(video_id),
            base_url=_first_usable_url(url_list),
            codecs=get_video_codec(str(node.get("codecid", ""))),
            bandwith=int(node.get("bandwidth", 0) or 0) // 1000,
            dur=p_dur,
            size=float(node.get("size") or 0),
        )
        if not tv_api and not app_api:
            video.res = f"{node.get('width', '')}x{node.get('height', '')}"
            video.fps = str(node.get("frame_rate", ""))
        if video not in parsed.video_tracks:
            parsed.video_tracks.append(video)


def _add_audios(parsed: ParsedResult, dash: dict, p_dur: int, tv_api: bool) -> None:
    audios = list(dash.get("audio") or [])

    # 杜比全景声 / Hi-Res 无损
    if not tv_api:
        dolby = dash.get("dolby")
        if isinstance(dolby, dict):
            audios.extend(dolby.get("audio") or [])
        flac = dash.get("flac")
        if isinstance(flac, dict) and flac.get("audio") is not None:
            audios.append(flac.get("audio"))

    for node in audios:
        url_list = [node.get("base_url", "")]
        backup = node.get("backup_url")
        if isinstance(backup, list):
            url_list.extend(backup)
        audio_id = str(node.get("id", ""))
        codecs = str(node.get("codecs", ""))
        codecs = {
            "mp4a.40.2": "M4A",
            "mp4a.40.5": "M4A",
            "ec-3": "E-AC-3",
            "fLaC": "FLAC",
        }.get(codecs, codecs)
        parsed.audio_tracks.append(
            Audio(
                id=audio_id,
                dfn=audio_id,
                base_url=_first_usable_url(url_list),
                codecs=codecs,
                bandwith=int(node.get("bandwidth", 0) or 0) // 1000,
                dur=p_dur,
            )
        )


def _parse_dubbing(parsed: ParsedResult, root: dict, dubbing: dict, aid: str, cid: str) -> None:
    """APP 番剧接口的背景音 + 角色配音。"""
    background = dubbing.get("background_audio") or []
    roles = dubbing.get("role_audio_list") or []
    if not background and not roles:
        return

    dash = root.get("dash") or {}
    p_dur = int(dash.get("duration") or 0) or int(root.get("timelength") or 0) // 1000

    for node in background:
        url_list = [node.get("base_url", "")]
        url_list.extend(node.get("backup_url") or [])
        audio_id = str(node.get("id", ""))
        parsed.background_audio_tracks.append(
            Audio(
                id=audio_id,
                dfn=audio_id,
                base_url=_first_usable_url(url_list),
                codecs=str(node.get("codecs", "")),
                bandwith=int(node.get("bandwidth", 0) or 0) // 1000,
                dur=p_dur,
            )
        )

    for role in roles:
        role_tracks: list[Audio] = []
        for node in role.get("audio") or []:
            url_list = [node.get("base_url", "")]
            url_list.extend(node.get("backup_url") or [])
            audio_id = str(node.get("id", ""))
            role_tracks.append(
                Audio(
                    id=audio_id,
                    dfn=audio_id,
                    base_url=_first_usable_url(url_list),
                    codecs=str(node.get("codecs", "")),
                    bandwith=int(node.get("bandwidth", 0) or 0) // 1000,
                    dur=p_dur,
                )
            )
        audio_id = str(role.get("audio_id", ""))
        parsed.role_audio_list.append(
            AudioMaterialInfo(
                title=str(role.get("title", "")),
                person_name=str(role.get("person_name", "")),
                path=f"{aid}/{aid}.{cid}.{audio_id}.m4a",
                audio=role_tracks,
            )
        )


def _parse_flv(
    parsed: ParsedResult,
    aid_ori: str,
    aid: str,
    cid: str,
    ep_id: str,
    tv_api: bool,
    intl_api: bool,
    app_api: bool,
    encoding: str,
) -> None:
    """FLV (durl) 模式：以最高清晰度重新解析。"""
    parsed.web_json_string = get_play_json(
        encoding, aid_ori, aid, cid, ep_id, tv_api, intl_api, app_api, get_max_qn()
    )
    root = _select_root(_loads(parsed.web_json_string))

    quality = str(root.get("quality", ""))
    video_codecid = str(root.get("video_codecid", ""))
    size = 0.0
    length = 0.0

    for node in root.get("durl") or []:
        parsed.clips.append(str(node.get("url", "")))
        size += float(node.get("size") or 0)
        length += float(node.get("length") or 0)

    qn_extras = root.get("qn_extras")
    if isinstance(qn_extras, list):
        parsed.dfns.extend(str(node.get("qn", "")) for node in qn_extras)
    else:
        accept_quality = root.get("accept_quality")
        if isinstance(accept_quality, list):
            parsed.dfns.extend(str(qn) for qn in accept_quality if str(qn) != "")

    video = Video(
        id=quality,
        dfn=Config.quality_name(quality),
        base_url="",
        codecs=get_video_codec(video_codecid),
        bandwith=0,
        dur=int(length) // 1000,
        size=size,
    )
    if video not in parsed.video_tracks:
        parsed.video_tracks.append(video)


def _parse_clip_info(parsed: ParsedResult, root: dict) -> None:
    """番剧片头片尾 -> 章节信息，效果：正片 -> 片头 -> 正片 -> 片尾。"""
    clip_list = root.get("clip_info_list")
    if not isinstance(clip_list, list):
        return

    points = [
        ViewPoint(
            title=str(clip.get("toastText", "")).replace("即将跳过", ""),
            start=int(clip.get("start", 0)),
            end=int(clip.get("end", 0)),
        )
        for clip in clip_list
    ]
    points.sort(key=lambda p: p.start)

    merged: list[ViewPoint] = []
    last_end = 0
    for point in points:
        if last_end < point.start:
            merged.append(ViewPoint(title="正片", start=last_end, end=point.start))
        merged.append(point)
        last_end = point.end
    parsed.extra_points = merged
