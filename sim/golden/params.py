"""Shared numeric contracts; generate RTL constants with gen_params_vh.py."""

FS_DEFAULT = 30.72e6
FS_DEFAULT_HZ = 30_720_000
NFFT = 2048
IQ_BITS = 16
WIN_BITS = 18
FFT_OUT_BITS = 24
PWR_BITS = 32
WELCH_ALPHA_SHIFT = 3
CFAR_N = 16
CFAR_G = 2
CFAR_MODES = {"CA": 0, "GO": 1, "SO": 2}
CFAR_ALPHA_FRAC = 8
CLUSTER_GAP = 2
MAX_TARGETS = 32
DC_MASK_BINS = 3
PFB_M = 16
PFB_D = 8
PFB_TAPS_PER_PHASE = 8
PFB_COEF_BITS = 18
NCO_PHASE_BITS = 32
CAPTURE_LEN = 1024
CAPTURE_LEN_AMC = 4096
AMC_FS = 480_000

# Actual confirmed ATK-MD0700 SSD1963 panel; not the draft 1024x600 RGB panel.
SCREEN_W, SCREEN_H = 800, 480
DISP_W, DISP_SPEC_H, DISP_WF_H = 720, 160, 200

MOD_CLASSES = ["BPSK", "QPSK", "8PSK", "16QAM", "64QAM", "2FSK", "GFSK", "OOK", "AM-DSB", "FM"]

# Right-shifting Galois x^32+x^22+x^2+x+1. Uniform words use disjoint PRBS bits.
LFSR_MASK = 0x80200003
LFSR_UNIFORM_BITS = 12
LFSR_DRAWS = 12
LFSR_STRIDE = 12
NOISE_AMP_BITS = 16
NOISE_AMP_FRAC = 15


def validate():
    assert NFFT > 0 and NFFT & (NFFT - 1) == 0
    assert CFAR_N > 0 and CFAR_N & (CFAR_N - 1) == 0
    assert PFB_M == 2 * PFB_D
    assert DISP_W <= SCREEN_W
    assert DISP_SPEC_H + DISP_WF_H <= SCREEN_H
    assert FS_DEFAULT == FS_DEFAULT_HZ


validate()
