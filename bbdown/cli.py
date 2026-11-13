"""命令行入口，对应 BBDown/Program.cs 的参数定义与 BBDown/CommandLineInvoker.cs。"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import PROJECT_NAME, __version__, workflow
from .console import log, log_banner, log_error
from .options import MyOption
from .util import app_dir

__all__ = ["main", "build_parser"]

_TRUE_WORDS = {"true", "1", "yes", "y", "on", "t"}
_FALSE_WORDS = {"false", "0", "no", "n", "off", "f"}


def _bool_value(text: str) -> bool:
    value = str(text).strip().lower()
    if value in _TRUE_WORDS:
        return True
    if value in _FALSE_WORDS:
        return False
    raise argparse.ArgumentTypeError(f"无效的布尔值: {text}")


#: 所有「可带一个可选布尔值」的开关（与 C# 的 Option<bool> 一致）
_BOOL_FLAGS = [
    "-tv", "--use-tv-api", "-app", "--use-app-api", "-intl", "--use-intl-api",
    "--use-mp4box", "-info", "--only-show-info", "--show-all", "-aria2", "--use-aria2c",
    "-ia", "--interactive", "-hs", "--hide-streams", "-mt", "--multi-thread", "--simply-mux",
    "--video-only", "--audio-only", "--danmaku-only", "--cover-only", "--sub-only",
    "--debug", "--skip-mux", "--skip-subtitle", "--skip-cover", "--force-http",
    "-dd", "--download-danmaku", "--skip-ai", "--video-ascending", "--audio-ascending",
    "--allow-pcdn", "--force-replace-host", "--save-archives-to-file",
    "--only-hevc", "-hevc", "--only-avc", "-avc", "--only-av1", "-av1",
    "--add-dfn-subfix", "--no-padding-page-num", "--bandwith-ascending",
]
_BOOL_FLAG_SET = set(_BOOL_FLAGS)


def normalize_bool_flags(argv: list[str]) -> list[str]:
    """把 ``--flag`` / ``--flag false`` 统一成 ``--flag=True|False``。

    这样开关既不会吞掉后面紧跟的 URL，也支持 BBDown 文档里的 ``--multi-thread false``。
    """
    result: list[str] = []
    index = 0
    while index < len(argv):
        token = argv[index]
        if "=" in token or token not in _BOOL_FLAG_SET:
            result.append(token)
            index += 1
            continue

        if index + 1 < len(argv) and argv[index + 1].strip().lower() in (_TRUE_WORDS | _FALSE_WORDS):
            result.append(f"{token}={argv[index + 1].strip().lower()}")
            index += 2
        else:
            result.append(f"{token}=True")
            index += 1
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bbdown",
        description="BBDown是一个免费且便捷高效的哔哩哔哩下载/解析软件.",
        add_help=True,
        argument_default=argparse.SUPPRESS,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "常用示例:\n"
            '  bbdown "https://www.bilibili.com/video/BV1qt4y1X7TW"\n'
            '  bbdown -tv "BV1qt4y1X7TW"\n'
            '  bbdown -p ALL "https://www.bilibili.com/bangumi/play/ss33073"\n'
            '  bbdown -info "BV1qt4y1X7TW"\n'
        ),
    )
    parser.add_argument("url", nargs="?", help="视频地址 或 av|bv|BV|ep|ss")
    parser.add_argument("--version", action="version", version=f"{PROJECT_NAME} {__version__}")

    def flag(*names: str, dest: str, help_text: str) -> None:
        parser.add_argument(
            *names,
            dest=dest,
            nargs="?",
            const=True,
            type=_bool_value,
            metavar="BOOL",
            help=help_text,
        )

    flag("-tv", "--use-tv-api", dest="use_tv_api", help_text="使用TV端解析模式")
    flag("-app", "--use-app-api", dest="use_app_api", help_text="使用APP端解析模式")
    flag("-intl", "--use-intl-api", dest="use_intl_api", help_text="使用国际版(东南亚视频)解析模式")
    flag("--use-mp4box", dest="use_mp4box", help_text="使用MP4Box来混流")

    parser.add_argument(
        "-e", "--encoding-priority", dest="encoding_priority",
        help='视频及音频编码的选择优先级, 用逗号分割 例: "hevc,av1,avc,flac,eac3,m4a"',
    )
    parser.add_argument(
        "-q", "--dfn-priority", dest="dfn_priority",
        help='画质优先级,用逗号分隔 例: "8K 超高清, 1080P 高码率, HDR 真彩, 杜比视界"',
    )
    flag("-info", "--only-show-info", dest="only_show_info", help_text="仅解析而不进行下载")
    flag("-hs", "--hide-streams", dest="hide_streams", help_text="不要显示所有可用音视频流")
    flag("-ia", "--interactive", dest="interactive", help_text="交互式选择清晰度")
    flag("--show-all", dest="show_all", help_text="展示所有分P标题")
    flag("-aria2", "--use-aria2c", dest="use_aria2c", help_text="调用aria2c进行下载(需要自行准备可执行文件)")
    parser.add_argument(
        "--aria2c-args", dest="aria2c_args",
        help='调用aria2c的附加参数(默认参数包含"-x16 -s16 -j16 -k 5M")',
    )
    flag("-mt", "--multi-thread", dest="multi_thread", help_text="使用多线程下载(默认开启)")
    parser.add_argument(
        "-p", "--select-page", dest="select_page",
        help="选择指定分p或分p范围: (-p 8 或 -p 1,2 或 -p 3-5 或 -p ALL 或 -p LAST 或 -p 3,5,LATEST)",
    )
    flag("--simply-mux", dest="simply_mux", help_text="精简混流，不增加描述、作者等信息")
    flag("--audio-only", dest="audio_only", help_text="仅下载音频")
    flag("--video-only", dest="video_only", help_text="仅下载视频")
    flag("--danmaku-only", dest="danmaku_only", help_text="仅下载弹幕")
    flag("--cover-only", dest="cover_only", help_text="仅下载封面")
    flag("--sub-only", dest="sub_only", help_text="仅下载字幕")
    flag("--debug", dest="debug", help_text="输出调试日志")
    flag("--skip-mux", dest="skip_mux", help_text="跳过混流步骤")
    flag("--skip-subtitle", dest="skip_subtitle", help_text="跳过字幕下载")
    flag("--skip-cover", dest="skip_cover", help_text="跳过封面下载")
    flag("--force-http", dest="force_http", help_text="下载音视频时强制使用HTTP协议替换HTTPS(默认开启)")
    flag("-dd", "--download-danmaku", dest="download_danmaku", help_text="下载弹幕")
    parser.add_argument(
        "-ddf", "--download-danmaku-formats", dest="download_danmaku_formats",
        help="指定需下载的弹幕格式, 用逗号分隔, 可选 xml/ass, 默认: xml,ass",
    )
    flag("--skip-ai", dest="skip_ai", help_text="跳过AI字幕下载(默认开启)")
    flag("--video-ascending", dest="video_ascending", help_text="视频升序(最小体积优先)")
    flag("--audio-ascending", dest="audio_ascending", help_text="音频升序(最小体积优先)")
    flag("--allow-pcdn", dest="allow_pcdn", help_text="不替换PCDN域名, 仅在正常情况与--upos-host均无法下载时使用")
    parser.add_argument(
        "--language", dest="language", help="设置混流的音频语言(代码), 如chi, jpn等"
    )
    parser.add_argument(
        "-ua", "--user-agent", dest="user_agent", help="指定user-agent, 否则使用随机user-agent"
    )
    parser.add_argument(
        "-c", "--cookie", dest="cookie", help="设置字符串cookie用以下载网页接口的会员内容"
    )
    parser.add_argument(
        "-token", "--access-token", dest="access_token",
        help="设置access_token用以下载TV/APP接口的会员内容",
    )
    parser.add_argument("--work-dir", dest="work_dir", help="设置程序的工作目录")
    parser.add_argument("--ffmpeg-path", dest="ffmpeg_path", help="设置ffmpeg的路径")
    parser.add_argument("--mp4box-path", dest="mp4box_path", help="设置mp4box的路径")
    parser.add_argument("--aria2c-path", dest="aria2c_path", help="设置aria2c的路径")
    parser.add_argument("--upos-host", dest="upos_host", help="自定义upos服务器")
    flag("--force-replace-host", dest="force_replace_host", help_text="强制替换下载服务器host(默认开启)")
    flag(
        "--save-archives-to-file", dest="save_archives_to_file",
        help_text="将下载过的视频记录到本地文件中, 用于后续跳过下载同个视频",
    )
    parser.add_argument(
        "--delay-per-page", dest="delay_per_page",
        help="设置下载合集分P之间的下载间隔时间(单位: 秒, 默认无间隔)",
    )
    parser.add_argument(
        "-F", "--file-pattern", dest="file_pattern",
        help=(
            "使用内置变量自定义单P存储文件名:\n"
            "<videoTitle> 视频主标题, <pageNumber> 分P序号, <pageNumberWithZero> 分P序号(补零),\n"
            "<pageTitle> 分P标题, <bvid>/<aid>/<cid>, <dfn> 清晰度, <res> 分辨率, <fps> 帧率,\n"
            "<videoCodecs>/<videoBandwidth>, <audioCodecs>/<audioBandwidth>,\n"
            "<ownerName>/<ownerMid>, <publishDate>/<videoDate>, <apiType>\n"
            "默认为: <videoTitle>"
        ),
    )
    parser.add_argument(
        "-M", "--multi-file-pattern", dest="multi_file_pattern",
        help="使用内置变量自定义多P存储文件名\n默认为: <videoTitle>/[P<pageNumberWithZero>]<pageTitle>",
    )
    parser.add_argument(
        "--host", dest="host",
        help="指定BiliPlus host(使用BiliPlus需要access_token, 不需要cookie)",
    )
    parser.add_argument(
        "--ep-host", dest="ep_host",
        help="指定BiliPlus EP host(用于代理api.bilibili.com/pgc/view/web/season)",
    )
    parser.add_argument(
        "--tv-host", dest="tv_host", help="自定义tv端接口请求Host(用于代理api.snm0516.aisee.tv)"
    )
    parser.add_argument("--area", dest="area", help="(hk|tw|th) 使用BiliPlus时必选, 指定BiliPlus area")
    parser.add_argument(
        "--config-file", dest="config_file",
        help="读取指定的BBDown本地配置文件(默认为程序目录下的 BBDown.config)",
    )

    # 以下仅为兼容旧版本命令行，不建议使用
    parser.add_argument("--aria2c-proxy", dest="aria2c_proxy", help=argparse.SUPPRESS)
    flag("--only-hevc", "-hevc", dest="only_hevc", help_text="只下载hevc编码")
    flag("--only-avc", "-avc", dest="only_avc", help_text="只下载avc编码")
    flag("--only-av1", "-av1", dest="only_av1", help_text="只下载av1编码")
    flag("--add-dfn-subfix", dest="add_dfn_subfix", help_text="为文件加入清晰度后缀, 如XXX[1080P 高码率]")
    flag("--no-padding-page-num", dest="no_padding_page_num", help_text="不给分P序号补零")
    flag("--bandwith-ascending", dest="bandwith_ascending", help_text="比特率升序(最小体积优先)")
    return parser


# ---------------------------------------------------------------------------
# 配置文件
# ---------------------------------------------------------------------------


def load_config_args(explicit_path: str | None) -> list[str]:
    """读取 BBDown.config，返回参数 token 列表。"""
    path = explicit_path or str(app_dir() / "BBDown.config")
    if not os.path.isfile(path):
        return []

    try:
        text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return []

    args: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("-") and " " in stripped:
            head, rest = stripped.split(" ", 1)
            args.append(head.strip().strip('"'))
            rest = rest.strip()
            if rest:
                args.append(rest.strip('"'))
        else:
            args.append(stripped.strip('"'))
    return args


def _namespace_from_config(parser: argparse.ArgumentParser, config_args: list[str]) -> dict:
    if not config_args:
        return {}
    try:
        return vars(parser.parse_args(normalize_bool_flags(config_args)))
    except SystemExit:
        log_error("配置文件读取异常，忽略")
        return {}


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def _print_banner() -> None:
    log_banner(f"{PROJECT_NAME} version {__version__}, Bilibili Downloader.")
    print("本项目是 https://github.com/nilaoda/BBDown 的 Python 重写版，仅供个人学习使用。")
    print("遇到问题请首先到以下地址查阅有无相关信息：")
    print("https://github.com/nilaoda/BBDown/issues")
    print()


def _run_download(argv: list[str]) -> int:
    parser = build_parser()
    try:
        cli_ns = parser.parse_args(normalize_bool_flags(argv))
    except SystemExit as exc:
        return int(exc.code or 0)

    config_args = load_config_args(getattr(cli_ns, "config_file", None))
    config_ns = _namespace_from_config(parser, config_args)
    if config_args:
        log(f"加载配置文件: {getattr(cli_ns, 'config_file', None) or app_dir() / 'BBDown.config'}")

    # 命令行优先级 > 配置文件优先级
    merged = {**config_ns, **vars(cli_ns)}

    option = MyOption()
    for key, value in merged.items():
        if hasattr(option, key):
            setattr(option, key, value)

    if not option.url:
        parser.print_help()
        return 1

    _print_banner()
    return workflow.do_work(option)


def _run_serve(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="bbdown serve", description="以服务器模式运行")
    parser.add_argument("--listen", "-l", default=None, help="服务器监听url")
    try:
        namespace = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)

    from .server import serve

    _print_banner()
    return serve(namespace.listen or "http://0.0.0.0:23333")


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    if args and args[0] == "login":
        from .login import login_web

        _print_banner()
        return login_web()

    if args and args[0] == "logintv":
        from .login import login_tv

        _print_banner()
        return login_tv()

    if args and args[0] == "serve":
        return _run_serve(args[1:])

    if args and args[0] in ("-h", "--help") and len(args) == 1:
        parser = build_parser()
        parser.print_help()
        print()
        print("Commands:")
        print("  login    通过APP扫描二维码以登录您的WEB账号")
        print("  logintv  通过APP扫描二维码以登录您的TV账号")
        print("  serve    以服务器模式运行")
        return 0

    return _run_download(args)
