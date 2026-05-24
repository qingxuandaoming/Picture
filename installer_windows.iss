; AI图片智能重命名与分类系统 Inno Setup 安装脚本
; --------------------------------------------------------

#define MyAppName "AI图片重命名 (开发：陈冠衡)"
#define MyAppVersion "2.2.5"
#define MyAppPublisher "陈冠衡"
#define MyAppExeName "VLM_Renamer.exe"

[Setup]
; AppId是唯一标识符，用于卸载和更新。生成自己的 GUID：在 Inno Setup IDE 中按 Tools -> Generate GUID
AppId={{9F82A0B7-4D3C-4C8D-9E9A-8F7B6A5C4D3E}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
; 默认安装目录
DefaultDirName={autopf}\VLM_Renamer
; 默认开始菜单文件夹
DefaultGroupName={#MyAppName}
; 禁用欢迎页面
DisableWelcomePage=no
; 输出安装包的名称和位置
OutputDir=dist\installers
OutputBaseFilename=VLM_Renamer_Setup_v2.2.5
; 压缩算法
Compression=lzma2/ultra64
SolidCompression=yes
; 需要管理员权限来安装到 Program Files
PrivilegesRequired=admin
; 卸载图标
SetupIconFile=logo.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; 我们将打包 PyInstaller 生成的单文件 exe
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
; 还可以添加文档、说明文件等
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion isreadme

[Icons]
; 开始菜单快捷方式
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
; 卸载快捷方式
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
; 桌面快捷方式
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; 安装完成后提供运行选项
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Registry]
; 可以在这里写入注册表信息，例如设置随系统启动，或添加右键菜单
; 示例：在当前用户注册表写入安装路径
Root: HKCU; Subkey: "Software\VLM_Renamer"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey
