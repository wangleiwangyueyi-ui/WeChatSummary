# 发布和升级

## 以后调整界面、修复问题、增加功能

1. 修改源码并测试。更新 `version.py` 的 `VERSION`（例如 `1.1.0` → `1.1.1`），填写 `CHANGELOG.md`。
2. 如果改了 Python 或依赖版本，同时增加 `RUNTIME_VERSION`；构建脚本会把它传给安装包，用于运行环境版本检查。
3. 在具有完整依赖的 Windows Python 3.12 环境中构建安装包。
4. 在隔离目录验证首次安装、升级和卸载；确认个人配置保留。将源码提交到 GitHub。
5. 创建对应的 `v版本` Git tag 和 GitHub Release，上传三个安装包、`release.json`、`SHA256SUMS.txt`。自动生成的 GitHub 源码压缩包与 tag 对应。
6. 用户点击“检查更新”，软件读取最新的正式 Release。同一运行环境优先下载 Update；运行环境变化时使用 Setup。图片/语音组件不随普通更新重新下载。

仅推送源码不会向用户发布更新；必须创建正式 Release。草稿和预览版不会被本软件选中。当前功能由用户主动检查、主动安装，不会后台强行覆盖正在运行的程序。

## 构建

使用官方 [Inno Setup](https://jrsoftware.org/inno-setup/downloads) 编译器。保持完整 Python 环境与软件测试环境一致。`prepare_release.py` 只读取指定环境和允许发布的源码文件，不读取应用配置。

```powershell
python release_tools/fetch_model.py --output models/sensevoice
pwsh -File release_tools/build_release.ps1 `
  -Python C:\Python312\python.exe `
  -Models "$PWD\models\sensevoice" `
  -Compiler "C:\Program Files (x86)\Inno Setup 7\ISCC.exe" `
  -BuildDirectory "$PWD\build-1.1.0"
```

输出目录必须是新的目录，避免误删旧文件。构建器支持普通 CPython 的 `tcl` 目录和 Conda 的 `Library` 目录。第三方具体版本记录在 `requirements-lock.txt` 与 `DEPENDENCIES.json`；发行时请附上完整对应源码和第三方许可证。

`build-版本/source` 是可发布源码目录；不要对开发工作区直接执行 `git add .`。只发布这个白名单目录，它不包括个人数据库、截图、验证记录、运行库、模型或安装包。安装包放 Releases，不放 Git 仓库。

## 发布工具

`release_tools/publish_release.py` 支持本机 Git Credential Manager 已授权的 GitHub 账号，或当前进程的 `GH_TOKEN`。不把令牌写入仓库或配置文件。先检查准备好的源码与安装包，再运行：

```powershell
python release_tools/publish_release.py --source build-1.1.0/source --assets build-1.1.0/installers
```

首次执行会创建公开仓库；后续提交新版本，上传到草稿 Release，最后再将草稿发布。任何上传失败都会保留草稿，避免用户看到缺件的正式更新。

## 用户数据与回退

安装程序只更新程序文件。配置、密钥、计数、定时记录和本地语音缓存位于 `%LOCALAPPDATA%\WeChatSummary`，不属于卸载清单。DPAPI 密钥绑定用户，不能复制给其他人的电脑使用。

需要退回旧版本时，先退出软件，保留个人数据备份，再安装对应旧版本 Setup。未来若涉及数据格式迁移，应先实现版本化迁移与备份，再发布；当前更新器不做数据格式迁移。

## 发布前检查

- 新用户没有作者账号路径、凭据或自动运行任务。
- 主程序在没有全局 Python 的情况下能启动；未装可选组件时文字功能能用。
- 图片/语音组件的许可证与模型来源齐全。
- 更新不覆盖配置；运行中安装会提示先退出。
- 测试版本比较、下载校验失败、网络失败和新用户初始化。
- 在另一台干净的 Windows 10/11 电脑上做实际微信版本兼容性验证。
