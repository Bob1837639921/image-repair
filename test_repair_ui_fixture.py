"""Isolated browser QA fixture; no user project data is loaded or changed."""
import os
import tempfile
from PIL import Image, ImageDraw

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=18766);parser.add_argument('--batch-demo',action='store_true');args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='scroll-repair-ui-') as folder:
        os.environ['SCROLL_STUDIO_DATA']=folder
        import server
        image=Image.new('RGB',(500,1000),(210,205,185))
        draw=ImageDraw.Draw(image)
        draw.rectangle((242,0,257,999),fill=(177,173,157))
        for y in range(80,900,150):
            draw.line((100,y,190,y+65),fill=(22,22,22),width=16)
            draw.line((320,y,410,y+65),fill=(22,22,22),width=16)
        image.save(server.DATA/'originals'/'fixture.png')
        server.ITEMS.append(dict(id='fixture',name='隔离测试 · 折痕样张.png',file='fixture.png',width=500,height=1000,points=server.FULL,rotation=0,settings=server.DEFAULTS.copy(),confirmed=True,candidates=[],revision=0,trim=server.validate_trim({})))
        if args.batch_demo:
            import repairing,time
            repairing.ai_repair=lambda image,*unused:(time.sleep(.3),image.copy())[1]
            server.REPAIRS.key='fixture-only-no-real-api'
            item=dict(server.ITEMS[0]);item.update(id='fixture2',name='隔离测试 · 第二幅.png');server.ITEMS.append(item)
            for item in server.ITEMS:item['repair_marks']=dict(signature=repairing.crop_signature(item),regions=[dict(id='one',region=[.4,.2,.6,.4],kind='crease'),dict(id='two',region=[.4,.6,.6,.8],kind='bump')])
        server.save()
        print(f'Repair UI fixture: http://127.0.0.1:{args.port}',flush=True)
        server.ThreadingHTTPServer(('127.0.0.1',args.port),server.Handler).serve_forever()
