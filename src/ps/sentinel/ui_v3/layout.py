"""Three pages rendered solely into right 240x400 and bottom 800x80 banks.

Power is deliberately labeled raw unless a calibrated measurement is supplied.
Scores remain uncalibrated; SENT labels never replace classifier predictions.
"""
import math
import time

import numpy as np
from PIL import Image, ImageDraw

from ..lcd_x5 import displayed_label
from .theme import BLACK, WHITE, YELLOW, CYAN, TITLE, BODY, SMALL, modulation_style
from .widgets import text, bar, badge, constellation

PAGES = ('SIG', 'TGT', 'STAT')


def hit_map(tracks, view='SIG', page=0):
    """Rectangles use half-open LCD physical coordinates, never PC scaling."""
    result = [dict(rect=[560+i*80, 0, 640+i*80, 29], action='tab:'+name)
              for i, name in enumerate(PAGES)]
    if view == 'SIG':
        page %= max(1, math.ceil(len(tracks)/4))
        result.extend(dict(rect=[563, 59+i*78, 797, 133+i*78], action='card:'+str(t.key))
                      for i, t in enumerate(tracks[page*4:(page+1)*4]))
    result.extend(dict(rect=[480+i*80, 450, 558+i*80, 480], action='soft:'+name)
                  for i, name in enumerate(('LISTEN', 'SNAP', 'REC', 'NEXT')))
    result.append(dict(rect=[0, 0, 560, 400], action='spectrum'))
    return result


def resolve_hit(x, y, tracks, view='SIG', page=0):
    for item in hit_map(tracks, view, page):
        left, top, right, bottom = item['rect']
        if left <= x < right and top <= y < bottom:
            return item
    raise ValueError('No control at this LCD coordinate')


