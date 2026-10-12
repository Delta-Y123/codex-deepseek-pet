# Codex + DeepSeek Harness Desktop Pet -- installer
# Run:  powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1
$ErrorActionPreference = 'Stop'

$src = Join-Path $PSScriptRoot 'dist\CodexDeepSeekPet.exe'
if (-not (Test-Path $src)) { throw "Missing $src - run the build script first." }

$dir = Join-Path $env:LOCALAPPDATA 'Programs\CodexDeepSeekPet'
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$exe = Join-Path $dir 'CodexDeepSeekPet.exe'
Copy-Item $src $exe -Force

$cfgDst = Join-Path $dir 'config.json'
if (-not (Test-Path $cfgDst)) {
    Copy-Item (Join-Path $PSScriptRoot 'config.json') $cfgDst -Force
}

$ws = New-Object -ComObject WScript.Shell
$startMenu = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'
$startup   = Join-Path $startMenu 'Startup'
$desktop   = [Environment]::GetFolderPath('Desktop')
$name = 'Codex DeepSeek Pet'

function New-Lnk($path) {
    $sc = $ws.CreateShortcut($path)
    $sc.TargetPath       = $exe
    $sc.WorkingDirectory = $dir
    $sc.IconLocation     = "$exe,0"
    $sc.Description      = 'Codex and DeepSeek Harness status desktop pet'
    $sc.Save()
}

New-Lnk (Join-Path $startMenu "$name.lnk")
New-Lnk (Join-Path $desktop   "$name.lnk")
New-Lnk (Join-Path $startup   'CodexDeepSeekPet.lnk')

Write-Host "Installed to : $dir"
Write-Host "Shortcuts    : Start Menu / Desktop / Startup"
Start-Process $exe
Write-Host "Started. To disable autostart delete: $startup\CodexDeepSeekPet.lnk"
