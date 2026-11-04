"""Bounded current FM IQ recording; no PL rebuild, transmission or old audio."""
import argparse
import fcntl
import hashlib
import math
import os
from pathlib import Path
import signal
import sys
import time
import uuid


BIT_SHA = '7a5fd71cc54c64e98697aec98d7cf73fa9afac5fe20867690443896bbd72795c'
LIB_SHA = 'b329018314e6ecc9c0b11440b0d5449d9670fda7b5d37deabdc55c4731616e83'
QUEUE_SHA = '2633928a478f09df2a2dcfb43d6505c6390c39c6805dd438d81f8f1b3d9c10ab'
RATE = 3840000
BLOCK_BYTES = 8388608
SECONDS = 5


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--session-id', required=True)
    parser.add_argument('--antenna-fm-confirmed', action='store_true', required=True)
    parser.add_argument('--listen-during-recording', action='store_true')
    args = parser.parse_args()
    session_id = str(uuid.UUID(args.session_id))
    root = args.root.resolve()
    bit = root/'overlay/sentinel_v2_100m/sentinel_v2_100m.bit'
    library = root/'ps/libad9361_pynq/libad9361_pynq.so'
    for path, expected in ((bit, BIT_SHA), (library, LIB_SHA),
                           (root/'ps/sentinel/rx_queue.py', QUEUE_SHA)):
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise RuntimeError('Accepted artifact differs: '+str(path))
    sys.path.insert(0, str(root/'ps'))
    os.environ['XILINX_XRT'] = '/usr'
    os.environ['SENTINEL_RF_LIBRARY'] = str(library)
    import numpy as np
    from sentinel.app.runtime_v1 import Session
    from sentinel.panorama_capture import radio_state, write_json, seal
    from sentinel.rx_queue import QueuedRx
    from sentinel.telemetry import read_temperature_c
    from sentinel.v2 import V2
    from sentinel.audio_y3 import CodecOutputs, PynqIicBus, shutdown_audio_outputs

    args.out.mkdir(parents=True, exist_ok=False)
    block_samples = BLOCK_BYTES//8
    block_count = math.ceil(SECONDS*RATE/block_samples)
    # Allocate ordinary RAM before starting RF. SD and DSP work occur after stop.
    recording = np.empty(block_count*BLOCK_BYTES, dtype=np.uint8)
    recording.fill(0)
    record = dict(status='STARTED', session_id=session_id, seconds_requested=SECONDS,
                  source='CURRENT_RX1A_FM_IQ', station_hz=95800000,
                  sample_rate_hz=RATE, tx_requested=False, synthetic=False,
                  speaker_pcm_readback=False, blocks=[], adc_exact_sequence_available=False,
                  raw_format='RX1_I_RX1_Q_RX2_I_RX2_Q_INT16_LE',
                  listen_during_recording=args.listen_during_recording, live_quality=[],
                  boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())
    session = queue = backend = codec = None
    completed = False
    quarantined = False
    started = time.monotonic()

    def stop(*_):
        raise KeyboardInterrupt('Controlled finite recording stop')

    for number in (signal.SIGTERM, signal.SIGINT):
        signal.signal(number, stop)
    with open('/run/lock/zss_release_v2.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            session = Session(str(bit), source='rf', rate=RATE, lo=96050000,
                              load=False, hw_factory=V2)
            session.__enter__()
            hw, radio = session.hw, session.radio
            record['before'] = radio_state(radio)
            if record['before']['rate_hz'] != RATE or abs(record['before']['lo_hz']-96050000) > 3:
                raise RuntimeError('RF rate/LO readback differs from baseline')
            if hw.audio.control.read(0) or hw.src_regs.read(0):
                raise RuntimeError('Source/audio must remain stopped during finite recording')
            if args.listen_during_recording:
                from sentinel.app.resident import ReceiveBackend
                from sentinel.release_support import load_config
                from sentinel.tracker_x5 import TargetTracker
                from sentinel.capture_x5 import select_channel
                from sentinel.fm_quality import stereo_quality

                class ListeningBackend(ReceiveBackend):
                    def _quality(self):
                        capture = self.hw.channel_capture.acquire(
                            select_channel(self.config['station_hz']-self.config['lo_hz']), source=0)
                        quality = stereo_quality(capture['iq'])
                        self.quality = quality
                        self.last_quality = time.monotonic()
                        record['live_quality'].append(dict(quality, observed_s=time.monotonic()-started))
                        return quality

                backend = ListeningBackend(root, args.out)
                backend.hw, backend.radio = hw, radio
                backend.config = load_config(root/'config.yaml')
                if backend.config['station_hz'] != 95800000 or backend.config['lo_hz'] != 96050000:
                    raise RuntimeError('Require the validated 95.8MHz listening configuration')
                hw.audio.disable(release_pins=True)
                codec = CodecOutputs(PynqIicBus(hw.audio_iic))
                codec.initialize(volume_db=-6, speaker_volume_db=0)
                backend.codec = codec
                backend.tracker = TargetTracker()
                hw.lcd.set_bus_phase(backend.config['bus_phase'])
                hw.lcd.enable()
                backend._start_receive()
                backend.enter_scene('listen')
                ready_deadline = time.monotonic()+6
                while not backend.ready('listen')['ready']:
                    backend.safety()
                    if time.monotonic() > ready_deadline:
                        raise RuntimeError('Live broadcast did not pass the existing quality gate')
                    time.sleep(.02)
                print('LIVE_SPEAKER_PLAYING_BEFORE_RECORD', flush=True)
                listen_until = time.monotonic()+5
                while time.monotonic() < listen_until:
                    backend.safety()
                    backend._audio_quality()
                    time.sleep(.05)
            adc = hw.checked.registers('axi_ad9361')
            queue = QueuedRx(hw.checked.registers('axi_ad9361_adc_dma'), nbytes=BLOCK_BYTES)
            queue.start()
            warmup = time.monotonic()+1
            while time.monotonic() < warmup:
                queue.consume(lambda _: None)
            # Only the pre-recording warmup flag is cleared, never measured faults.
            adc.write(0x88, 4)
            if adc.read(0x88) & 4:
                raise RuntimeError('Overflow persists after pre-recording warmup')
            epoch = time.monotonic()
            copy_times = []
            if backend is not None:
                record['audio_at_record_start'] = hw.audio.snapshot()
                print('LIVE_SPEAKER_AND_RECORDING_STARTED', flush=True)
            for index in range(block_count):
                if time.monotonic()-epoch > 15:
                    raise TimeoutError('Five-second recording exceeded bounded deadline')

                def copy(buffer):
                    view = np.asarray(buffer).view(np.uint8).reshape(-1)
                    if view.nbytes != BLOCK_BYTES or not view.flags.c_contiguous:
                        raise ValueError('Unexpected completed DMA buffer shape')
                    mark = time.monotonic()
                    np.copyto(recording[index*BLOCK_BYTES:(index+1)*BLOCK_BYTES], view)
                    copy_times.append(time.monotonic()-mark)

                identifier = queue.consume(copy)
                overflow = int(adc.read(0x88))
                record['blocks'].append(dict(index=index, descriptor_id=identifier,
                    first_delivered_sample=index*block_samples, samples=block_samples,
                    fifo_status=overflow, copy_s=copy_times[-1], completed_offset_s=time.monotonic()-epoch))
                if overflow & 4:
                    raise RuntimeError('ADC FIFO overflow; recording must not be played')
                if backend is not None:
                    backend._audio_quality()
                    backend.safety()
                    audio_state = hw.audio.snapshot()
                    record['blocks'][-1]['live_audio'] = audio_state
                    record['blocks'][-1]['speaker_audible'] = backend.audible
                    if not backend.audible or not audio_state['playing']:
                        raise RuntimeError('Live speaker became muted during recording')
                if index % 7 == 0:
                    state = radio_state(radio)
                    temperature = read_temperature_c()
                    if temperature is None or temperature >= 85:
                        raise RuntimeError('Invalid or excessive SoC temperature')
                    print('FM_RECORD_BLOCK', index+1, '/', block_count, flush=True)
                    record['blocks'][-1].update(radio=state, temperature_c=temperature)
            record.update(measured_wall_s=time.monotonic()-epoch,
                          recorded_samples=block_count*block_samples,
                          sampled_duration_s=block_count*block_samples/RATE,
                          observed_overflow_epochs=0,
                          continuity='No FIFO overflow observed; no embedded ADC sequence counter')
            # Drain hardware ownership before processing or writing the capture.
            queue.close()
            record['after'] = radio_state(radio)
            if backend is not None:
                record['audio_at_record_end'] = hw.audio.snapshot()
                print('LIVE_RECORDING_DONE_SPEAKER_CONTINUES', flush=True)
                listen_until = time.monotonic()+5
                while time.monotonic() < listen_until:
                    backend.safety()
                    backend._audio_quality()
                    time.sleep(.05)
            completed = True
        except BaseException as error:
            record.update(status='FAIL', error=repr(error))
        finally:
            if queue is not None:
                try:
                    queue.close()
                except BaseException as error:
                    record.update(status='FAIL', cleanup_error=repr(error))
                quarantined = queue.failed
            record['buffers_quarantined'] = quarantined
            if codec is not None:
                errors = shutdown_audio_outputs(codec, session.hw.audio)
                if errors:
                    record.update(status='FAIL', audio_cleanup_errors=errors)
            if not quarantined:
                try:
                    if session is not None:
                        session.close()
                    if session is not None and session.hw is not None:
                        record['stopped'] = dict(
                            gpio=session.hw.checked.registers('axi_ad9361_gpio').read(0),
                            source=session.hw.src_regs.read(0), audio=session.hw.audio.control.read(0))
                        if any(record['stopped'].values()):
                            raise RuntimeError('Stop readback nonzero')
                except BaseException as error:
                    record.update(status='FAIL', stop_error=repr(error))
            record['elapsed_s'] = time.monotonic()-started
            if completed and record['status'] != 'FAIL' and not quarantined:
                if recording.view('<i2').min() < -2048 or recording.view('<i2').max() > 2047:
                    record.update(status='FAIL', error='Invalid signed ADC format')
                else:
                    path = args.out/'current_adc_iq.i16'
                    with path.open('xb') as stream:
                        recording.tofile(stream)
                    seal(path)
                    record.update(status='PASS_FINITE_RECORDING', file=path.name,
                                  file_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            write_json(args.out/'result.json', record)
            if quarantined:
                while True:
                    time.sleep(1)  # Retain all in-flight allocation owners.
    return 0 if record['status'] == 'PASS_FINITE_RECORDING' else 1


if __name__ == '__main__':
    raise SystemExit(main())
