"""Read-only review of saved and newly detected crops; never updates the library."""
import json
import time
import hashlib
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from imaging import automatic_process, artwork_aspect, effective_crop_points, load


def main():
    root=Path(__file__).resolve().parent
    version=hashlib.sha256((root/'imaging.py').read_bytes()).hexdigest()[:10]
    destination=root/'data'/'crop-audit'/version
    destination.mkdir(parents=True,exist_ok=True)
    print('Audit folder:',destination,flush=True)
    snapshot=(root/'data'/'project.json').read_bytes()
    (destination/'project-before.json').write_bytes(snapshot)
    items=json.loads(snapshot)
    records=[]
    sheet=None
    started=time.monotonic()
    for index,item in enumerate(items):
        if index%15==0:
            sheet=Image.new('RGB',(1050,2200),'white')
        try:
            source=root/'data'/'originals'/item['file']
            result=automatic_process(source,item.get('rotation',0),artwork_aspect(item['name'],item['width'],item['height'],item.get('rotation',0)))
            dimensions=(item['height'],item['width']) if item.get('rotation',0)%180 else (item['width'],item['height'])
            outline=effective_crop_points(result['points'],*dimensions,result.get('trim'))
            records.append(dict(id=item['id'],name=item['name'],result=result,outline=outline))
            image=load(source,item.get('rotation',0))
            image.thumbnail((340,405))
            draw=ImageDraw.Draw(image)
            for points,colour in [(item['points'],'#ff4545'),(outline,'#00ee66')]:
                scaled=[(x*(image.width-1),y*(image.height-1)) for x,y in points]
                draw.line(scaled+[scaled[0]],fill=colour,width=2)
            tile=Image.new('RGB',(350,440),'#f2f2f2')
            tile.paste(image,((350-image.width)//2,25))
            draw=ImageDraw.Draw(tile)
            method=result['candidates'][0]['method'] if result['candidates'] else 'none'
            draw.text((5,5),f"{index+1:03d} {item['name'].split('_')[1]} {method}",fill='black')
            draw.text((5,427),'RED saved / GREEN new',fill='black')
            sheet.paste(tile,((index%3)*350,((index%15)//3)*440))
        except Exception as error:
            records.append(dict(id=item['id'],name=item['name'],error=str(error)))
        if (index+1)%15==0 or index+1==len(items):
            sheet.save(destination/f'sheet-{index//15+1:02d}.jpg',quality=93)
            (destination/'results.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),'utf-8')
            print(f'{index+1}/{len(items)} reviewed, {time.monotonic()-started:.1f}s',flush=True)
    print('Library unchanged:',(root/'data'/'project.json').read_bytes()==snapshot,flush=True)


if __name__=='__main__':
    main()
