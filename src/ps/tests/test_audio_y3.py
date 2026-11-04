"""Safety/protocol tests with injected IIC/MMIO, never hardware."""
import pytest

from src.ps.sentinel.audio_y3 import AudioControl, CodecOutputs, shutdown_audio_outputs


@pytest.mark.parametrize('address,kind', [(0, 'xilinx.com:ip:axi_iic:2.1'),
                                       (0x41630000, 'unknown:device')])
def test_audio_iic_rejects_wrong_hardware_before_driver_import(address, kind):
    from types import SimpleNamespace
    from src.ps.sentinel.audio_y3 import bind_audio_iic
    overlay = SimpleNamespace(ip_dict={'axi_iic_audio': dict(
        phys_addr=address, addr_range=65536, type=kind)})
    with pytest.raises(ValueError, match='contract'):
        bind_audio_iic(overlay)


def test_audio_iic_binds_explicit_driver_only(monkeypatch):
    import sys
    from types import SimpleNamespace
    from src.ps.sentinel.audio_y3 import bind_audio_iic
    entry = dict(phys_addr=0x41630000, addr_range=65536,
                 type='xilinx.com:ip:axi_iic:2.1')
    monkeypatch.setitem(sys.modules, 'pynq.lib.iic', SimpleNamespace(AxiIIC=lambda d: d))
    assert bind_audio_iic(SimpleNamespace(ip_dict={'axi_iic_audio': entry})) == entry


@pytest.mark.parametrize('codec_failure', ['none', 'reported', 'raised'])
@pytest.mark.parametrize('audio_failure', [False, True])
def test_shutdown_mutes_before_clock_release_and_attempts_all_cleanup(codec_failure, audio_failure):
    from types import SimpleNamespace
    events = []

    def mute():
        events.append('codec')
        if codec_failure == 'raised':
            raise IOError('IIC unavailable')
        return ['Mute readback failed'] if codec_failure == 'reported' else []

    def release(release_pins):
        assert release_pins is True
        events.append('pins')
        if audio_failure:
            raise IOError('MMIO unavailable')

    errors = shutdown_audio_outputs(SimpleNamespace(shutdown=mute),
                                    SimpleNamespace(disable=release))
    assert events == ['codec', 'pins']
    assert len(errors) == int(codec_failure != 'none') + int(audio_failure)


def test_shutdown_can_clean_up_partial_initialization():
    from types import SimpleNamespace
    events = []
    assert shutdown_audio_outputs(None, None) == []
    assert shutdown_audio_outputs(SimpleNamespace(shutdown=lambda: events.append('codec') or []),
                                  None) == []
    assert shutdown_audio_outputs(None, SimpleNamespace(
        disable=lambda release_pins: events.append(('pins', release_pins)))) == []
    assert events == ['codec', ('pins', True)]


class Bus:
    def __init__(self):
        self.regs = {}
        self.writes = []
        self.pointer = None
        self.bad = None
        self.short = False

    def send(self, address, data, length, option=0):
        assert address == 0x10
        assert len(data) == length
        if self.short:
            return length-1
        if length == 2:
            assert option == 0
            self.writes.append(tuple(data))
            self.regs[data[0]] = data[1]
        else:
            assert option == 1
            self.pointer = data[0]
        return length

    def receive(self, address, data, length):
        assert address == 0x10 and length == 1
        data[0] = self.regs.get(self.pointer, 0) ^ (1 if self.bad == self.pointer else 0)
        return 1

    def wait(self):
        pass


class Regs:
    def __init__(self):
        self.values = {0: 0, 8: 0}

    def read(self, address):
        return self.values[address]

    def write(self, address, value):
        self.values[address] = value


def setup():
    bus = Bus()
    codec = CodecOutputs(bus, delay=lambda _: None)
    return bus, codec


def test_initialize_is_muted_out1_out2_and_unmute_requires_readback():
    bus, codec = setup()
    with pytest.raises(RuntimeError):
        codec.unmute()
    codec.initialize()
    assert bus.regs[0x19] == 0x26 and bus.regs[0x04] == 0x3c
    assert all(bus.regs[reg] == 16 for reg in (0x2e, 0x2f, 0x30, 0x31))
    assert bus.regs[0x1a] == bus.regs[0x1b] == 0
    assert codec.volume_db == -21
    assert bus.regs[0x08] == 0 and bus.regs[0x27] & 0xc0 == 0x80
    codec.unmute()
    assert bus.regs[0x19] == 0x22
    assert codec.shutdown() == []
    assert bus.regs[0x19] == 0x26 and bus.regs[0x04] == 0xc0


class ResetSensitiveBus(Bus):
    """Model the reset-held register readbacks observed on the real codec."""
    def send(self, address, data, length, option=0):
        if length == 2:
            reg, value = data
            if reg == 0 and value & 0x80:
                self.regs = {0: 0x80, 4: 0xc0, 8: 0x80, 0x19: 0x22}
            elif self.regs.get(0, 0) & 0x80 and reg != 0:
                self.writes.append((reg, value))
                return length
        return super().send(address, data, length, option)


