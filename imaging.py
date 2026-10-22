import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / '.deps' / 'opencv'))
import cv2
import numpy as np
from PIL import Image, ImageOps, ImageEnhance

DEFAULTS = dict(brightness=1.0, contrast=1.0, sharpness=1.0)
FULL = [[0, 0], [1, 0], [1, 1], [0, 1]]


def load(path, rotation=0):
    with Image.open(path) as src:
        src.load()
        im = ImageOps.exif_transpose(src).convert('RGB')
    return im.rotate(-rotation, expand=True) if rotation else im


def validate(points):
    p = np.asarray(points, dtype=np.float32)
    if p.shape != (4, 2) or not np.isfinite(p).all() or (p < 0).any() or (p > 1).any():
        raise ValueError('四角坐标必须在图片范围内')
    cross = []
    for i in range(4):
        a, b = p[(i+1) % 4]-p[i], p[(i+2) % 4]-p[(i+1) % 4]
        cross.append(float(a[0]*b[1]-a[1]*b[0]))
    if min(cross) <= 0.00001 or cv2.contourArea(p) < .002:
        raise ValueError('四角不能交叉或重叠，请按左上、右上、右下、左下排列')
    return p


def validate_trim(trim=None):
    result={side:float((trim or {}).get(side,0)) for side in ('left','top','right','bottom')}
    if any(not np.isfinite(v) or not 0<=v<=.05 for v in result.values()):
        raise ValueError('每边收边范围为 0–5%')
    return result


