Add-Type -AssemblyName System.Windows.Forms

$state = Join-Path $env:LOCALAPPDATA "SC2WorkbenchPreview"
New-Item -ItemType Directory -Force -Path $state | Out-Null
$config = Join-Path $state "map.txt"

try {
    Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8765/" -TimeoutSec 1 | Out-Null
    Start-Process "http://127.0.0.1:8765/"
    return
} catch {}

$map = if (Test-Path -LiteralPath $config) { (Get-Content -LiteralPath $config -Raw -Encoding UTF8).Trim() } else { "" }
if (-not $map -or -not (Test-Path -LiteralPath $map) -or $map -notmatch '-UI-Test') {
    $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
    $dialog.Description = "Select the map copy ending in -UI-Test (contains ComponentList.SC2Components)"
    if ($dialog.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) { return }
    $map = $dialog.SelectedPath
    Set-Content -LiteralPath $config -Value $map -Encoding UTF8
}

$python = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe"),
    (Get-Command py -ErrorAction SilentlyContinue).Source,
    (Get-Command python -ErrorAction SilentlyContinue).Source
) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1

if (-not $python) { throw "Python 3.10+ was not found." }
& $python (Join-Path $PSScriptRoot "live_preview.py") --map-copy $map --replace-font-styles
