#ifndef SourceRoot
  #define SourceRoot "..\dist\VoiceBridge"
#endif
#ifndef OutputRoot
  #define OutputRoot "..\dist"
#endif
#define AppVersion "1.1.0"

[Setup]
AppId=VoiceBridge.OpenSource
AppName=声桥 VoiceBridge
AppVersion={#AppVersion}
AppPublisher=VoiceBridge contributors
AppPublisherURL=https://github.com/hyh31415-maker/VoiceBridge
DefaultDirName={localappdata}\Programs\VoiceBridgePublic
DefaultGroupName=声桥 VoiceBridge
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
WizardStyle=modern
DisableProgramGroupPage=yes
OutputDir={#OutputRoot}
OutputBaseFilename=VoiceBridge-Windows-x64-Setup-{#AppVersion}
SetupIconFile=..\desktop\voicebridge\assets\app.ico
UninstallDisplayIcon={app}\VoiceBridge.exe
Compression=lzma2/max
SolidCompression=yes
CloseApplications=yes
RestartApplications=no
SetupLogging=yes
UsePreviousAppDir=yes

[Languages]
Name: "chinesesimp"; MessagesFile: "ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "{#SourceRoot}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\声桥 VoiceBridge"; Filename: "{app}\VoiceBridge.exe"; WorkingDir: "{app}"
Name: "{group}\使用说明"; Filename: "{app}\README.md"

[Run]
Filename: "{app}\VoiceBridge.exe"; Description: "启动声桥 VoiceBridge"; Flags: nowait postinstall skipifsilent

; User settings/history are preserved on uninstall.
