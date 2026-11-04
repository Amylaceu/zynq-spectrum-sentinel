"""Generate isolated X5 memories and exact references, using the AMD FFT model."""
import json
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sim.golden.pfb import design_prototype, pfb_os2_fixed
from sim.golden.nco_capture_fixed import sine_table, scap_words, nco_mix_fixed


def hexfile(path, data, width):
    mask = (1 << width) - 1
    path.write_text("".join(f"{int(v) & mask:0{(width+3)//4}x}\n" for v in data), encoding="ascii")


def pack(x):
    return x[:, 0].astype(np.uint16).astype(np.uint32) | (x[:, 1].astype(np.uint16).astype(np.uint32) << 16)


def main():
    work = ROOT / "build/work/x5_vectors"
    work.mkdir(parents=True, exist_ok=True)
    taps = design_prototype()
    hexfile(ROOT / "src/rtl/pfb/x5_pfb_coeff.hex", taps, 18)
    hexfile(ROOT / "src/rtl/nco_capture/x5_nco_sine.hex", sine_table(), 18)
    rng = np.random.default_rng(0x5835)
    # Non-multiple-of-D length, startup impulse, fullscale corners, all channels,
    # negative frequencies and general random IQ. A 4096-point full-chain capture.
    x = rng.integers(-32768, 32768, (32769, 2), dtype=np.int16)
    x[:256] = 0
    x[0] = (32767, -32768)
    x[256:512] = (32767, 32767)
    for ch in range(16):
        n = np.arange(512)
        tone = 26000 * np.exp(2j*np.pi*(ch/16 + 0.0031)*n)
        x[512+ch*512:1024+ch*512] = np.rint(np.column_stack((tone.real, tone.imag))).astype(np.int16)
    x[8704:8832] = np.tile(np.array([[32767, -32768], [-32768, 32767]], dtype=np.int16), (64, 1))
    y = pfb_os2_fixed(x, taps)
    hexfile(work / "x5_input.hex", pack(x), 32)
    hexfile(work / "x5_pfb_expected.hex", pack(y.reshape(-1, 2)), 32)
    hexfile(work / "x5_chain_expected.hex", scap_words(y[:4096, 3], 0x12345678, 3, src=0x13579bdf), 32)
    # Independent NCO vectors. Four capture lengths/FCWs, including negative FCW
    # and exact-unity FCW=0. Fullscale quadrature inputs exercise saturation.
    niq = rng.integers(-32768, 32768, (4096, 2), dtype=np.int16)
    niq[:4] = [[32767,32767],[-32768,-32768],[32767,-32768],[-32768,32767]]
    hexfile(work / "x5_nco_input.hex", pack(niq), 32)
    cases = [(4096,0x12345678),(257,0xf1234567),(1,0),(127,0x20000000)]
    outputs = []
    for length, fcw in cases:
        outputs.extend(scap_words(niq[:length], fcw, 5, src=0xa55a0042))
    hexfile(work / "x5_nco_expected.hex", outputs, 32)
    assert np.array_equal(nco_mix_fixed(niq, 0), niq)
    (work / "manifest.json").write_text(json.dumps({"input_samples":len(x), "pfb_frames":len(y),
        "pfb_iq_words":int(y.shape[0]*16), "chain_iq":4096,
        "nco_cases":[[n,f] for n,f in cases], "nco_packet_words":len(outputs)}, indent=2)+"\n")
    print(f"X5_VECTORS_PASS: {len(x)} inputs, {len(y)} frames, {len(outputs)} standalone NCO words")


if __name__ == "__main__":
    main()
