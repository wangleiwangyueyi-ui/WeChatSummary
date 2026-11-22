#ifndef Version
  #define Version "1.1.0"
#endif
#ifndef Kind
  #define Kind "setup"
#endif
#ifndef RuntimeVersion
  #define RuntimeVersion "1"
#endif
#ifndef Payload
  #error Payload is required
#endif
#ifndef Output
  #error Output is required
#endif
#if Kind == "media"
  #define ProductName "WeChatSummary 图片与语音组件"
  #define FilePrefix "WeChatSummary-Media"
#elif Kind == "update"
  #define ProductName "WeChatSummary 程序更新"
  #define FilePrefix "WeChatSummary-Update"
#else
  #define ProductName "微信聊天总结分析助手"
  #define FilePrefix "WeChatSummary-Setup"
#endif

[Setup]
#if Kind == "media"
AppId=Boyce.WeChatSummary.Media
#else
AppId=Boyce.WeChatSummary
#endif
AppName={#ProductName}
AppVersion={#Version}
AppPublisher=Boyce
AppPublisherURL=https://github.com/wangleiwangyueyi-ui/WeChatSummary
AppSupportURL=https://github.com/wangleiwangyueyi-ui/WeChatSummary/issues
AppUpdatesURL=https://github.com/wangleiwangyueyi-ui/WeChatSummary/releases
DefaultDirName={localappdata}\Programs\WeChatSummary
DefaultGroupName=微信聊天总结分析助手
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#Output}
OutputBaseFilename={#FilePrefix}-{#Version}
Compression=lzma2
SolidCompression=yes
LZMANumBlockThreads=4
WizardStyle=modern
UninstallDisplayName={#ProductName}
AppMutex=Local\WeChatSummaryDesktop
CloseApplications=no
RestartApplications=no
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
UsePreviousTasks=yes
SetupLogging=yes
#if Kind != "media"
LicenseFile={#Payload}\LICENSE
SetupIconFile={#Payload}\assets\wechat-summary.ico
UninstallDisplayIcon={app}\assets\wechat-summary.ico
#endif
#if Kind == "media"
UninstallFilesDir={app}\uninstall-media
#endif

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "{#Payload}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

#if Kind != "media"
#if Kind == "setup"
[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; Flags: checkedonce
#endif
[Icons]
Name: "{autoprograms}\微信聊天总结分析助手"; Filename: "{app}\runtime\pythonw.exe"; Parameters: "-s ""{app}\wechat_gui.pyw"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\wechat-summary.ico"; Check: not WizardNoIcons
#if Kind == "setup"
Name: "{autodesktop}\微信聊天总结分析助手"; Filename: "{app}\runtime\pythonw.exe"; Parameters: "-s ""{app}\wechat_gui.pyw"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\wechat-summary.ico"; Tasks: desktopicon
#else
Name: "{autodesktop}\微信聊天总结分析助手"; Filename: "{app}\runtime\pythonw.exe"; Parameters: "-s ""{app}\wechat_gui.pyw"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\wechat-summary.ico"; Check: HasDesktopShortcut
#endif
#endif
#if Kind != "media"
[Run]
Filename: "{app}\runtime\pythonw.exe"; Parameters: "-s ""{app}\wechat_gui.pyw"""; WorkingDir: "{app}"; Description: "启动微信聊天总结分析助手"; Flags: nowait postinstall skipifsilent
#endif

[Code]
#if Kind == "update"
function HasDesktopShortcut: Boolean;
begin
  Result := FileExists(ExpandConstant('{autodesktop}\微信聊天总结分析助手.lnk'));
end;
#endif

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Runtime: AnsiString;
begin
  Result := '';
#if Kind != "setup"
  if not FileExists(ExpandConstant('{app}\installed-mode.json')) then
    Result := '请先安装主程序安装包（Setup），再选择相同安装目录。'
  else if not LoadStringFromFile(ExpandConstant('{app}\runtime-version.txt'), Runtime) then
    Result := '未找到运行环境版本，请安装主程序安装包。'
  else if Trim(String(Runtime)) <> '{#RuntimeVersion}' then
    Result := '运行环境不匹配，请从发布页下载完整主程序安装包。';
#endif
end;
