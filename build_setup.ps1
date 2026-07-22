
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSCommandPath
Set-Location $root

function Test-PythonInvocation {
    param([string]$Exe, [string[]]$PrefixArgs)
    try {
        & $Exe @PrefixArgs -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" 2>$null
        return $LASTEXITCODE -eq 0
    }
    catch { return $false }
}

function Find-Python {
    $candidates = @()
    if (Get-Command py.exe -ErrorAction SilentlyContinue) {
        $candidates += [pscustomobject]@{ Exe = "py.exe"; PrefixArgs = @("-3.11") }
        $candidates += [pscustomobject]@{ Exe = "py.exe"; PrefixArgs = @("-3") }
    }
    if (Get-Command python.exe -ErrorAction SilentlyContinue) {
        $candidates += [pscustomobject]@{ Exe = "python.exe"; PrefixArgs = @() }
    }
    foreach ($path in @(
        "$env:LocalAppData\Programs\Python\Python311\python.exe",
        "$env:ProgramFiles\Python311\python.exe",
        "${env:ProgramFiles(x86)}\Python311\python.exe"
    )) {
        if ($path -and (Test-Path -LiteralPath $path)) {
            $candidates += [pscustomobject]@{ Exe = $path; PrefixArgs = @() }
        }
    }
    foreach ($candidate in $candidates) {
        if (Test-PythonInvocation -Exe $candidate.Exe -PrefixArgs $candidate.PrefixArgs) {
            return $candidate
        }
    }
    return $null
}

function Find-Iscc {
    $command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($command -and $command.Source -and (Test-Path -LiteralPath $command.Source)) {
        return $command.Source
    }

    $candidates = @(
        "$env:LocalAppData\Programs\Inno Setup 7\ISCC.exe",
        "$env:LocalAppData\Programs\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 7\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 7\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
    )

    foreach ($registryPath in @(
        "Registry::HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\App Paths\ISCC.exe",
        "Registry::HKEY_LOCAL_MACHINE\Software\Microsoft\Windows\CurrentVersion\App Paths\ISCC.exe",
        "Registry::HKEY_LOCAL_MACHINE\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\ISCC.exe"
    )) {
        try {
            $value = (Get-Item -LiteralPath $registryPath -ErrorAction Stop).GetValue("")
            if ($value) { $candidates += [string]$value }
        }
        catch {}
    }

    foreach ($basePath in @("$env:LocalAppData\Programs", "$env:ProgramFiles", "${env:ProgramFiles(x86)}")) {
        if (-not $basePath -or -not (Test-Path -LiteralPath $basePath)) { continue }
        Get-ChildItem -LiteralPath $basePath -Directory -Filter "Inno Setup *" -ErrorAction SilentlyContinue |
            ForEach-Object { $candidates += (Join-Path $_.FullName "ISCC.exe") }
    }

    foreach ($candidate in $candidates | Select-Object -Unique) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    return $null
}

function Wait-ForIscc {
    for ($attempt = 1; $attempt -le 20; $attempt++) {
        $found = Find-Iscc
        if ($found) { return $found }
        Start-Sleep -Seconds 1
    }
    return $null
}

function Ensure-Python {
    $pythonInfo = Find-Python
    if (-not $pythonInfo) {
        if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
            throw "Python 3.11 or newer was not found. Install 64-bit Python 3.11 and run BUILD_SETUP.bat again."
        }
        Write-Host "Installing Python 3.11..."
        & winget.exe install --id Python.Python.3.11 -e --accept-package-agreements --accept-source-agreements --silent
        if ($LASTEXITCODE -ne 0) { throw "Python 3.11 could not be installed." }
        $pythonInfo = Find-Python
    }
    if (-not $pythonInfo) { throw "Python 3.11 was installed but could not be located." }
    return $pythonInfo
}

function Ensure-Iscc {
    $iscc = Find-Iscc
    if (-not $iscc) {
        if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
            throw "Inno Setup 6 or 7 was not found. Install Inno Setup and run BUILD_SETUP.bat again."
        }
        Write-Host "Installing Inno Setup..."
        & winget.exe install --id JRSoftware.InnoSetup -e --accept-package-agreements --accept-source-agreements --silent
        if ($LASTEXITCODE -ne 0) { throw "Inno Setup could not be installed." }
        $iscc = Wait-ForIscc
    }
    if (-not $iscc) { throw "Inno Setup was installed but ISCC.exe could not be located." }
    return $iscc
}

if ($env:OS -ne "Windows_NT") { throw "The installer must be built on Windows." }

