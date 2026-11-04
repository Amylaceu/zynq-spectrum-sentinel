"""Visible G5 demo observation; owns no hardware and sends no device commands."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'src/ps'), str(ROOT/'tools/host')]
from PySide6 import QtCore, QtWidgets
from sentinel_host.shell import Window, demo_page
from sentinel_host.session import Recorder
from sentinel_host.theme import configure
from sentinel.release_support import write_result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--address', required=True)
    parser.add_argument('--group', choices=('A', 'B'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seconds', type=int, default=720)
    args = parser.parse_args()
    app = QtWidgets.QApplication([])
    configure(app)
    window = Window()
    window.show()
    window.address.setText(args.address)
    window.recorder = Recorder(args.output/('live_'+args.group+'.zsr'), source='live')
    window.connect_board()
    start = time.monotonic()
    counts, pages, states = Counter(), [], []
    wire = (args.output/'wire.jsonl').open('x', encoding='utf-8')
    finished = [False]

    def packet(header, payload, received):
        counts[header['type']] += 1
        wire.write(json.dumps(dict(header=header, host_received_mono=received,
                                  payload_sha256=hashlib.sha256(payload).hexdigest()))+'\n')
        if header['type'] == 'demo':
            signature = (header.get('group'), header.get('segment'))
            if not pages or tuple(pages[-1]['signature']) != signature:
                row = dict(signature=list(signature), active_page=window.active_page,
                           expected_page=demo_page(header), elapsed_s=received-start,
                           title=header.get('title'), remaining_s=header.get('remaining_s'))
                pages.append(row)
                print('DEMO_PAGE', json.dumps(row), flush=True)

    def state(text):
        states.append(dict(elapsed_s=time.monotonic()-start, state=text))

    window.worker.packet.connect(packet)
    window.worker.state.connect(state)

    def finish(reason):
        if finished[0]:
            return
        finished[0] = True
        window.grab().save(str(args.output/'live.png'))
        window.stop_worker()
        if window.recorder:
            window.recorder.close()
            window.recorder = None
        wire.close()
        write_result(args.output/'gui_metrics.json', dict(
            source='live', group=args.group, elapsed_s=time.monotonic()-start,
            finish_reason=reason, counts=dict(counts), page_transitions=pages,
            page_mapping_pass=bool(pages) and all(p['active_page']==p['expected_page'] for p in pages),
            connection_states=states, errors=window.data_errors,
            pl_frames=window.twin.pl_count, ui_frames=window.twin.ui_count,
            pc_audio='DISABLED_DMA_LONG_TEST_FAILED', human_confirmation='PENDING'))
        print('G5_GUI_FINISHED', reason, flush=True)
        window.close()

    def check():
        if (args.output/'board_finished.json').exists():
            finish('BOARD_COMPLETED')
        elif time.monotonic()-start > args.seconds:
            finish('TIMEOUT')
    timer = QtCore.QTimer(window)
    timer.timeout.connect(check)
    timer.start(500)
    app.aboutToQuit.connect(lambda: finish('USER_CLOSED'))
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
