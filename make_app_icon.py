"""Draw the original, scalable Scroll Studio scroll-and-ink emblem."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

ROOT=Path(__file__).resolve().parent
INK='#303d39'
SVG='''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">
<defs><linearGradient id="tile" x2=".8" y2="1"><stop stop-color="#bd5140"/><stop offset="1" stop-color="#812b26"/></linearGradient><linearGradient id="paper" x2=".8" y2="1"><stop stop-color="#fff8e9"/><stop offset="1" stop-color="#e5cfaa"/></linearGradient></defs>
<rect x="8" y="8" width="240" height="240" rx="54" fill="url(#tile)"/>
<rect x="17" y="17" width="222" height="222" rx="47" fill="none" stroke="#f3c59b" stroke-opacity=".24" stroke-width="1.5"/>
<rect x="68" y="57" width="133" height="165" rx="14" fill="#4b1919" opacity=".2"/>
<path d="M67 48H183V188Q183 205 200 205H80Q62 205 62 187V63Q62 48 77 48" fill="url(#paper)"/>
<rect x="55" y="43" width="139" height="22" rx="11" fill="#f8e8c8"/>
<path d="M64 60H184" stroke="#ccad7d" stroke-width="2"/>
<path d="M183 183H196Q207 183 207 194Q207 205 196 205H84Q96 205 96 194Q96 183 84 183Z" fill="#e6cba0"/>
<path d="M84 95Q119 86 159 92L156 100Q117 96 86 102Z M118 105L131 103L127 156L115 159Z M87 127Q120 116 155 123L153 131Q122 126 90 136Z M89 153Q118 156 155 143L164 150Q132 170 91 163Z" fill="#303d39"/>
<rect x="151" y="161" width="17" height="17" rx="3" fill="#b74937"/><path d="M156 165V174M163 165V174M156 169H163" stroke="#f5dec0" stroke-width="1.4"/>
</svg>'''

def main():
    # Supersampling keeps all Windows icon sizes sharp without a raster dependency.
    scale=4;size=256*scale
    im=Image.new('RGBA',(size,size));d=ImageDraw.Draw(im)
    def box(coords):return tuple(int(v*scale) for v in coords)
    mask=Image.new('L',im.size);ImageDraw.Draw(mask).rounded_rectangle(box((8,8,248,248)),54*scale,fill=255)
    gradient=Image.new('RGBA',im.size);pixels=gradient.load()
    for y in range(size):
        for x in range(size):
            t=min(1,max(0,(x*.25+y*.75)/size))
            pixels[x,y]=(int(189-60*t),int(81-38*t),int(64-26*t),255)
    im.paste(gradient,(0,0),mask);d=ImageDraw.Draw(im)
    d.rounded_rectangle(box((17,17,239,239)),47*scale,outline='#cf8267',width=2*scale)
    shadow=Image.new('RGBA',im.size);ImageDraw.Draw(shadow).rounded_rectangle(box((68,57,201,222)),14*scale,fill=(55,17,15,48))
    im=Image.alpha_composite(im,shadow.filter(ImageFilter.GaussianBlur(5*scale)));d=ImageDraw.Draw(im)
    d.rounded_rectangle(box((62,48,183,205)),15*scale,fill='#f8ebd2')
    d.rounded_rectangle(box((55,43,194,65)),11*scale,fill='#ffefd0')
    d.line(box((65,61,183,61)),fill='#d5ba8c',width=2*scale)
    d.rounded_rectangle(box((83,183,207,205)),11*scale,fill='#e5c99e')
    d.ellipse(box((75,183,96,205)),fill='#f9e7c4')
    # Intentional, asymmetric ink strokes: a small abstract artwork on a scroll.
    for polygon in [((84,95),(117,87),(159,91),(156,100),(116,97),(86,103)),((118,105),(131,103),(127,156),(115,159)),((87,127),(120,118),(155,123),(153,132),(122,128),(90,137)),((89,153),(119,156),(155,143),(164,150),(134,166),(91,163))]:
        d.polygon([(int(x*scale),int(y*scale)) for x,y in polygon],fill=INK)
    d.rounded_rectangle(box((151,161,168,178)),3*scale,fill='#b74937')
    for line in ((156,165,156,174),(163,165,163,174),(156,169,163,169)):d.line(box(line),fill='#f5dec0',width=scale)
    assets=ROOT/'assets';assets.mkdir(exist_ok=True)
    im.resize((256,256),Image.Resampling.LANCZOS).save(assets/'app-icon.png')
    im.save(assets/'app.ico',sizes=[(16,16),(20,20),(24,24),(32,32),(40,40),(48,48),(64,64),(128,128),(256,256)])
    (ROOT/'static'/'app-icon.svg').write_text(SVG,'utf-8')

if __name__=='__main__':main()
