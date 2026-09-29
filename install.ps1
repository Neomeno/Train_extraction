$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw 'Python 3.10 以降をインストールし、py コマンドを使えるようにしてください。'
}
py -3 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
Write-Host 'セットアップ完了。ffmpeg と ffprobe が PATH にあることを確認し、run.bat を開いてください。'

