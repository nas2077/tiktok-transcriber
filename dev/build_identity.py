"""Render the Syllark pixel mark as SVG, PNG and a Windows icon."""
from pathlib import Path
import struct
import zlib

ROOT = Path(__file__).resolve().parent.parent
GRID = [
    '................','................','.........ww.....','........wwww....',
    '.......wwwwwa...','......wwwwww....','..ww.wwwwww.....','...wwwwwwww.....',
    '....wwwwww......','.....wwwww......','......www.......','.....w.w........',
    '....ww.ww.......','................','................','................'
]


def png(size, transparent=False):
    scale=size//16
    colors={'.':bytes.fromhex('1b2632')+bytes([0 if transparent else 255]),
            'w':bytes.fromhex('eee9df')+b'\xff','a':bytes.fromhex('ffb162')+b'\xff'}
    rows=[b''.join(colors[c]*scale for c in row) for row in GRID for _ in range(scale)]
    def chunk(kind,data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
    return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',size,size,8,6,0,0,0))+
            chunk(b'IDAT',zlib.compress(b''.join(b'\0'+r for r in rows),9))+chunk(b'IEND',b''))


def main():
    folder=ROOT/'.github/assets'
    folder.mkdir(parents=True,exist_ok=True)
    shapes=''.join(f'<rect x="{x}" y="{y}" width="1" height="1" class="{"body" if c=="w" else "accent"}"/>'
                   for y,row in enumerate(GRID) for x,c in enumerate(row) if c!='.')
    svg=('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="160" height="160" '
         'shape-rendering="crispEdges" role="img" aria-label="Syllark"><title>Syllark</title>'
         '<style>.body{fill:#eee9df}.accent{fill:#ffb162}@media(prefers-color-scheme:light){.body{fill:#1b2632}.accent{fill:#a35139}}</style>'
         +shapes+'</svg>\n')
    (folder/'syllark.svg').write_bytes(svg.encode())
    (folder/'syllark.png').write_bytes(png(256))
    sizes=[16,32,48,64,128,256]
    images=[png(size) for size in sizes]
    offset=6+16*len(sizes)
    entries=[]
    for size,data in zip(sizes,images):
        entries.append(struct.pack('<BBBBHHII',size%256,size%256,0,0,1,32,len(data),offset))
        offset+=len(data)
    (ROOT/'src/icon.ico').write_bytes(struct.pack('<HHH',0,1,len(sizes))+b''.join(entries)+b''.join(images))
    # macOS bundles and Linux desktop entries take a plain PNG
    (ROOT/'src/icon.png').write_bytes(png(512))
    path=ROOT/'src/ui.html'
    text=path.read_text(encoding='utf-8')
    start=text.index('<svg',text.index('<div class="brand '))
    end=text.index('</svg>',start)+len('</svg>')
    inline=('<svg class="n-pixel" width="32" height="32" viewBox="0 0 16 16" role="img" aria-label="Syllark">'
            +shapes.replace('class="body"','fill="currentColor"').replace('class="accent"','fill="var(--pixel-orange)"')+'</svg>')
    text=text[:start]+inline+text[end:]
    path.write_bytes(text.encode('utf-8'))
    print("Syllark SVG/PNG, six-size ICO, 512 px PNG and application header updated.")


if __name__=='__main__':
    main()
