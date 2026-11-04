"""Build a relocatable Windows one-folder client; no Vivado or board access."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-name', default='SentinelHost')
    parser.add_argument('--session', type=Path, help=argparse.SUPPRESS)
    args=parser.parse_args()
    if not args.output_name or not all(c.isalnum() or c in '-_' for c in args.output_name):
        parser.error('Output name must be a simple directory name')
    target=ROOT/'dist'/args.output_name
    if target.exists():
        raise FileExistsError('Preserve previous distribution; move it before rebuilding')
    stage=ROOT/'build/host_pack'/args.output_name
    if stage.exists():
        raise FileExistsError('Preserve previous staging directory')
    acceptance=ROOT/'board/overlay/sentinel_v2_100m/acceptance.json'
    if hashlib.sha256(acceptance.read_bytes()).hexdigest()!=Path(str(acceptance)+'.sha256').read_text().split()[0]:
        raise ValueError('Frozen build evidence checksum differs')
    if args.session:
        parser.error('现场版不打包历史会话；请移除 --session')
    command=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onedir','--windowed',
        '--name','SentinelHost','--paths',str(ROOT/'tools/host'),'--paths',str(ROOT/'tools'),'--paths',str(ROOT/'src/ps'),'--paths',str(ROOT),
        '--distpath',str(stage),'--workpath',str(stage/'work'),
        '--specpath',str(stage/'spec'),
        '--add-data',str(acceptance)+os.pathsep+'build_evidence',
        '--add-data',str(acceptance)+'.sha256'+os.pathsep+'build_evidence',
        '--add-data',str(ROOT/'tools/host/scenes.yaml')+os.pathsep+'.',
        '--hidden-import','pyqtgraph.exporters','--collect-data','pyqtgraph']
    for name in ('j_ssid_decode', 'current_fm_audio', 'wifi.beacon', 'wifi.dsss', 'scipy.io', 'scipy.signal'):
        command.extend(['--hidden-import', name])
    for name in ('PyQt5','PyQt6','PySide2','tkinter','matplotlib','pandas','IPython','pytest','torch','cv2'):
        command.extend(['--exclude-module',name])
    command.append(str(ROOT/'tools/host/product.py'))
    environment=os.environ.copy()
    if sys.platform == 'win32':
        import ctypes
        buffer=ctypes.create_unicode_buffer(32768)
        ctypes.windll.kernel32.GetSystemDirectoryW(buffer,len(buffer))
        system=Path(buffer.value)
        # Other document tools may put an incompatible ICU DLL on PATH.
        # Qt imports the Windows ICU ABI; let Windows supply its system DLL.
        environment['SystemRoot']=str(system.parent)
        environment['PATH']=os.pathsep.join((str(system),str(system.parent),str(Path(sys.executable).parent)))
    subprocess.run(command,check=True,cwd=ROOT,env=environment)
    shutil.move(str(stage/'SentinelHost'),str(target))
    shutil.copytree(ROOT/'tools/wifi', target/'tools/wifi', ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copy2(ROOT/'tools/j_ssid_decode.py', target/'tools/j_ssid_decode.py')
    (target/'wifi_decoder.json').write_text(json.dumps(dict(matlab_root=''), indent=2)+'\n', encoding='utf-8')
    (target/'MATLAB_CHECK_zh.txt').write_text(
        'Wi-Fi名称来自本轮AD9361采集与电脑解码。\n'
        '在wifi_decoder.json中填matlab_root，例如 C:/Program Files/MATLAB/R2025b；也可设置MATLAB_ROOT环境变量。\n'
        '在MATLAB中执行：ver; which wlanLLTFDemodulate; license("test","WLAN_Toolbox")\n'
        '应看到WLAN Toolbox、函数路径及许可返回1；否则保留采集文件并报告解码依赖未就绪。\n'
        'MATLAB及WLAN Toolbox需在演示电脑另行安装并持有可用许可，未包含在本程序中。\n', encoding='utf-8')
    for name in ('README.md','alarms.yaml'):
        shutil.copy2(ROOT/'tools/host'/name,target/name)
    (target/'QUICKSTART_zh.txt').write_text(
        '频谱监测终端现场版\n启动：SentinelHost.exe --connect 192.168.2.99\n'
        'T：对照LCD并返回；F11：全屏；SIG/TGT/STAT：同步控制LCD。\n'
        '接收结果来自本轮开发板。十类推理明确使用已有实测输入；录音仅允许本轮验证通过的文件。\n'
        '未接入功能显示待接入；连接仅建立通信，页内按键才运行硬件。\n'
        '关闭窗口前等待开发板待机确认。识别为实验模型输出。\n', encoding='utf-8')
    manifest={str(p.relative_to(target)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in target.rglob('*') if p.is_file()}
    path=target/'files_sha256.json'
    path.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    Path(str(path)+'.sha256').write_text(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+path.name+'\n')
    print('HOST_BUILD_COMPLETE',len(manifest),'files',flush=True)


if __name__=='__main__':
    main()
