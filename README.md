# 微信聊天总结分析助手

<img src="assets/wechat-summary.png" alt="微信聊天总结分析助手图标" width="88" align="right">

这款 Windows 10/11 64 位工具可以导出本机已同步的微信群聊，按人物筛选，也可以用 Gemini 汇总并通过 PushPlus 发到手机。

## 第一次安装

**[直接下载 Windows 主安装包 v1.2.6（Setup）](https://github.com/wangleiwangyueyi-ui/WeChatSummary/releases/download/v1.2.6/WeChatSummary-Setup-1.2.6.exe)**

双击已包含 Python 的主安装包，保留默认勾选的「创建桌面快捷方式」。装好后，在桌面双击「微信聊天总结分析助手」，也可以在开始菜单搜索同名应用。

### 安装后怎么配置

1. 打开 Windows 微信，让要导出的群聊同步到本机。再打开本工具的「基础配置与初始化」。
2. 选择包含 `db_storage` 的微信账号文件夹，按「首次离线初始化向导」完成本机初始化。微信版本兼容性以向导的校验结果为准。
3. **只导出文字**，到「历史与人物查询」选群和时间，点击「仅导出记录」。**需要 AI 总结**，在基础配置中填自己的 Gemini API Key。**需要手机推送**，再填自己的 PushPlus Token。填好后点击「保存参数」。
4. **需要识图或语音转写**，在「基础配置与初始化 → 图片/语音组件」按需安装。需要处理 V2 加密图片时，再完成本机图片密钥初始化。
5. **需要每天自动汇总**，在「日常汇总」勾选群聊、选择运行时间，点击「保存日常设置」，再点击「启用定时计划」。

### 其他下载

[查看最新正式版及全部安装包](https://github.com/wangleiwangyueyi-ui/WeChatSummary/releases/latest)

| 文件 | 适合谁 | 内容 |
| --- | --- | --- |
| `WeChatSummary-Setup-版本.exe` | 第一次安装 | 主程序、Python 运行环境、文本导出、Gemini 和 PushPlus 接口 |
| `WeChatSummary-Media-版本.exe` | 需要识图、语音转写 | 可选本地 OCR、语音引擎与语音模型，先装主程序，再装到同一目录 |
| `WeChatSummary-Update-版本.exe` | 已安装用户 | 小型程序更新；运行环境有变化时改用 Setup |

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
