# Dot-source from any directory: . <repo>/tools/env.ps1
$zssSavedErrorAction = $ErrorActionPreference
$ErrorActionPreference = 'Stop'
try {
    $env:REPO = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
    Set-Location -LiteralPath $env:REPO

    # Search fixed disks only. Removable media may be in a whole-card backup
    # or exclusively locked by the imaging tool; never probe it for installs.
    $zssSearchRoots = @(
        foreach ($drive in Get-PSDrive -PSProvider FileSystem) {
            try {
                $zssDriveInfo = [System.IO.DriveInfo]::new($drive.Root)
                if ($zssDriveInfo.DriveType -ne [System.IO.DriveType]::Fixed) { continue }
            } catch { continue }
            foreach ($folder in 'AMDDesignTools', 'Xilinx', 'FPGA', 'Vivado') {
                $candidate = Join-Path $drive.Root $folder
                if (Test-Path -LiteralPath $candidate -PathType Container -ErrorAction SilentlyContinue) { $candidate }
            }
        }
    )
    $zssInstallRoots = @(
        foreach ($base in $zssSearchRoots) {
            $base
            foreach ($child in Get-ChildItem -LiteralPath $base -Directory -ErrorAction SilentlyContinue) {
                if ($child.Name -match '^\d{4}\.\d+$|AMD|Xilinx|Vivado') {
                    $child.FullName
                    Get-ChildItem -LiteralPath $child.FullName -Directory -ErrorAction SilentlyContinue |
                        Where-Object Name -Match '^\d{4}\.\d+$' |
                        Select-Object -ExpandProperty FullName
                }
            }
        }
    ) | Sort-Object -Unique

    $zssVivadoCommand = Get-Command vivado.bat -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($zssVivadoCommand) {
        $zssInstallRoots += Split-Path (Split-Path (Split-Path $zssVivadoCommand.Source))
    }
    if (-not $env:XILINX_ROOT -or -not (Test-Path -LiteralPath (Join-Path $env:XILINX_ROOT 'Vivado/bin/vivado.bat'))) {
        $zssVivadoRoots = @($zssInstallRoots | Where-Object {
            (Split-Path $_ -Leaf) -in '2025.2', '2026.1' -and
            (Test-Path -LiteralPath (Join-Path $_ 'Vivado/bin/vivado.bat'))
        })
        $env:XILINX_ROOT = $zssVivadoRoots | Sort-Object @{Expression={if ((Split-Path $_ -Leaf) -eq '2025.2') {0} else {1}}}, @{Expression={$_}} | Select-Object -First 1
    }
    if (-not $env:XILINX_ROOT) { throw 'Vivado not found. Set XILINX_ROOT to its version directory.' }
    $env:VIVADO_VER = Split-Path $env:XILINX_ROOT -Leaf
    if ($env:VIVADO_VER -notin '2025.2', '2026.1') { throw "Unsupported Vivado version: $env:VIVADO_VER" }

    foreach ($entry in @(
        @{Variable='VITIS_ROOT'; File='Vitis/bin/vitis-run.bat'},
        @{Variable='XSCT_ROOT'; File='Vitis/bin/xsct.bat'}
    )) {
        $value = [Environment]::GetEnvironmentVariable($entry.Variable, 'Process')
        if (-not $value -or -not (Test-Path -LiteralPath (Join-Path $value $entry.File))) {
            $value = @($env:XILINX_ROOT) + @($zssInstallRoots) | Where-Object {
                (Split-Path $_ -Leaf) -eq $env:VIVADO_VER -and
                (Test-Path -LiteralPath (Join-Path $_ $entry.File))
            } | Select-Object -First 1
        }
        if (-not $value) { throw "Missing $($entry.File). Set $($entry.Variable) to a matching installation version directory." }
        if ((Split-Path $value -Leaf) -ne $env:VIVADO_VER) { throw "$($entry.Variable) version differs from Vivado." }
        [Environment]::SetEnvironmentVariable($entry.Variable, $value, 'Process')
    }

    $zssVenvPython = Join-Path $env:REPO '.venv/Scripts/python.exe'
    if (Test-Path -LiteralPath $zssVenvPython) {
        $env:ZSS_PYTHON = $zssVenvPython
    } elseif (-not $env:ZSS_PYTHON -or -not (Test-Path -LiteralPath $env:ZSS_PYTHON)) {
        $zssPython = @()
        foreach ($pythonVersion in '3.12', '3.11', '3.10') {
            if (Get-Command py -ErrorAction SilentlyContinue) {
                $result = & py "-$pythonVersion" -c 'import json,sys; print(json.dumps(sys.executable, ensure_ascii=True))' 2>$null
                if ($LASTEXITCODE -eq 0 -and $result) { $zssPython += ($result | Select-Object -Last 1 | ConvertFrom-Json); break }
            }
        }
        if (-not $zssPython.Count) {
            $command = Get-Command python.exe -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($command) { $zssPython += $command.Source }
        }
        $env:ZSS_PYTHON = $zssPython | Select-Object -First 1
    }
    if (-not $env:ZSS_PYTHON) { throw 'Python 3.10-3.12 not found. Set ZSS_PYTHON to its executable.' }
    & $env:ZSS_PYTHON -c 'import sys; assert (3,10) <= sys.version_info[:2] <= (3,12), sys.version'
    if ($LASTEXITCODE -ne 0) { throw 'Project Python must be 3.10-3.12.' }

    $zssPrepend = @(
        Join-Path $env:XILINX_ROOT 'Vivado/bin'
        Join-Path $env:VITIS_ROOT 'Vitis/bin'
        Join-Path $env:XSCT_ROOT 'Vitis/bin'
        Split-Path $env:ZSS_PYTHON
    )
    $env:PATH = (@($zssPrepend) + @($env:PATH -split ';') | Where-Object { $_ } | Select-Object -Unique) -join ';'
    $env:ADI_IGNORE_VERSION_CHECK = '1'
    $env:BOARD_IP = ''
    $zssBoardInfo = Join-Path $env:REPO 'docs/board_info.md'
    if (Test-Path -LiteralPath $zssBoardInfo) {
        $match = Select-String -LiteralPath $zssBoardInfo -Pattern '^board_ip=(\S+)' | Select-Object -First 1
        if ($match) { $env:BOARD_IP = $match.Matches[0].Groups[1].Value }
    }
    $zssActivate = Join-Path $env:REPO '.venv/Scripts/Activate.ps1'
    if (Test-Path -LiteralPath $zssActivate) { . $zssActivate }
    Write-Host "REPO=$env:REPO  VIVADO=$env:VIVADO_VER  PYTHON=$env:ZSS_PYTHON  BOARD_IP=$env:BOARD_IP" -ForegroundColor Green
} finally {
    $ErrorActionPreference = $zssSavedErrorAction
}
