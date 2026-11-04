"""Explicit, injectable ES8388 speaker/OUT1 and Y3 continuous-audio controls.

Importing never opens hardware. Register definitions: ES8388 Rev5, sections
4/6.1/6.3. DAC24 I2S, slave,256Fs; analog ADC paths stay disabled.
Codec must be slave before FPGA clock-pin drivers are enabled.
"""
import math
import time

from .capture_x5 import select_channel


def shutdown_audio_outputs(codec, audio):
    """Mute/power down the DAC before releasing clocks, attempting both steps.

    Return cleanup errors so callers can preserve failed evidence while still
    stopping RF and releasing their session. Neither argument must exist when
    initialization failed partway through.
    """
    errors = []
    if codec is not None:
        try:
            errors.extend(codec.shutdown())
        except Exception as error:
            errors.append('Codec mute/power-down: ' + repr(error))
    if audio is not None:
        try:
            audio.disable(release_pins=True)
        except Exception as error:
            errors.append('PL audio mute/Hi-Z: ' + repr(error))
    return errors


def bind_audio_iic(overlay):
    """Bind only the verified audio controller, not all mismatched IPs."""
    description = dict(overlay.ip_dict['axi_iic_audio'])
    if (description.get('type') not in ('xilinx.com:ip:axi_iic:2.0',
                                       'xilinx.com:ip:axi_iic:2.1')
            or int(description.get('phys_addr', -1)) != 0x41630000
            or int(description.get('addr_range', 0)) < 4096):
        raise ValueError('Unexpected audio AXI IIC contract')
    from pynq.lib.iic import AxiIIC
    return AxiIIC(description)


class PynqIicBus:
    """Normalize CFFI buffers for the installed PYNQ2.7 AxiIIC driver."""
    def __init__(self, ip):
        self.ip = ip

    def send(self, address, data, length, option=0):
        buffer = self.ip._ffi.new('unsigned char[]', bytes(data[:length]))
        return self.ip.send(address, buffer, length, option)

    def receive(self, address, data, length, option=0):
        buffer = self.ip._ffi.new('unsigned char[]', length)
        count = self.ip.receive(address, buffer, length, option)
        data[:count] = bytes(self.ip._ffi.buffer(buffer, count))
        return count

    def wait(self):
        self.ip.wait()


