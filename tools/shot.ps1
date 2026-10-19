param([string]$Exe, [string]$Out, [int]$Wait = 5, [string[]]$Do = @(), [switch]$Keep)
# Launch the game (or reuse the running one), run actions, capture the client area to $Out.
# Actions: click:X,Y (stage coords, stage = 350x250) | key:NAME (left right up down space enter esc) | sleep:MS
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System; using System.Runtime.InteropServices; using System.Threading;
public class W {
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr h, ref POINT p);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint f, int x, int y, uint d, UIntPtr e);
  [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, UIntPtr extra);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X, Y; }
  public static void Key(byte scan, bool ext, int hold) {
    uint f = 0x0008 | (ext ? 0x0001u : 0u);
    keybd_event(0, scan, f, UIntPtr.Zero); Thread.Sleep(hold);
    keybd_event(0, scan, f | 0x0002, UIntPtr.Zero);
  }
  public static void Click(int x, int y) {
    SetCursorPos(x, y); Thread.Sleep(80);
    mouse_event(2, 0, 0, 0, UIntPtr.Zero); Thread.Sleep(80); mouse_event(4, 0, 0, 0, UIntPtr.Zero);
  }
}
"@
[W]::SetProcessDPIAware() | Out-Null
$map = @{ up = @(0x48, 1); down = @(0x50, 1); left = @(0x4B, 1); right = @(0x4D, 1); enter = @(0x1C, 0); esc = @(0x01, 0); space = @(0x39, 0) }
$name = [IO.Path]::GetFileNameWithoutExtension($Exe)
$p = Get-Process | Where-Object { $_.ProcessName -eq $name } | Select-Object -First 1
if (-not $p) {
  $p = Start-Process -FilePath $Exe -PassThru
  Start-Sleep $Wait
  $p.Refresh()
}
$h = $p.MainWindowHandle
[W]::SetForegroundWindow($h) | Out-Null
Start-Sleep -Milliseconds 300
function Geo {
  $r = New-Object W+RECT; [W]::GetClientRect($h, [ref]$r) | Out-Null
  $pt = New-Object W+POINT; [W]::ClientToScreen($h, [ref]$pt) | Out-Null
  # the projector letterboxes the 350x250 stage into the client area (no menu bar in fullscreen)
  $s = [Math]::Min($r.R / 350.0, $r.B / 250.0)
  @{ X = $pt.X; Y = $pt.Y; W = $r.R; H = $r.B; S = $s; OX = ($r.R - 350 * $s) / 2; OY = ($r.B - 250 * $s) / 2 }
}
foreach ($a in $Do) {
  $g = Geo
  if ($a -match '^click:(\d+),(\d+)$') {
    [W]::Click([int]($g.X + $g.OX + [int]$matches[1] * $g.S), [int]($g.Y + $g.OY + [int]$matches[2] * $g.S))
  } elseif ($a -match '^key:(\w+)(?::(\d+))?$') {
    $s = $map[$matches[1]]; $hold = if ($matches[2]) { [int]$matches[2] } else { 90 }
    [W]::Key([byte]$s[0], [bool]$s[1], $hold)
  } elseif ($a -match '^sleep:(\d+)$') { Start-Sleep -Milliseconds $matches[1] }
  Start-Sleep -Milliseconds 300
}
Start-Sleep -Milliseconds 500
$g = Geo
$bmp = New-Object Drawing.Bitmap $g.W, $g.H
$gr = [Drawing.Graphics]::FromImage($bmp); $gr.CopyFromScreen($g.X, $g.Y, 0, 0, $bmp.Size)
$bmp.Save($Out); "saved $Out ($($g.W)x$($g.H))"
if (-not $Keep) { Stop-Process -Id $p.Id -Force }
