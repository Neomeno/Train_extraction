param([switch]$CheckOnly)

$ErrorActionPreference = 'Stop'

# Run this file as a script. Pasting its lines into a console leaves
# $PSScriptRoot empty and would install into the wrong directory.
$projectDir = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($projectDir)) {
    throw 'この内容を1行ずつ貼り付けず、展開したフォルダの install.bat を実行してください。'
}
Set-Location -LiteralPath $projectDir

$candidates = New-Object 'System.Collections.Generic.List[string]'
$pyLauncher = Get-Command py -ErrorAction SilentlyContinue
if ($pyLauncher) {
    try {
        $resolved = & $pyLauncher.Source -3 -c 'import sys; print(sys.executable)' 2>$null
        if ($LASTEXITCODE -eq 0 -and $resolved) {
            $candidates.Add(([string]$resolved).Trim())
        }
    } catch { }
}
foreach ($name in @('python', 'python3')) {
    $command = Get-Command $name -ErrorAction SilentlyContinue
    if ($command -and $command.Source) {
        $candidates.Add($command.Source)
    }
}

# Codex Desktop bundles Python on some machines. This fallback avoids
# changing a system-wide Python installation.
if ($env:USERPROFILE) {
    $codexPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
    if (Test-Path -LiteralPath $codexPython) {
        $candidates.Add($codexPython)
    }
}

$python = $null
foreach ($candidate in ($candidates | Select-Object -Unique)) {
    try {
        $supported = & $candidate -c 'import sys; print(int(sys.version_info >= (3, 10) and sys.maxsize > 2**32))' 2>$null
        if ($LASTEXITCODE -eq 0 -and ([string]$supported).Trim() -eq '1') {
            $python = $candidate
            break
        }
    } catch { }
}
if (-not $python) {
    throw '64-bit Python 3.10 以降が見つかりません。https://www.python.org/downloads/windows/ からインストールし、再度 install.bat を実行してください。'
}
Write-Host "使用する Python: $python"
if ($CheckOnly) { return }

$venvPath = Join-Path $projectDir '.venv'
$venvPython = Join-Path $venvPath 'Scripts\python.exe'
& $python -m venv $venvPath
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $venvPython)) {
    throw 'Python 仮想環境の作成に失敗しました。'
}
& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip の更新に失敗しました。' }
& $venvPython -m pip install -r (Join-Path $projectDir 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw '依存パッケージのインストールに失敗しました。' }

if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue) -or
    -not (Get-Command ffprobe -ErrorAction SilentlyContinue)) {
    Write-Warning 'FFmpeg と ffprobe が PATH に見つかりません。https://ffmpeg.org/download.html から導入後、run.bat を実行してください。'
} else {
    Write-Host 'FFmpeg と ffprobe を確認しました。'
}
Write-Host 'セットアップ完了。run.bat を開いてください。'

