# Deploy only N4 runtime inputs; never overwrite notebooks or measurements.
# Run from this checkout after audit_sentinel_v1.ps1 succeeds.
# No sudo, overlay loading, or RF access occurs in this script.
#requires -Version 7.0
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$facts = @{}
foreach ($line in Get-Content docs/board_info.md) {
    if ($line -match '^([a-z_]+)=(.*)$') { $facts[$matches[1]] = $matches[2].Trim() }
}
if ($facts.board_ip -notmatch '^\d{1,3}(\.\d{1,3}){3}$' -or
    $facts.board_user -notmatch '^[a-z_][a-z0-9_-]*$') { throw 'Invalid board identity' }
$target = "$($facts.board_user)@$($facts.board_ip)"
$remote = '/home/xilinx/sentinel'
$options = @('-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8')
$bundle = 'board/overlay/sentinel_v1'
$acceptance = Get-Content build/reports/sentinel_v1/acceptance.json -Raw | ConvertFrom-Json
if ($acceptance.status -ne 'PASS') { throw 'PC implementation acceptance is required' }
foreach ($extension in 'bit','hwh','xsa') {
    $name = "sentinel_v1.$extension"
    if ((Get-FileHash "$bundle/$name").Hash.ToLowerInvariant() -ne $acceptance.artifacts_sha256.$name) {
        throw "Accepted local artifact changed: $name"
    }
}
Copy-Item build/reports/sentinel_v1/acceptance.json "$bundle/acceptance.json"
& ssh @options $target "mkdir -p $remote/overlay $remote/scripts $remote/data $remote/sim"
if ($LASTEXITCODE) { throw 'Remote directories unavailable' }
foreach ($pair in @(
    @('src/ps', $remote),
    @("$bundle/sentinel_v1.bit", "$remote/overlay/sentinel_v1"),
    @("$bundle/sentinel_v1.hwh", "$remote/overlay/sentinel_v1"),
    @("$bundle/sentinel_v1.xsa", "$remote/overlay/sentinel_v1"),
    @("$bundle/sha256.txt", "$remote/overlay/sentinel_v1"),
    @("$bundle/acceptance.json", "$remote/overlay/sentinel_v1"),
    @("$bundle/provenance.json", "$remote/overlay/sentinel_v1"),
    @('board/scripts/bench_lcd.py', "$remote/scripts"),
    @('data/reference/spectrum', "$remote/data/reference"),
    @('sim/golden', "$remote/sim")
)) {
    Write-Output "Copy $($pair[0]) -> $($pair[1])"
    $isDirectory = (Get-Item -LiteralPath $pair[0]).PSIsContainer
    $scpArgs = @($options)
    if ($isDirectory) { $scpArgs += '-r' }
    $scpArgs += @($pair[0], "${target}:$($pair[1])/")
    & scp @scpArgs
    if ($LASTEXITCODE) { throw "Copy failed: $($pair[0])" }
}
& ssh @options $target "cd $remote/overlay/sentinel_v1 && sed 's/\r$//' sha256.txt | sha256sum -c -"
if ($LASTEXITCODE) { throw 'Remote artifact hashes failed' }
& ssh @options $target 'sudo -n /usr/local/sbin/zss-n4-admin health'
if ($LASTEXITCODE) { throw 'N4 administrator entry point is not ready' }
Write-Output 'N4_DEPLOY_PASS (no overlay loading or RF operation)'
