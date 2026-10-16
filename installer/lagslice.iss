; -*- coding: utf-8 -*-
; LagSlice — Inno Setup installer script (dark neon theme, matching the app).
; Built by GitHub Actions: iscc installer/lagslice.iss /DAppVersion=<ver>
; SPDX-License-Identifier: AGPL-3.0-only
; Copyright (C) 2026 Taha Arefi

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{C0C51400-F498-4A16-A3DB-01C55961AC30}}
AppName=LagSlice
AppVersion={#AppVersion}
AppVerName=LagSlice v{#AppVersion}
AppPublisher=Taha Arefi
AppPublisherURL=https://github.com/thaarfknight-star/LagSlice
AppSupportURL=https://github.com/thaarfknight-star/LagSlice
AppUpdatesURL=https://github.com/thaarfknight-star/LagSlice/releases
DefaultDirName={autopf}\LagSlice
DefaultGroupName=LagSlice
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
SetupIconFile=..\assets\lagslice.ico
UninstallDisplayIcon={app}\LagSlice.exe
WizardStyle=modern
WizardImageFile=wizard-image.bmp
WizardSmallImageFile=wizard-small.bmp
Compression=lzma2/max
SolidCompression=yes
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64
OutputDir=..\dist
OutputBaseFilename=LagSlice-Setup-v{#AppVersion}
; تم تیره‌ی نئونی: رنگ accent مدرن ویزارد
WizardImageStretch=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "آیکون دسکتاپ (Desktop icon)"; GroupDescription: "میانبرها:"

[Files]
Source: "..\dist\LagSlice.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\THIRD_PARTY_NOTICES"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\docs\lagslice-help-fa.pdf"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\LagSlice"; Filename: "{app}\LagSlice.exe"; Comment: "LagSlice — بهینه‌ساز استریم"
Name: "{group}\راهنمای فارسی (Persian guide)"; Filename: "{app}\lagslice-help-fa.pdf"
Name: "{group}\حذف LagSlice (Uninstall)"; Filename: "{uninstallexe}"
Name: "{autodesktop}\LagSlice"; Filename: "{app}\LagSlice.exe"; Tasks: desktopicon; Comment: "LagSlice — بهینه‌ساز استریم"

[Run]
Filename: "{app}\LagSlice.exe"; Description: "اجرای LagSlice (Run LagSlice)"; Flags: nowait postinstall skipifsilent runascurrentuser

[Code]
{ قدمی کوچک برای حس نئونی: متن خوش‌آمد سفارشی }
procedure InitializeWizard();
begin
  WizardForm.WelcomeLabel1.Caption := 'به LagSlice خوش آمدید';
  WizardForm.WelcomeLabel1.Font.Size := 16;
  WizardForm.WelcomeLabel1.Font.Style := [fsBold];
  WizardForm.WelcomeLabel2.Caption :=
    'این ویزارد LagSlice v{#AppVersion} را روی سیستم شما نصب می‌کند.' + #13#10 +
    'LagSlice بهینه‌ساز استریم برای اینترنت ایران است.' + #13#10 + #13#10 +
    'This wizard will install LagSlice on your computer.';
  WizardForm.FinishedLabel.Caption :=
    'نصب LagSlice با موفقیت تمام شد.' + #13#10 +
    'برای بهترین نتیجه، برنامه را با Run as administrator اجرا کنید.' + #13#10 + #13#10 +
    'LagSlice has been installed successfully.';
end;
