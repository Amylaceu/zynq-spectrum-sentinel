param(
    [Parameter(Mandatory)][ValidateSet('push','run','pull','check')][string]$Cmd,
    [string]$Arg='',
    [switch]$AsRoot
)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$facts=@{}
foreach($line in Get-Content (Join-Path $env:REPO 'docs/board_info.md')){
    if($line -match '^([a-z_]+)=(.*)$'){$facts[$matches[1]]=$matches[2].Trim()}
}
if($facts.board_ip -notmatch '^\d{1,3}(\.\d{1,3}){3}$' -or $facts.board_user -notmatch '^[a-z_][a-z0-9_-]*$'){
    throw 'Missing or invalid board IP/user in docs/board_info.md'
}
if($facts.board_python -notmatch '^/[a-zA-Z0-9_./-]+$'){throw 'Invalid board Python path'}
$target="$($facts.board_user)@$($facts.board_ip)"
$remote='/home/xilinx/sentinel'
$sshOptions=@('-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8')
function Invoke-Board([string]$Command){
    & ssh @sshOptions $target $Command
    if($LASTEXITCODE -ne 0){throw "Board command failed (exit $LASTEXITCODE)"}
}
switch($Cmd){
    'check' {Invoke-Board "echo ok; $($facts.board_python) -c 'import sys,pynq; print(sys.version.split()[0]); print(pynq.__version__)'"}
    'push' {
        Invoke-Board "mkdir -p $remote/data $remote/sim"
        $copies=@(
            @('src/ps',$remote),@('board/overlay',$remote),@('board/notebooks',$remote),
            @('board/scripts',$remote),@('data/reference',"$remote/data"),@('sim/golden',"$remote/sim")
        )
        foreach($pair in $copies){
            $source=Join-Path $env:REPO $pair[0]
            if(-not(Test-Path -LiteralPath $source)){throw "Missing source: $source"}
            Write-Host "Copy $($pair[0]) -> $($pair[1])"
            & scp @sshOptions -p -r $source "${target}:$($pair[1])/"
            if($LASTEXITCODE -ne 0){throw "Copy failed: $($pair[0])"}
        }
        # Accept Windows-generated CRLF manifests without treating CR as part
        # of the filename; file bytes themselves remain unchanged.
        Invoke-Board "cd $remote/overlay/base_z20 && sed 's/\r$//' sha256.txt | sha256sum -c -"
    }
    'run' {
        if([string]::IsNullOrWhiteSpace($Arg)){throw 'run requires a command'}
        if($Arg -match '^python3(?=\s|$)'){$Arg=$facts.board_python+$Arg.Substring(7)}
        $privilege=if($AsRoot){'sudo -n -E '}else{''}
        $sq=[string][char]39; $dq=[string][char]34
        $quoted=$sq+$Arg.Replace($sq,($sq+$dq+$sq+$dq+$sq))+$sq
        Invoke-Board "cd $remote && ${privilege}env PYTHONPATH=${remote}/ps:$remote sh -c $quoted"
    }
    'pull' {
        if($Arg -notmatch '^[a-zA-Z0-9_/-]+$' -or $Arg.StartsWith('/') -or ($Arg.Split('/') -contains '..')){
            throw 'pull requires a repository-relative board path'
        }
        $sub=$Arg -replace '^board/',''
        if($sub -notmatch '^(measurements|notebooks|scripts)(/|$)'){throw 'pull supports board measurements/notebooks/scripts only'}
        $destination=Join-Path $env:REPO "board/$sub"
        $parent=Split-Path $destination -Parent
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
        & scp @sshOptions -p -r "${target}:${remote}/$sub" $parent
        if($LASTEXITCODE -ne 0){throw 'Pull failed'}
    }
}
