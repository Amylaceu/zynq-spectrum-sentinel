"""Pixel-exact RGB565 reference for the confirmed 800x480 SSD1963 display."""

import numpy as np

from .params import DISP_SPEC_H, DISP_W, DISP_WF_H, SCREEN_H, SCREEN_W


def palette_rgb565():
    """256-entry blue->cyan->yellow->red palette, using integer interpolation."""
    anchors = np.array([[0, 0, 0], [0, 0, 31], [0, 63, 31], [31, 63, 0], [31, 0, 0]])
    colors = []
    for i in range(256):
        position = i * 4
        segment = min(position // 255, 3)
        fraction = position - segment * 255
        r, g, b = (anchors[segment] * (255 - fraction) + anchors[segment + 1] * fraction + 127) // 255
        colors.append((int(r) << 11) | (int(g) << 5) | int(b))
    return np.array(colors, dtype=np.uint16)


PALETTE = palette_rgb565()


def _columns(values, width):
    a = np.asarray(values)
    if a.ndim != 1 or len(a) < width or not np.issubdtype(a.dtype, np.integer):
        raise ValueError("Expected integer Q8.8 trace with at least display-width bins")
    if len(a) == width:
        return a.astype(np.int64)
    # Peak-preserving bin-to-column mapping; deterministic integer boundaries.
    edges = np.arange(width + 1) * len(a) // width
    return np.array([np.max(a[edges[i]:edges[i + 1]]) for i in range(width)], dtype=np.int64)


def _trace(canvas, values, color, width, height, low, high, dashed=False):
    v = _columns(values, width)
    y = np.clip((high - v) * (height - 1) // (high - low), 0, height - 1)
    previous = y[0]
    for x, current in enumerate(y):
        if not dashed or x % 4 < 2:
            canvas[min(previous, current):max(previous, current) + 1, x] = color
        previous = current


def render_frame(spec_db_q88, peak_db_q88, thr_db_q88, targets,
                 wf_rows, dpx_hist, ui_rgb565, cfg=None):
    """Return [480,800] uint16; UI color key F81F exposes the PL layer.

    Layer order: density -> spectrum -> peak -> threshold -> targets -> UI.
    Rows in wf_rows are palette indices in ring storage; cfg.wf_head is top row.
    DPX is [128,360] counts, scaled by nearest-neighbour into the spectrum area.
    """
    cfg = {} if cfg is None else cfg
    if cfg.get('profile') == 'x5_frozen':
        return render_x5(spec_db_q88, thr_db_q88, wf_rows, ui_rgb565, cfg)
    width, height, wf_height = DISP_W, DISP_SPEC_H, DISP_WF_H
    low, high = int(cfg.get("db_min_q88", -100 * 256)), int(cfg.get("db_max_q88", 0))
    if high <= low:
        raise ValueError("Invalid display dB limits")
    out = np.zeros((SCREEN_H, SCREEN_W), dtype=np.uint16)
    if dpx_hist is not None:
        density = np.asarray(dpx_hist)
        if density.shape != (128, 360) or not np.issubdtype(density.dtype, np.integer):
            raise ValueError("DPX must be integer [128,360]")
        if np.any(density < 0) or np.any(density > 255):
            raise ValueError("DPX counts must fit uint8")
        scaled = density[(np.arange(height) * 128 // height)[:, None], np.arange(width) * 360 // width]
        out[:height, :width] = PALETTE[scaled]
    if wf_rows is not None:
        wf = np.asarray(wf_rows)
        if wf.ndim != 2 or wf.shape[1] != width or wf.shape[0] < wf_height:
            raise ValueError("Waterfall ring too small or wrong width")
        if not np.issubdtype(wf.dtype, np.integer) or np.any(wf < 0) or np.any(wf > 255):
            raise ValueError("Waterfall palette indices must fit uint8")
        rows = (int(cfg.get("wf_head", 0)) + np.arange(wf_height)) % len(wf)
        out[height:height + wf_height, :width] = PALETTE[wf[rows]]
    for values, color, dashed in ((spec_db_q88, 0x07FF, False), (peak_db_q88, 0xFFE0, False),
                                  (thr_db_q88, 0xF800, True)):
        if values is not None:
            _trace(out, values, color, width, height, low, high, dashed)
    if targets is not None:
        bins = int(cfg.get("nfft", len(spec_db_q88) if spec_db_q88 is not None else 2048))
        for target in targets:
            start, stop = int(target["start"]), int(target["stop"])
            if not 0 <= start <= stop < bins:
                raise ValueError("Target outside spectrum")
            left, right = start * width // bins, min(width - 1, stop * width // bins)
            out[[0, height - 1], left:right + 1] = 0x07E0
            out[:height, [left, right]] = 0x07E0
    if ui_rgb565 is not None:
        ui = np.asarray(ui_rgb565)
        if ui.shape != out.shape or ui.dtype != np.uint16:
            raise ValueError("UI must be uint16 [480,800]")
        opaque = ui != 0xF81F
        out[opaque] = ui[opaque]
    return out


def x5_levels(spec):
    """Integer mapping of lcd/lcd_trace_pixel.v, including the zero sentinel."""
    a = np.asarray(spec, dtype=np.int32)
    delta = 23119-a
    y = np.where((a == -32768) | (delta >= 25600), 159,
                 np.where(delta <= 0, 0, delta//160))
    level = np.where((a == -32768) | (delta >= 25600), 0,
                     np.where(delta <= 0, 255, 255-delta//100))
    return y.astype(np.int64), level.astype(np.uint8)


def x5_palette():
    v = np.arange(256, dtype=np.uint16)
    seg, n = v >> 6, v & 63
    return np.select([seg == 0, seg == 1, seg == 2],
        [n >> 1, (n << 5) | 31, ((n >> 1) << 11) | (63 << 5) | (31-(n >> 1))],
        default=(31 << 11) | ((63-n) << 5)).astype(np.uint16)


def render_x5(spec, threshold, waterfall, ui, cfg):
    """Reference for the frozen 560x160 + 560x240 LCD raster.

    This is a software reference addition only. No RTL/build artifact changes.
    A missing threshold is omitted, never invented from a spectrum snapshot.
    """
    output = np.zeros((480, 800), dtype=np.uint16)
    x, y = np.arange(560), np.arange(160)
    output[:160, :560] = np.where((y[:, None] % 32 == 0) | (x % 80 == 0), 0x18c3, 0)
    if spec is not None:
        data = np.asarray(spec)
        if data.shape != (560,) or data.dtype.kind not in 'iu':
            raise ValueError('Frozen LCD spectrum requires 560 Q8.8 values')
        current, _ = x5_levels(data)
        previous = np.r_[current[0], current[:-1]]
        mask = (y[:, None] >= np.minimum(current, previous)) & (y[:, None] <= np.maximum(current, previous))
        output[:160, :560][mask] = 0x07e0
    if threshold is not None:
        if np.asarray(threshold).shape != (560,):
            raise ValueError('Frozen LCD threshold requires 560 values')
        threshold_y, _ = x5_levels(threshold)
        output[threshold_y[x % 8 < 4], x[x % 8 < 4]] = 0xf800
    if waterfall is not None:
        rows = np.asarray(waterfall)
        if rows.shape != (240, 560) or rows.dtype.kind not in 'iu' or np.any(rows < 0) or np.any(rows > 255):
            raise ValueError('Frozen LCD waterfall requires 240x560 palette indices')
        output[160:400, :560] = x5_palette()[rows]
    if ui is not None:
        layer = np.asarray(ui)
        if layer.shape != output.shape or layer.dtype != np.uint16:
            raise ValueError('UI must be uint16 [480,800]')
        opaque = layer != 0xf81f
        output[opaque] = layer[opaque]
    return output
