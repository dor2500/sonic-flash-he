param([switch]$NoExe, [int]$Hd = 6, [int]$CharHd = 4, [switch]$NoChars)
# Builds the Hebrew game: orig\Ultimate Flash Sonic.swf -> output\
#   1. JPEXS dumps (texts, fonts, scripts) into work\ (once)
#   2. tools\translate.py -> work\he (texts, fonts list, patched scripts)
#   3. HeTool (fonts + texts, SWF v6) -> work\step1.swf ; ffdec -importScript -> output\*.swf
#   4. tools\make_chars.py + CharTool: extra playable characters (drawn by code, cloned into the swf)
#   5. HD (xBRZ), Flash Player projector + swf -> one exe
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$work = "$root\work"
$ffdec = "$work\bin\ffdec\ffdec.jar"
$cp = "$work\bin\ffdec\lib\*"
$swf = "$root\orig\Ultimate Flash Sonic.swf"
if (-not (Test-Path $ffdec)) {
  $r = Invoke-RestMethod https://api.github.com/repos/jindrapetrik/jpexs-decompiler/releases/latest
  $a = $r.assets | Where-Object name -match '^ffdec_[\d.]+\.zip$' | Select-Object -First 1
  New-Item -ItemType Directory -Force "$work\bin" | Out-Null
  Invoke-WebRequest $a.browser_download_url -OutFile "$work\bin\ffdec.zip"
  Expand-Archive "$work\bin\ffdec.zip" "$work\bin\ffdec" -Force
}
if (-not (Test-Path "$work\ex\scripts")) { java -jar $ffdec -export script,font "$work\ex" $swf }
New-Item -ItemType Directory -Force "$work\cls", "$root\output" | Out-Null
javac -encoding UTF-8 -cp $cp -d "$work\cls" "$root\tools\HeTool.java" "$root\tools\CharTool.java"
if (-not (Test-Path "$work\fmt")) { java -cp "$work\cls;$cp" HeTool dump $swf "$work\fmt" }
if (-not (Test-Path "$work\ex\images")) { java -jar $ffdec -export image "$work\ex" $swf }
if (-not (Test-Path "$work\swf.xml")) { java -jar $ffdec -swf2xml $swf "$work\swf.xml" }
# new characters first: translate.py reads their roster (menu, names, saves)
if (Test-Path "$work\chars") { Remove-Item "$work\chars" -Recurse -Force }
if (-not $NoChars) {
  python -I "$root\tools\make_chars.py" $root
  if ($LASTEXITCODE) { throw 'make_chars.py failed' }
}
python -I "$root\tools\translate.py" $root
if ($LASTEXITCODE) { throw 'translate.py failed' }
python -I "$root\tools\make_logo.py" $root
Set-Content "$work\he\images.txt" "105`t$work\he\logo.png" -Encoding utf8
java -cp "$work\cls;$cp" HeTool patch $swf "$work\step1.swf" "$work\he\fonts.txt" "$work\he\texts"
if ($LASTEXITCODE) { throw 'HeTool failed' }
$out = "$root\output\Ultimate Flash Sonic HE.swf"
java -jar $ffdec -importScript "$work\step1.swf" $out "$work\he\scripts"
if (-not (Test-Path $out)) { throw 'importScript failed' }
if (-not $NoChars) {
  java -cp "$work\cls;$cp" CharTool chars $out "$work\step_c.swf" "$work\chars\spec.txt" "$work\chars\newimages.txt"
  if ($LASTEXITCODE) { throw 'CharTool failed' }
  Move-Item "$work\step_c.swf" $out -Force
}
# HD: every bitmap xBRZ x$Hd (vectors and text are already resolution independent)
if ($Hd -gt 1) {
  if (-not (Test-Path "$work\bin\xbrz_cli.exe")) { throw 'work\bin\xbrz_cli.exe missing (build xBRZ, see README)' }
  java -cp "$work\cls;$cp" HeTool fills $out "$work\fills.txt"
  python -I "$root\tools\hd_images.py" "$work\ex\images" "$work\fills.txt" "$work\hd$Hd" $Hd "$work\bin\xbrz_cli.exe"
  if ($LASTEXITCODE) { throw 'hd_images failed' }
  $dirs, $ks = "$work\hd$Hd", "$Hd"
  if (-not $NoChars) {
    # new character bitmaps (new ids every build): fresh 1x copies -> xBRZ x$CharHd
    $byid, $hdc = "$work\chars\byid", "$work\chars\hd$CharHd"
    New-Item -ItemType Directory -Force $byid | Out-Null
    foreach ($l in Get-Content "$work\chars\newimages.txt" -Encoding utf8) { $p = $l -split "`t"; if ($p.Count -eq 2) { Copy-Item $p[1] "$byid\$($p[0]).png" } }
    python -I "$root\tools\hd_images.py" $byid "$work\fills.txt" $hdc $CharHd "$work\bin\xbrz_cli.exe"
    if ($LASTEXITCODE) { throw 'hd_images (chars) failed' }
    $dirs, $ks = "$hdc;$dirs", "$CharHd;$Hd"
  }
  java --add-exports java.desktop/com.sun.imageio.plugins.jpeg=ALL-UNNAMED -cp "$work\cls;$cp" HeTool hd $out "$work\step2.swf" $dirs $ks
  if ($LASTEXITCODE) { throw 'HeTool hd failed' }
  Move-Item "$work\step2.swf" $out -Force
}
# zlib-compressed SWF (CWS): the projector refuses a large appended FWS, and it is 3x smaller for the web
python -I -c "import sys,zlib,struct; d=open(sys.argv[1],'rb').read(); d=d if d[:3]==b'CWS' else b'CWS'+d[3:8]+zlib.compress(d[8:],9); open(sys.argv[1],'wb').write(d)" $out
"swf: $out ($([math]::Round((Get-Item $out).Length / 1MB, 1)) MB)"
if ($NoExe) { return }
# Projector: Flash Player standalone + swf + footer (0xFA123456, swf length)
$exe = "$root\output\סוניק פלאש.exe"
$projExe = "$work\projector.exe"
Copy-Item "$root\orig\flashplayer_32_sa.exe" $projExe -Force
python -I "$root\tools\set_icon.py" $projExe "$root\orig\icon.ico"
if ($LASTEXITCODE) { throw 'set_icon failed' }
$proj = [IO.File]::ReadAllBytes($projExe)
$data = [IO.File]::ReadAllBytes($out)
$fs = [IO.File]::Create($exe)
$fs.Write($proj, 0, $proj.Length); $fs.Write($data, 0, $data.Length)
$fs.Write([byte[]](0x56, 0x34, 0x12, 0xFA), 0, 4)
$fs.Write([BitConverter]::GetBytes([uint32]$data.Length), 0, 4)
$fs.Close()
"built $exe"
