#define AppName GetEnv("PIXO_APP_NAME")
#if AppName == ""
  #define AppName "PixoPDF"
#endif

#define AppVersion GetEnv("PIXO_APP_VERSION")
#if AppVersion == ""
  #define AppVersion "0.1.3"
#endif

#define SourceDir GetEnv("PIXO_SOURCE_DIR")
#if SourceDir == ""
  #define SourceDir "..\..\dist\PixoPDF"
#endif

#define OutputDir GetEnv("PIXO_OUTPUT_DIR")
#if OutputDir == ""
  #define OutputDir "..\..\release"
#endif

#define RootDir GetEnv("PIXO_ROOT_DIR")
#if RootDir == ""
  #define RootDir "..\.."
#endif

#define WizardImageFile GetEnv("PIXO_WIZARD_IMAGE")
#define WizardSmallImageFile GetEnv("PIXO_WIZARD_SMALL_IMAGE")

[Setup]
AppId={{B667819A-40DE-4DA6-B587-3CA588F3B8BE}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=PixoGlace
AppPublisherURL=https://github.com/PixoGlace/pixopdf
AppSupportURL=https://github.com/PixoGlace/pixopdf/issues
AppUpdatesURL=https://github.com/PixoGlace/pixopdf/releases
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
LicenseFile={#RootDir}\LICENSE
OutputDir={#OutputDir}
OutputBaseFilename=PixoPDF-windows-x86_64-setup
SetupIconFile={#RootDir}\assets\PixoPDF.ico
WizardImageFile={#WizardImageFile}
WizardSmallImageFile={#WizardSmallImageFile}
WizardImageStretch=no
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayIcon={app}\{#AppName}.exe

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppName}.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppName}.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppName}.exe"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
