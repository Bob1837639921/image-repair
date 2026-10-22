"""Prepare local visual-review sheets and a crop plan without changing the project."""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from imaging import effective_crop_points, load, refine_native, validate

ROOT=Path(__file__).resolve().parent
OUTPUT=ROOT/'data'/'crop-audit'/'review'


def key(item):
    parts=item['name'].split('_')
    return ('m' if parts[0]=='会员' else 'g')+parts[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('keys',nargs='*')
    parser.add_argument('--audit',default='56769c3884')
    args=parser.parse_args()
    OUTPUT.mkdir(parents=True,exist_ok=True)
    items=json.loads((ROOT/'data'/'project.json').read_text('utf-8'))
    results=json.loads((OUTPUT.parent/args.audit/'results.json').read_text('utf-8'))
    by_id={r['id']:r['result'] for r in results}
    corrections=OUTPUT/'corrections.json'
    overrides=json.loads(corrections.read_text('utf-8')) if corrections.exists() else {}
    plan=[]
    selected=[x for x in items if not args.keys or key(x) in args.keys]
    for index,item in enumerate(selected):
        label=key(item)
        result=by_id[item['id']]
        dimensions=(item['height'],item['width']) if item.get('rotation',0)%180 else (item['width'],item['height'])
        points=overrides.get(label,effective_crop_points(result['points'],*dimensions,result.get('trim')))
        validate(points)
        image=load(ROOT/'data'/'originals'/item['file'],item['rotation'])
        if label in overrides:
            points=refine_native(image,points)['points']
        image.thumbnail((600,800))
        draw=ImageDraw.Draw(image)
        for fraction in np.arange(.1,1,.1):
            x=round(fraction*(image.width-1));y=round(fraction*(image.height-1))
            draw.line([(x,0),(x,image.height-1)],fill='#cc8888',width=1)
            draw.line([(0,y),(image.width-1,y)],fill='#cc8888',width=1)
            draw.text((x,0),f'{fraction:.1f}',fill='red')
            draw.text((0,y),f'{fraction:.1f}',fill='red')
        polygon=[(x*(image.width-1),y*(image.height-1)) for x,y in points]
        draw.line(polygon+[polygon[0]],fill='#00ff66',width=2)
        tile=Image.new('RGB',(620,840),'white')
        tile.paste(image,((620-image.width)//2,30))
        ImageDraw.Draw(tile).text((10,5),label+(' CORRECTED' if label in overrides else 'ALGORITHM'),fill='black')
        tile.save(OUTPUT/(label+'.jpg'),quality=94)
        plan.append(dict(id=item['id'],key=label,name=item['name'],points=points,manually_corrected=label in overrides))
    (OUTPUT/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2),'utf-8')
    print('Reviewed plan:',len(plan),'Manual corrections:',sum(r['manually_corrected'] for r in plan))


if __name__=='__main__':
    main()
