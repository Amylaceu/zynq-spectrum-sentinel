"""Preserve the verified SSD1963 sequence; create a shared ROM and bus fixture."""
from pathlib import Path
import re,json,hashlib

root=Path(__file__).resolve().parents[1]
source=root/'src/hw/fmcomms2_z20_lcd_live/lcd_j22_framebuffer.v'
words=[(int(i),int(word,16)) for i,word in re.findall(r'(\d+): rom = 32\'h([0-9a-fA-F]+);',source.read_text())]
assert [i for i,_ in words]==list(range(72))
out=root/'data/reference/lcd';out.mkdir(exist_ok=True,parents=True)
header='// Extracted from the already board-verified initialization ROM.\nfunction [31:0] lcd_init_rom;\ninput [7:0] address;\nbegin\ncase(address)\n'
header+=''.join(f"8'd{i}: lcd_init_rom=32'h{word:08x};\n" for i,word in words)
header+="default:lcd_init_rom=0;\nendcase\nend\nendfunction\n"
(root/'src/rtl/common/lcd_init_rom.vh').write_bytes(header.encode())
bus=[((w>>30)&1)<<16 | (w&65535) for _,w in words if (w>>30)!=2]
(out/'n4_lcd_init_bus.hex').write_bytes(''.join(f'{word:05x}\n' for word in bus).encode())
(out/'n4_init_manifest.json').write_bytes((json.dumps(dict(source=source.relative_to(root).as_posix(),
    source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),instructions=len(words),bus_words=len(bus)),indent=2)+'\n').encode())
print('LCD_INIT_EXPORT_PASS',len(words),len(bus))
def window(x0,x1,y0,y1):
    return [0x2a,0x10000|(x0>>8),0x10000|(x0&255),0x10000|(x1>>8),0x10000|(x1&255),
            0x2b,0x10000|(y0>>8),0x10000|(y0&255),0x10000|(y1>>8),0x10000|(y1&255),0x2c]
region=window(1,3,2,3)+[0x10000|0xf000+i for i in range(6)]
region+=window(0,7,0,3)+[0x107e0]*32
region+=[0x33,0x10000,0x100a0,0x10000,0x100f0,0x10000,0x10050,0x37,0x10001,0x1008f]
region+=window(560,561,400,400)+[0x11234,0x1abcd]
assert len(region)==83
(out/'n4_region_expected.hex').write_bytes(''.join(f'{word:05x}\n' for word in region).encode())
