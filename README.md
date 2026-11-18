# 微信聊天总结分析助手

Windows 10/11 64 位桌面工具：读取本机已同步的微信群记录，导出历史、按人物筛选，使用 Gemini 汇总并通过 PushPlus 发送到自己的手机。

## 下载与安装

打开 [正式版本下载页](https://github.com/wangleiwangyueyi-ui/WeChatSummary/releases/latest)。

| 文件 | 适合谁 | 内容 |
| --- | --- | --- |
| `WeChatSummary-Setup-版本.exe` | 第一次安装 | 主程序、Python 运行环境、文本导出、Gemini 和 PushPlus 接口 |
| `WeChatSummary-Media-版本.exe` | 需要识图、语音转写 | 可选本地 OCR、语音引擎与语音模型，先装主程序，再装到同一目录 |
| `WeChatSummary-Update-版本.exe` | 已安装用户 | 小型程序更新；运行环境有变化时改用 Setup |

普通用户不必安装 Python、不必运行 pip。模型保留在本机，不需要每次升级重新下载。

首次安装后：

1. 打开“基础配置与初始化”，选择自己电脑上包含 `db_storage` 的微信账号文件夹。
2. 根据“首次离线初始化”向导完成本机初始化。微信版本兼容性以实际校验为准；每台新电脑都需要独立初始化。
3. 填入自己的 Gemini Key、PushPlus Token；代理按自己网络填写，没有则留空。密钥加密保存在当前 Windows 用户目录中。
4. 若使用图片或语音，安装可选组件，按需初始化图片密钥，然后勾选本地识别功能并保存。
5. 选择群聊、保存日常设置，再启用自动运行。只导出文字不需要 Gemini Key；云端总结和推送需要对应服务可用额度。

## 更新

“基础配置与初始化 → 检查更新”显示版本与更新说明，下载完成会验证 SHA-256。点击“退出并安装”后打开安装向导。任务运行时不会执行安装。

安装版程序默认位于 `%LOCALAPPDATA%\Programs\WeChatSummary`，个人配置位于 `%LOCALAPPDATA%\WeChatSummary`。更新不覆盖个人数据，卸载也保留个人数据。旧版便携目录仍沿用原存储方式；更新到同一旧目录时会优先读取原有配置，不自动迁移密钥。

GitHub 无法访问时可使用作者分享的相同安装包；检测失败不会影响日常运行。软件尚未购买 Windows 代码签名证书，Windows 可能显示“未知发布者”；发布页提供 SHA256SUMS 校验文件。

## 数据与费用

原始记录来自本机已同步内容，不能恢复已删除或未同步记录。本地 OCR/语音不调用 Gemini；需要云端汇总时，会把选中的文本及本地识别结果发送给所配置的 Gemini 服务。PushPlus 接收生成的报告。排版、查看帮助、检查版本不消耗 Gemini 额度。免费层与限制以各服务当前账号和官方规则为准。

仓库与安装包不包含作者的 Key、Token、数据库密钥、聊天数据库、账号目录、群聊选择、日志或使用记录。

## 开发与发布

源码使用 Python 3.12 和 CustomTkinter。开发环境执行 `python -m pip install -r requirements.txt`，然后运行 `python wechat_gui.pyw`。第一次运行不启用定时任务。

详见 [发布与升级步骤](UPGRADING.md)、[更新记录](CHANGELOG.md)、[第三方说明](THIRD_PARTY.txt)。源代码采用 GPL-3.0；随附完整 LICENSE。第三方依赖与模型遵循各自许可证，安装包保留其许可证和版本清单。

作者：Boyce
