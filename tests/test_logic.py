"""protobuf 编解码、分片计算、参数解析、输入解析的单元测试（不联网）。"""

from __future__ import annotations

import gzip

from bbdown import grpc_app, pb
from bbdown.cli import build_parser, normalize_bool_flags
from bbdown.download import get_all_clips
from bbdown.entity import Page, Video, VInfo
from bbdown.options import MyOption
from bbdown.workflow import (
    format_save_path,
    get_selected_pages,
    parse_dfn_priority,
    parse_encoding_priority,
)


# ---------------------------------------------------------------------------
# protobuf
# ---------------------------------------------------------------------------


def test_varint_roundtrip() -> None:
    for value in (0, 1, 127, 128, 300, 2**40, 2**63 - 1):
        encoded = pb.encode_varint(value)
        decoded, position = pb.read_varint(encoded, 0)
        assert decoded == value
        assert position == len(encoded)


def test_message_roundtrip() -> None:
    request = grpc_app.PlayViewReq(
        ep_id=448351430,
        cid=123456,
        qn=127,
        fnval=4048,
        fourk=True,
        spmid="main.ugc-video-detail.0.0",
        prefer_codec_type=grpc_app.CODE_265,
        download=0,
        force_host=2,
    )
    parsed = grpc_app.PlayViewReq.parse(request.serialize())
    assert parsed.ep_id == 448351430
    assert parsed.cid == 123456
    assert parsed.qn == 127
    assert parsed.fourk is True
    assert parsed.spmid == "main.ugc-video-detail.0.0"
    assert parsed.prefer_codec_type == 2


def test_nested_message_and_repeated() -> None:
    item = grpc_app.DashItem(
        id=30280,
        base_url="https://example/a.m4s",
        backup_url=["https://example/b.m4s"],
        bandwidth=320000,
    )
    video = grpc_app.DashVideo(base_url="https://example/v.m4s", size=1024, codecid=12)
    info = grpc_app.VideoInfo(
        timelength=120000, dash_audio=[item], flac=grpc_app.DolbyItem(audio=item)
    )
    stream = grpc_app.StreamItem(stream_info=grpc_app.StreamInfo(quality=80), dash_video=video)
    info.stream_list.append(stream)
    reply = grpc_app.PlayViewReply(video_info=info)

    parsed = grpc_app.PlayViewReply.parse(reply.serialize())
    assert parsed.video_info.timelength == 120000
    assert parsed.video_info.stream_list[0].stream_info.quality == 80
    assert parsed.video_info.dash_audio[0].backup_url == ["https://example/b.m4s"]
    assert parsed.video_info.flac.audio.id == 30280
    # 未设置的字段保持 None
    assert parsed.business is None


def test_grpc_framing() -> None:
    payload = b"hello grpc"
    frame = grpc_app.pack_message(payload)
    assert frame[0] == 1
    assert int.from_bytes(frame[1:5], "big") == len(frame) - 5
    assert gzip.decompress(frame[5:]) == payload
    assert grpc_app.read_message(frame) == payload


def test_dash_json_shape() -> None:
    item = grpc_app.DashItem(id=30280, base_url="https://example/a.m4s", bandwidth=320000)
    video = grpc_app.DashVideo(base_url="https://example/v.m4s", size=1250000, codecid=12)
    info = grpc_app.VideoInfo(
        timelength=10000,
        stream_list=[
            grpc_app.StreamItem(stream_info=grpc_app.StreamInfo(quality=80), dash_video=video)
        ],
        dash_audio=[item],
    )
    reply = grpc_app.PlayViewReply(
        video_info=info,
        business=grpc_app.BusinessInfo(
            clip_info=[grpc_app.ClipInfo(start=0, end=90, toast_text="即将跳过片头")]
        ),
    )
    text = grpc_app._convert_to_dash_json(reply)
    # 必须保持紧凑格式，解析端会做 '"dash":{' 这类字符串特征判断
    assert '"dash":{"video"' in text
    assert '"data":{' in text

    import json

    payload = json.loads(text)
    assert payload["data"]["dash"]["video"][0]["id"] == 80
    # 10000ms = 10s, 1250000 byte * 8 / 10 = 1000000 bit/s
    assert payload["data"]["dash"]["video"][0]["bandwidth"] == 1000000
    assert payload["data"]["clip_info_list"][0]["toastText"] == "即将跳过片头"


