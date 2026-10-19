param([string]$Version = '1.1', [int]$Code = 2)
# Android app: android\ (WebView activity) + output\web (build_web.ps1) as assets -> output\sonic_flash_he.apk
# No Gradle: aapt2 (resources + manifest), javac + d8 (code), zipalign + apksigner.
# Signing key: %USERPROFILE%\.android\sonic-flash-he.jks (made once; keep it - updates need the same key).
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot
$sdk = if ($env:ANDROID_HOME) { $env:ANDROID_HOME } else { "$env:LOCALAPPDATA\Android\Sdk" }
$bt = Get-ChildItem "$sdk\build-tools" | Sort-Object { [version]$_.Name } | Select-Object -Last 1 -ExpandProperty FullName
$plat = Get-ChildItem "$sdk\platforms" | Where-Object Name -match '^android-\d+$' | Sort-Object { [int]($_.Name -replace '\D') } | Select-Object -Last 1 -ExpandProperty FullName
$jar = "$plat\android.jar"
$web = "$root\output\web"
if (-not (Test-Path "$web\game.swf")) { throw 'run tools\build_web.ps1 first' }
$b = "$root\work\apk"
if (Test-Path $b) { Remove-Item $b -Recurse -Force }
New-Item -ItemType Directory -Force "$b\res\mipmap-xxxhdpi", "$b\res\mipmap-xxhdpi", "$b\res\mipmap-xhdpi", "$b\res\mipmap-hdpi", "$b\res\mipmap-mdpi", "$b\assets", "$b\cls", "$b\dex" | Out-Null

# launcher icons from the game icon
python -I -c @"
import sys
from PIL import Image
im = Image.open(sys.argv[1]); im.size = max(im.ico.sizes()); im.load(); im = im.convert('RGBA')
for d, s in (('xxxhdpi', 192), ('xxhdpi', 144), ('xhdpi', 96), ('hdpi', 72), ('mdpi', 48)):
    im.resize((s, s), Image.LANCZOS).save(sys.argv[2] + '/mipmap-' + d + '/ic_launcher.png')
"@ "$root\orig\icon.ico" "$b\res"
if ($LASTEXITCODE) { throw 'icons failed' }
Copy-Item $web "$b\assets\www" -Recurse

& "$bt\aapt2.exe" compile --dir "$b\res" -o "$b\res.zip"
if ($LASTEXITCODE) { throw 'aapt2 compile failed' }
& "$bt\aapt2.exe" link -I $jar --manifest "$root\android\AndroidManifest.xml" -A "$b\assets" -o "$b\base.apk" `
  --min-sdk-version 24 --target-sdk-version 35 --version-code $Code --version-name $Version "$b\res.zip" `
  -0 swf -0 wasm -0 png
if ($LASTEXITCODE) { throw 'aapt2 link failed' }

$src = Get-ChildItem "$root\android\src" -Recurse -Filter *.java | ForEach-Object FullName
javac -encoding UTF-8 --release 11 -classpath $jar -d "$b\cls" $src 2>&1 | Where-Object { $_ -notmatch 'warning|^Note' }
if ($LASTEXITCODE) { throw 'javac failed' }
$classes = Get-ChildItem "$b\cls" -Recurse -Filter *.class | ForEach-Object FullName
& "$bt\d8.bat" --release --min-api 24 --lib $jar --output "$b\dex" $classes
if ($LASTEXITCODE) { throw 'd8 failed' }
# rewrite the zip with classes.dex added (appending in place leaves mismatched local headers)
python -I -c @"
import sys, zipfile
src, dex, dst = sys.argv[1:4]
with zipfile.ZipFile(src) as zi, zipfile.ZipFile(dst, 'w') as zo:
    for it in zi.infolist():
        zo.writestr(zipfile.ZipInfo(it.filename, it.date_time), zi.read(it), compress_type=it.compress_type)
    zo.write(dex, 'classes.dex', compress_type=zipfile.ZIP_DEFLATED)
"@ "$b\base.apk" "$b\dex\classes.dex" "$b\full.apk"
if ($LASTEXITCODE) { throw 'zip failed' }

& "$bt\zipalign.exe" -f -p 4 "$b\full.apk" "$b\aligned.apk"
if ($LASTEXITCODE) { throw 'zipalign failed' }
$ks = "$env:USERPROFILE\.android\sonic-flash-he.jks"
if (-not (Test-Path $ks)) {
  keytool -genkeypair -keystore $ks -alias sonic -keyalg RSA -keysize 2048 -validity 36500 `
    -storepass sonicflash -keypass sonicflash -dname "CN=Sonic Flash HE, O=dor2500" 2>&1 | Out-Null
}
$apk = "$root\output\sonic_flash_he.apk"
& "$bt\apksigner.bat" sign --ks $ks --ks-pass pass:sonicflash --key-pass pass:sonicflash --out $apk "$b\aligned.apk"
if ($LASTEXITCODE) { throw 'apksigner failed' }
& "$bt\apksigner.bat" verify $apk
if ($LASTEXITCODE) { throw 'verify failed' }
"apk: $apk ($([math]::Round((Get-Item $apk).Length / 1MB, 1)) MB)"