def test_reset_released_before_mute_or_output_enable():
    bus = ResetSensitiveBus()
    codec = CodecOutputs(bus, delay=lambda _: None)
    codec.initialize()
    assert bus.writes.index((0, 0x06)) < bus.writes.index((0x19, 0x26))
    assert bus.regs[8] == 0 and bus.regs[0x19] == 0x26
    assert codec.shutdown() == []
    assert bus.regs[4] == 0xc0


def test_cleanup_releases_leftover_reset_then_mutes():
    bus = ResetSensitiveBus()
    bus.send(0x10, bytes((0, 0x80)), 2)
    codec = CodecOutputs(bus, delay=lambda _: None)
    assert codec.shutdown() == []
    assert bus.regs[0] & 0x80 == 0
    assert bus.regs[0x19] == 0x26 and bus.regs[4] == 0xc0


def test_bad_readback_or_short_transaction_fails_closed():
    bus, codec = setup()
    bus.bad = 0x17
    with pytest.raises(IOError):
        codec.initialize()
    assert not codec.initialized and bus.regs[0x04] == 0xc0
    bus.bad = None
    codec.initialize()
    bus.regs[0x04] &= ~4  # missing speaker output must prevent unmute
    with pytest.raises(IOError):
        codec.unmute()
    assert not codec.initialized and bus.regs[0x04] == 0xc0
    bus.short = True
    with pytest.raises(IOError):
        codec.initialize()
    assert not codec.initialized


@pytest.mark.parametrize('reg', [0x2e, 0x2f, 0x30, 0x31, 0x1a, 0x1b])
def test_wrong_output_gain_prevents_unmute_and_powers_down(reg):
    bus, codec = setup()
    codec.initialize()
    bus.regs[reg] ^= 1
    with pytest.raises(IOError):
        codec.unmute()
    assert not codec.initialized and bus.regs[0x04] == 0xc0


@pytest.mark.parametrize('volume', [0, -46, -14, -29, float('nan'), float('inf')])
def test_volume_rejected_before_bus_io(volume):
    bus, codec = setup()
    with pytest.raises(ValueError):
        codec.initialize(volume)
    assert not bus.writes


def test_audio_tuning_enforce_stop_slave_and_observe_fault_counters():
    bus, codec = setup()
    ctrl, state, counts = Regs(), Regs(), Regs()
    audio = AudioControl(ctrl, state, counts)
    with pytest.raises(RuntimeError):
        audio.configure(95800000, 96400000, codec)
    codec.initialize()
    selection = audio.configure(95800000, 96400000, codec)
    assert selection.channel == 14 and selection.fcw == 0xc0000000
    assert ctrl.read(0) == 0xe2
    audio.start()
    with pytest.raises(RuntimeError):
        audio.configure(95450000, 96400000, codec)
    state.write(0, 4096 << 4 | 15)
    state.write(8, 123)
    counts.write(0, 2)
    counts.write(8, 4219)
    s = audio.snapshot()
    assert s['fifo_level'] == 4096 and s['iq_overflow'] and s['pcm_full']
    assert s['underflows'] == 2 and s['frames'] == 123 and s['pcm_samples'] == 4219
    audio.disable()
    assert ctrl.read(0) == 0xe2
    audio.disable(release_pins=True)
    assert ctrl.read(0) == 0


def test_tone_requires_muted_codec_and_clears_on_release():
    bus, codec = setup()
    ctrl, state, counts = Regs(), Regs(), Regs()
    audio = AudioControl(ctrl, state, counts)
    with pytest.raises(RuntimeError):
        audio.configure_tone(codec)
    codec.initialize()
    audio.configure_tone(codec)
    assert ctrl.read(0) == 0x102
    audio.start()
    assert ctrl.read(0) == 0x103
    with pytest.raises(RuntimeError):
        audio.configure_tone(codec)
    audio.disable(release_pins=True)
    assert ctrl.read(0) == 0
    assert codec.shutdown() == []


def test_y3_channel_reset_preserves_stop_before_reset_protocol():
    from types import SimpleNamespace
    from src.ps.sentinel.v_y3 import VY3
    hw = VY3.__new__(VY3)
    hw.src_regs, hw.x5_ctrl, hw.x5_status = Regs(), Regs(), Regs()
    hw.channel_capture = SimpleNamespace(failed=False)
    hw.src_regs.write(0, 1)
    with pytest.raises(RuntimeError, match='Stop source'):
        hw.reset_channelizer()
    hw.src_regs.write(0, 0)
    hw.reset_channelizer()
    assert hw.x5_ctrl.values == {0: 0, 8: 0}
    hw.channel_capture.failed = True
    with pytest.raises(RuntimeError, match='full PL reset'):
        hw.reset_channelizer()