class CodecOutputs:
    ADDRESS = 0x10
    MUTE = 0x26  # soft ramp + mute, preserving factory reserved bit1
    UNMUTE = 0x22
    DIGITAL_VOLUME_DB = 0  # Z7 gain is set at the four analog output attenuators

    def __init__(self, bus, delay=time.sleep):
        self.bus, self.delay = bus, delay
        self.initialized = False
        self.volume_db = None
        self.speaker_volume_db = None

    def write(self, reg, value):
        if self.bus.send(self.ADDRESS, bytes((reg, value)), 2) != 2:
            raise IOError('Short codec IIC write')
        self.bus.wait()

    def read(self, reg):
        if self.bus.send(self.ADDRESS, bytes((reg,)), 1, 1) != 1:
            raise IOError('Short codec IIC address')
        result = bytearray(1)
        if self.bus.receive(self.ADDRESS, result, 1) != 1:
            raise IOError('Short codec IIC read')
        self.bus.wait()
        return result[0]

    def checked(self, reg, value):
        self.write(reg, value)
        actual = self.read(reg)
        if actual != value:
            raise IOError('Codec readback reg%02x got%02x expected%02x' % (reg, actual, value))

    @staticmethod
    def volume_code(volume_db):
        # F1 absolute software ceiling; this is analog gain, not acoustic SPL.
        if type(volume_db) not in (int, float) or not math.isfinite(volume_db) or not -45 <= volume_db <= -6:
            raise ValueError('Output analog volume must be -45..-6 dB')
        code = round((volume_db+45)/1.5)
        if abs((-45+1.5*code)-volume_db) > 1e-6:
            raise ValueError('Output volume must use 1.5 dB steps')
        return code

    @staticmethod
    def speaker_volume_code(volume_db):
        # Explicit ROUT2-only extension, requested after -6 dB listening.
        # ES8388 Rev5 p28: code 30 = 0 dB. Keep positive gain unavailable.
        if type(volume_db) not in (int, float) or not math.isfinite(volume_db) or not -45 <= volume_db <= 0:
            raise ValueError('Speaker analog volume must be -45..0 dB')
        code = round((volume_db+45)/1.5)
        if abs((-45+1.5*code)-volume_db) > 1e-6:
            raise ValueError('Speaker volume must use 1.5 dB steps')
        return code

    def initialize(self, volume_db=-21, speaker_volume_db=None):
        code = self.volume_code(volume_db)  # reject before any bus writes
        speaker_code = code if speaker_volume_db is None else self.speaker_volume_code(speaker_volume_db)
        self.initialized = False
        self.volume_db = None
        self.speaker_volume_db = None
        try:
            self.write(0x04, 0xc0)  # all analog outputs off before reset
            self.write(0x00, 0x80)
            self.delay(.01)
            # ES8388 Rev5 section 6.1.1: SCPReset is level-sensitive.
            # Release it before checking registers; otherwise writes can
            # continue reading their reset defaults (e.g. DAC mute 0x22).
            self.checked(0x00, 0x06)
            self.checked(0x04, 0xc0)
            self.checked(0x08, 0x00)  # slave, non-inverted BCLK, no MCLK /2
            self.checked(0x19, self.MUTE)
            for reg, value in (
                (0x04, 0xc0), (0x02, 0xc3), (0x03, 0xfc),
                (0x00, 0x3d),  # DAC-clock source, SameFs, sequence, ref,VMID50k
                (0x01, 0x40),  # preserve factory bit6, normal analog/bias/vref
                (0x05, 0x00), (0x06, 0x00), (0x07, 0x7c),
                (0x17, 0x00), (0x18, 0x02), (0x1a, 0x00), (0x1b, 0x00),
                (0x1c, 0x08), (0x1d, 0x00), (0x26, 0x00),
                (0x27, 0xb8), (0x2a, 0xb8),  # DAC only; analog bypass off
                (0x2b, 0x88),  # shared DAC LRCK, ADC DLL off, MCLK on
                (0x2e, 0x00), (0x2f, 0x00), (0x30, 0x00), (0x31, 0x00),
                (0x02, 0x8a),  # DAC digital/filter/reference on, ADC off
            ):
                self.checked(reg, value)
            self.delay(.1)  # references/VMID settle with outputs still disabled
            self.checked(0x04, 0x3c)  # double DAC + OUT1 and OUT2; ROUT2 drives J36 amp
            self.delay(.1)
            self.checked(0x2e, code)
            self.checked(0x2f, code)
            self.checked(0x30, code)
            self.checked(0x31, speaker_code)
            self.volume_db = volume_db
            self.speaker_volume_db = volume_db if speaker_volume_db is None else speaker_volume_db
            self.assert_safe(require_muted=True)
            self.initialized = True
        except BaseException:
            self.shutdown()
            raise

    def assert_safe(self, require_muted=False):
        if self.volume_db is None:
            raise RuntimeError('Codec volume/readback required')
        code = self.volume_code(self.volume_db)
        expected = {0x04: 0x3c, 0x08: 0x00, 0x17: 0x00, 0x18: 0x02,
                    0x1a: 0x00, 0x1b: 0x00, 0x27: 0xb8, 0x2a: 0xb8,
                    0x2e: code, 0x2f: code, 0x30: code,
                    0x31: self.speaker_volume_code(self.speaker_volume_db)}
        if require_muted:
            expected[0x19] = self.MUTE
        for reg, value in expected.items():
            if self.read(reg) != value:
                raise IOError('Unsafe/unexpected codec register%02x' % reg)
        return True

    def unmute(self):
        if not self.initialized:
            raise RuntimeError('Codec initialization/readback required')
        try:
            self.assert_safe(require_muted=True)
            self.checked(0x19, self.UNMUTE)
        except BaseException:
            self.shutdown()
            raise

    def shutdown(self):
        # Best effort: even a failed mute read/write must not skip power-down.
        errors = []
        try:
            control = self.read(0x00)
            if control & 0x80:
                self.checked(0x00, control & 0x7f)
        except Exception as error:
            errors.append('Reset release during shutdown: ' + str(error))
        for reg, value in ((0x19, self.MUTE), (0x04, 0xc0)):
            try:
                self.checked(reg, value)
            except Exception as error:
                errors.append(str(error))
        self.initialized = False
        return errors


class AudioControl:
    """All GPIO accesses are DSP-clocked via explicit AXI clock converters."""
    def __init__(self, control, state, counts):
        self.control, self.state, self.counts = control, state, counts

    def disable(self, release_pins=False):
        value = 0 if release_pins else int(self.control.read(0)) & ~1
        self.control.write(0, value)
        if self.control.read(0) != value:
            raise IOError('Audio disable readback mismatch')

    def configure(self, station_hz, lo_hz, codec):
        if not codec.initialized:
            raise RuntimeError('Configure codec before driving audio clocks')
        codec.assert_safe(require_muted=True)
        if self.control.read(0) & 1:
            raise RuntimeError('Stop audio before changing channel/FCW')
        selection = select_channel(station_hz-lo_hz)
        value = (selection.channel << 4) | 2  # pins on; stream still off
        self.control.write(8, selection.fcw)
        self.control.write(0, value)
        if self.control.read(8) != selection.fcw or self.control.read(0) != value:
            raise IOError('Audio config readback mismatch')
        return selection

    def configure_tone(self, codec):
        """Arm the fixed 1 kHz self-test without initializing RF or DMA."""
        if not codec.initialized:
            raise RuntimeError('Configure codec before driving audio clocks')
        codec.assert_safe(require_muted=True)
        if self.control.read(0) & 1:
            raise RuntimeError('Stop audio before switching to test tone')
        value = 0x102  # tone_mode + clock pins; stream enable remains clear
        self.control.write(0, value)
        if self.control.read(0) != value:
            raise IOError('Audio tone configuration readback mismatch')

    def start(self):
        value = int(self.control.read(0))
        if not value & 2:
            raise RuntimeError('Audio clock pins must be configured first')
        self.control.write(0, value | 1)
        if self.control.read(0) != (value | 1):
            raise IOError('Audio enable readback mismatch')

    def snapshot(self):
        raw = int(self.state.read(0))
        return dict(raw_status=raw, enabled=bool(raw & 1), iq_overflow=bool(raw & 2),
            pcm_full=bool(raw & 4), playing=bool(raw & 8), fifo_level=(raw >> 4) & 0x3fff,
            frames=int(self.state.read(8)), underflows=int(self.counts.read(0)),
            pcm_samples=int(self.counts.read(8)))
