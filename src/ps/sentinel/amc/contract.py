"""Training/deployment contract, independent of torch and FPGA drivers."""

AMC_FS = 480_000
CAPTURE_LEN_AMC = 4096
FRONTEND_BLOCK = 8
CLASSES = ('BPSK', 'QPSK', '8PSK', '16QAM', '64QAM', '2FSK', 'GFSK', 'OOK', 'AM-DSB', 'FM')
COARSE_CLASSES = ('BPSK', 'PSK-high', 'QAM', '2FSK', 'GFSK', 'OOK', 'AM', 'FM')
COARSE_MAP = (0, 1, 1, 2, 2, 3, 4, 5, 6, 7)
FEATURE_COUNT = 24
SCHEMA = 'amc-v2-4096-480k-block8-f24-r1'
