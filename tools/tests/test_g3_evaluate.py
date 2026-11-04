from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from g3_evaluate import evaluate


def test_latency_unverified_stays_fail_and_bit2_is_not_overflow():
    baseline=dict(telemetry=[dict(display_fps=40)])
    enabled=dict(status='completed',elapsed_total_s=421,RF_TX_requested=False,
        telemetry=[dict(display_fps=40,processing_status=4,tx_atten_mdb=[89750,89750])])
    execution=dict(status='PASS',worker_exit_code=0,
        stop_readback=dict(status='PASS',gpio_data=0,source_ctrl=0,audio_control=0))
    link=dict(network_cpu_single_core_pct=3,capture_error=None,thread_error=None,rejected=4,
        rejections=[{}]*4,spectrum_hz=9.99,spectrum_samples=4190,max_queue_bytes=7000,
        producer_drops=0,client_drops=0)
    validation=dict(reconnects=[dict(disconnected_s=30)]*10,
        responses=[dict(header=dict(type='error',request_seq=i)) for i in (5,6,7,8)]+
        [dict(header=dict(type='reply',snapshot='a',ok=True)),dict(header=dict(type='reply',status={},ok=True))],
        web_page_ok=True,sse_first_line=': ready',sse_message='data: {}')
    result=evaluate(baseline,enabled,execution,link,validation,[])
    assert result['status']=='FAIL' and result['functional_status']=='PASS'
    enabled['telemetry'][0]['processing_status']=5
    assert evaluate(baseline,enabled,execution,link,validation,[])['functional_status']=='FAIL'
