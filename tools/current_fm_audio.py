"""Decode only the capture bound to the current recording request."""
from pathlib import Path
import sys
import wave

import numpy as np

from run_x1_board import ROOT, sha, write_evidence
from x2_transport import verified


def current_capture(directory, session_id):
    directory = Path(directory)
    validation = verified(directory/'validation.json')
    raw = verified(directory/'raw/result.json')
    if (validation['status'] != 'PASS_FINITE_RECORDING'
            or raw['status'] != 'PASS_FINITE_RECORDING'
            or validation.get('session_id') != session_id or raw.get('session_id') != session_id):
        raise ValueError('Capture does not belong to this successful recording request')
    if validation['postflight']['status'] != 'PASS' or raw.get('buffers_quarantined'):
        raise ValueError('Require independent stopped readback and released DMA ownership')
    if raw.get('observed_overflow_epochs') != 0 or raw.get('synthetic') is not False:
        raise ValueError('Refuse overflowed or synthetic audio')
    if sha(directory/'raw/result.json') != validation['files_sha256']['result.json']:
        raise ValueError('Raw result not bound to capture validation')
    name = raw['file']
    if name != 'current_adc_iq.i16':
        raise ValueError('Unexpected current recording artifact')
    path = directory/'raw'/name
    if (sha(path) != raw['file_sha256'] or sha(path) != validation['files_sha256'][name]
            or path.stat().st_size != raw['recorded_samples']*8):
        raise ValueError('Current IQ length or SHA256 differs')
    return raw, path


def decode(directory, session_id):
    directory = Path(directory)
    raw, path = current_capture(directory, session_id)
    return _decode_verified(directory, session_id, raw, path)


def decode_current_owner(directory, session_id):
    """Resident-owner evidence, distinct from an independent process postflight."""
    directory = Path(directory)
    validation = verified(directory/'validation.json')
    raw = verified(directory/'raw/result.json')
    stopped = raw.get('owner_stopped', {})
    if (validation.get('source') != 'RESIDENT_OWNER_STOPPED_RECORDING'
            or validation.get('session_id') != session_id or raw.get('session_id') != session_id
            or raw.get('status') != 'PASS_FINITE_RECORDING' or raw.get('synthetic') is not False
            or raw.get('observed_overflow_epochs') != 0 or raw.get('buffers_quarantined') is not False
            or raw.get('listen_during_recording') is not True
            or stopped.get('source_ctrl') != 0 or stopped.get('audio_control') != 0
            or stopped.get('codec_muted') is not True or stopped.get('rate_hz') != 3840000
            or stopped.get('tx_attenuation_db') != [89.75, 89.75]
            or validation.get('capture_sha256') != sha(directory/'raw/result.json')):
        raise ValueError('Resident recording identity, quality or stopped readback differs')
    if raw.get('file') != 'current_adc_iq.i16':
        raise ValueError('Unexpected current recording artifact')
    path = directory/'raw'/raw['file']
    if sha(path) != raw['file_sha256'] or path.stat().st_size != raw['recorded_samples']*8:
        raise ValueError('Resident IQ digest or length differs')
    return _decode_verified(directory, session_id, raw, path)


def _decode_verified(directory, session_id, raw, path):
    output = directory/'current_recording.wav'
    if output.exists() or (directory/'audio.json').exists():
        raise FileExistsError('Preserve the prior audio result')
    sys.path.insert(0, str(ROOT/'src/ps'))
    from sentinel.fm_receive import demodulate_chunk
    counts = np.fromfile(path, dtype='<i2').reshape(-1, 4)[:, :2]
    iq = counts[:, 0].astype(float) + 1j*counts[:, 1].astype(float)
    audio, metrics, _, _ = demodulate_chunk(iq, raw['sample_rate_hz'],
        raw['before']['lo_hz'], raw['station_hz'], profile='wide')
    # Fixed scale preserves signal/noise relation; no gap filling or old PCM.
    pcm_float = audio/75000.
    clip_fraction = float(np.mean(abs(pcm_float) > .95))
    pcm = np.rint(np.clip(pcm_float, -.95, .95)*32767).astype('<i2')
    with output.open('xb') as stream:
        with wave.open(stream, 'wb') as wav:
            wav.setparams((1, 2, 48000, 0, 'NONE', 'not compressed'))
            wav.writeframes(pcm.tobytes())
    Path(str(output)+'.sha256').write_text(sha(output)+'  '+output.name+'\n', encoding='ascii')
    result = dict(status='READY_FOR_LISTENING' if metrics['stereo_pilot_evidence'] and clip_fraction < .001
                  else 'QUALITY_UNCONFIRMED', session_id=session_id,
                  source='CURRENT_RF_IQ_SOFTWARE_FM_DEMOD', synthetic=False,
                  station_hz=raw['station_hz'],
                  wav=output.name, wav_sha256=sha(output), sample_rate_hz=48000,
                  samples=len(pcm), duration_s=len(pcm)/48000,
                  scale_hz_per_full_scale=75000, output_clipped_fraction=clip_fraction,
                  pcm_rms=float(np.sqrt(np.mean((pcm.astype(float)/32768.)**2))),
                  metrics=metrics, source_validation_sha256=sha(directory/'validation.json'),
                  source_iq_sha256=sha(path), speaker_pcm_readback=False,
                  simultaneous_live_speaker=raw.get('listen_during_recording', False),
                  inserted_silence_samples=0, stitched_snapshot_gaps=False,
                  adc_continuity_note=raw['continuity'], human_listening='PENDING')
    write_evidence(directory/'audio.json', result)
    return output, result
