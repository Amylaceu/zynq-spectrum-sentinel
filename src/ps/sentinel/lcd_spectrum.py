"""CPU diagnostic spectrum and UI; explicitly uses gapped antenna snapshots."""
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from .lcd_framebuffer import WIDTH, HEIGHT, rgb332


def spectrum(words, sample_rate_hz, lo_hz, nfft=2048):
    words = np.asarray(words)
    if words.ndim != 2 or words.shape[1] != 4 or len(words) % nfft:
        raise ValueError('Need complete I1,Q1,I2,Q2 FFT blocks')
    if sample_rate_hz <= 0 or nfft < 16:
        raise ValueError('Invalid sample rate or FFT length')
    z = words[:, 0].astype(float)+1j*words[:, 1].astype(float)
    w = np.hanning(nfft)
    power = np.mean(abs(np.fft.fft(z.reshape(-1, nfft)*w, axis=1))**2, axis=0)
    power /= nfft*np.sum(w*w)*2048**2
    frequency = lo_hz+np.fft.fftshift(np.fft.fftfreq(nfft, 1./sample_rate_hz))
    return frequency, 10*np.log10(np.maximum(np.fft.fftshift(power), 1e-14))


class SpectrumScreen:
    def __init__(self, font_path='/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf'):
        try:
            self.font = ImageFont.truetype(font_path, 10)
            self.title_font = ImageFont.truetype(font_path, 14)
        except OSError:
            self.font = self.title_font = ImageFont.load_default()
        self.waterfall = np.zeros((55, 360, 3), dtype=np.uint8)
        self.edges = np.linspace(88e6, 108e6, 361)
        self.palette = np.array([(int(255*min(1,max(0,(i-128)/80))),
                                  int(255*min(1,max(0,(i-40)/150))),
                                  int(255*min(1,i/80))) for i in range(256)], dtype=np.uint8)

    def draw(self, frequency, db, frame, gain_db=0, state='LIVE RX', fps=0):
        columns = np.empty(360)
        for i in range(360):
            mask = (frequency >= self.edges[i]) & (frequency < self.edges[i+1])
            columns[i] = np.max(db[mask]) if np.any(mask) else -100
        level = np.clip((columns+100)/85, 0, 1)
        self.waterfall[1:] = self.waterfall[:-1].copy()
        self.waterfall[0] = self.palette[np.rint(level*255).astype(np.uint8)]
        im = Image.new('RGB', (WIDTH, HEIGHT), (8, 12, 23))
        d = ImageDraw.Draw(im)
        # Binary glyph coverage avoids grey antialias fringes after RGB332/2x display.
        d.fontmode = '1'
        d.rectangle((0, 0, 399, 21), fill=(0, 48, 72))
        d.text((8, 1), 'ZYNQ SPECTRUM', fill='white', font=self.title_font)
        d.ellipse((379, 6, 387, 14), fill=(0, 255, 80) if frame % 2 else (0, 110, 50))
        d.text((8, 24), 'RX1 88-108 MHz  30.72 MSPS  TX OFF', fill=(0, 255, 255), font=self.font)
        for db_tick in (-100, -80, -60, -40, -20):
            y = int(143-(db_tick+100)*85/85)
            d.line((30, y, 389, y), fill=(40, 49, 62))
            d.text((0, y-5), str(db_tick), fill=(224, 224, 255), font=self.font)
        for mhz in (88, 93, 98, 103, 108):
            x = int(30+(mhz-88)*359/20)
            d.line((x, 47, x, 143), fill=(30, 40, 55))
            d.text((min(371, max(30, x-6)), 145), str(mhz), fill=(224, 224, 255), font=self.font)
        y = np.rint(143-level*85).astype(int)
        d.line([(i+30, int(v)) for i, v in enumerate(y)], fill=(50, 255, 100), width=1)
        d.text((31, 36), 'dBFS/bin  CPU FFT / RX snapshots', fill=(224, 224, 255), font=self.font)
        im.paste(Image.fromarray(self.waterfall), (30, 159))
        d.text((8, 215), '%s  GAIN %ddB  FRAME %d' % (state, gain_db, frame), fill='white', font=self.font)
        d.text((8, 228), 'ID 0A | %.1f fps | classifier paused' % fps, fill=(224, 224, 255), font=self.font)
        return im, rgb332(np.asarray(im))