def draw_ui_v3(tracks, selected=None, iq=None, symbols=None, lo_hz=0,
               rate_hz=3840000, frame=0, fps=0, temperature_c=None, page=0,
               model_status='MODEL EXPERIMENTAL', demo_title=None,
               demo_remaining_s=None, demo_mode=None, tx_active=False,
               tx_atten_db=None, *, view=None, now=None, uptime_s=0,
               pc_connected=False, events=(), histogram=None, sent_label=None,
               accuracy=None, selftest_checks=None, ui_state=None):
    if type(tx_active) is not bool or (tx_active and (tx_atten_db is None or
            not math.isfinite(tx_atten_db) or not 40 <= tx_atten_db <= 89.75)):
        raise ValueError('Active OTA display requires checked attenuation 40..89.75dB')
    now = time.monotonic() if now is None else now
    view = PAGES[int(now//6) % 3] if view is None else view
    if view not in PAGES:
        raise ValueError('Unknown UI page')
    images = [Image.new('L', (240, 400), BLACK), Image.new('L', (800, 80), BLACK)]
    right, status = [ImageDraw.Draw(im) for im in images]
    right.fontmode = status.fontmode = '1'
    for index, title in enumerate(PAGES):
        badge(right, (index*80, 0, index*80+78, 28), title,
              CYAN if title == view else WHITE, title == view, TITLE)
    subtitle = demo_title or {'SIG': 'SIGNAL LIST', 'TGT': 'SELECTED TARGET', 'STAT': 'LABEL STATISTICS'}[view]
    text(right, (7, 33), subtitle, 226, BODY, YELLOW)
    if demo_remaining_s is not None:
        # Countdown stays separate from a potentially long segment title.
        right.rectangle((182, 32, 239, 53), fill=BLACK)
        text(right, (186, 33), '%3ds' % max(0, math.ceil(demo_remaining_s)), 52, BODY, CYAN)

    selected_track = next((t for t in tracks if t.key == selected), None)
    if selected_track is None and tracks:
        selected_track = tracks[0]
    if selftest_checks is not None:
        for row, (name, passed) in enumerate(selftest_checks[:4]):
            label = 'OK' if passed is True else 'FAIL' if passed is False else 'WAIT'
            text(right, (8, 75+row*57), '['+label+']', 72, TITLE,
                 CYAN if passed is True else YELLOW)
            text(right, (89, 78+row*57), name, 143, BODY)
        text(right, (8, 340), 'RX CHECK / TX MUTED', 224, BODY, YELLOW)
    elif view == 'SIG':
        count = max(1, math.ceil(len(tracks)/4))
        page %= count
        for row, track in enumerate(tracks[page*4:(page+1)*4]):
            y = 59+row*78
            label = displayed_label(track)
            color, family = modulation_style(label)
            right.rectangle((3, y, 236, y+73), outline=CYAN if selected == track.key else WHITE)
            text(right, (9, y+3), '%.3fM' % (track.frequency_hz/1e6), 115, TITLE)
            text(right, (128, y+7), family+' '+label, 103, BODY, color)
            text(right, (9, y+30), 'BW %.0fk  P %s' % (track.bandwidth_hz/1e3, track.power),
                 222, SMALL)
            bar(right, (9, y+52, 112, y+63), track.confidence, color)
            text(right, (120, y+47), '%.0f%%' % (track.confidence*100), 47, BODY, color)
            if 0 <= now-track.first_seen < 3:
                badge(right, (177, y+46, 229, y+66), 'NEW', YELLOW, True, SMALL)
        if not tracks:
            text(right, (16, 120), 'SCANNING FOR TARGETS', 215, BODY, CYAN)
        text(right, (8, 378), 'P:raw  %d signals  %d/%d' % (len(tracks), page+1, count), 224, SMALL)
    elif view == 'TGT':
        if selected_track is not None:
            track = selected_track
            label = displayed_label(track)
            color, family = modulation_style(label)
            text(right, (8, 59), '%.3f MHz' % (track.frequency_hz/1e6), 224, TITLE)
            text(right, (8, 87), label, 171, 24, color)
            badge(right, (193, 88, 230, 113), family, color, True, TITLE)
            bar(right, (9, 124, 168, 135), track.confidence, color)
            text(right, (174, 119), '%.0f%%' % (track.confidence*100), 59, BODY, color)
            votes = ' '.join(name[:3] for name, _ in track.votes)
            text(right, (8, 146), 'VOTES '+(votes or 'PENDING'), 224, SMALL)
        else:
            text(right, (8, 66), 'NO TARGET SELECTED', 224, BODY, YELLOW)
        constellation(right, symbols if symbols is not None else iq)
        text(right, (8, 380), 'IQ / SYMBOLS | SCORE:RAW', 224, SMALL, YELLOW)
    else:
        counts = histogram
        if counts is None:
            counts = {}
            for track in tracks:
                label = displayed_label(track)
                counts[label] = counts.get(label, 0)+1
        text(right, (8, 59), 'VISIBLE LABELS' if histogram is None else 'CLASSIFICATION COUNTS', 224, SMALL)
        peak = max([1]+list(counts.values()))
        for row, (label, count) in enumerate(sorted(counts.items(), key=lambda x: -x[1])[:8]):
            y = 85+row*27
            color, _ = modulation_style(label)
            text(right, (8, y-3), label, 78, SMALL, color)
            bar(right, (91, y, 194, y+11), count/peak, color)
            text(right, (200, y-3), str(count), 34, SMALL)
        if sent_label is not None:
            badge(right, (6, 309, 233, 336), 'SENT '+sent_label, YELLOW, True, BODY)
            text(right, (8, 342), 'RX '+(displayed_label(selected_track) if selected_track else '?'), 224, BODY, CYAN)
        if accuracy is not None:
            correct, total = accuracy
            text(right, (8, 367), 'ACC %d/%d %s' % (correct, total,
                '%.1f%%' % (100*correct/total) if total else 'N/A'), 224, BODY)
        else:
            text(right, (8, 377), 'COUNTS ARE NOT ACCURACY', 224, SMALL, YELLOW)

    mode = demo_mode or 'MONITOR'
    badge(status, (4, 3, 116, 28), mode, YELLOW if tx_active else CYAN, True, BODY)
    text(status, (124, 6), 'LO %.3fM' % (lo_hz/1e6), 128, BODY)
    text(status, (259, 6), '%.2fMSPS' % (rate_hz/1e6), 94, BODY)
    text(status, (360, 6), '%.1ffps' % fps, 81, BODY)
    text(status, (448, 6), '%.1fC' % temperature_c if temperature_c is not None
         and math.isfinite(temperature_c) else 'TEMP N/A', 76, BODY)
    badge(status, (532, 3, 692, 28), 'TX ON %.1fdB' % tx_atten_db if tx_active else 'TX OFF',
          YELLOW if tx_active else WHITE, tx_active and int(now*2) % 2 == 0, BODY)
    text(status, (704, 6), 'PC:ON' if pc_connected else 'PC:OFF', 89, BODY,
         CYAN if pc_connected else WHITE)
    text(status, (8, 32), 'FRAME %d' % frame, 222, SMALL, YELLOW)
    seconds = max(0, int(uptime_s))
    text(status, (239, 32), 'UP %02d:%02d:%02d' % (seconds//3600, seconds//60 % 60, seconds % 60), 166, SMALL)
    text(status, (420, 32), model_status, 372, SMALL)
    for row, event in enumerate(list(events)[:3]):
        value = (event if isinstance(event, str) else
                 '%s %s %s' % (event.timestamp_utc, event.kind, event.text))
        # Three events fit without touching PL: two short entries + one full row.
        xy, width = ((8, 48), 462) if row == 0 else ((8, 64), 462) if row == 1 else ((408, 32), 384)
        if row == 2:
            continue  # model status stays legible; two events leave room for soft keys
        text(status, xy, value, width, SMALL, CYAN if row == 0 else WHITE)
    state = ui_state or {}
    for i, name in enumerate(('LISTEN', 'SNAP', 'REC', 'NEXT')):
        pressed = state.get('action') == 'soft:'+name and state.get('pressed', False)
        active = (name == 'LISTEN' and state.get('listening')) or (name == 'REC' and state.get('recording'))
        badge(status, (480+i*80, 50, 557+i*80, 78), name,
              YELLOW if active else CYAN, bool(pressed or active), SMALL)
    if state.get('hint'):
        status.rectangle((0, 48, 475, 79), fill=BLACK)
        text(status, (8, 54), state['hint'], 464, SMALL, YELLOW)
    rect = state.get('rect')
    if rect:
        left, top, end, bottom = rect
        if left >= 560 and bottom <= 400:
            right.rectangle((left-560, top, end-561, bottom-1), outline=YELLOW)
        elif top >= 400:
            status.rectangle((left, top-400, end-1, bottom-401), outline=YELLOW)
    return tuple(np.asarray(image, dtype=np.uint8) for image in images)
