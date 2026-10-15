$ErrorActionPreference = "Stop"

$desktopPath = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktopPath "Gravador de Tela.lnk"
$launcherPath = Join-Path $PSScriptRoot "Iniciar Gravador.vbs"
$pythonwPath = Join-Path $PSScriptRoot ".venv\Scripts\pythonw.exe"
$wscriptPath = Join-Path $env:WINDIR "System32\wscript.exe"

if (-not (Test-Path -LiteralPath $launcherPath -PathType Leaf)) {
    throw "O iniciador Iniciar Gravador.vbs nao foi encontrado."
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $wscriptPath
$shortcut.Arguments = "//NoLogo `"$launcherPath`""
$shortcut.WorkingDirectory = $PSScriptRoot
$shortcut.Description = "Abre o Gravador de Tela"
if (Test-Path -LiteralPath $pythonwPath -PathType Leaf) {
    $shortcut.IconLocation = "$pythonwPath,0"
}
$shortcut.Save()

Write-Output "Atalho criado em: $shortcutPath"