$pythonInfo = Ensure-Python
Write-Host "Creating the build environment..."
Remove-Item -LiteralPath ".build-venv" -Recurse -Force -ErrorAction SilentlyContinue
& $pythonInfo.Exe @($pythonInfo.PrefixArgs) -m venv ".build-venv"
if ($LASTEXITCODE -ne 0) { throw "The Python build environment could not be created." }

$python = Join-Path $root ".build-venv\Scripts\python.exe"
& $python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip could not be updated." }
& $python -m pip install -r requirements.txt "pyinstaller==6.14.2"
if ($LASTEXITCODE -ne 0) { throw "The build packages could not be installed." }

Write-Host "Checking the application source..."
& $python -m py_compile "$root\app.py"
if ($LASTEXITCODE -ne 0) { throw "app.py did not compile." }

Remove-Item -LiteralPath "build", "dist", "release" -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path "build", "release" -Force | Out-Null

$versionInfo = @'
VSVersionInfo(
  ffi=FixedFileInfo(filevers=(1,0,0,0), prodvers=(1,0,0,0), mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0,0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'domm-f'),
      StringStruct('FileDescription', 'Camera Gesture Hotkeys'),
      StringStruct('FileVersion', '1.0.0'),
      StringStruct('InternalName', 'Camera Gesture Hotkeys'),
      StringStruct('LegalCopyright', 'Copyright (c) 2026 domm-f'),
      StringStruct('OriginalFilename', 'Camera Gesture Hotkeys.exe'),
      StringStruct('ProductName', 'Camera Gesture Hotkeys'),
      StringStruct('ProductVersion', '1.0.0')
    ])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
'@
$versionInfoPath = Join-Path $root "build\version_info.txt"
$versionInfo | Set-Content -LiteralPath $versionInfoPath -Encoding UTF8

Write-Host "Building Camera Gesture Hotkeys..."
& $python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --onedir `
    --noupx `
    --name "Camera Gesture Hotkeys" `
    --version-file "$versionInfoPath" `
    --add-data "$root\pose_landmarker_lite.task;." `
    --collect-all "mediapipe" `
    --collect-submodules "pynput" `
    --distpath "$root\dist" `
    --workpath "$root\build\work" `
    --specpath "$root\build" `
    "$root\app.py"
if ($LASTEXITCODE -ne 0) { throw "The application build failed." }

$iscc = Ensure-Iscc
$installerScript = @'
#define AppName "Camera Gesture Hotkeys"
#define AppVersion "1.0.0"
#define AppPublisher "domm-f"
#define AppExeName "Camera Gesture Hotkeys.exe"

[Setup]
AppId={{6AB4029D-8327-4A8B-B5BA-69F4059A46C2}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL=https://github.com/domm-f/CameraGestureHotkeys
AppSupportURL=https://github.com/domm-f/CameraGestureHotkeys/issues
AppUpdatesURL=https://github.com/domm-f/CameraGestureHotkeys/releases
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
OutputDir=..\release
OutputBaseFilename=Camera_Gesture_Hotkeys_Setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
UninstallDisplayIcon={app}\{#AppExeName}
VersionInfoVersion={#AppVersion}
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppName} Setup
VersionInfoProductName={#AppName}
VersionInfoProductVersion={#AppVersion}

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\Camera Gesture Hotkeys\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C taskkill /F /IM ""{#AppExeName}"""; Flags: runhidden; RunOnceId: "StopCameraGestureHotkeys"

[UninstallDelete]
Type: filesandordirs; Name: "{userappdata}\CameraGestureHotkeys"
'@
$installerPath = Join-Path $root "build\CameraGestureHotkeys.iss"
$installerScript | Set-Content -LiteralPath $installerPath -Encoding UTF8

Write-Host "Building the setup file..."
& $iscc $installerPath
if ($LASTEXITCODE -ne 0) { throw "The setup build failed." }

$setup = Join-Path $root "release\Camera_Gesture_Hotkeys_Setup.exe"
if (-not (Test-Path -LiteralPath $setup)) { throw "The expected setup file was not created." }
$hash = (Get-FileHash -LiteralPath $setup -Algorithm SHA256).Hash.ToLowerInvariant()
"$hash  Camera_Gesture_Hotkeys_Setup.exe" | Set-Content -LiteralPath "$root\release\SHA256SUMS.txt" -Encoding ASCII

Write-Host ""
Write-Host "Finished:" -ForegroundColor Green
Write-Host $setup -ForegroundColor Green