# ---------------------------------------------------------------------------
# 分片
# ---------------------------------------------------------------------------


def test_get_all_clips_covers_file() -> None:
    size = 45 * 1024 * 1024
    clips = get_all_clips("http://x", size)
    assert len(clips) == 3
    assert clips[0].from_ == 0
    assert clips[-1].to == -1
    # 相邻分片首尾相接，不重叠也不留空洞
    for previous, current in zip(clips, clips[1:]):
        assert current.from_ == previous.to + 1


def test_get_all_clips_small_file() -> None:
    clips = get_all_clips("http://x", 100)
    assert len(clips) == 1
    assert clips[0].to == -1


def test_get_all_clips_zero() -> None:
    assert get_all_clips("http://x", 0) == []


# ---------------------------------------------------------------------------
# 命令行
# ---------------------------------------------------------------------------


def test_normalize_bool_flags() -> None:
    assert normalize_bool_flags(["--multi-thread", "false", "URL"]) == ["--multi-thread=false", "URL"]
    assert normalize_bool_flags(["-mt", "URL"]) == ["-mt=True", "URL"]
    assert normalize_bool_flags(["URL"]) == ["URL"]


def test_parse_flags_with_url() -> None:
    parser = build_parser()
    namespace = vars(parser.parse_args(normalize_bool_flags(["--show-all", "BV1xx"])))
    assert namespace["show_all"] is True
    assert namespace["url"] == "BV1xx"


def test_parse_multi_thread_false() -> None:
    parser = build_parser()
    namespace = vars(parser.parse_args(normalize_bool_flags(["--multi-thread", "false", "BV1xx"])))
    assert namespace["multi_thread"] is False


def test_parse_absent_options_are_suppressed() -> None:
    parser = build_parser()
    namespace = vars(parser.parse_args(normalize_bool_flags(["BV1xx"])))
    # 未出现的选项不应污染 namespace，这样配置文件才能生效
    assert "debug" not in namespace
    assert "file_pattern" not in namespace


def test_parse_hidden_options() -> None:
    parser = build_parser()
    namespace = vars(parser.parse_args(normalize_bool_flags(["-hevc", "BV1xx"])))
    assert namespace["only_hevc"] is True


# ---------------------------------------------------------------------------
# 选项解析
# ---------------------------------------------------------------------------


def test_parse_encoding_priority() -> None:
    option = MyOption(encoding_priority="hevc, av1,avc")
    priority, first = parse_encoding_priority(option)
    assert first == "HEVC"
    assert priority == {"HEVC": 0, "AV1": 1, "AVC": 2}


def test_parse_encoding_priority_hyphen() -> None:
    option = MyOption(encoding_priority="e-ac3")
    priority, first = parse_encoding_priority(option)
    assert first == "EAC3"
    assert priority == {"EAC3": 0}


def test_parse_encoding_priority_absent() -> None:
    priority, first = parse_encoding_priority(MyOption())
    assert priority == {} and first == ""


def test_parse_dfn_priority() -> None:
    option = MyOption(dfn_priority="8k 超高清，1080P 高码率")
    assert parse_dfn_priority(option) == {"8K 超高清": 0, "1080P 高码率": 1}


# ---------------------------------------------------------------------------
# 路径模板
# ---------------------------------------------------------------------------


def _page() -> Page:
    return Page(
        index=3,
        aid="626497566",
        cid="123456",
        epid="",
        title="第3话 测试",
        dur=600,
        res="1920x1080",
        pub_time=1700000000,
        owner_name="UP主",
        owner_mid="1234",
    )


def _video() -> Video:
    return Video(
        id="80", dfn="1080P 高清", base_url="", codecs="AVC", bandwith=2000, res="1920x1080"
    )


def test_format_save_path_basic() -> None:
    result = format_save_path(
        "<videoTitle>/[P<pageNumberWithZero>]<pageTitle>",
        "标题",
        _video(),
        None,
        _page(),
        12,
        "WEB",
        1699999999,
    )
    assert result == "标题/[P03]第3话 测试.mp4"


def test_format_save_path_variables() -> None:
    result = format_save_path(
        "<bvid>_<aid>_<cid>_<dfn>_<apiType>_<ownerMid>", "标题", _video(), None, _page(), 1, "TV", 0
    )
    assert result == "BV1qt4y1X7TW_626497566_123456_1080P 高清_TV_1234.mp4"


