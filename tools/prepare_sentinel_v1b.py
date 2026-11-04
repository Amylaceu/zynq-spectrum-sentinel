"""Derive a separate v1b project without modifying the accepted v1 overlay."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text, old, new):
    if text.count(old)!=1:
        raise ValueError('Unexpected overlay anchor: '+old)
    return text.replace(old,new,1)


def main():
    source = ROOT/'src/hw/sentinel_v1'
    destination = ROOT/'src/hw/sentinel_v1b'
    if destination.exists():
        raise FileExistsError('Preserve existing v1b project')
    outputs = {}
    for path in source.iterdir():
        if path.is_file():
            outputs[path.name] = path.read_bytes()
    for name in ('system_project.tcl','Makefile'):
        outputs[name] = outputs[name].decode('utf-8').replace('sentinel_v1','sentinel_v1b').encode('utf-8')
    text = outputs['system_bd.tcl'].decode('utf-8')
    text = replace_once(text, 'set extra_repositories [list',
        'set extra_repositories [list [file normalize $::env(REPO)/build/work/x1_packaged_ip]')
    outputs['system_bd.tcl'] = text.encode('utf-8')
    text = outputs['sentinel_bd.tcl'].decode('utf-8')
    text = replace_once(text, 'ad_ip_instance cfar_core cfar_core_0', 'ad_ip_instance cfar_core_x1 cfar_core_0')
    text = replace_once(text, 'logs/N4_bd_addresses.txt', 'logs/X1_v1b_bd_addresses.txt')
    text = text.replace('# Sentinel v1:', '# Sentinel v1b:')
    outputs['sentinel_bd.tcl'] = text.encode('utf-8')
    destination.mkdir()
    for name,data in outputs.items():
        (destination/name).write_bytes(data)
    record = {'scope':'PC-only derived project; no build/board acceptance yet',
        'parent':'src/hw/sentinel_v1','output':'src/hw/sentinel_v1b',
        'source_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir() if p.is_file()},
        'output_sha256':{name:hashlib.sha256(data).hexdigest() for name,data in outputs.items()}}
    out = ROOT/'docs/x1_v1b_derivation.json'
    if out.exists():
        raise FileExistsError('Preserve derivation evidence')
    out.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    out.with_name(out.name+'.sha256').write_text(hashlib.sha256(out.read_bytes()).hexdigest()+'  '+out.name+'\n',encoding='ascii')
    print('SENTINEL_V1B_PROJECT_PREPARED',len(outputs))


if __name__=='__main__':
    main()
