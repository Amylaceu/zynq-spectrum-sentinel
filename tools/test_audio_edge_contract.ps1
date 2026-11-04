#requires -Version 7.0
$ErrorActionPreference='Stop'
& "$PSScriptRoot/../sim/scripts/run_xsim.ps1" -Top tb_audio_edge_contract `
  -RunId y3_audio_edges_r1 -Srcs @('src/rtl/audio_y3/i2s_tx_y3.v','sim/tb/tb_audio_edge_contract.sv')
exit $LASTEXITCODE
