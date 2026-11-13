# BBDown-python

**BBDown-python version 1.0.0, Bilibili Downloader.**

命令行式哔哩哔哩下载 / 解析工具，是 [BBDown](https://github.com/nilaoda/BBDown)（C# / .NET 9）的
Python 重写实现。保留原项目的命令行参数、输出格式和接口请求方式，用纯 Python 重新实现全部功能。

> 本项目仅供个人学习、研究和非商业用途。请自行确保遵守相关法律法规与平台条款，仅在有合法授权的情况下使用。

---

## 目录

- [致谢与参考](#致谢与参考)
- [版本说明](#版本说明)
- [功能特性](#功能特性)
- [安装](#安装)
- [快速开始](#快速开始)
- [详细使用](#详细使用)
  - [支持的输入格式](#支持的输入格式)
  - [参数总表](#参数总表)
  - [常用场景](#常用场景)
  - [自定义输出文件名](#自定义输出文件名)
  - [配置文件](#配置文件)
  - [扫码登录](#扫码登录)
  - [服务器模式](#服务器模式)
  - [退出码与环境变量](#退出码与环境变量)
- [常见问题](#常见问题)
- [代码结构](#代码结构)
- [与原版的差异](#与原版的差异)
- [开发与测试](#开发与测试)
- [许可](#许可)

---

## 致谢与参考

这个项目**不是**原创作品，而是对 [nilaoda/BBDown](https://github.com/nilaoda/BBDown) 的学习性重写。
所有接口协议、参数命名、流程编排、输出文案都来自原项目，在此向原作者和社区致谢：

| 参考对象 | 说明 |
| --- | --- |
| [nilaoda/BBDown](https://github.com/nilaoda/BBDown) | 原项目（C# / .NET 9，MIT）。本项目的模块划分、命令行参数、解析流程、混流参数、日志格式均移植自它 |
| BBDown 的 `README.md` / `json-api-doc.md` | 参数语义与 HTTP 服务器接口文档 |
| [Colerar/abv](https://github.com/Colerar/abv) | BV 号 / av 号互转算法（原项目注释中标明出处，本项目同样移植自此） |
| [QRCoder](https://github.com/codebude/QRCoder) | 原项目用它生成登录二维码；Python 版改用可选的 `qrcode` 库 |
| [Google.Protobuf](https://github.com/protocolbuffers/protobuf) / [grpc](https://github.com/grpc/grpc) | 原项目的 APP 端 gRPC 调用；Python 版用自写的极简 proto2 编解码器复刻 |
| [System.CommandLine](https://github.com/dotnet/command-line-api) | 原项目的命令行框架；Python 版改用 `argparse` 并复刻其布尔开关行为 |
| [SharpZipLib](https://github.com/icsharpcode/SharpZipLib) | 原项目的压缩依赖；Python 版直接用标准库 `gzip` |
| [SocialSisterYi/bilibili-API-collect](https://github.com/SocialSisterYi/bilibili-API-collect) | B 站接口文档（原项目致谢对象，本项目同样受益） |
| [SeeFlowerX/bilibili-grpc-api](https://github.com/SeeFlowerX/bilibili-grpc-api) | APP 端 gRPC 接口资料（原项目致谢对象） |
| [FFmpeg](https://github.com/FFmpeg/FFmpeg) | 音视频混流、FLV 分段转封装 |
| [GPAC / MP4Box](https://github.com/gpac/gpac) | `--use-mp4box` 时的替代混流器 |
| [aria2](https://github.com/aria2/aria2) | `--use-aria2c` 时的外部下载器 |

原项目采用 MIT 协议，本项目同样以 MIT 发布（见 [许可](#许可)）。

## 版本说明

本项目的版本号**自成一条线，从 1.0.0 开始**，与原 C# 项目 BBDown 的 1.6.x 没有对应关系：

```
$ bbdown --version
BBDown-python 1.0.0
```

启动横幅：

```
BBDown-python version 1.0.0, Bilibili Downloader.
```

也正因如此，Python 版**不做**「检查 BBDown 是否有新版本」——那是原项目的发布渠道，
与这里无关（原版会在启动时比对 GitHub Release tag）。

## 功能特性

- 普通投稿视频下载：Web / TV / APP / 国际版四种接口
- 番剧下载：Web / TV / APP（APP 端可选角色配音、背景音轨，并支持片头片尾章节）
- 课程（cheese）、合集（collection）、系列（series）、收藏夹（favlist）、UP 主投稿列表
- 多分 P 自动下载、指定分 P / 范围 / 交集下载
- 画质与编码选择（8K / HDR / 杜比视界 / 杜比全景声 / Hi-Res 无损，AVC / HEVC / AV1）
- 外挂字幕下载并转换为 SRT
- 弹幕下载（保留 XML 和/或生成 ASS 字幕）
- 自动合并「视频 + 音频 + 字幕 + 封面 + 章节」，支持 ffmpeg 与 MP4Box
- 单独下载视频 / 音频 / 字幕 / 封面 / 弹幕
- 多线程分片下载、断点续传，或调用 aria2c
- 二维码登录（网页账号 / 云视听小电视）
- 自定义输出文件名、本地配置文件
- HTTP 服务器模式（供第三方程序提交任务、查询进度）

## 安装

只需要 Python 3.10+。

```bash
# 1. 直接运行，不安装
cd BBDown-python
python -m bbdown "BV1qt4y1X7TW"

# 2. 以开发模式安装，之后任何目录都能用 bbdown 命令
cd BBDown-python
python -m pip install -e .
bbdown "BV1qt4y1X7TW"

# 3. 只装依赖后手动加 PATH / 用绝对路径
python -m pip install -r requirements.txt
```

### Windows 上 `python` 打不开？

如果敲 `python` 提示「Python was not found; run without arguments to install from the Microsoft Store」，
但你**确实装过** Python，通常是 **微软商店的"应用执行别名"** 抢占了 `python` 这个名字：

```powershell
# 看看 python 到底指向哪，出现两条就说明被抢了
Get-Command python -All

# 真解释器通常在（配合 py 启动器使用）
py --version
```

三种解决办法，任选其一：

1. 把命令里的 `python` 换成 `py`（Windows 官方启动器，最省事）；
2. 设置 → 应用 → 高级应用设置 → **应用执行别名** → 关掉 `python.exe` / `python3.exe`，重开终端；
3. 用完整路径，例如 `C:\Users\<你>\AppData\Local\Python\bin\python.exe`。

### 依赖

| 依赖 | 用途 | 是否必需 |
| --- | --- | --- |
| `requests` | 所有 HTTP 请求 | **必需** |
| `ffmpeg` | 混流、FLV 分段转封装 | **下载时必需** |
| `mp4box` | `--use-mp4box` 时混流 | 可选 |
| `aria2c` | `--use-aria2c` 时下载 | 可选 |
| `qrcode` | 登录时生成二维码图片 | 可选（没有也能扫终端二维码/链接） |

```bash
python -m pip install requests
python -m pip install qrcode      # 可选
```

`ffmpeg` 需要在 `PATH` 里，或者用 `--ffmpeg-path` 指定；`--version`（即 `ffmpeg -version`）建议 5.0 以上，
否则杜比视界片源会自动改用 mp4box 混流。

## 快速开始

```powershell
cd D:\workspace\BBDown-python

# 先看解析结果，不下载
py -m bbdown -info "BV1qt4y1X7TW"

# 下载 + 自动混流，产物落在当前目录
py -m bbdown "BV1qt4y1X7TW"

# 下载番剧全集
py -m bbdown -p ALL "https://www.bilibili.com/bangumi/play/ss33073"
```

下载完成后当前目录会得到 `视频标题.mp4`（多分P 时为 `视频标题/[P01]分P标题.mp4`）。

## 详细使用

```
bbdown <url> [options]
bbdown login|logintv|serve
```

### 支持的输入格式

大小写不敏感；`https://` 可以省略；首尾的引号（含中文引号）和空格会自动去掉。

```
BV1qt4y1X7TW                              av170001
bilibili.com/video/BV1qt4y1X7TW           带 ?p=2&spm_id_from=... 等参数的完整链接
b23.tv/xxxxxx                             b23 短链（自动跟随重定向）
ep12345                                   ss33073                    md12345
https://www.bilibili.com/bangumi/play/ep12345
https://www.bilibili.com/bangumi/media/md12345
https://space.bilibili.com/2/lists/1560264?type=season        合集
https://space.bilibili.com/2/channel/seriesdetail?sid=340933   系列
https://space.bilibili.com/3/favlist?fid=123                   收藏夹（fid 留空则用默认收藏夹）
https://space.bilibili.com/3                                   UP 主投稿（仅导出地址列表）
cheese/ep100                              课程
```

### 参数总表

开关型参数（`BOOL`）都可以只写参数名（等价于 `true`），也可以显式写值，例如 `--multi-thread false`。

#### 1) 使用哪个解析接口

| 参数 | 说明 |
| --- | --- |
| `-tv, --use-tv-api` | 用 TV 端接口解析（粉丝量大的 UP 主基本无水印片源） |
| `-app, --use-app-api` | 用 APP 端接口解析（番剧可拿到角色配音、背景音；需配合 `-token`） |
| `-intl, --use-intl-api` | 用国际版（东南亚）接口解析 |
| `--host HOST` | 指定 BiliPlus host（需要 access_token，不需要 cookie） |
| `--ep-host HOST` | 指定 BiliPlus EP host（代理 `api.bilibili.com/pgc/view/web/season`） |
| `--tv-host HOST` | 自定义 TV 端接口 host（代理 `api.snm0516.aisee.tv`） |
| `--area AREA` | `hk` / `tw` / `th`，使用 BiliPlus 时必选 |

默认使用 Web 接口，四者互斥优先级为 `-tv` > `-app` > `-intl` > Web。

#### 2) 解析与画质选择

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `-info, --only-show-info` | `false` | 只解析不下载；同时会打印每条流的直链 |
| `-q, --dfn-priority` | 无 | 画质优先级，逗号分隔，如 `"8K 超高清, 1080P 高码率, HDR 真彩, 杜比视界"` |
| `-e, --encoding-priority` | 无 | 编码优先级，逗号分隔，如 `"hevc,av1,avc,flac,eac3,m4a"` |
| `--video-ascending` | `false` | 视频按码率升序（最小体积优先） |
| `--audio-ascending` | `false` | 音频按码率升序（最小体积优先） |
| `--show-all` | `false` | 列出所有分 P（默认只显示前 5 个和最后 1 个） |
| `-hs, --hide-streams` | `false` | 不打印可用音视频流列表 |
| `-ia, --interactive` | `false` | 交互式选择清晰度（会忽略 `-hs`） |

同时给出 `-e` 与 `-q` 时，按它们在命令行中**出现的先后顺序**决定主次排序。

#### 3) 下载什么

| 参数 | 说明 |
| --- | --- |
| `-p, --select-page PAGE` | 选择分 P：`8` / `1,2` / `3-5` / `ALL` / `LAST` / `LATEST` / `3,5,LATEST` |
| `--audio-only` | 只下载音频（输出 `.m4a`） |
| `--video-only` | 只下载视频 |
| `--sub-only` | 只下载字幕 |
| `--cover-only` | 只下载封面 |
| `--danmaku-only` | 只下载弹幕 |
| `--skip-subtitle` | 跳过字幕下载 |
| `--skip-cover` | 跳过封面下载 |
| `--skip-mux` | 跳过混流（保留中间文件） |
| `--simply-mux` | 精简混流，不写入描述、作者等元数据 |
| `-dd, --download-danmaku` | 下载弹幕 |
| `-ddf, --download-danmaku-formats` | 弹幕格式，逗号分隔：`xml` / `ass`，默认 `xml,ass` |
| `--skip-ai` | 跳过 AI 字幕（默认开启） |
| `--language LANG` | 混流时写入的音频语言代码，如 `chi` / `jpn` |
| `--delay-per-page N` | 多分 P 之间的间隔秒数，默认 `0` |

`--audio-only` 与 `--video-only` 同时给出时两者都失效（按普通下载处理）。

#### 4) 下载与混流方式

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `-mt, --multi-thread` | `true` | 多线程分片下载（20MB 一片，支持续传） |
| `--force-http` | `true` | 下载音视频时把 `https` 换成 `http`（部分 CDN 更稳） |
| `-aria2, --use-aria2c` | `false` | 调用 aria2c 下载 |
| `--aria2c-args ARGS` | 无 | aria2c 附加参数（默认已带 `-x16 -s16 -j16 -k5M`） |
| `--aria2c-path PATH` | 自动查找 | aria2c 可执行文件路径 |
| `--use-mp4box` | `false` | 用 MP4Box 混流（替代 ffmpeg） |
| `--ffmpeg-path PATH` | 自动查找 | ffmpeg 路径 |
| `--mp4box-path PATH` | 自动查找 | mp4box 路径 |
| `--upos-host HOST` | 无 | 强制替换下载服务器 host，如 `upos-sz-mirrorali.bilivideo.com` |
| `--force-replace-host` | `true` | 强制替换下载服务器 host（PCDN 自动换备用源） |
| `--allow-pcdn` | `false` | 不替换 PCDN 域名（仅在其它方式都下不动时使用） |

#### 5) 输出与记录

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `-F, --file-pattern PATTERN` | `<videoTitle>` | 单分 P 文件名模板 |
| `-M, --multi-file-pattern PATTERN` | `<videoTitle>/[P<pageNumberWithZero>]<pageTitle>` | 多分 P 文件名模板 |
| `--work-dir DIR` | 当前目录 | 工作目录（会自动创建并支持 `%VAR%` 环境变量） |
| `--save-archives-to-file` | `false` | 把已下载过的 aid 记到 `BBDown.archives`，下次自动跳过 |
| `--config-file PATH` | 程序目录 `BBDown.config` | 指定配置文件 |

#### 6) 鉴权

| 参数 | 说明 |
| --- | --- |
| `-c, --cookie COOKIE` | 网页端 cookie 字符串，如 `"SESSDATA=xxxx"` |
| `-token, --access-token TOKEN` | TV / APP 端 access_token |
| `-ua, --user-agent UA` | 指定 User-Agent（默认随机） |

#### 7) 其它

| 参数 | 说明 |
| --- | --- |
| `--debug` | 输出调试日志（同时把接口原始 JSON 落盘为 `debug_*.json`） |
| `--version` | 打印版本号 |
| `-h, --help` | 帮助 |

已弃用但仍兼容的参数：`--only-hevc/-hevc`、`--only-avc/-avc`、`--only-av1/-av1`、
`--add-dfn-subfix`、`--no-padding-page-num`、`--bandwith-ascending`、`--aria2c-proxy`。
使用时会提示替代写法。

### 常用场景

```bash
# 普通下载 / 只看信息
bbdown "BV1qt4y1X7TW"
bbdown -info "BV1qt4y1X7TW"

# TV 接口（无水印片源）
bbdown -tv "BV1qt4y1X7TW"

# APP 接口（番剧配音）
bbdown -app -token "xxxx" "ep12345"

# 只要 1080P 高码率，且优先 HEVC
bbdown -q "1080P 高码率" -e hevc "BV1qt4y1X7TW"

# 只要音频 / 只要视频 / 只要封面 / 只要字幕 / 只要弹幕
bbdown --audio-only "BV1qt4y1X7TW"
bbdown --video-only "BV1qt4y1X7TW"
bbdown --cover-only "BV1qt4y1X7TW"
bbdown --sub-only   "BV1qt4y1X7TW"
bbdown --danmaku-only "BV1qt4y1X7TW"

# 顺带下载弹幕（xml + ass），并且跳过封面和字幕
bbdown -dd --skip-cover --skip-subtitle "BV1qt4y1X7TW"

# 选分P：单个 / 多个 / 范围 / 最后一个
bbdown -p 10 "BV1At41167aj"
bbdown -p 1,2,10 "BV1At41167aj"
bbdown -p 1-10 "BV1At41167aj"
bbdown -p LAST "BV1At41167aj"

# 番剧全集
bbdown -p ALL "https://www.bilibili.com/bangumi/play/ss33073"

# 下载到指定目录，并自定义文件名
bbdown --work-dir "D:\Videos" -F "<videoTitle>[<dfn>]" "BV1qt4y1X7TW"

# 交互式挑清晰度
bbdown -ia "BV1qt4y1X7TW"

# 下载不动时换源 / 关多线程
bbdown --upos-host upos-sz-mirrorali.bilivideo.com "BV1qt4y1X7TW"
bbdown -mt false "BV1qt4y1X7TW"

# 用 aria2c 下载
bbdown -aria2 "BV1qt4y1X7TW"

# 只保留中间文件，自己手动混流
bbdown --skip-mux "BV1qt4y1X7TW"
```

### 自定义输出文件名

`-F`（单分 P）与 `-M`（多分 P）支持以下变量：

| 变量 | 含义 |
| --- | --- |
| `<videoTitle>` | 视频主标题 |
| `<pageNumber>` | 分P序号 |
| `<pageNumberWithZero>` | 分P序号（前缀补零） |
| `<pageTitle>` | 分P标题 |
| `<bvid>` / `<aid>` / `<cid>` | BV 号 / aid / cid |
| `<dfn>` / `<res>` / `<fps>` | 清晰度 / 分辨率 / 帧率 |
| `<videoCodecs>` / `<videoBandwidth>` | 视频编码 / 码率 |
| `<audioCodecs>` / `<audioBandwidth>` | 音频编码 / 码率 |
| `<ownerName>` / `<ownerMid>` | UP 主名称 / mid |
| `<publishDate>` / `<videoDate>` | 收藏夹·番剧·合集发布时间 / 视频发布时间 |
| `<apiType>` | 接口类型：`TV` / `APP` / `INTL` / `WEB` |

日期变量可以带自定义 .NET 风格格式，例如：

```
-F "<publishDate:yyyyMMdd>_<videoTitle>[<dfn>]"
-F "<videoDate:yyyy-MM-dd HH-mm-ss>_<pageTitle>"
```

默认值：

- 单分 P：`<videoTitle>`
- 多分 P：`<videoTitle>/[P<pageNumberWithZero>]<pageTitle>`

文件名中的非法字符（`\ / : * ? " < > |` 与控制符）会被替换成 `_`。

### 配置文件

默认读取程序目录下的 `BBDown.config`，可用 `--config-file` 指定其它路径。
格式：以 `#` 开头为注释，其余每行一个 token，带参数的选项把参数写在下一行。

```config
# 输出文件名格式
--file-pattern
<videoTitle>[<dfn>]

--multi-file-pattern
<videoTitle>/[P<pageNumberWithZero>]<pageTitle>[<dfn>]

# 多分P 之间间隔 2 秒
--delay-per-page
2

# 开启弹幕下载
--download-danmaku

# 默认用 TV 接口
--use-tv-api
```

规则：

- 命令行参数的优先级**高于**配置文件；
- 配置文件里的开关也能写 `--multi-thread false` 这种形式；
- 解析失败会提示「配置文件读取异常，忽略」并继续执行。

### 扫码登录

```bash
bbdown login      # 网页账号，cookie 写入 BBDown.data
bbdown logintv    # 云视听小电视，access_token 写入 BBDownTV.data
```

终端会打印二维码并生成 `qrcode.png`（没装 `qrcode` 时退化为打印登录链接）。
登录成功后 cookie/token 保存到程序目录，后续启动自动读取。

APP 端的 token 需要自己抓包获取（请求头 `authorization: identify_v1 xxxx` 里的 `xxxx`），
也可以把 `BBDownTV.data` 复制成 `BBDownApp.data` 复用。

### 服务器模式

```bash
bbdown serve -l http://0.0.0.0:23333
```

默认监听 `http://0.0.0.0:23333`。接口与原项目 `json-api-doc.md` 一致
（响应字段 PascalCase，请求体字段大小写不敏感，只需 `Url`）：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/get-tasks/` | 所有任务（`{"Running": [...], "Finished": [...]}`） |
| GET | `/get-tasks/running` | 正在运行的任务列表 |
| GET | `/get-tasks/finished` | 已完成的任务列表 |
| GET | `/get-tasks/{aid}` | 单个任务，找不到返回 404 |
| POST | `/add-task` | 提交任务，body 为 `MyOption` 的 JSON；参数错误返回 400 |
| GET | `/remove-finished/` | 清空已完成任务 |
| GET | `/remove-finished/failed` | 只清理失败的任务 |
| GET | `/remove-finished/{aid}` | 清理指定 aid 的任务 |

`DownloadTask` 字段：`Aid`、`Url`、`TaskCreateTime`、`Title`、`Pic`、`VideoPubTime`、
`TaskFinishTime`、`Progress`、`DownloadSpeed`、`TotalDownloadedBytes`、`IsSuccessful`、`SavePaths`。

```bash
curl -X POST -H 'Content-Type: application/json' \
     -d '{"Url":"BV1qt4y1X7TW","FilePattern":"D:\\\\Downloads\\\\<videoTitle>"}' \
     http://127.0.0.1:23333/add-task

curl http://127.0.0.1:23333/get-tasks/finished
```

可选字段 `CallBackWebHook`：任务结束后把 `DownloadTask` 以 JSON POST 到该地址。
服务器不支持 HTTPS，需要的话自行用 nginx 反代。

### 退出码与环境变量

| 退出码 | 含义 |
| --- | --- |
| `0` | 成功 |
| `1` | 参数错误、解析失败、下载或混流失败 |

环境变量：

| 变量 | 作用 |
| --- | --- |
| `BBDOWN_HOME` | 指定数据目录（`BBDown.data` / `BBDownTV.data` / `BBDown.config` / `BBDown.archives` 所在处） |

数据目录查找顺序：`BBDOWN_HOME` → 源码工程根目录 → 当前工作目录。

## 常见问题

**Q：敲 `python` 提示去微软商店安装？**
说明装了 Python 但被商店的「应用执行别名」抢占，用 `py` 代替 `python`，或按[安装](#安装)一节关掉别名。

**Q：提示「找不到可执行的ffmpeg文件」？**
装 ffmpeg 并确保在 `PATH` 里，或用 `--ffmpeg-path "C:\ffmpeg\bin\ffmpeg.exe"` 指定。
不需要混流时可以加 `--skip-mux`。

**Q：为什么最高只有 480P / 360P？**
未登录时 B 站只给低清晰度。先 `bbdown login`，或用 `-c "SESSDATA=..."`。
1080P 高码率、4K、HDR、杜比等通常还需要大会员。

**Q：提示「此视频需要大会员」？**
登录一个有大会员的账号；番剧也可以试 `-tv` 或 `-app -token`。

**Q：下载报「服务器可能并不支持多线程下载」？**
部分 CDN 不支持 Range 请求，加 `-mt false` 关掉多线程。

**Q：混流失败 / 音画不同步？**
先确认 `ffmpeg -version` 可用。杜比视界片源建议 ffmpeg 5.0+，程序检测到版本过低会自动改用 mp4box。

**Q：上次下载中断了，能续传吗？**
可以。分片和单线程下载都会写 `.tmp` / `.vclip` / `.aclip` 临时文件，重新执行同一命令会从断点继续。
想彻底重下就删掉这些临时文件。

**Q：控制台中文乱码？**
程序启动时会把控制台切到 UTF-8（代码页 65001）。仍异常的话用 Windows Terminal，或先执行 `chcp 65001`。

**Q：`-dd` 没有生成 ass？**
可能是该视频没有弹幕，或弹幕 XML 解析失败（会打印提示并删掉 xml）。
也可以用 `-ddf` 只保留其中一种格式。

## 代码结构

模块与原 C# 工程基本一一对应，方便对照阅读：

| 原项目文件 | Python 模块 | 说明 |
| --- | --- | --- |
| `BBDown/Program.cs` | `bbdown/workflow.py` | 主流程、逐分P下载 |
| `BBDown/Program.Methods.cs` | `bbdown/workflow.py` | 选项预处理、轨道排序、CDN 替换 |
| `BBDown/CommandLineInvoker.cs` | `bbdown/cli.py` | 命令行参数定义 |
| `BBDown/MyOption.cs` | `bbdown/options.py` | 选项数据模型 |
| `BBDown/BBDownUtil.cs` | `bbdown/util.py`、`bbdown/aid.py` | 通用工具、输入解析 |
| `BBDown/BBDownDownloadUtil.cs` | `bbdown/download.py` | 单线程 / 多线程分片下载 |
| `BBDown/BBDownMuxer.cs` | `bbdown/muxer.py` | ffmpeg / mp4box 混流 |
| `BBDown/BBDownAria2c.cs` | `bbdown/aria2c.py` | aria2c 调用 |
| `BBDown/BBDownLoginUtil.cs` | `bbdown/login.py` | 扫码登录 |
| `BBDown/BBDownApiServer.cs` | `bbdown/server.py` | HTTP 服务器 |
| `BBDown/ProgressBar.cs` | `bbdown/console.py` | 进度条 |
| `BBDown.Core/Parser.cs` | `bbdown/playurl.py` | playurl 解析 |
| `BBDown.Core/AppHelper.cs` | `bbdown/grpc_app.py` + `bbdown/pb.py` | APP 端 gRPC 接口 |
| `BBDown.Core/Fetcher/*.cs` | `bbdown/fetchers/` | 普通 / 番剧 / 课程 / 国际版 / 合集 / 系列 / 收藏夹 / 空间 |
| `BBDown.Core/Entity/*.cs` | `bbdown/entity.py` | 数据实体 |
| `BBDown.Core/Util/HTTPUtil.cs` | `bbdown/net.py` | HTTP 封装 |
| `BBDown.Core/Util/SubUtil.cs` | `bbdown/subtitle.py` | 字幕接口与 SRT 转换 |
| `BBDown.Core/Util/BilibiliBvConverter.cs` | `bbdown/bv.py` | BV / av 互转 |
| `BBDown.Core/DanmakuUtil.cs` | `bbdown/danmaku.py` | 弹幕解析与 ASS 生成 |
| `BBDown.Core/Logger.cs` | `bbdown/console.py` | 彩色日志 |
| `BBDown.Core/Config.cs` | `bbdown/config.py` | 全局配置 |

## 与原版的差异

行为、参数、输出都尽量与 BBDown 一致，但实现上有这些不同：

**实现方式**

1. 原版是 `async/await`，这里是同步 IO + 线程池（分片下载、服务器任务、进度条各用线程）。
2. 原版用 `Grpc.Tools` 生成 protobuf 类，这里用 `bbdown/pb.py` 手写的极简 proto2 编解码器，不需要 protoc。
3. 原版用 `System.CommandLine`，这里用 `argparse` 并额外做了布尔开关的预处理。
4. 二维码依赖改为可选，没有 `qrcode` 时退化为打印链接。
5. 版本号独立（1.0.0 起），因此移除了「检查 BBDown 新版本」功能。

**顺手修掉的 7 个原版问题**

1. **断点续传**：原版用「整文件长度 != Content-Length」判断完整性，导致续传必然失败重试三次；改成比较本次实际接收字节数。
2. **字幕流索引**：原版混流时用带 `skip` 的循环下标做 `-metadata:s:s:i`，空字幕文件会让索引错位；改用独立计数器。
3. **FLV 分段合并**：原版扫描整个目录下的 `*.mp4` 再合并，多分P并发时可能串台；只合并本次下载的分段。
4. **未知清晰度**：`qn` 不在内置表里时原版抛 `KeyNotFoundException`；回退为原值。
5. **错误提示**：视频信息接口 `code != 0` 时给出明确错误，而不是得到一个空标题。
6. **并发数**：原版等于 CPU 核心数，这里取 `min(16, max(4, cpu))`，避免把 CDN 打挂。
7. **开关值写法**：`--multi-thread false` 不会被误当成 URL。

## 开发与测试

```bash
# 不依赖 pytest 的测试运行器
python tests/run_tests.py

# 或者用 pytest
python -m pip install pytest
pytest
```

目前 49 项单元测试，覆盖：BV 号互转、protobuf 编解码、gRPC 分帧、下载分片切分、
文件名模板、命令行参数解析、输入链接容错、字幕语言映射、弹幕转 ASS、版本与横幅。

目录约定：

```
BBDown-python/
├── bbdown/                 主程序包
│   ├── fetchers/           各场景的元信息解析器
│   ├── __main__.py         python -m bbdown 入口
│   ├── cli.py              参数定义与入口分发
│   └── workflow.py         主流程
├── tests/                  单元测试
├── pyproject.toml
├── requirements.txt
└── README.md
```

## 许可

与原项目 BBDown 一致，采用 [MIT License](https://opensource.org/licenses/MIT)。

原项目版权归 [nilaoda](https://github.com/nilaoda) 及 BBDown 贡献者所有；
本 Python 重写版的改动部分同样以 MIT 发布。
