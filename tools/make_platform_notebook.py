"""Create the actual-panel P5.1 notebook, executable on PYNQ Python 3.8."""

from pathlib import Path
import argparse
import nbformat as n


def generate(cpu_only=False):
    notebook = n.v4.new_notebook()
    cells = [n.v4.new_markdown_cell("""# P5.1 Z20 platform acceptance

Actual panel: ATK-MD0700 V2.4 / SSD1963 / J22 / 800x480. J7/J8=2.5V.
User has confirmed the original wiring and no direct TX/RX cable.
This notebook loads the vendor DMA loopback and then the verified J22 diagnostic bitstream.
It does not load the J26 RGB example, initialize AD9361, or enable TX.
Final screen observation remains a HUMAN acceptance item.
""")]
    sources = [r'''
import os,sys,json,time,platform,hashlib
from pathlib import Path
os.environ['XILINX_XRT']='/usr'
import numpy as np
import pynq
from pynq import Overlay,Bitstream,allocate
root=Path('/home/xilinx/sentinel')
sys.path.insert(0,str(root))
measure=root/'measurements'
measure.mkdir(exist_ok=True)
result={'kernel':platform.platform(),'python':sys.version,'pynq':pynq.__version__,
        'lcd_resolution':[800,480],'lcd_interface':'SSD1963 J22 8080'}
print(json.dumps(result,indent=2))
print(Path('/proc/meminfo').read_text().splitlines()[0])
print(Path('/proc/cpuinfo').read_text())
HARDWARE_VALIDATED=False  # Keep false until the interrupted platform test is diagnosed.
''', r'''
if not HARDWARE_VALIDATED:
    raise RuntimeError('Hardware execution disabled pending diagnosis; use CPU-only notebook')
dma_path=root/'overlay/vendor_dma_diag/dma_tutorial.bit'
overlay=Overlay(str(dma_path))
dma=overlay.axi_dma_0
input_buffer=allocate(shape=(1024,),dtype=np.uint32)
output_buffer=allocate(shape=(1024,),dtype=np.uint32)
try:
    input_buffer[:]=np.arange(1024,dtype=np.uint32)^np.uint32(0xabcd0000)
    output_buffer[:]=0
    dma.recvchannel.transfer(output_buffer)
    dma.sendchannel.transfer(input_buffer)
    deadline=time.monotonic()+5
    while not (dma.sendchannel.idle and dma.recvchannel.idle):
        if time.monotonic()>deadline:
            raise TimeoutError('DMA timeout: MM2S=%08x S2MM=%08x' %
                               (dma.mmio.read(0x04),dma.mmio.read(0x34)))
        time.sleep(.001)
    dma.sendchannel.wait()
    dma.recvchannel.wait()
    np.testing.assert_array_equal(output_buffer,input_buffer)
    result['dma_loopback']={'status':'PASS','words':1024,'bytes':4096}
    print(result['dma_loopback'])
finally:
    dma.sendchannel.stop()
    dma.recvchannel.stop()
    input_buffer.freebuffer()
    output_buffer.freebuffer()
''', r'''
from sim.golden.cfar import cfar,alpha_for_pfa
from PIL import Image,ImageDraw
rng=np.random.default_rng(372)
x=(rng.normal(size=2048)+1j*rng.normal(size=2048)).astype(np.complex64)
p=np.rint(rng.exponential(2**18,2048)).astype(np.uint32)
alpha=alpha_for_pfa(.001)
def bench(function,repeats):
    for _ in range(5): function()
    elapsed=[]
    for _ in range(repeats):
        start=time.perf_counter();function();elapsed.append(time.perf_counter()-start)
    return float(np.median(elapsed))
fft_s=bench(lambda:np.fft.fft(x),1000)
cfar_s=bench(lambda:cfar(p,alpha_q88=alpha),100)
points=[(i,int(80+60*np.sin(i*.07))) for i in range(720)]
waterfall=Image.fromarray(rng.integers(0,256,(200,720,3),dtype=np.uint8))
def draw_frame():
    frame=Image.new('RGB',(800,480));draw=ImageDraw.Draw(frame)
    draw.line(points,fill=(0,255,255));frame.paste(waterfall,(0,160))
    return frame
render_s=bench(draw_frame,100)
result['cpu_baseline']={'fft2048_median_s':fft_s,'fft_max_frames_per_s':1/fft_s,
                        'cfar2048_median_s':cfar_s,'pillow800x480_median_s':render_s}
print(json.dumps(result['cpu_baseline'],indent=2))
''', r'''
lcd_path=root/'overlay/lcd_j22_diag/lcd_j22_diag.bit'
expected='d163ee4f5e92159f4e4b05a562e8e4c96c6af7dbfc0649c00148fbc2336e072a'
assert hashlib.sha256(lcd_path.read_bytes()).hexdigest()==expected
Bitstream(str(lcd_path)).download()
time.sleep(2)
result['lcd_download']={'status':'download_returned','sha256':expected,
                        'visual_acceptance':'PENDING_HUMAN','touch':'not_connected'}
(measure/'p5_platform.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print('LCD diagnostic loaded. HUMAN: report eight vertical color bars and changing top region.')
print('Download success does not prove the physical screen image.')
''']
    if cpu_only:
        sources=[sources[0],sources[2]+"\n(measure/'p5_cpu_baseline.json').write_text(json.dumps(result,indent=2),encoding='utf-8')\n"]
        cells[0]=n.v4.new_markdown_cell('# P5.1 CPU-only platform baseline\n\nNo bitstream download, DMA, MMIO or RF operations. Actual display reference: 800x480.')
    cells.extend(n.v4.new_code_cell(source.strip()) for source in sources)
    cells.append(n.v4.new_markdown_cell("""## HUMAN screen observation

Report whether eight vertical color bars appear and whether the top region changes periodically.
The display ID is the confirmed module model, not a readback: this write-only test holds RD high.
No claim of touch or ID readback is made. Save a screen photo under measurements/p5_lcd.jpg for competition evidence.
"""))
    notebook.cells=cells
    notebook.metadata={'kernelspec':{'name':'python3','display_name':'Python 3','language':'python'}}
    name='test_00_cpu_baseline.ipynb' if cpu_only else 'test_00_platform.ipynb'
    destination=Path(__file__).resolve().parents[1]/'board/notebooks'/name
    n.write(notebook,destination)
    print(destination)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--cpu-only',action='store_true')
    generate(parser.parse_args().cpu_only)
