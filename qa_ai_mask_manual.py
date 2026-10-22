import json,io,base64,urllib.request,urllib.error
from pathlib import Path
from PIL import Image
import numpy as np,cv2
from ai_config import load_connection
from imaging import render

def main():
    p=Path('data/crop-audit/review');c=load_connection(Path('data/ai-connection.json'));i=next(x for x in json.loads(Path('data/project.json').read_text('utf-8')) if x['name'].startswith('会员_003_'))
    with render(Path('data/originals')/i['file'],i['points'],i['rotation']) as im:
     x=100;y=round(im.height*.66)-512;a=im.crop((x,y,x+1536,y+1024)).convert('RGB')
    a.save(p/'ai-61-mask-before.png');arr=np.asarray(a);gray=cv2.cvtColor(arr,cv2.COLOR_RGB2GRAY)
    protect=((gray<120)|((arr[:,:,0].astype(float)-arr[:,:,1])>22)).astype('uint8');protect=cv2.dilate(protect,np.ones((13,13),np.uint8))>0
    editable=np.zeros(gray.shape,bool);editable[460:560,30:1506]=True;editable&=~protect
    mask=np.full((1024,1536,4),255,np.uint8);mask[editable,3]=0;m=Image.fromarray(mask);m.save(p/'ai-61-mask.png')
    def data(im):
     b=io.BytesIO();im.save(b,'PNG');return 'data:image/png;base64,'+base64.b64encode(b.getvalue()).decode()
    body={'model':'gpt-6.1-sol','input':[{'role':'user','content':[{'type':'input_text','text':'Edit this exact image using the supplied mask. Only reduce the paper crease shadow inside the transparent mask. Preserve all opaque pixels, every ink stroke and red seal, original grain and paper color. Maintain exact 1536x1024 canvas, framing and pixel alignment. No borders, no padding, no rescaling, no redrawing. Return the edited image.'},{'type':'input_image','image_url':data(a)}]}],'tools':[{'type':'image_generation','size':'1536x1024','quality':'high','input_image_mask':{'image_url':data(m)}}],'tool_choice':{'type':'image_generation'},'store':False}
    try:
     req=urllib.request.Request(c['base_url']+'/responses',json.dumps(body).encode(),{'Authorization':'Bearer '+c['key'],'Content-Type':'application/json'})
     r=json.load(urllib.request.urlopen(req,timeout=300));summary={'status':r.get('status'),'types':[o.get('type') for o in r.get('output',[])]}
     for o in r.get('output',[]):
      if o.get('type')=='image_generation_call' and o.get('result'): (p/'ai-61-mask-after.png').write_bytes(base64.b64decode(o['result']));summary['saved']=True
     print(json.dumps(summary));(p/'ai-61-mask-summary.json').write_text(json.dumps(summary))
    except urllib.error.HTTPError as e:print('HTTP',e.code,e.read().decode().replace(c['key'],'[REDACTED]')[:2000])


if __name__=='__main__':
    main()
