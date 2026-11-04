# Passive UART capture. Never sends text, BREAK, reset, or modem signals.
#requires -Version 7.0
param(
    [Parameter(Mandatory=$true)][ValidatePattern('^COM[0-9]+$')][string]$Port,
    [ValidateRange(10,1800)][int]$Seconds=180,
    [ValidatePattern('^X0_[A-Za-z0-9_-]+$')][string]$Tag='X0_recovery_uart_r1'
)
$ErrorActionPreference='Stop'
$repoRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$logRoot=Join-Path $repoRoot 'logs'
$rawPath=Join-Path $logRoot ($Tag+'.bin')
$textPath=Join-Path $logRoot ($Tag+'.log')
$readyPath=Join-Path $logRoot ($Tag+'_ready.json')
$resultPath=Join-Path $logRoot ($Tag+'_result.json')
foreach($path in @($rawPath,$textPath,$readyPath,$resultPath)){
    if(Test-Path -LiteralPath $path){throw "Preserve existing UART evidence: $path"}
}
$serial=[System.IO.Ports.SerialPort]::new($Port,115200,[System.IO.Ports.Parity]::None,8,[System.IO.Ports.StopBits]::One)
$serial.DtrEnable=$false
$serial.RtsEnable=$false
$serial.Handshake=[System.IO.Ports.Handshake]::None
$serial.ReadTimeout=250
$stream=$null
$count=0
$errorText=$null
$started=[DateTimeOffset]::UtcNow
try {
    $serial.Open()
    $stream=[IO.FileStream]::new($rawPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
    @{port=$Port;baud=115200;started_utc=$started.ToString('o');transmitted_bytes=0;dtr=$false;rts=$false} | ConvertTo-Json | Set-Content -Encoding utf8 $readyPath
    $buffer=[byte[]]::new(4096)
$deadline=[DateTime]::UtcNow.AddSeconds($Seconds)
    while([DateTime]::UtcNow -lt $deadline){
        $available=$serial.BytesToRead
        if($available -gt 0){
            $n=$serial.Read($buffer,0,[Math]::Min($buffer.Length,$available))
            $stream.Write($buffer,0,$n);$stream.Flush($true);$count+=$n
        } else {Start-Sleep -Milliseconds 100}
    }
} catch { $errorText=$_.Exception.Message; throw }
finally {
    if($stream){$stream.Flush($true);$stream.Dispose()}
    $serial.Dispose()
    if(Test-Path -LiteralPath $rawPath){
        $bytes=[IO.File]::ReadAllBytes($rawPath)
        [IO.File]::WriteAllText($textPath,[Text.Encoding]::UTF8.GetString($bytes),[Text.UTF8Encoding]::new($false))
        $result=@{port=$Port;baud=115200;started_utc=$started.ToString('o');ended_utc=[DateTimeOffset]::UtcNow.ToString('o');bytes=$count;transmitted_bytes=0;error=$errorText;raw_sha256=(Get-FileHash $rawPath).Hash.ToLowerInvariant();text_sha256=(Get-FileHash $textPath).Hash.ToLowerInvariant()}
        $result | ConvertTo-Json | Set-Content -Encoding utf8 $resultPath
        $result | ConvertTo-Json | Write-Output
    }
}
