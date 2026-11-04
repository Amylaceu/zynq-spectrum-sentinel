param([string]$Tag='base_z20', [string]$Proj='fmcomms2_z20')
$ErrorActionPreference='Stop'
if ($Tag -notmatch '^[a-z][a-z0-9_]*$' -or $Proj -notmatch '^[a-z][a-z0-9_]*$') {throw 'Invalid artifact name'}
. (Join-Path $PSScriptRoot 'env.ps1')
$sub=if($Proj -eq 'fmcomms2_z20'){'z20'}else{$Proj}
$project=Join-Path $env:REPO "build/work/adi_hdl/projects/fmcomms2/$sub"
$implementation=Join-Path $project "$Proj.runs/impl_1"
$bit=Join-Path $implementation 'system_top.bit'
$xsa=Join-Path $project "$Proj.sdk/system_top.xsa"
$hwh=@(Get-ChildItem -LiteralPath (Join-Path $project "$Proj.gen") -Recurse -Filter system.hwh)
if(-not(Test-Path -LiteralPath $bit) -or -not(Test-Path -LiteralPath $xsa) -or $hwh.Count -ne 1){
    throw 'Missing or ambiguous bit/hwh/xsa; no complete artifact set can be collected'
}
$out=Join-Path $env:REPO "board/overlay/$Tag"
$reports=Join-Path $env:REPO "build/reports/$Tag"
New-Item -ItemType Directory -Path $out,$reports -Force | Out-Null
Copy-Item -LiteralPath $bit -Destination (Join-Path $out "$Tag.bit") -Force
Copy-Item -LiteralPath $hwh[0].FullName -Destination (Join-Path $out "$Tag.hwh") -Force
Copy-Item -LiteralPath $xsa -Destination (Join-Path $out "$Tag.xsa") -Force
$bundleTime=[DateTime]::UtcNow
$sources=@($bit,$hwh[0].FullName,$xsa)
$records=foreach($source in $sources){
    $file=Get-Item -LiteralPath $source
    [ordered]@{source=$source.Substring($env:REPO.Length+1).Replace('\','/');
        source_modified_utc=$file.LastWriteTimeUtc.ToString('o');
        sha256=(Get-FileHash -LiteralPath $source).Hash}
}
# Source generation times can legitimately differ by an entire implementation
# run. Preserve them in provenance, while stamping the verified exported SET.
foreach($extension in 'bit','hwh','xsa'){
    (Get-Item -LiteralPath (Join-Path $out "$Tag.$extension")).LastWriteTimeUtc=$bundleTime
}
[ordered]@{tag=$Tag;bundled_utc=$bundleTime.ToString('o');sources=@($records)} |
    ConvertTo-Json -Depth 4 | Set-Content (Join-Path $out 'provenance.json') -Encoding utf8
Get-ChildItem -LiteralPath $implementation -Filter '*.rpt' |
    Where-Object Name -Match 'timing_summary|utilization' | Copy-Item -Destination $reports -Force
Get-ChildItem -LiteralPath $project -Filter 'timing_*.log' | Copy-Item -Destination $reports -Force
Get-FileHash -LiteralPath (Join-Path $out "$Tag.bit"),(Join-Path $out "$Tag.hwh"),(Join-Path $out "$Tag.xsa") |
    ForEach-Object {"$($_.Hash)  $(Split-Path $_.Path -Leaf)"} |
    Set-Content -LiteralPath (Join-Path $out 'sha256.txt') -Encoding utf8
Write-Host "Collected complete bit/hwh/xsa set -> $out"
