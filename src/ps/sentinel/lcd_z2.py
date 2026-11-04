"""Z2 eight-color LCD UI (version 6); right 200x200 constellation stays out of scroll.

Epoch parity selects one 64 KiB bank. CPU owns only the inactive bank and may
publish one epoch at a time. Applied acknowledges the swap and completed redraw.
"""
import math
import time

import numpy as np

from .drivers.regs import lcd_ctrl as R


VERSION = 0x4c430006
BANK_WORDS = 16384
USED_WORDS = 16000


def displayed_label(track):
    """Keep uncalibrated low-score predictions visibly undecided."""
    return track.label if track.confidence >= .5 else '?'


def pack_ui(right_pixels, status_pixels):
    arrays = []
    for pixels, shape in ((right_pixels, (400,240)), (status_pixels, (80,800))):
        a = np.asarray(pixels)
        if a.shape != shape or not np.issubdtype(a.dtype, np.integer) or np.any(a < 0) or np.any(a > 7):
            raise ValueError('Z2 UI requires palette 0..7 in 400x240 and 80x800')
        arrays.append(a.astype(np.uint32).reshape(-1))
    lanes = np.concatenate(arrays).reshape(-1,10)
    words = np.zeros(USED_WORDS, dtype=np.uint32)
    for lane in range(10):
        words |= lanes[:,lane] << (3*lane)
    return words


class Z2LCD:
    def __init__(self, registers, memory):
        if registers.read(R.VERSION) != VERSION:
            raise ValueError('Z2 LCD requires double-buffer/scroll-aware version 6')
        self.registers, self.ui_memory = registers, memory

    def enable(self, enabled=True):
        self.registers.write(R.CTRL, int(bool(enabled)))

    def set_bus_phase(self, cycles):
        if type(cycles) is not int or not 1 <= cycles <= 255:
            raise ValueError('Invalid bus phase')
        self.registers.write(R.BUS_PHASE, cycles)

    def submit_ui(self, right, status):
        epoch = self.registers.read(R.UI_EPOCH)
        if epoch != self.registers.read(R.UI_APPLIED):
            raise RuntimeError('A UI swap is already pending')
        if self.registers.read(R.STATUS) & 0x1c:
            raise RuntimeError('LCD reports a framing/region error')
        token = (epoch+1) & 0xffffffff
        offset = (token & 1)*BANK_WORDS
        words = pack_ui(right, status)
        if hasattr(self.ui_memory, 'array'):
            if len(self.ui_memory.array) < 2*BANK_WORDS:
                raise ValueError('UI BRAM must map 128 KiB')
            self.ui_memory.array[offset:offset+USED_WORDS] = words
        else:
            for index, word in enumerate(words):
                self.ui_memory.write(4*(offset+index), int(word))
        for index in (0, USED_WORDS-1):
            if self.ui_memory.read(4*(offset+index)) != int(words[index]):
                raise IOError('UI bank readback mismatch')
        self.registers.write(R.UI_EPOCH, token)
        return token

    def wait_ui(self, token, timeout=2):
        deadline = time.monotonic()+timeout
        while self.registers.read(R.UI_APPLIED) != token:
            if time.monotonic() >= deadline:
                raise TimeoutError('LCD page swap timed out')
            time.sleep(.001)


PALETTE_RGB565 = (0x0000, 0xffff, 0xffe0, 0x07ff, 0xf800, 0x07e0, 0x5bff, 0xf81f)
CLASS_COLOR = {'FM': 3, 'AM-DSB': 3, 'AM-SSB': 3, 'AM': 3,
               'BPSK': 6, 'QPSK': 6, '8PSK': 6, 'PSK': 6,
               '16QAM': 7, '64QAM': 7, 'QAM': 7,
               '2FSK': 2, '4FSK': 2, 'GFSK': 2, 'CPFSK': 2, 'FSK': 2,
               'OOK': 1, '?': 1}


def draw_ui(tracks, selected=None, iq=None, symbols=None, lo_hz=0, rate_hz=3840000,
            frame=0, fps=0, temperature_c=None, page=0, model_status='X4 FAIL CANDIDATE',
            mode='RX', tx_on=False, tx_atten_db=89.75, events=()):
    """Draw actual caller-supplied readbacks; this function never controls TX.

    Model class colors indicate predictions, not verified signal identities.
    Caller must obtain TX state/attenuation from the safety/control layer.
    """
    from PIL import Image, ImageDraw, ImageFont
    from .lcd_x5 import draw_ui as base_draw
    if mode not in ('RX', 'TEST', 'REPLAY', 'OTA', 'LISTEN') or type(tx_on) is not bool:
        raise ValueError('Invalid mode/TX state')
    if not math.isfinite(tx_atten_db) or not 0 <= tx_atten_db <= 89.75:
        raise ValueError('Invalid TX attenuation readback')
    base, _ = base_draw(tracks, selected, iq, symbols, lo_hz, rate_hz,
                        frame, fps, temperature_c, page, model_status)
    images = [Image.fromarray(base.copy()), Image.new('L', (800, 80), 0)]
    right, status = [ImageDraw.Draw(im) for im in images]
    try:
        font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf', 12)
    except OSError:
        font = ImageFont.load_default()
    right.fontmode = status.fontmode = '1'
    page %= max(1, (len(tracks)+3)//4)
    for row, track in enumerate(tracks[page*4:(page+1)*4]):
        y = 37+row*32
        label = displayed_label(track)
        right.rectangle((0, y, 239, y+14), fill=0)
        right.text((4, y), '%s %s %.0f%% P%u' % (
            '>' if selected == track.key else ' ', label, 100*track.confidence, track.power),
            font=font, fill=CLASS_COLOR.get(label, 1))
    status.text((8, 2), '%s LO %.3fM %.3fMSPS' % (mode, lo_hz/1e6, rate_hz/1e6), font=font, fill=3)
    temperature = '%.1fC' % temperature_c if temperature_c is not None and math.isfinite(temperature_c) else 'N/A'
    status.text((8, 21), 'FRAME %u %.1fFPS %s' % (frame, fps, temperature), font=font, fill=2)
    status.text((8, 40), 'TX %s %.2fdB' % ('ON' if tx_on else 'OFF', tx_atten_db),
                font=font, fill=4 if tx_on else 5)
    chosen = next((t for t in tracks if t.key == selected), None)
    latency = chosen.display_latency_ms if chosen is not None else None
    status.text((170, 40), 'FIRST %s' % ('%.0fms' % latency if latency is not None else 'PENDING'),
                font=font, fill=1)
    status.text((8, 60), model_status[:42], font=font, fill=1)
    status.line((398, 0, 398, 79), fill=1)
    for index, event in enumerate(tuple(events)[:5]):
        text = '%s %s %s' % (event.timestamp_utc, event.kind, event.text)
        # Pixel-width crop keeps events inside the actual LCD margins.
        while text and status.textbbox((0, 0), text, font=font)[2] > 386:
            text = text[:-1]
        status.text((406, 2+15*index), text, font=font, fill=4 if event.kind == 'ALARM' else 1)
    return tuple(np.asarray(im, dtype=np.uint8) for im in images)

