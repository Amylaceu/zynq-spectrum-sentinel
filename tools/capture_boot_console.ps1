param([string]$Port='COM14',[int]$Seconds=600,[string]$LogPrefix='N1_boot_console')
$ErrorActionPreference='Stop'
if($LogPrefix -notmatch '^[A-Za-z0-9_-]+$'){throw 'LogPrefix must be a simple file stem'}
$logBase=Join-Path (Join-Path (Get-Location) 'logs') $LogPrefix
$serial=$null
$end=[DateTime]::UtcNow.AddSeconds($Seconds)
try {
 while([DateTime]::UtcNow -lt $end){
  try {
   if($null -eq $serial -or !$serial.IsOpen){
    if($serial){$serial.Dispose()}
    $serial=New-Object System.IO.Ports.SerialPort $Port,115200,([System.IO.Ports.Parity]::None),8,([System.IO.Ports.StopBits]::One)
    $serial.DtrEnable=$false;$serial.RtsEnable=$false;$serial.Open()
    "READY $Port 115200 8N1 DTR=0 RTS=0 $([DateTime]::UtcNow.ToString('o'))" | Set-Content -Encoding utf8 ($logBase+'_ready.txt')
    $serial.Write("`r`n")
   }
   $chunk=$serial.ReadExisting()
   if($chunk){[IO.File]::AppendAllText(($logBase+'.log'),$chunk,[Text.Encoding]::UTF8)}
  } catch {
   "$([DateTime]::UtcNow.ToString('o')) $($_.Exception.Message)" | Out-File -Append -Encoding utf8 ($logBase+'_reconnect.log')
   if($serial){$serial.Dispose();$serial=$null}
   Start-Sleep -Milliseconds 800
  }
  Start-Sleep -Milliseconds 200
 }
} catch {$_ | Out-File -Encoding utf8 ($logBase+'_error.log');exit 1}
finally {if($serial){$serial.Dispose()}}
