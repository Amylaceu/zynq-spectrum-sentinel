$ErrorActionPreference='Stop'
$serial = New-Object System.IO.Ports.SerialPort 'COM14',115200,([System.IO.Ports.Parity]::None),8,([System.IO.Ports.StopBits]::One)
$serial.DtrEnable=$false;$serial.RtsEnable=$false;$serial.ReadTimeout=500
try {
 $serial.Open();$serial.Write("`r`n")
 $end=[DateTime]::UtcNow.AddSeconds(12)
 while([DateTime]::UtcNow -lt $end){
  $chunk=$serial.ReadExisting()
  if($chunk){$chunk | Out-File -Append -Encoding utf8 logs/N1_serial_probe.log;Write-Output $chunk}
  Start-Sleep -Milliseconds 300
 }
} finally {if($serial.IsOpen){$serial.Close()}}
