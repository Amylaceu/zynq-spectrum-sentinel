"""Palette indices are the hardware contract; RGB is for offline previews."""
from functools import lru_cache
from pathlib import Path
import sys

from PIL import ImageFont

BLACK, WHITE, YELLOW, CYAN = range(4)
RGB = ((0, 0, 0), (255, 255, 255), (255, 255, 0), (0, 255, 255))
TITLE, BODY, SMALL = 20, 14, 12


@lru_cache(maxsize=4)
def font(size):
    candidates = (
        Path('/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf'),
        Path(sys.prefix)/'Lib/site-packages/matplotlib/mpl-data/fonts/ttf/DejaVuSansMono-Bold.ttf',
    )
    for path in candidates:
        if path.is_file():
            return ImageFont.truetype(str(path), size)
    raise RuntimeError('DejaVuSansMono-Bold.ttf required; provide the existing board font or PC matplotlib font')


def clean(value):
    """ASCII-only labels avoid dependence on CJK packages on the board."""
    return ''.join(c if 32 <= ord(c) < 127 else '?' for c in str(value))


def modulation_style(label):
    if label == 'FM':
        return WHITE, 'A'
    if label.startswith('AM') or label == 'OOK':
        return YELLOW, 'A' if label.startswith('AM') else 'D'
    return CYAN, 'D' if label not in ('?', 'PENDING') else '?'
