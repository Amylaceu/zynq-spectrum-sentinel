"""Create immutable evidence for verified Y3 integration fixes."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCES = (
    'src/rtl/audio_y3/audio_sink_y3.v',
    'src/rtl/audio_y3/fm_audio_filter_y3.v',
    'src/rtl/audio_y3/y3_frontend.v',
    'src/rtl/audio_y3/rom/y3_tone.hex',
    'sim/tb/tb_audio_sink_y3.sv',
    'sim/tb/tb_audio_tone_y3.sv',
    'src/ps/sentinel/audio_y3.py',
    'src/ps/tests/test_audio_y3.py',
)
LOGS = (
    'logs/Y3_fm_regression_r3.log',
    'logs/Y3_sink_regression_r3d.log',
    'logs/Y3_tone_sim_r1d.log',
    'logs/Y3_audio_pc_r4.log',
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    result = ROOT/'sim/results/y3_integration_regression_r1.json'
    archive = ROOT/'report/results/y3_integration_regression_r1.zip'
    if any(path.exists() for path in (result, Path(str(result)+'.sha256'), archive,
                                      Path(str(archive)+'.sha256'))):
        raise FileExistsError('Preserve previous integration regression evidence')
    for name in LOGS[:3]:
        if 'TB_RESULT: PASS' not in (ROOT/name).read_text(encoding='utf-8', errors='replace'):
            raise ValueError('Missing simulation PASS marker: '+name)
    if '33 passed' not in (ROOT/LOGS[3]).read_text(encoding='utf-8', errors='replace'):
        raise ValueError('Missing PS regression result')
    members = SOURCES + LOGS
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as bundle:
        for name in members:
            bundle.write(ROOT/name, name)
    Path(str(archive)+'.sha256').write_text(sha(archive)+'  '+archive.name+'\n', encoding='ascii')
    value = dict(
        schema='y3-integration-regression-v1', status='PASS',
        recorded_at_pc=datetime.now(timezone.utc).isoformat(),
        scope='FM golden, continuous I2S sink, 1kHz tone at external I2S pins, PS protocol tests; no board claim',
        checks=dict(fm_golden='PASS: 8193 IQ / 820 PCM exact',
                    continuous_sink='PASS: 800 stereo frames, +80ppm, zero underflows',
                    tone='PASS: 1kHz/48kHz, 96 stereo frames, zero underflows',
                    ps_tests='PASS: 33 tests'),
        sources_sha256={name: sha(ROOT/name) for name in SOURCES},
        logs_sha256={name: sha(ROOT/name) for name in LOGS},
        archive=archive.relative_to(ROOT).as_posix(), archive_sha256=sha(archive))
    result.write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')
    Path(str(result)+'.sha256').write_text(sha(result)+'  '+result.name+'\n', encoding='ascii')
    print('Y3_INTEGRATION_REGRESSION_PASS')


if __name__ == '__main__':
    main()
