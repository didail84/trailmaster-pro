; Installateur Windows de TrailMaster Pro (Inno Setup 6).
; Fabriqué par packaging/construire.py après PyInstaller.
; Installation dans le dossier de l'utilisateur : pas besoin d'être administrateur.
; Les données (base, photos) restent dans %APPDATA%\TrailMaster Pro et ne sont jamais touchées.

#ifndef VersionApp
  #define VersionApp "0"
#endif

[Setup]
AppId={{6E0F3B5A-5C1B-4E7E-9C2A-7A1D2B9F4E21}
AppName=TrailMaster Pro
AppVersion={#VersionApp}
AppVerName=TrailMaster Pro {#VersionApp}
AppPublisher=TrailMaster Pro (open source)
AppPublisherURL=https://github.com/didail84/trailmaster-pro
AppUpdatesURL=https://github.com/didail84/trailmaster-pro/releases
DefaultDirName={localappdata}\Programs\TrailMaster Pro
DisableDirPage=yes
DefaultGroupName=TrailMaster Pro
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=TrailMasterPro-{#VersionApp}-windows-x64
SetupIconFile=..\build\icone.ico
UninstallDisplayIcon={app}\TrailMaster Pro.exe
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "bureau"; Description: "Créer un raccourci sur le Bureau"; GroupDescription: "Raccourcis :"

[InstallDelete]
; Retire les fichiers de l'ancienne version avant de poser la nouvelle (jamais les données)
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\TrailMaster Pro\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\TrailMaster Pro"; Filename: "{app}\TrailMaster Pro.exe"
Name: "{autodesktop}\TrailMaster Pro"; Filename: "{app}\TrailMaster Pro.exe"; Tasks: bureau

[Run]
Filename: "{app}\TrailMaster Pro.exe"; Description: "Lancer TrailMaster Pro"; Flags: nowait postinstall skipifsilent
