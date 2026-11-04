"""Run real GUI receive/record stability against the frozen G3 release."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import socket
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'src/ps'),str(ROOT/'tools/host')]
from g3_validate import launch,completed
from fetch_release_evidence import fetch
from run_x1_board import write_evidence
from x2_transport import Transport,PYTHON,REMOTE
from sentinel_host.session import Replay
from sentinel_host.model import Model


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sudo-stdin',action='store_true',required=True)
    p.add_argument('--seconds',type=int,default=1800)
    p.add_argument('--name',choices=('g4_board_r1','g4_board_r2','g4_board_r3'),default='g4_board_r1')
    args=p.parse_args()
    output=ROOT/'board/measurements'/args.name
    output.mkdir(exist_ok=False)
    t=Transport(password=sys.stdin.readline().rstrip('\r\n'))
    root=REMOTE+'/release/v2'
    result=dict(status='STARTED',configuration='A',RF_TX_requested=False,host_started_utc=datetime.now(timezone.utc).isoformat())
    try:
        launch(t,args.name,args.seconds+75,True)
        address=t.target.rsplit('@',1)[-1]
        deadline=time.monotonic()+90
        while True:
            try:
                with socket.create_connection((address,9000),timeout=2):
                    break
            except OSError:
                if time.monotonic()>deadline:
                    raise
                time.sleep(1)
        command=[sys.executable,str(ROOT/'tools/host/run_host.py'),'--connect',address,
            '--record',str(output/'live_A.zsr'),'--auto-exit',str(args.seconds),
            '--evidence',str(output/'gui_metrics.json'),'--screenshot-out',str(output/'live_A.png')]
        print('GUI_START',json.dumps(command),flush=True)
        subprocess.run(command,check=True,timeout=args.seconds+120,cwd=ROOT)
        print('GUI_COMPLETE',flush=True)
        print(t.ssh(['sh',root+'/scripts/sentinel.sh','stop'],privileged=True),flush=True)
        tag=completed(t,args.name,90)
        fetch(tag,'monitor',output/'board_raw')
        state=Model()
        for elapsed,header,payload in Replay(output/'live_A.zsr'):
            state.apply(header,payload,observed=elapsed)
        metrics=json.loads((output/'gui_metrics.json').read_text())
        result.update(status='MEASURED_REQUIRES_EVALUATION',tag=tag,
            targets_replay_equal=state.targets==metrics['final_targets'],
            events_replay_equal=list(state.events)==metrics['final_events'])
        result['postflight']=json.loads(t.ssh([PYTHON,'-I',root+'/scripts/y3_postflight.py',
            '--bit',root+'/overlay/sentinel_v2_100m/sentinel_v2_100m.bit'],privileged=True))
    except BaseException as error:
        result.update(status='FAIL',error=repr(error))
        try:
            result['stop']=t.ssh(['sh',root+'/scripts/sentinel.sh','stop'],privileged=True)
        except BaseException as stop_error:
            result['stop_error']=repr(stop_error)
        raise
    finally:
        write_evidence(output/'validation.json',result)
    print('G4_BOARD_MEASUREMENT_COMPLETE',flush=True)


if __name__=='__main__':
    main()
