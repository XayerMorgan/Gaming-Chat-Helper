param(
    [switch]$Desktop
)

$ErrorActionPreference = "Stop"
$projectDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$batchPath = Join-Path $projectDirectory "Start Hyperline.bat"
$iconPath = Join-Path $projectDirectory "assets\app.ico"

if (-not (Test-Path -LiteralPath $batchPath)) {
    throw "Launcher not found: $batchPath"
}
if (-not (Test-Path -LiteralPath $iconPath)) {
    throw "Icon not found: $iconPath"
}

$shortcutDirectory = if ($Desktop) {
    [Environment]::GetFolderPath("Desktop")
} else {
    $projectDirectory
}
$shortcutPath = Join-Path $shortcutDirectory "Start Hyperline.lnk"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $batchPath
$shortcut.WorkingDirectory = $projectDirectory
$shortcut.IconLocation = "$iconPath,0"
$shortcut.Description = "Launch Hyperline AI"
$shortcut.WindowStyle = 7
$shortcut.Save()

Write-Host "Created: $shortcutPath"
