param([string]$Path)
# Windows 内置 OCR（Windows.Media.Ocr），输出 JSON：[{text,x,y,w,h}, ...]
Add-Type -AssemblyName System.Runtime.WindowsRuntime
[void][Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
[void][Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
[void][Windows.Storage.StorageStream, Windows.Storage, ContentType = WindowsRuntime]
[void][Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]
[void][Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics, ContentType = WindowsRuntime]

$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() |
  Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
                 $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]

function Await-Op($op, $type) {
  $m = $asTask.MakeGenericMethod($type)
  $t = $m.Invoke($null, @($op))
  $t.Wait()
  return $t.Result
}

$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage('zh-CN')
if ($null -eq $engine) {
  $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
}
if ($null -eq $engine) { Write-Error 'no ocr engine'; exit 1 }

$file   = Await-Op ([Windows.Storage.StorageFile]::GetFileFromPathAsync($Path)) ([Windows.Storage.StorageFile])
$stream = Await-Op ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await-Op ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bmp    = Await-Op ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$res    = Await-Op ($engine.RecognizeAsync($bmp)) ([Windows.Media.Ocr.OcrResult])

$out = @()
foreach ($line in $res.Lines) {
  foreach ($w in $line.Words) {
    $r = $w.BoundingRect
    $out += [pscustomobject]@{
      text = $w.Text
      x = [math]::Round([double]$r.X, 1)
      y = [math]::Round([double]$r.Y, 1)
      w = [math]::Round([double]$r.Width, 1)
      h = [math]::Round([double]$r.Height, 1)
    }
  }
}
if ($out.Count -eq 0) { Write-Output '[]' } else { $out | ConvertTo-Json -Compress }
