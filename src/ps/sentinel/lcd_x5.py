"""Double-buffered X5 LCD UI; right 200x200 constellation stays out of scroll.

Epoch parity selects one 64 KiB bank. CPU owns only the inactive bank and may
publish one epoch at a time. Applied acknowledges the swap and completed redraw.
"""
import math
import time

import numpy as np

from .drivers.regs import lcd_ctrl as R


VERSION = 0x4c430005
BANK_WORDS = 16384
USED_WORDS = 10000


def displayed_label(track):
    """Keep uncalibrated low-score predictions visibly undecided."""
    return track.label if track.confidence >= .5 else '?'


def label_color(label):
    """Use only the four colors physically supported by the frozen LCD IP."""
    if label == 'FM':
        return 1  # white
    if label.startswith('AM'):
        return 2  # yellow
    return 3  # cyan: digital or undecided; names remain visible


def pack_ui(right_pixels, status_pixels):
    arrays = []
    for pixels, shape in ((right_pixels, (400,240)), (status_pixels, (80,800))):
        a = np.asarray(pixels)
        if a.shape != shape or not np.issubdtype(a.dtype, np.integer) or np.any(a < 0) or np.any(a > 3):
            raise ValueError('X5 UI requires palette 0..3 in 400x240 and 80x800')
        arrays.append(a.astype(np.uint32).reshape(-1))
    lanes = np.concatenate(arrays).reshape(-1,16)
    words = np.zeros(USED_WORDS, dtype=np.uint32)
    for lane in range(16):
        words |= lanes[:,lane] << (2*lane)
    return words


class X5LCD:
    def __init__(self, registers, memory):
        if registers.read(R.VERSION) != VERSION:
            raise ValueError('X5 LCD requires double-buffer/scroll-aware version 5')
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


def draw_ui(tracks, selected=None, iq=None, symbols=None, lo_hz=0, rate_hz=3840000,
            frame=0, fps=0, temperature_c=None, page=0, model_status='X4 FAIL CANDIDATE',
            demo_title=None, demo_remaining_s=None, demo_mode=None,
            tx_active=False, tx_atten_db=None):
    if type(tx_active) is not bool or (tx_active and
            (tx_atten_db is None or not math.isfinite(tx_atten_db) or not 40 <= tx_atten_db <= 89.75)):
        raise ValueError('Active OTA display requires checked attenuation 40..89.75dB')
    from PIL import Image, ImageDraw, ImageFont
    try:
        font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf', 12)
    except OSError:
        font = ImageFont.load_default()
    images = [Image.new('L',(240,400),0), Image.new('L',(800,80),0)]
    right, status = [ImageDraw.Draw(im) for im in images]
    right.fontmode = status.fontmode = '1'
    pages = max(1, (len(tracks)+3)//4)
    page %= pages
    header = 'SIGNALS %d  %d/%d' % (len(tracks),page+1,pages)
    if demo_title is not None:
        header = '%s %ds' % (demo_title, max(0, math.ceil(demo_remaining_s or 0)))
    right.text((4,2), header[:30], font=font, fill=2)
    for row,t in enumerate(tracks[page*4:(page+1)*4]):
        y = 23+row*32
        right.text((4,y), '%8.3fM %6.1fk' % (t.frequency_hz/1e6,t.bandwidth_hz/1e3), font=font, fill=1)
        right.text((4,y+14), '%s %s %.0f%% P%u' % (
            '>' if selected == t.key else ' ', displayed_label(t),
            100*t.confidence, t.power), font=font, fill=label_color(displayed_label(t)))
    right.text((20,160), 'IQ / SYMBOLS (200x200)', font=font, fill=2)
    right.rectangle((20,180,219,379), outline=1)
    right.line((120,181,120,378),fill=2)
    right.line((21,280,218,280),fill=2)
    values = symbols if symbols is not None else iq
    if values is not None:
        values = np.asarray(values, dtype=np.complex64).reshape(-1)
        values = values[np.isfinite(values)]
        if len(values):
            scale = max(float(np.percentile(np.abs(values),98)), 1e-12)
            xy = np.column_stack((120+95*values.real/scale,280-95*values.imag/scale))
            for x,y in xy[::max(1,len(xy)//1500)].astype(int):
                if 21 <= x <= 218 and 181 <= y <= 378:
                    right.point((int(x),int(y)),fill=3)
    status.text((8,3), '%s   LO %.3f MHz   %.3f MSPS' % (
        demo_mode or 'PL PFB16 / NCO / AMC', lo_hz/1e6,rate_hz/1e6),font=font,fill=3)
    status.text((8,25), 'FRAME %d  %.1f FPS  SOC %s' % (frame,fps,'%.1f C' % temperature_c if temperature_c is not None and math.isfinite(temperature_c) else 'N/A'),font=font,fill=2)
    selected_track = next((t for t in tracks if t.key == selected), None)
    latency = selected_track.display_latency_ms if selected_track else None
    status.text((8,47), 'FIRST LABEL %s  %s' % ('%.1f ms'%latency if latency is not None else 'PENDING',model_status),font=font,fill=1)
    if demo_title is not None:
        status.text((620,25), 'TX ON %.2fdB' % tx_atten_db if tx_active else 'TX OFF',
                    font=font, fill=2 if tx_active else 3)
        status.text((8,65), 'EVENT %s  | FM:white AM:yellow DIGITAL:cyan | score uncalibrated' %
                    demo_title, font=font, fill=2)
    return tuple(np.asarray(im,dtype=np.uint8) for im in images)
