"""Bounded widgets; no MMIO, RF, file writes or hidden initialization."""
import math
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw

from .theme import BLACK, WHITE, YELLOW, CYAN, BODY, clean, font


@lru_cache(maxsize=4)
def metrics(size):
    face = font(size)
    # The selected font is monospaced. Measure once, rather than invoke the
    # old board FreeType renderer repeatedly for every truncated status line.
    advance = (face.getlength('M') if hasattr(face, 'getlength')
               else face.getsize('M'*32)[0]/32)
    ascent, descent = face.getmetrics()
    return advance, ascent+descent


@lru_cache(maxsize=384)
def glyph(character, size):
    advance, height = metrics(size)
    image = Image.new('1', (math.ceil(advance)+4, height), 0)
    pen = ImageDraw.Draw(image)
    pen.fontmode = '1'
    pen.text((0, 0), character, font=font(size), fill=1)
    return image


@lru_cache(maxsize=512)
def line_mask(value, size):
    advance, height = metrics(size)
    image = Image.new('1', (max(1, math.ceil(len(value)*advance)+4), height), 0)
    for index, character in enumerate(value):
        mask = glyph(character, size)
        image.paste(1, (round(index*advance), 0), mask)
    return image


def text(pen, xy, value, width, size=BODY, color=WHITE):
    value = clean(value)
    advance, _ = metrics(size)
    value = value[:max(0, int(width/advance))]
    if value:
        pen.bitmap(xy, line_mask(value, size), fill=color)
    return value


def bar(pen, box, score, color=CYAN):
    if not math.isfinite(score) or not 0 <= score <= 1:
        raise ValueError('Confidence must be finite and in 0..1')
    x0, y0, x1, y1 = box
    pen.rectangle(box, outline=color)
    end = x0+1+int((x1-x0-2)*score)
    if end > x0+1:
        pen.rectangle((x0+1, y0+1, end, y1-1), fill=color)


def badge(pen, box, value, color=CYAN, solid=True, size=BODY):
    pen.rectangle(box, fill=color if solid else BLACK, outline=color)
    text(pen, (box[0]+5, box[1]+2), value, box[2]-box[0]-9, size,
         BLACK if solid else color)


def constellation(pen, values, box=(20, 176, 219, 375)):
    x0, y0, x1, y1 = box
    cx, cy = (x0+x1)/2, (y0+y1)/2
    pen.rectangle(box, outline=WHITE)
    pen.line((int(cx), y0+1, int(cx), y1-1), fill=YELLOW)
    pen.line((x0+1, int(cy), x1-1, int(cy)), fill=YELLOW)
    if values is None:
        return
    values = np.asarray(values, dtype=np.complex64).reshape(-1)
    values = values[np.isfinite(values)]
    if not len(values):
        return
    values = values[::max(1, math.ceil(len(values)/1024))]
    scale = max(float(np.percentile(np.abs(values), 98)), 1e-12)
    radius = min(x1-x0, y1-y0)*.475
    for value in values:
        x, y = int(cx+radius*value.real/scale), int(cy-radius*value.imag/scale)
        if x0 < x < x1 and y0 < y < y1:
            pen.point((x, y), fill=CYAN)
