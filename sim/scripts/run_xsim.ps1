param(
    [Parameter(Mandatory)][string]$Top,
    [Parameter(Mandatory)][string[]]$Srcs,
    [string[]]$Libraries=@(),
    [string[]]$VhdlFiles=@(),
    [string[]]$MemoryFiles=@(),
    [switch]$IncludeGlbl,
    [ValidatePattern('^[a-zA-Z0-9_]+$')][string]$RunId='',
    [ValidatePattern('^[a-zA-Z0-9_]+$')][string[]]$Defines=@()
)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '../../tools/env.ps1')
$suffix=if($RunId){"_$RunId"}else{''}
$work=Join-Path $env:REPO "build/work/xsim_$Top$suffix"
New-Item -ItemType Directory -Force $work | Out-Null
$sources=@(foreach($source in $Srcs){(Resolve-Path (Join-Path $env:REPO $source)).Path})
if($IncludeGlbl){$sources+="$env:XILINX_ROOT/Vivado/data/verilog/src/glbl.v"}
$vhdl=@(foreach($source in $VhdlFiles){(Resolve-Path (Join-Path $env:REPO $source)).Path})
foreach($memory in $MemoryFiles){Copy-Item -LiteralPath (Join-Path $env:REPO $memory) -Destination $work -Force}
$result=if($RunId){Join-Path $env:REPO "sim/results/$RunId/$Top.log"}else{Join-Path $env:REPO "sim/results/$Top.log"}
New-Item -ItemType Directory -Force (Split-Path $result -Parent) | Out-Null
Push-Location $work
try {
    Copy-Item -LiteralPath "$env:XILINX_ROOT/Vivado/data/xsim/xsim.ini" -Destination xsim.ini -Force
    if($vhdl.Count){
        & "$env:XILINX_ROOT/Vivado/bin/xvhdl.bat" --2008 @vhdl *> xvhdl_console.log
        if($LASTEXITCODE){throw 'xvhdl failed; inspect work log'}
    }
    $defineArgs=@(foreach($define in $Defines){'-d';$define})
    & "$env:XILINX_ROOT/Vivado/bin/xvlog.bat" --sv -i "$env:REPO/src/rtl/common" @defineArgs @sources *> xvlog_console.log
    if($LASTEXITCODE){throw 'xvlog failed; inspect work log'}
    $libraryArgs=@('-L','xpm','-L','unisims_ver','-L','secureip')
    foreach($library in $Libraries){$libraryArgs+=@('-L',$library)}
    $tops=@($Top)
    if($IncludeGlbl){$tops+='glbl'}
    & "$env:XILINX_ROOT/Vivado/bin/xelab.bat" @tops -debug typical --mt 2 --timescale 1ns/1ps @libraryArgs -s "${Top}_snap" *> xelab_console.log
    if($LASTEXITCODE){throw 'xelab failed; inspect work log'}
    & "$env:XILINX_ROOT/Vivado/bin/xsim.bat" "${Top}_snap" -runall *> xsim_console.log
    if($LASTEXITCODE){throw 'xsim failed; inspect work log'}
    Copy-Item -LiteralPath xsim_console.log -Destination $result -Force
    Get-ChildItem -Filter '*_out.hex' -File | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination (Split-Path $result -Parent) -Force
    }
    if(-not(Select-String -LiteralPath xsim_console.log -Pattern '^TB_RESULT: PASS' -Quiet)){
        throw 'Missing testbench PASS marker'
    }
    Write-Output "PASS $Top"
} finally {Pop-Location}
