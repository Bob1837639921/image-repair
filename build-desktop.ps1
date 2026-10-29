param(
    [string]$Python = 'python',
    [string]$Output = 'D:\画心桌面版',
    [string]$BuildPath = 'D:\画心构建缓存'
)
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $StaticAssets = Join-Path $PSScriptRoot 'static'
    $BrandAssets = Join-Path $PSScriptRoot 'assets'
    $Stage = Join-Path $BuildPath 'package'
    $VersionFile = Join-Path $PSScriptRoot 'desktop-version.txt'
    # Some Python distributions load an additional public CA policy file from ssl.py.
    $SslPolicy = & $Python -c "import ssl,pathlib; p=pathlib.Path(ssl.__file__).with_name('codex-rejected-cas.pem'); print(str(p) if p.exists() else '')"
    $ExtraAssets = @()
    if ($SslPolicy) { $ExtraAssets += @('--add-data', "$SslPolicy;.") }
    # Build in staging: PyInstaller clears its output folder, never point it at a live library.
    & $Python -m PyInstaller --noconfirm --windowed --onedir --name '画心' --icon (Join-Path $BrandAssets 'app.ico') --version-file $VersionFile --distpath $Stage --workpath $BuildPath --specpath $BuildPath --add-data "$StaticAssets;static" --add-data "$BrandAssets;assets" @ExtraAssets --collect-all webview --collect-all clr_loader --hidden-import pystray._win32 --hidden-import PIL._tkinter_finder (Join-Path $PSScriptRoot 'desktop.py')
    if ($LASTEXITCODE -ne 0) { throw '打包失败' }
    $Destination = Join-Path $Output '画心'
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    Copy-Item -Path (Join-Path $Stage '画心\*') -Destination $Destination -Recurse -Force
    Copy-Item -LiteralPath '桌面版使用说明.txt' -Destination (Join-Path $Destination '使用说明.txt')
    & $Python (Join-Path $PSScriptRoot 'package_desktop.py') $Destination (Join-Path $Output '画心桌面版_0.2.0.zip')
    if ($LASTEXITCODE -ne 0) { throw '压缩包校验失败' }
    Write-Output (Join-Path $Output '画心\画心.exe')
} finally { Pop-Location }
