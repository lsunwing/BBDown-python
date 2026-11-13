"""命令行参数模型，对应 BBDown/MyOption.cs。"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["MyOption"]


@dataclass
class MyOption:
    """所有命令行选项。字段名与原型一一对应（去掉下划线即为 CLI 参数名）。"""

    url: str = ""

    use_tv_api: bool = False
    use_app_api: bool = False
    use_intl_api: bool = False
    use_mp4box: bool = False
    #: None 表示用户没设置，与 C# 的可空字段语义一致
    encoding_priority: str | None = None
    dfn_priority: str | None = None
    only_show_info: bool = False
    show_all: bool = False
    use_aria2c: bool = False
    interactive: bool = False
    hide_streams: bool = False
    multi_thread: bool = True
    simply_mux: bool = False
    video_only: bool = False
    audio_only: bool = False
    danmaku_only: bool = False
    cover_only: bool = False
    sub_only: bool = False
    debug: bool = False
    skip_mux: bool = False
    skip_subtitle: bool = False
    skip_cover: bool = False
    force_http: bool = True
    download_danmaku: bool = False
    download_danmaku_formats: str | None = None
    skip_ai: bool = True
    video_ascending: bool = False
    audio_ascending: bool = False
    allow_pcdn: bool = False
    force_replace_host: bool = True
    save_archives_to_file: bool = False

    file_pattern: str = ""
    multi_file_pattern: str = ""
    select_page: str = ""
    language: str = ""
    user_agent: str = ""
    cookie: str = ""
    access_token: str = ""
    aria2c_args: str = ""
    work_dir: str = ""
    ffmpeg_path: str = ""
    mp4box_path: str = ""
    aria2c_path: str = ""
    upos_host: str = ""
    delay_per_page: str = "0"
    host: str = "api.bilibili.com"
    ep_host: str = "api.bilibili.com"
    tv_host: str = "api.snm0516.aisee.tv"
    area: str = ""
    config_file: str | None = None

    # 以下仅为兼容旧版本命令行
    aria2c_proxy: str = ""
    only_hevc: bool = False
    only_avc: bool = False
    only_av1: bool = False
    add_dfn_subfix: bool = False
    no_padding_page_num: bool = False
    bandwith_ascending: bool = False

    #: 服务器模式专用：任务完成回调地址
    call_back_web_hook: str | None = None

    def to_camel_dict(self) -> dict:
        """转成 camelCase 字典（供日志 / 服务器接口使用）。"""
        result = {}
        for name, value in self.__dict__.items():
            head, *rest = name.split("_")
            result[head + "".join(part.capitalize() for part in rest)] = value
        return result
