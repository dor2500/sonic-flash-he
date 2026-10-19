param([string]$Out)
# Web build: web\ + Ruffle (self-hosted) + output\Ultimate Flash Sonic HE.swf -> output\web (+ zip for the release)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot
$work = "$root\work"
if (-not $Out) { $Out = "$root\output\web" }
$swf = "$root\output\Ultimate Flash Sonic HE.swf"
if (-not (Test-Path $swf)) { throw 'build.ps1 first (no output swf)' }
if (-not (Test-Path "$work\ruffle\ruffle.js")) {
  $r = Invoke-RestMethod https://api.github.com/repos/ruffle-rs/ruffle/releases/latest
  $a = $r.assets | Where-Object name -match 'web-selfhosted\.zip$' | Select-Object -First 1
  Invoke-WebRequest $a.browser_download_url -OutFile "$work\ruffle.zip"
  Expand-Archive "$work\ruffle.zip" "$work\ruffle" -Force
}
if (Test-Path $Out) { Remove-Item $Out -Recurse -Force }
Copy-Item "$root\web" $Out -Recurse
New-Item -ItemType Directory -Force "$Out\ruffle" | Out-Null
Get-ChildItem "$work\ruffle" -File | Where-Object Name -notmatch '\.map$|package\.json' | Copy-Item -Destination "$Out\ruffle"
Copy-Item $swf "$Out\game.swf"
python -I -c "import sys; from PIL import Image; im=Image.open(sys.argv[1]); im.size=max(im.ico.sizes()); im.load(); im.convert('RGBA').resize((256,256)).save(sys.argv[2])" "$root\orig\icon.ico" "$Out\icon.png"
if ($LASTEXITCODE) { throw 'icon failed' }
$zip = "$root\output\sonic_flash_he_web.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive "$Out\*" $zip
"web: $Out ; zip: $zip ($([math]::Round((Get-Item $zip).Length / 1MB, 1)) MB)"
