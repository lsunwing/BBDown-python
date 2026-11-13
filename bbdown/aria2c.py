"""aria2c 调用，对应 BBDown/BBDownAria2c.cs。"""

from __future__ import annotations

import os
import subprocess

from .config import Config

__all__ = ["ARIA2C", "download_file_by_aria2c"]

ARIA2C = "aria2c"


def run_command_code(command: str, args: list[str]) -> int:
    process = subprocess.Popen([command, *args])
    return process.wait()


def download_file_by_aria2c(url: str, path: str, extra_args: str) -> None:
    """用 aria2c 下载；``extra_args`` 是用户额外参数（按空格切分）。"""
    args = [
        "--auto-file-renaming=false",
        "--download-result=hide",
        "--allow-overwrite=true",
        "--console-log-level=warn",
        "-x16",
        "-s16",
        "-j16",
        "-k5M",
    ]
    if "platform=android_tv_yst" not in url and "platform=android" not in url:
        args.append("--header=Referer: https://www.bilibili.com")
    args.append("--header=User-Agent: Mozilla/5.0")
    args.append(f"--header=Cookie: {Config.COOKIE}")

    if extra_args:
        import shlex

        args.extend(shlex.split(extra_args, posix=False))

    args.extend([url, "-d", os.path.dirname(path) or ".", "-o", os.path.basename(path)])
    run_command_code(ARIA2C, args)
