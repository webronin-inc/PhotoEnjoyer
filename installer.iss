; installer.iss — конфиг Inno Setup
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef AppName
  #define AppName "PhotoEnjoyer"
#endif
#ifndef AppPublisher
  #define AppPublisher "PhotoEnjoyer"
#endif
#ifndef AppExeName
  #define AppExeName "PhotoEnjoyer"
#endif
#ifndef AppIcon
  #define AppIcon "icon.ico"
#endif
#ifndef AppUrl
  #define AppUrl ""
#endif

[Setup]
AppId={{1E2D4E1B-1DAA-484D-971F-54B5C4925CF5}-{#AppName}}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppUrl}
AppSupportURL={#AppUrl}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
AllowNoIcons=yes
OutputDir=installer
OutputBaseFilename={#AppName}-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#AppExeName}.exe
SetupIconFile={#AppIcon}


; Лицензия и README — подключаются, только если файлы есть
#ifdef HasLicense
LicenseFile=LICENSE.txt
#endif
#ifdef HasReadme
InfoBeforeFile=README.md
#endif

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon";     Description: "Создать ярлык на рабочем столе"; \
                         GroupDescription: "Дополнительные значки:"; Flags: checkedonce
Name: "quicklaunchicon"; Description: "Создать ярлык в панели быстрого запуска"; \
                         GroupDescription: "Дополнительные значки:"; Flags: unchecked
Name: "autostart";       Description: "Запускать {#AppName} при старте Windows"; \
                         GroupDescription: "Дополнительно:"; Flags: unchecked

[Files]
; Вся папка dist\PhotoEnjoyer\ целиком — onedir
Source: "dist\{#AppExeName}\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{group}\{#AppName}";              Filename: "{app}\{#AppExeName}.exe"
Name: "{group}\Проверить обновления";    Filename: "{app}\{#AppExeName}.exe"; Parameters: "--check-updates"
Name: "{group}\Удалить {#AppName}";      Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}";        Filename: "{app}\{#AppExeName}.exe"; Tasks: desktopicon
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\{#AppName}"; \
      Filename: "{app}\{#AppExeName}.exe"; Tasks: quicklaunchicon
Name: "{userstartup}\{#AppName}";        Filename: "{app}\{#AppExeName}.exe"; Tasks: autostart

[Run]
Filename: "{app}\{#AppExeName}.exe"; Description: "Запустить {#AppName}"; \
          Flags: nowait postinstall

[UninstallDelete]
Type: filesandordirs; Name: "{app}\plugins"