def test_format_save_path_custom_date() -> None:
    from datetime import datetime

    expected = datetime.fromtimestamp(1700000000).strftime("%Y%m%d")
    result = format_save_path("<videoDate:yyyyMMdd>", "标题", None, None, _page(), 1, "WEB", 0)
    assert result == expected + ".mp4"


def test_format_save_path_keeps_mp4() -> None:
    assert format_save_path("a.mp4", "t", None, None, _page(), 1, "WEB", 0) == "a.mp4"


def test_format_save_path_unknown_variable() -> None:
    assert format_save_path("<nope>", "t", None, None, _page(), 1, "WEB", 0) == "<nope>.mp4"


# ---------------------------------------------------------------------------
# 分 P 选择
# ---------------------------------------------------------------------------


def _v_info(count: int) -> VInfo:
    pages = [Page(i + 1, "1", str(i + 1), "", f"p{i + 1}", 0, "", 0) for i in range(count)]
    return VInfo(title="t", desc="d", pic="", pub_time=0, pages_info=pages)


def test_select_pages_all() -> None:
    assert get_selected_pages(MyOption(select_page="ALL"), _v_info(5), "") is None


def test_select_pages_range() -> None:
    assert get_selected_pages(MyOption(select_page="2-4"), _v_info(5), "") == ["2", "3", "4"]


def test_select_pages_last() -> None:
    assert get_selected_pages(MyOption(select_page="LATEST"), _v_info(7), "") == ["7"]


def test_select_pages_list() -> None:
    assert get_selected_pages(MyOption(select_page="1,3"), _v_info(5), "") == ["1", "3"]


def test_select_pages_from_url() -> None:
    assert get_selected_pages(MyOption(), _v_info(5), "https://x/video/BV1?p=2") == ["2"]


def test_select_pages_bad_input() -> None:
    assert get_selected_pages(MyOption(select_page="a-b"), _v_info(5), "") is None


# ---------------------------------------------------------------------------
# 输入解析（打桩，避免联网）
# ---------------------------------------------------------------------------


def test_get_av_id(monkeypatch) -> None:
    from bbdown import aid

    monkeypatch.setattr(aid, "_fix_avid", lambda value: value)
    cases = [
        ("BV1qt4y1X7TW", "626497566"),
        ("bv1qt4y1X7TW", "626497566"),
        ("ep12345", "ep:12345"),
        ("cheese/ep100", "cheese:100"),
        ("md123", "ep:__md__"),
    ]
    # md 分支需要联网查 new_ep，这里单独打桩
    monkeypatch.setattr(aid, "_get_ep_id_by_md", lambda md_id: "__md__")
    for raw, expected in cases:
        assert aid.get_av_id(raw) == expected, raw


def test_get_av_id_url(monkeypatch) -> None:
    from bbdown import aid

    monkeypatch.setattr(aid, "_fix_avid", lambda value: value)
    assert aid.get_av_id("https://www.bilibili.com/video/BV1qt4y1X7TW?p=2") == "626497566"
    assert aid.get_av_id("https://www.bilibili.com/bangumi/play/ep12345") == "ep:12345"
    assert (
        aid.get_av_id("https://space.bilibili.com/2/lists/1560264?type=season") == "listBizId:1560264"
    )
    assert (
        aid.get_av_id("https://space.bilibili.com/2/lists/1560264?type=series")
        == "seriesBizId:1560264"
    )
    assert aid.get_av_id("https://space.bilibili.com/3/favlist?fid=123") == "favId:123:3"
    assert aid.get_av_id("https://space.bilibili.com/3") == "mid:3"


def test_get_av_id_tolerates_pasted_links(monkeypatch) -> None:
    """从浏览器/聊天软件复制出来的链接常见形态都要能认。"""
    from bbdown import aid

    monkeypatch.setattr(aid, "_fix_avid", lambda value: value)
    cases = [
        # 没有协议头
        "bilibili.com/video/BV1qt4y1X7TW/?spm_id_from=333.1387.favlist.content.click",
        "www.bilibili.com/video/BV1qt4y1X7TW",
        "//www.bilibili.com/video/BV1qt4y1X7TW",
        # 中文引号包裹 + 首尾空白
        "“https://www.bilibili.com/video/BV1qt4y1X7TW”",
        "  'BV1qt4y1X7TW'  ",
    ]
    for raw in cases:
        assert aid.get_av_id(raw) == "626497566", raw
