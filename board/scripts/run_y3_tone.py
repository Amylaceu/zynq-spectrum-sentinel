"""Bounded, receive-disabled 1 kHz test of the accepted Y3 speaker path.

The PS selects the PL tone ROM and the regular I2S serializer. This entry
never initializes AD9361, allocates a DMA buffer, or enables the RF source.
The listener's report is a separate human acceptance gate.
"""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import time


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def receipt(path, record):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(record, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    temporary.replace(path)
    path.with_name(path.name + '.sha256').write_text(
        sha(path) + '  ' + path.name + '\n', encoding='ascii')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bit', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--load', action='store_true', required=True)
    parser.add_argument('--volume', type=float, default=-21)
    parser.add_argument('--image', choices=('sentinel_y3', 'sentinel_v2_100m'),
                        default='sentinel_y3')
    args = parser.parse_args()
    if args.out.exists():
        parser.error('Preserve the previous tone-test evidence')
    if os.geteuid() != 0:
        parser.error('PYNQ overlay and codec require sudo')
    os.environ['XILINX_XRT'] = '/usr'
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ps'))
    from sentinel.audio_y3 import (AudioControl, CodecOutputs, PynqIicBus,
                                   shutdown_audio_outputs, bind_audio_iic)
    from sentinel.overlay import validate_artifacts
    from sentinel.v_y3 import checked_y3_bundle, ADDRESSES
    from pynq import MMIO, Overlay

    CodecOutputs.volume_code(args.volume)
    checked_y3_bundle(args.bit, image=args.image)
    validate_artifacts(args.bit)
    def interrupted(signum, _frame):
        # timeout sends TERM before KILL; allow the normal finally block to
        # mute the codec, release the output pins and save a failure receipt.
        raise InterruptedError('Tone interrupted by signal %d' % signum)
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    args.out.mkdir(parents=True, exist_ok=False)
    result_path = args.out / 'result.json'
    record = dict(status='started', image=args.image, source='pl_1khz_tone',
                  tone_hz=1000, duration_requested_s=3, analog_volume_db=args.volume,
                  tx_requested=False, rf_initialized=False, dma_allocated=False,
                  human_hearing='PENDING', output='ES8388 ROUT2 -> MD8002A -> J36',
                  bit_sha256=sha(args.bit), hwh_sha256=sha(args.bit.with_suffix('.hwh')),
                  boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                  started_utc=datetime.now(timezone.utc).isoformat(), samples=[])
    receipt(result_path, record)
    audio = codec = source = gpio = None
    lock = open('/run/lock/zss_ad9361.lock', 'a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        overlay = Overlay(str(args.bit), download=True)
        if not overlay.is_loaded():
            raise RuntimeError('Audited Y3 image did not load')
        for name, base in ADDRESSES.items():
            if int(overlay.ip_dict[name]['phys_addr']) != base:
                raise RuntimeError('Wrong Y3 peripheral address: ' + name)
        gpio = MMIO(0x41200000, 4096)
        source = MMIO(0x43c00000, 4096)
        if gpio.read(0) != 0 or source.read(0) & 1:
            raise RuntimeError('RF reset/source not idle after image load')
        audio = AudioControl(MMIO(ADDRESSES['y3_audio_ctrl'], 4096),
                             MMIO(ADDRESSES['y3_audio_state'], 4096),
                             MMIO(ADDRESSES['y3_audio_counts'], 4096))
        audio.disable(release_pins=True)
        codec = CodecOutputs(PynqIicBus(bind_audio_iic(overlay)))
        codec.initialize(volume_db=args.volume)
        audio.configure_tone(codec)
        audio.start()
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline and not audio.snapshot()['playing']:
            time.sleep(.01)
        before = audio.snapshot()
        if not before['playing'] or before['underflows']:
            raise RuntimeError('Tone serializer did not start cleanly: ' + str(before))
        codec.unmute()
        start = time.monotonic()
        record.update(status='playing', codec_registers={hex(reg): codec.read(reg)
                      for reg in (0x04, 0x08, 0x19, 0x2e, 0x2f, 0x30, 0x31)},
                      audio_before=before)
        receipt(result_path, record)
        while time.monotonic() - start < 3:
            time.sleep(min(.25, max(.005, 3 - (time.monotonic() - start))))
            sample = audio.snapshot()
            if sample['underflows'] or not sample['playing']:
                raise RuntimeError('Tone lost I2S playback: ' + str(sample))
            record['samples'].append(sample)
        after = audio.snapshot()
        record.update(audio_after=after, elapsed_s=time.monotonic() - start,
                      i2s_frames_delta=after['frames'] - before['frames'])
        if record['i2s_frames_delta'] < 140000 or after['underflows']:
            raise RuntimeError('Three-second I2S frame-count gate failed')
        record['status'] = 'completed_awaiting_human_hearing'
    except BaseException as error:
        record.update(status='failed', error=repr(error))
        raise
    finally:
        errors = shutdown_audio_outputs(codec, audio)
        if audio is not None:
            try:
                record['audio_control_after'] = audio.control.read(0)
            except Exception as error:
                errors.append('Audio pins: ' + repr(error))
        if source is not None and gpio is not None:
            try:
                record['source_control_after'] = source.read(0)
                record['rf_gpio_after'] = gpio.read(0)
                if record['source_control_after'] & 1 or record['rf_gpio_after']:
                    errors.append('RF unexpectedly active')
            except Exception as error:
                errors.append('RF idle readback: ' + repr(error))
        record['safe_stop_errors'] = errors
        if errors:
            record['status'] = 'failed_safe_stop'
        record['stopped_utc'] = datetime.now(timezone.utc).isoformat()
        receipt(result_path, record)
        lock.close()


if __name__ == '__main__':
    main()