def suggest_trim(image):
    """Find an edge-connected band unlike the adjacent paper, in any hue."""
    rgb=np.asarray(image);h,w=rgb.shape[:2]
    result=validate_trim();evidence={}
    short=min(w,h)
    for side in result:
        oriented=rgb if side=='left' else rgb[:,::-1] if side=='right' else rgb.transpose(1,0,2) if side=='top' else rgb[::-1].transpose(1,0,2)
        axis=w if side in ('left','right') else h
        limit=max(2,min(100,int(axis*.05),int(short*.05)))
        reference_width=max(10,min(40,int(short*.035)))
        strip=np.ascontiguousarray(oriented[::max(1,len(oriented)//1800),:limit+reference_width+5])
        colors=cv2.cvtColor(cv2.medianBlur(strip,3),cv2.COLOR_RGB2LAB).astype('float32')
        reference=colors[:,limit+4:]
        if reference.shape[1]<4:continue
        paper=np.median(reference,axis=1)
        distance=np.linalg.norm((colors-paper[:,None,:])*[.55,1.,1.],axis=2)
        variation=np.percentile(distance[:,limit+4:],80,axis=1)
        threshold=np.maximum(13,variation*2.5+5)
        mismatch=distance[:,:limit+4]>threshold[:,None]
        # Four stable paper pixels reject isolated flecks in patterned mounting.
        matches=~mismatch
        stable=matches[:,:-3]&matches[:,1:-2]&matches[:,2:-1]&matches[:,3:]
        found=stable.any(axis=1)
        depths=np.where(found,stable.argmax(axis=1),limit+1)
        attached=mismatch[:,:min(3,limit)].mean(axis=1)>=.5
        usable=attached&found&(depths>0)&(depths<=limit)&(variation<18)
        support=float(np.mean(usable))
        if support<.12:
            evidence[side]=dict(support=round(support,3),pixels=0)
            continue
        depth=int(np.ceil(np.percentile(depths[usable],98)))+1
        gray=cv2.cvtColor(strip,cv2.COLOR_RGB2GRAY)
        ref_gray=np.median(gray[:,limit+4:],axis=1)
        chroma=np.linalg.norm(colors[:,:,1:]-128,axis=2)
        protected=(gray[:,:depth]<np.maximum(15,ref_gray*.45)[:,None])&(chroma[:,:depth]<22)
        if np.mean(protected)>.005:
            evidence[side]=dict(support=round(support,3),pixels=0,protected=True)
            continue
        result[side]=min(.05,depth/axis)
        evidence[side]=dict(support=round(support,3),pixels=depth)
    return dict(trim=result,evidence=evidence,note='已按纸面颜色差异去残边' if any(result.values()) else '未发现可靠残边，保留当前边界')


def render(path, points, rotation=0, settings=None, preview=False, trim=None):
    im = load(path, rotation)
    if preview:
        im.thumbnail((1600, 1600))
    rgb = np.asarray(im)
    p = validate(points) * [im.width-1, im.height-1]
    w = max(2, round(max(np.linalg.norm(p[1]-p[0]), np.linalg.norm(p[2]-p[3])))+1)
    h = max(2, round(max(np.linalg.norm(p[3]-p[0]), np.linalg.norm(p[2]-p[1])))+1)
    matrix = cv2.getPerspectiveTransform(p.astype('float32'), np.array([[0,0],[w-1,0],[w-1,h-1],[0,h-1]], dtype='float32'))
    out = Image.fromarray(cv2.warpPerspective(rgb, matrix, (w,h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE))
    t=validate_trim(trim)
    out=out.crop((round(w*t['left']),round(h*t['top']),w-round(w*t['right']),h-round(h*t['bottom'])))
    s = {**DEFAULTS, **(settings or {})}
    for key, enhancer in [('brightness', ImageEnhance.Brightness), ('contrast', ImageEnhance.Contrast), ('sharpness', ImageEnhance.Sharpness)]:
        value = float(s[key])
        if not .5 <= value <= 2:
            raise ValueError('优化参数超出允许范围')
        if value != 1:
            out = enhancer(out).enhance(value)
    return out


def automatic_process(path, rotation=0):
    candidates=detect(path,rotation)
    points=candidates[0]['points'] if candidates else FULL
    if candidates:
        candidate=candidates[0]
        coverage=cv2.contourArea(np.asarray(points,dtype='float32'))
        supports=candidate.get('edge_support',[])
        # A nearly full-frame rectangle without supported internal edges is
        # already framed. Dense grids/text must not create an inset trapezoid.
        if coverage>.85 and supports and sum(v>=2 for v in supports)<2:
            return dict(points=FULL,trim=validate_trim(),candidates=[dict(points=FULL,method='full-frame')]+candidates[:3],auto_result=dict(needs_review=False,note='画面已基本铺满，保留完整边界'))
    trim=validate_trim()
    notes=[]
    if candidates:
        with render(path,points,rotation) as image:
            trim=suggest_trim(image)['trim']
        if candidates[0].get('score',0)<.35:notes.append('画心边界不够明确')
        supports=candidates[0].get('edge_support',[])
        if supports and min(supports)<2:notes.append('部分纸边不清晰')
    else:notes.append('没有找到明确画心边界')
    return dict(points=points,trim=trim,candidates=candidates,auto_result=dict(needs_review=bool(notes),note='；'.join(notes) if notes else '自动处理完成'))


def refine_native(image, points):
    """Fit continuous edges in narrow source-pixel strips; never resize strips."""
    rgb=np.asarray(image)
    height,width=rgb.shape[:2]
    pts=validate(points).astype(float)*[width-1,height-1]
    boundaries=[]; evidence=[]
    for side in range(4):
        start,end=pts[side],pts[(side+1)%4]
        tangent=end-start; length=np.linalg.norm(tangent)
        normal=np.array([-tangent[1],tangent[0]])/max(length,1)
        depth=2*abs(np.dot(pts.mean(axis=0)-(start+end)/2,normal))
        radius=int(min(48,max(10,min(depth*.06,max(width,height)*.008))))
        offsets=np.arange(-radius-4,radius+5,dtype=np.float32)
        positions=np.linspace(.08,.92,max(64,min(2000,int(length/2))))
        base=start+positions[:,None]*tangent
        coords=base[:,None,:]+offsets[None,:,None]*normal
        valid=(coords[:,:,0]>=0)&(coords[:,:,0]<width-1)&(coords[:,:,1]>=0)&(coords[:,:,1]<height-1)
        strip=cv2.remap(rgb,coords[:,:,0].astype('float32'),coords[:,:,1].astype('float32'),cv2.INTER_LINEAR,borderMode=cv2.BORDER_REPLICATE)
        colors=cv2.cvtColor(cv2.GaussianBlur(strip,(3,3),0),cv2.COLOR_RGB2LAB).astype(float)
        gray=cv2.cvtColor(strip,cv2.COLOR_RGB2GRAY)
        delta=(colors[:,6:]-colors[:,:-6])*[.6,1,1]
        contrast=np.linalg.norm(delta,axis=2)
        search=offsets[3:-3]
        usable=valid[:,6:]&valid[:,:-6]&(gray[:,6:]>75)&(gray[:,:-6]>75)
        contrast=np.where(usable,contrast,0)
        strength=np.percentile(contrast,35,axis=0)
        scores=strength-.035*np.abs(search)
        index=int(np.argmax(scores)); chosen=float(search[index])
        support=float(np.mean(contrast[:,index]>2.5))
        shift=0.; slope=0.
        if strength[index]>=3 and support>=.65:
            # Fit separately measured segments, rejecting isolated strokes,
            # fingers and folds rather than following a single strong pixel.
            local=[]
            nearby=np.where(np.abs(search-chosen)<=5)[0]
            for indices in np.array_split(np.arange(len(positions)),12):
                segment=np.percentile(contrast[indices],35,axis=0)
                best=nearby[np.argmax(segment[nearby]-.08*np.abs(search[nearby]-chosen))]
                if segment[best]>=2.5:local.append([float(np.mean(positions[indices])),float(search[best])])
            if len(local)>=8:
                local=np.asarray(local)
                fit=np.polyfit(local[:,0],local[:,1],1)
                residual=np.abs(local[:,1]-np.polyval(fit,local[:,0]))
                keep=residual<3
                if keep.sum()>=8:
                    fit=np.polyfit(local[keep,0],local[keep,1],1)
                    if max(abs(np.polyval(fit,[0,1])))<=radius:
                        slope,shift=fit
                        # Avoid a systematic inward bias from gradient width.
                        shift-=1.5
        moves=shift+slope*positions
        swept=(offsets[None,:]>=0)&(offsets[None,:]<=moves[:,None])&valid
        dark=(gray<70)&swept
        if swept.sum() and dark.sum()/swept.sum()>.015:
            shift=0.;slope=0.
        boundaries.append((start+normal*shift,end+normal*(shift+slope)))
        evidence.append(dict(side=side,support=round(support,3),shift=round(float(shift),2),slope=round(float(slope),2)))
    corners=[]
    for i in range(4):
        a,b=boundaries[(i-1)%4];c,d=boundaries[i]
        matrix=np.column_stack((b-a,-(d-c)))
        if abs(np.linalg.det(matrix))<1e-6:return dict(points=points,native_edges=evidence)
        corners.append(a+(b-a)*np.linalg.solve(matrix,c-a)[0])
    normalized=np.clip(np.asarray(corners)/[width-1,height-1],0,1)
    try:validate(normalized)
    except ValueError:return dict(points=points,native_edges=evidence)
    return dict(points=normalized.tolist(),native_edges=evidence)


def detect(path, rotation=0):
    im = load(path, rotation)
    im.thumbnail((1100,1100))
    a = np.asarray(im)
    h,w = a.shape[:2]
    gray = cv2.cvtColor(a, cv2.COLOR_RGB2GRAY)
    dark_limit=min(85,float(np.percentile(gray,85))*.5)
    candidates = []
    # Suppress ink strokes before segmenting the paper colour. The original
    # pixels remain untouched; these images are used only to propose corners.
    paper=cv2.medianBlur(a,15)
    lab=cv2.cvtColor(paper,cv2.COLOR_RGB2LAB).astype(np.float32)
    gray_smooth=cv2.cvtColor(paper,cv2.COLOR_RGB2GRAY)
    texture=cv2.absdiff(gray,gray_smooth)

    def add_quad(pts, method, rectangularity=1.):
        pts=np.asarray(pts,dtype=float).reshape(4,2)
        center=pts.mean(axis=0)
        pts=pts[np.argsort(np.arctan2(pts[:,1]-center[1],pts[:,0]-center[0]))]
        pts=np.roll(pts,-np.argmin(pts.sum(axis=1)),axis=0)
        norm=np.clip(pts/[w-1,h-1],0,1)
        try: validate(norm)
        except ValueError: return
        area=cv2.contourArea(norm.astype('float32'))
        if not .065<area<.97: return
        mask=np.zeros((h,w),np.uint8)
        cv2.fillConvexPoly(mask,pts.astype('int32'),255)
        eroded=cv2.erode(mask,np.ones((13,13),np.uint8))
        inner=(mask>0)&(eroded==0)
        outer=(cv2.dilate(mask,np.ones((15,15),np.uint8))>0)&(mask==0)
        edge_noise=float(np.mean(texture[inner])) if inner.any() else 30
        outside_noise=float(np.mean(texture[outer])) if outer.any() else 0
        uniformity=1-min(edge_noise/22,1)
        contrast=min(max(outside_noise-edge_noise,0)/15,1)
        center_penalty=np.linalg.norm(center/[w,h]-.5)
        interior_noise=float(np.mean((texture[mask>0]>12)&(gray[mask>0]>85)))
        vectors=np.roll(pts,-1,axis=0)-pts
        corner_skew=max(abs(float(np.dot(vectors[i],vectors[(i+1)%4])))/(np.linalg.norm(vectors[i])*np.linalg.norm(vectors[(i+1)%4])+1e-6) for i in range(4))
        coverage=max(np.ptp(norm[:,0]),np.ptp(norm[:,1]))
        score=.10*area+.30*uniformity+.15*contrast+.12*rectangularity-.3*center_penalty-1.8*interior_noise+.25*coverage-.4*corner_skew
        if method=='paper': score+=.12
        if method=='lines': score+=.10
        record=dict(points=norm.tolist(),score=round(float(score),3),method=method)
        for i,c in enumerate(candidates):
            if np.mean(np.abs(norm-np.array(c['points'])))<.018:
                if score>c['score']:candidates[i]=record
                return
        candidates.append(record)

    noise=((texture>9)&(gray>80)).astype('float32')
    local_noise=cv2.boxFilter(noise,-1,(25,25))
    for threshold in (.035,.065,.10):
        mask=((local_noise<threshold)&(gray_smooth>75)).astype('uint8')*255
        mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((27,27),np.uint8))
        mask=cv2.morphologyEx(mask,cv2.MORPH_OPEN,np.ones((11,11),np.uint8))
        contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            area=cv2.contourArea(contour)
            if not .065*w*h<area<.95*w*h:continue
            hull=cv2.convexHull(contour)
            quad=cv2.approxPolyDP(hull,.03*cv2.arcLength(hull,True),True)
            rect=cv2.minAreaRect(contour)
            extent=area/max(rect[1][0]*rect[1][1],1)
            if len(quad)==4 and extent>.85:add_quad(quad[:,0,:],'smooth',extent)

    seeds=[]
    for sy in (.15,.35,.55,.75,.9):
        for sx in (.35,.45,.55,.65):
            yy,xx=int(h*sy),int(w*sx)
            patch=lab[max(0,yy-8):yy+9,max(0,xx-8):xx+9].reshape(-1,3)
            bright=patch[patch[:,0]>=np.percentile(patch[:,0],65)]
            seed=np.median(bright,axis=0)
            if all(np.linalg.norm(seed-s)>9 for s in seeds):seeds.append(seed)
    for seed in seeds:
        distance=np.sqrt(((lab-seed)**2*np.array([.45,1.,1.])).sum(axis=2))
        for threshold in (9,16,24):
            mask=(distance<threshold).astype(np.uint8)*255
            mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((13,13),np.uint8))
            mask=cv2.morphologyEx(mask,cv2.MORPH_OPEN,np.ones((7,7),np.uint8))
            contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
            for contour in contours:
                area=cv2.contourArea(contour)
                if not .065*w*h<area<.96*w*h:continue
                rect=cv2.minAreaRect(contour)
                rect_area=rect[1][0]*rect[1][1]
                extent=area/max(rect_area,1)
                if extent<.80:continue
                quad=cv2.approxPolyDP(cv2.convexHull(contour),.025*cv2.arcLength(contour,True),True)
                if len(quad)==4:add_quad(quad[:,0,:],'paper',extent)
                elif extent>.94:add_quad(cv2.boxPoints(rect),'paper',extent)
    for lo,hi in [(25,80),(55,160)]:
        edges = cv2.Canny(cv2.GaussianBlur(gray,(5,5),0),lo,hi)
        edges = cv2.morphologyEx(edges,cv2.MORPH_CLOSE,np.ones((5,5),np.uint8))
        contours,_ = cv2.findContours(edges,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            area = cv2.contourArea(contour)/(w*h)
            if not .08 < area < .97:
                continue
            quad = cv2.approxPolyDP(contour,.025*cv2.arcLength(contour,True),True)
            if len(quad)!=4 or not cv2.isContourConvex(quad):
                continue
            add_quad(quad[:,0,:],'edge')
    # Recover incomplete paper contours from long, nearly vertical boundaries.
    # In handheld photos the top or bottom can touch the photograph boundary.
    edges=cv2.Canny(cv2.GaussianBlur(gray,(5,5),0),25,80)
    lines=cv2.HoughLinesP(edges,1,np.pi/1800,threshold=55,minLineLength=min(h,w)*.23,maxLineGap=max(h,w)*.035)
    vertical=[];horizontal=[]
    if lines is not None:
        for x1,y1,x2,y2 in lines.reshape(-1,4):
            if abs(y2-y1)>h*.30 and abs(x2-x1)<abs(y2-y1)*.12:
                slope=(x2-x1)/(y2-y1);intercept=x1-slope*y1
                vertical.append((abs(y2-y1),intercept,slope))
            if abs(x2-x1)>w*.15 and abs(y2-y1)<abs(x2-x1)*.12:
                horizontal.append((abs(x2-x1),min(x1,x2),max(x1,x2),(y2-y1)/(x2-x1),y1-(y2-y1)/(x2-x1)*x1))
    unique=[]
    for line in sorted(vertical,reverse=True):
        mid=line[1]+line[2]*h*.5
        if all(abs(mid-(v[1]+v[2]*h*.5))>w*.012 for v in unique):unique.append(line)
    unique=sorted(unique[:16],key=lambda v:v[1]+v[2]*h*.5)
    for i,left in enumerate(unique):
        for right in unique[i+1:]:
            xl=left[1]+left[2]*h*.5;xr=right[1]+right[2]*h*.5
            if not .12*w<xr-xl<.91*w or not .28*w<(xl+xr)/2<.72*w:continue
            matching=[v for v in horizontal if min(xr,v[2])-max(xl,v[1])>(xr-xl)*.7]
            top=[v for v in matching if v[3]*(xl+xr)/2+v[4]<h*.30]
            bottom=[v for v in matching if v[3]*(xl+xr)/2+v[4]>h*.65]
            top=sorted(top,reverse=True)[:2] or [(0,0,w,0,0)]
            bottom=sorted(bottom,reverse=True)[:2] or [(0,0,w,0,h-1)]
            for t in top:
                for b in bottom:
                    def intersection(v,hh):
                        yy=(hh[3]*v[1]+hh[4])/(1-hh[3]*v[2])
                        return [v[1]+v[2]*yy,yy]
                    add_quad([intersection(left,t),intersection(right,t),intersection(right,b),intersection(left,b)],'lines')
    candidates.sort(key=lambda x:x['score'],reverse=True)
    # Refine each side against a long strip of paper, not individual ink strokes.
    # Keep this search local so a plausible paper rectangle cannot jump to a
    # different work or to the outside of the mounting.
    def refine(record):
        pts=np.asarray(record['points'])*[w-1,h-1]
        center=pts.mean(axis=0)
        boundaries=[]
        supports=[]
        for i in range(4):
            start,end=pts[i],pts[(i+1)%4]
            tangent=end-start
            normal=np.array([-tangent[1],tangent[0]])
            normal/=max(np.linalg.norm(normal),1)
            if np.dot(center-(start+end)/2,normal)<0:normal=-normal
            depth=abs(np.dot(center-(start+end)/2,normal))*2
            limit=min(80,max(8,depth*.24))
            offsets=np.arange(-min(limit,12),limit+1)
            base=start[None,:]+np.linspace(.12,.88,130)[:,None]*tangent
            scores=[]
            for offset in offsets:
                outside=base+normal*(offset-5)
                inside=base+normal*(offset+5)
                valid=(outside[:,0]>=0)&(outside[:,0]<w)&(outside[:,1]>=0)&(outside[:,1]<h)&(inside[:,0]>=0)&(inside[:,0]<w)&(inside[:,1]>=0)&(inside[:,1]<h)
                if valid.mean()<.75:
                    scores.append(-100);continue
                if offset>3:
                    swept=base[:,None,:]+normal*np.linspace(0,offset,12)[None,:,None]
                    swept=swept.reshape(-1,2).astype(int)
                    swept=swept[(swept[:,0]>=0)&(swept[:,0]<w)&(swept[:,1]>=0)&(swept[:,1]<h)]
                    if len(swept) and np.mean(gray[swept[:,1],swept[:,0]]<dark_limit)>.015:
                        scores.append(-100);continue
                out=outside[valid].astype(int);inn=inside[valid].astype(int)
                delta=np.linalg.norm((lab[out[:,1],out[:,0]]-lab[inn[:,1],inn[:,0]])*np.array([.6,1.,1.]),axis=1)
                # Lower percentile requires evidence along most of the edge.
                strength=float(np.percentile(delta,35))
                # Brocade can have almost the same colour as paper. Prefer a
                # boundary with a quiet inner strip and textured outer strip.
                # Use non-dark texture (computed above), so black ink itself
                # is not mistaken for patterned mounting.
                inner_noise=float(np.median(local_noise[inn[:,1],inn[:,0]]))
                outer_noise=float(np.median(local_noise[out[:,1],out[:,0]]))
                texture_step=max(0,outer_noise-inner_noise)
                inner_colors=lab[inn[:,1],inn[:,0]]
                outer_colors=lab[out[:,1],out[:,0]]
                inner_spread=float(np.percentile(np.linalg.norm(inner_colors-np.median(inner_colors,axis=0),axis=1),60))
                outer_spread=float(np.percentile(np.linalg.norm(outer_colors-np.median(outer_colors,axis=0),axis=1),60))
                scores.append(strength+45*texture_step-65*inner_noise+.5*max(0,outer_spread-inner_spread)-.4*inner_spread-.06*abs(offset))
            best=int(np.argmax(scores));offset=float(offsets[best])
            if scores[best]<3:offset=0
            supports.append(round(max(0,scores[best]),2))
            # Leave a small outward safety allowance at detected boundaries.
            if offset!=0:offset-=1.5
            boundaries.append((start+normal*offset,end+normal*offset))
        refined=[]
        for i in range(4):
            a,b=boundaries[(i-1)%4];c,d=boundaries[i]
            matrix=np.column_stack((b-a,-(d-c)))
            if abs(np.linalg.det(matrix))<1e-6:return record
            refined.append(a+(b-a)*np.linalg.solve(matrix,c-a)[0])
        norm=np.clip(np.asarray(refined)/[w-1,h-1],0,1)
        try:validate(norm)
        except ValueError:return record
        return {**record,'points':norm.tolist(),'edge_support':supports,'method':record['method']+'+refined'}
    results=[refine(c) for c in candidates[:4]]
    if results:
        with load(path,rotation) as original:
            native=refine_native(original,results[0]['points'])
        coarse=results[0]
        precise={**coarse,**native,'method':coarse['method']+'+native'}
        # Keep the coarse result available for immediate comparison/recovery.
        results=([precise,coarse]+results[1:])[:4]
    for c in results:
        c['review_note']='自动边界需复核；贴边笔画与印章请放大检查'
    return results
