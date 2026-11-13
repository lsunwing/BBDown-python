"""BBDown-python —— BBDown 的 Python 重写版。

本项目是 nilaoda/BBDown 的独立 Python 实现，版本号自成一条线，从 1.0.0 开始，
与原 C# 项目的 1.6.x 版本号没有对应关系。

原项目：https://github.com/nilaoda/BBDown (MIT License)
"""

from __future__ import annotations

#: 本项目的版本号（独立于原 C# 项目 BBDown 的版本号）
__version__ = "1.0.0"

#: 项目名，用于日志横幅、--version、HTTP Server 头等
PROJECT_NAME = "BBDown-python"

__all__ = ["__version__", "PROJECT_NAME"]
