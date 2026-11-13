"""基础工具与实体的单元测试（不联网）。"""

from __future__ import annotations

import os

from bbdown import bv
from bbdown.console import format_file_size
from bbdown.danmaku import DanmakuItem, parse_xml, save_as_ass
from bbdown.entity import Audio, Page, Video
from bbdown.playurl import get_video_codec
from bbdown.subtitle import convert_sub_from_json, get_subtitle_code
from bbdown.util import format_time, get_valid_filename, format_timestamp, dotnet_format
from datetime import datetime, timezone, timedelta


def test_bv_roundtrip() -> None:
    for avid in (1, 2, 170001, 448351430, 1130000000000):
        bvid_body = bv.encode(avid)
        assert len(bvid_body) == 12 and bvid_body.startswith("BV1")
        assert bv.decode(bvid_body[3:]) == avid


def test_bv_known_value() -> None:
    # BV1qt4y1X7TW 是 BBDown README 里的示例视频
    assert bv.encode(626497566) == "BV1qt4y1X7TW"
    assert bv.decode("qt4y1X7TW") == 626497566


def test_format_file_size() -> None:
    assert format_file_size(512) == "512 bytes"
    assert format_file_size(2048) == "2.00 KB"
    assert format_file_size(5 * 1024 * 1024) == "5.00 MB"
    assert format_file_size(3 * 1024 ** 3) == "3.00 GB"


def test_format_time() -> None:
    assert format_time(59) == "00m59s"
    assert format_time(61) == "01m01s"
    assert format_time(3661) == "1h01m01s"
    assert format_time(3661, True) == "01:01:01"


def test_get_valid_filename() -> None:
    assert get_valid_filename('a/b:c*d?"e<f>g|h') == "a_b_c_d__e_f_g_h"
    assert get_valid_filename("a/b", filter_slash=True) == "a_b"


def test_dotnet_format() -> None:
    value = datetime(2024, 3, 4, 5, 6, 7, tzinfo=timezone(timedelta(hours=8)))
    assert dotnet_format(value, "yyyy-MM-dd_HH-mm-ss") == "2024-03-04_05-06-07"
    assert dotnet_format(value, "yyyy-MM-dd HH:mm:ss zzz") == "2024-03-04 05:06:07 +08:00"
    assert dotnet_format(value, "yy/M/d") == "24/3/4"


def test_format_timestamp_zero() -> None:
    assert format_timestamp(0, "yyyy") == "null"


def test_video_codec() -> None:
    assert get_video_codec("7") == "AVC"
    assert get_video_codec("12") == "HEVC"
    assert get_video_codec("13") == "AV1"
    assert get_video_codec("99") == "UNKNOWN"


def test_audio_short_codecs() -> None:
    audio = Audio(id="1", dfn="1", base_url="", codecs="E-AC-3")
    assert audio.short_codecs == "EAC3"


def test_page_equality_and_bvid() -> None:
    first = Page(1, "626497566", "1", "", "t", 10, "1920x1080", 0)
    second = Page(2, "626497566", "1", "", "t2", 20, "", 0)
    assert first == second  # 以 aid/cid/epid 判等
    assert first.bvid == "BV1qt4y1X7TW"


def test_subtitle_code() -> None:
    assert get_subtitle_code("zh-Hans") == ("chi", "中文（简体）")
    assert get_subtitle_code("zh-hans") == ("chi", "中文（简体）")
    assert get_subtitle_code("unknown-lang") == ("und", "Undetermined")


def test_convert_sub_from_json() -> None:
    raw = '{"body":[{"from":1.5,"to":3.25,"content":"你好"}]}'
    srt = convert_sub_from_json(raw)
    assert "00:00:01,500 --> 00:00:03,250" in srt
    assert "你好" in srt


def test_danmaku_xml_and_ass(tmp_path) -> None:
    xml = tmp_path / "d.xml"
    xml.write_text(
        '<?xml version="1.0" encoding="utf-8"?><i>'
        '<d p="1.5,1,25,16777215,0,0,0,0">弹幕一</d>'
        '<d p="2.0,5,25,255,0,0,0,0">弹幕二</d>'
        "</i>",
        encoding="utf-8",
    )
    items = parse_xml(str(xml))
    assert items is not None and len(items) == 2
    assert items[0].start_time == "0:00:01.50"

    out = tmp_path / "out.ass"
    save_as_ass(items, str(out))
    text = out.read_text(encoding="utf-8-sig")
    assert "[Script Info]" in text
    assert "\\move(" in text
    assert "\\an8\\pos(" in text


def test_danmaku_mode() -> None:
    item = DanmakuItem(["1.0", "4", "25", "16777215", "0", "0", "0", "0"], "底部")
    assert item.danmaku_mode == 3
    assert item.end_time == "0:00:05.00"


def test_version_is_independent() -> None:
    """本项目的版本号自成一条线，从 1.0.0 开始，不跟随原 C# 项目的 1.6.x。"""
    from bbdown import PROJECT_NAME, __version__

    assert __version__ == "1.0.0"
    assert PROJECT_NAME == "BBDown-python"


def test_banner_text() -> None:
    import io
    from contextlib import redirect_stdout

    from bbdown import PROJECT_NAME, __version__
    from bbdown.cli import _print_banner

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        _print_banner()
    assert f"{PROJECT_NAME} version {__version__}, Bilibili Downloader." in buffer.getvalue()


def test_scan_cwd_independent() -> None:
    # app_dir 在没有 BBDOWN_HOME 时也应该可用
    from bbdown.util import app_dir

    assert os.path.isdir(str(app_dir()))


def test_video_equality() -> None:
    a = Video(id="80", dfn="1080P 高清", base_url="u", codecs="AVC")
    b = Video(id="80", dfn="1080P 高清", base_url="u2", codecs="AVC")
    assert a == b  # baseUrl 不参与比较
