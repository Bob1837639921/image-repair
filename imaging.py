import sys
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / '.deps' / 'opencv'))
import cv2
import numpy as np
from PIL import Image, ImageOps, ImageEnhance

DEFAULTS = dict(brightness=1.0, contrast=1.0, sharpness=1.0)
FULL = [[0, 0], [1, 0], [1, 1], [0, 1]]


def artwork_aspect(name, width, height, rotation=0):
    """Use supplied artwork dimensions only to rank, never stretch, candidates."""
    match=re.search(r'(\d+(?:\.\d+)?)\s*[×xX*]\s*(\d+(?:\.\d+)?)(?:\s*[×xX*]\s*(\d+))?\s*(?:厘米|cm)',name)
    if not match:return None
    first,second=map(float,match.group(1,2))
    if not first or not second:return None
    second*=float(match.group(3) or 1)
    ratio=min(first,second)/max(first,second)
    if rotation%180:width,height=height,width
    return ratio if height>=width else 1/ratio


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
        # Judge the entire removed band, not its average darkness. A small
        # seal or a thin stroke must not be diluted by thousands of blank rows.
        band=np.ascontiguousarray(oriented[:,:depth])
        band_gray=cv2.cvtColor(band,cv2.COLOR_RGB2GRAY)
        band_lab=cv2.cvtColor(band,cv2.COLOR_RGB2LAB).astype(float)
        paper_gray=float(np.percentile(ref_gray,70))
        paper_a=float(np.median(reference[:,:,1]))
        ink=(band_gray<max(30,paper_gray*.65))&(np.linalg.norm(band_lab[:,:,1:]-128,axis=2)<32)
        red=(band_lab[:,:,1]>max(145,paper_a+12))&(band[:,:,0].astype(float)>band[:,:,1]*1.25)
        protected=(ink|red).astype('uint8')
        count,labels,stats,_=cv2.connectedComponentsWithStats(protected,8)
        significant=any(s[cv2.CC_STAT_AREA]>=max(4,short*.002) for s in stats[1:])
        if significant:
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


def effective_crop_points(points, width, height, trim=None):
    """Map the actual rounded output trim back onto the original photograph."""
    p=validate(points)*[width-1,height-1]
    output_width=max(2,round(max(np.linalg.norm(p[1]-p[0]),np.linalg.norm(p[2]-p[3])))+1)
    output_height=max(2,round(max(np.linalg.norm(p[3]-p[0]),np.linalg.norm(p[2]-p[1])))+1)
    target=np.array([[0,0],[output_width-1,0],[output_width-1,output_height-1],[0,output_height-1]],dtype='float32')
    matrix=cv2.getPerspectiveTransform(target,p.astype('float32'))
    t=validate_trim(trim)
    left=round(output_width*t['left']);right=output_width-round(output_width*t['right'])-1
    top=round(output_height*t['top']);bottom=output_height-round(output_height*t['bottom'])-1
    corners=np.array([[[left,top],[right,top],[right,bottom],[left,bottom]]],dtype='float32')
    return (cv2.perspectiveTransform(corners,matrix)[0]/[width-1,height-1]).tolist()


def same_colour_sheet(path,rotation=0):
    """Conservative fallback for wide sheets whose left/right edges are off-frame.

    Require two full-width transitions, quiet ink-free backing, and a stronger
    texture change below the sheet. Internal fan outlines cannot satisfy these
    tests. This is deliberately not a general-purpose rectangle detector.
    """
    with load(path,rotation) as image:
        image.thumbnail((1100,1100));rgb=np.asarray(image)
    h,w=rgb.shape[:2]
    if w/h<1.1 or min(w,h)<100:return None
    gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY).astype('float32')
    blur=cv2.GaussianBlur(gray,(0,0),1)
    difference=blur[4:]-blur[:-4]
    margin=max(5,round(w*.05))
    profile=np.median(difference[:,margin:-margin],axis=1)
    def boundary(lo,hi):
        lo=max(3,round(h*lo));hi=min(h-4,round(h*hi))
        peak=lo+int(np.argmax(np.abs(profile[lo-2:hi-2])))
        sign=np.sign(profile[peak-2]);strength=abs(float(profile[peak-2]))
        if strength<3:return None
        # Refit the same transition in independent bands, including the sides.
        xs=[];ys=[];weights=[]
        for left,right in zip(np.linspace(margin,w-margin,17)[:-1],np.linspace(margin,w-margin,17)[1:]):
            local=np.median(difference[:,int(left):int(right)],axis=1)*sign
            start=max(2,peak-14);end=min(h-3,peak+15)
            y=start+int(np.argmax(local[start-2:end-2]))
            weight=float(local[y-2])
            if weight>=max(2,strength*.25):xs.append((left+right)/2);ys.append(y);weights.append(weight)
        if len(xs)<14:return None
        xs=np.asarray(xs);ys=np.asarray(ys);slope,intercept=np.polyfit(xs,ys,1)
        residual=np.abs(ys-(slope*xs+intercept))
        good=residual<3
        if good.sum()<14 or abs(slope)*w>h*.035:return None
        slope,intercept=np.polyfit(xs[good],ys[good],1)
        return np.array([intercept,intercept+slope*(w-1)]),strength
    top=boundary(.025,.22);bottom=boundary(.55,.90)
    if top is None or bottom is None:return None
    t,ts=top;b,bs=bottom
    if min(b-t)<h*.45:return None
    # A genuine blank support sheet must not contain omitted strokes/seals.
    yy,xx=np.mgrid[:h,:w];top_line=t[0]+(t[1]-t[0])*xx/(w-1);bottom_line=b[0]+(b[1]-b[0])*xx/(w-1)
    inside=(yy>top_line+8)&(yy<bottom_line-8)
    outside=(yy<top_line-8)|(yy>bottom_line+8)
    dark=gray<min(100,float(np.percentile(gray,80))*.58)
    red=(rgb[:,:,0].astype(float)>rgb[:,:,1]*1.18)&(rgb[:,:,0].astype(float)>rgb[:,:,2]*1.13)&(rgb[:,:,1]<165)
    if np.mean((dark|red)[outside])>.001 or np.mean(dark[inside])<.003:return None
    # Printed long rules alone are insufficient: paper/backing texture differs.
    texture=cv2.GaussianBlur(gray,(0,0),2)-cv2.GaussianBlur(gray,(0,0),9)
    above=(yy>bottom_line-h*.12)&(yy<bottom_line-12)&~dark&~red
    below=(yy>bottom_line+12)&(yy<bottom_line+h*.12)&~dark&~red
    if min(above.sum(),below.sum())<w*8:return None
    # Median energy is not dominated by the fan's gold outline near the edge.
    if float(np.median(np.abs(texture[below])))<max(.7,float(np.median(np.abs(texture[above])))*1.25):return None
    # Shift two preview pixels inward to exclude the seam itself, not the fan.
    points=[[0,(t[0]+2)/(h-1)],[1,(t[1]+2)/(h-1)],[1,(b[1]-2)/(h-1)],[0,(b[0]-2)/(h-1)]]
    return dict(points=validate(points).tolist(),score=.9,method='same-colour-sheet',edge_support=[ts,0,bs,0])


def automatic_process(path, rotation=0, expected_aspect=None):
    candidates=detect(path,rotation,expected_aspect) if expected_aspect else detect(path,rotation)
    points=candidates[0]['points'] if candidates else FULL
    if candidates:
        candidate=candidates[0]
        coverage=cv2.contourArea(np.asarray(points,dtype='float32'))
        supports=candidate.get('edge_support',[])
        # A nearly full-frame rectangle without supported internal edges is
        # already framed. Dense grids/text must not create an inset trapezoid.
        if coverage>.85 and supports and sum(v>=2 for v in supports)<2:
            sheet=same_colour_sheet(path,rotation)
            if sheet:
                return dict(points=sheet['points'],trim=validate_trim(),candidates=[sheet]+candidates[:3],auto_result=dict(needs_review=False,method='same-colour-sheet',note='已结合连续纸边与纹理差异排除同色垫纸'))
            return dict(points=FULL,trim=validate_trim(),candidates=[dict(points=FULL,method='full-frame')]+candidates[:3],auto_result=dict(needs_review=True,note='纸边证据不足，暂保留完整原图，请检查画心边界'))
    if not candidates:
        sheet=same_colour_sheet(path,rotation)
        if sheet:return dict(points=sheet['points'],trim=validate_trim(),candidates=[sheet],auto_result=dict(needs_review=False,method='same-colour-sheet',note='已结合连续纸边与纹理差异排除同色垫纸'))
    trim=validate_trim()
    notes=[]
    if candidates:
        with load(path,rotation) as original:
            guarded=protect_crossing_marks(original,points)
        points=guarded['points']
        if guarded['adjusted']:
            candidates=[{**candidates[0],'points':points,'method':candidates[0]['method']+'+ink-guard'}]+candidates[1:]
            notes.append('已保留跨纸边笔画，请复核纸边')
        with render(path,points,rotation) as image:
            trim=suggest_trim(image)['trim']
        if candidates[0].get('score',0)<.35:notes.append('画心边界不够明确')
        supports=candidates[0].get('edge_support',[])
        if supports and min(supports)<2:notes.append('部分纸边不清晰')
    else:notes.append('没有找到明确画心边界')
    return dict(points=points,trim=trim,candidates=candidates,auto_result=dict(needs_review=bool(notes),note='；'.join(notes) if notes else '自动处理完成'))


def protect_crossing_marks(image, points):
    """Keep connected ink crossing an estimated edge, within a narrow margin.

    Only components connected across the edge count; nearby background and
    isolated mounting patterns must not pull the crop outwards.
    """
    rgb=np.asarray(image);height,width=rgb.shape[:2]
    p=validate(points).astype(float)*[width-1,height-1]
    radius=max(24,min(48,round(min(width,height)*.012)))
    boundaries=[];adjusted=False
    for side in range(4):
        start,end=p[side],p[(side+1)%4]
        tangent=end-start;length=np.linalg.norm(tangent)
        normal=np.array([-tangent[1],tangent[0]])/length
        positions=np.linspace(.01,.99,max(64,min(2400,round(length))))
        offsets=np.arange(-radius,radius+1)
        coords=start+positions[:,None,None]*tangent+offsets[None,:,None]*normal
        strip=cv2.remap(rgb,coords[:,:,0].astype('float32'),coords[:,:,1].astype('float32'),cv2.INTER_LINEAR,borderMode=cv2.BORDER_REPLICATE)
        gray=cv2.cvtColor(strip,cv2.COLOR_RGB2GRAY)
        lab=cv2.cvtColor(strip,cv2.COLOR_RGB2LAB).astype(float)
        paper=float(np.percentile(gray[:,radius:],80))
        dark=(gray<max(35,paper*.55))&(np.linalg.norm(lab[:,:,1:]-128,axis=2)<32)
        paper_a=float(np.median(lab[:,radius:,1]))
        red=(lab[:,:,1]>max(132,paper_a+5))&(strip[:,:,0].astype(float)>strip[:,:,1]*1.08)
        mask=(dark|red).astype('uint8')
        count,labels,stats,_=cv2.connectedComponentsWithStats(mask,8)
        shift=0
        for label in range(1,count):
            x,y,w,h,area=stats[label]
            seal=area>=10 and float(np.mean(red[labels==label]))>.65 and x>=radius-24
            if area<6 or h>len(positions)*.3 or x>=radius or (x+w<=radius+2 and not seal):continue
            # A component running out of the search strip is uncertain; do
            # not follow arbitrary background beyond this bounded margin.
            if x==0:continue
            shift=min(shift,x-radius-(12 if seal else 3))
        adjusted|=shift<0
        boundaries.append((start+normal*shift,end+normal*shift))
    corners=[]
    for i in range(4):
        a,b=boundaries[(i-1)%4];c,d=boundaries[i]
        matrix=np.column_stack((b-a,-(d-c)))
        if abs(np.linalg.det(matrix))<1e-6:return dict(points=points,adjusted=False)
        corners.append(a+(b-a)*np.linalg.solve(matrix,c-a)[0])
    result=np.clip(np.asarray(corners)/[width-1,height-1],0,1)
    try:validate(result)
    except ValueError:return dict(points=points,adjusted=False)
    return dict(points=result.tolist(),adjusted=bool(adjusted))


def refine_surface_boundary(image, points):
    """Recover a paper/brocade transition, requiring agreement along each edge.

    Work on an analysis copy and reject inward moves across ink or seals.
    A wider search is used only when a sustained textured-outside / quiet-inside
    transition exists, never merely because a larger rectangle is possible.
    """
    small=image.copy();small.thumbnail((1800,1800))
    rgb=np.asarray(small);h,w=rgb.shape[:2]
    gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY).astype('float32')
    fine=np.abs(gray-cv2.GaussianBlur(gray,(0,0),1.2))
    texture=cv2.boxFilter(fine,-1,(7,7))
    p=validate(points).astype(float)*[w-1,h-1]
    short=min(np.linalg.norm(np.roll(p,-1,axis=0)-p,axis=1))
    radius=int(max(12,min(60,short*.14)))
    lines=[];evidence=[]
    for side in range(4):
        start,end=p[side],p[(side+1)%4];tangent=end-start
        normal=np.array([-tangent[1],tangent[0]])/np.linalg.norm(tangent)
        positions=np.linspace(.08,.92,360);offsets=np.arange(-radius-20,radius+21)
        coords=start+positions[:,None,None]*tangent+offsets[None,:,None]*normal
        valid=(coords[:,:,0]>=0)&(coords[:,:,0]<w-1)&(coords[:,:,1]>=0)&(coords[:,:,1]<h-1)
        strip=cv2.remap(texture,coords[:,:,0].astype('float32'),coords[:,:,1].astype('float32'),cv2.INTER_LINEAR)
        colors=cv2.remap(cv2.cvtColor(rgb,cv2.COLOR_RGB2LAB).astype('float32'),coords[:,:,0].astype('float32'),coords[:,:,1].astype('float32'),cv2.INTER_LINEAR)
        # Evaluate entire straight boundaries, rather than fitting independently
        # chosen local maxima that can come from unrelated brocade motifs.
        evidence_map=[]
        for k in range(20,len(offsets)-20):
            outer=np.median(strip[:,k-16:k-4],axis=1)
            inner=np.median(strip[:,k+4:k+16],axis=1)
            colour=np.linalg.norm((np.mean(colors[:,k-5:k-1],axis=1)-np.mean(colors[:,k+1:k+5],axis=1))*[.6,1,1],axis=1)
            usable=valid[:,k-16:k+16].all(axis=1)
            response=colour+12*np.maximum(0,outer-inner)-3*inner
            usable &= (outer>1.1)&(outer>inner*1.5)&(outer-inner>.45)
            evidence_map.append(np.where(usable,response,-20))
        response=np.asarray(evidence_map).T
        segments=np.array_split(np.arange(len(positions)),18)
        score_map=np.asarray([np.percentile(response[seg],35,axis=0) for seg in segments])
        t=np.asarray([positions[seg].mean() for seg in segments])
        endpoints=np.arange(-radius,radius+1,2)
        aa,bb=np.meshgrid(endpoints,endpoints);aa=aa.ravel();bb=bb.ravel()
        locations=aa[:,None]+(bb-aa)[:,None]*t
        indices=np.clip(np.rint(locations+radius).astype(int),0,2*radius)
        measured=score_map[np.arange(18)[None,:],indices]
        scores=np.percentile(measured,25,axis=1)-.018*np.mean(np.abs(locations),axis=1)
        best=int(np.argmax(scores));shift=slope=0.;support=0
        if scores[best]>3 and np.mean(measured[best]>3)>=.78:
            shift=float(aa[best])-1.;slope=float(bb[best]-aa[best]);support=int(np.sum(measured[best]>3))
        moves=shift+slope*positions
        swept=valid&(offsets[None,:]>=0)&(offsets[None,:]<=moves[:,None])
        protected=((colors[:,:,0]<75)|(colors[:,:,1]>150))&swept
        count,labels,stats,_=cv2.connectedComponentsWithStats(protected.astype('uint8'),8)
        if any(stat[cv2.CC_STAT_AREA]>=6 for stat in stats[1:]):
            shift=slope=0.;support=0
        lines.append((start+normal*shift,end+normal*(shift+slope)))
        evidence.append(dict(side=side,support=support,shift=round(float(shift),2),slope=round(float(slope),2)))
    corners=[]
    for i in range(4):
        a,b=lines[(i-1)%4];c,d=lines[i];matrix=np.column_stack((b-a,-(d-c)))
        if abs(np.linalg.det(matrix))<1e-6:return dict(points=points,surface_edges=evidence)
        corners.append(a+(b-a)*np.linalg.solve(matrix,c-a)[0])
    result=np.clip(np.asarray(corners)/[w-1,h-1],0,1)
    try:validate(result)
    except ValueError:return dict(points=points,surface_edges=evidence)
    return dict(points=result.tolist(),surface_edges=evidence)


def refine_native(image, points, wide=True):
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
        tilted_top=wide and side==0 and min(start[1],end[1])<radius and abs(end[1]-start[1])>radius
        if tilted_top:radius=min(100,max(radius,int(abs(end[1]-start[1]))))
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
        if (strength[index]>=3 and support>=.65) or tilted_top:
            # Fit separately measured segments, rejecting isolated strokes,
            # fingers and folds rather than following a single strong pixel.
            local=[]
            # An initially tilted edge can cross the true paper boundary at
            # different offsets in each segment. Search the full bounded strip;
            # the robust line fit below still requires eight agreeing segments.
            nearby=np.where(np.abs(search)<=radius)[0] if tilted_top else np.where(np.abs(search-chosen)<=5)[0]
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
        if tilted_top and shift==0 and slope==0:
            fallback=refine_native(image,points,wide=False)
            fp=np.asarray(fallback['points'])*[width-1,height-1]
            boundaries.append((fp[side],fp[(side+1)%4]))
            evidence.append(fallback['native_edges'][side])
            continue
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


def detect(path, rotation=0, expected_aspect=None):
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
    paper_light=cv2.morphologyEx(gray,cv2.MORPH_CLOSE,np.ones((17,17),np.uint8))
    ink=cv2.dilate((gray<np.maximum(dark_limit,paper_light*.72)).astype('uint8'),np.ones((5,5),np.uint8))>0
    light_surface=cv2.GaussianBlur(paper_light,(9,9),0).astype(float)

    def tall_surface_quad(contour):
        # Hands or a fold may attach a spur to an otherwise rectangular mask.
        # Recover its two long sides from the majority of rows, not the hull.
        cloud=contour[:,0,:]
        if np.ptp(cloud[:,1])<h*.6:return None
        rows=np.unique(cloud[:,1])
        bounds=[]
        for yy in rows:
            xs=cloud[cloud[:,1]==yy,0]
            bounds.append((yy,xs.min(),xs.max()))
        bounds=np.asarray(bounds,dtype=float)
        widths=bounds[:,2]-bounds[:,1]
        median=np.median(widths)
        keep=(widths>median*.75)&(widths<median*1.25)
        if keep.sum()<h*.45 or not w*.10<median<w*.85:return None
        data=bounds[keep]
        fits=[]
        for column in (1,2):
            good=np.ones(len(data),dtype=bool)
            for _ in range(4):
                fit=np.polyfit(data[good,0],data[good,column],1)
                residual=np.abs(data[:,column]-np.polyval(fit,data[:,0]))
                good=residual<max(3,float(np.percentile(residual,60)))
            fits.append(fit)
        top,bottom=np.percentile(data[:,0],[.5,99.5])
        return np.array([[np.polyval(fits[0],top),top],[np.polyval(fits[1],top),top],[np.polyval(fits[1],bottom),bottom],[np.polyval(fits[0],bottom),bottom]])

    def fit_paper_sides(contour, quad):
        # Polygon simplification may choose a corner dent caused by ink or a
        # fold. Fit each long side from its middle instead of that single dent.
        pts=quad.astype(float)
        center=pts.mean(axis=0)
        pts=pts[np.argsort(np.arctan2(pts[:,1]-center[1],pts[:,0]-center[0]))]
        pts=np.roll(pts,-np.argmin(pts.sum(axis=1)),axis=0)
        cloud=contour[:,0,:].astype(float)
        lines=[]
        for i in range(4):
            start,end=pts[i],pts[(i+1)%4]
            length=np.linalg.norm(end-start);tangent=(end-start)/max(length,1)
            normal=np.array([-tangent[1],tangent[0]])
            along=(cloud-start)@tangent;across=(cloud-start)@normal
            selected=cloud[(along>length*.08)&(along<length*.92)&(np.abs(across)<12)]
            if len(selected)<8:return pts
            vx,vy,x,y=cv2.fitLine(selected.astype('float32'),cv2.DIST_HUBER,0,.01,.01).ravel()
            direction=np.array([vx,vy],dtype=float)
            if abs(np.dot(direction,tangent))<.99:return pts
            # Allow one detection pixel outside the paper to protect edge ink.
            anchor=np.array([x,y])-normal
            lines.append((anchor,anchor+direction))
        corners=[]
        for i in range(4):
            a,b=lines[(i-1)%4];c,d=lines[i]
            matrix=np.column_stack((b-a,-(d-c)))
            if abs(np.linalg.det(matrix))<1e-6:return pts
            corners.append(a+(b-a)*np.linalg.solve(matrix,c-a)[0])
        return np.asarray(corners)

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
        inner_clean=inner&~ink;outer_clean=outer&~ink
        edge_noise=float(np.mean(texture[inner_clean])) if inner_clean.any() else 30
        outside_noise=float(np.mean(texture[outer_clean])) if outer_clean.any() else 0
        uniformity=1-min(edge_noise/22,1)
        contrast=min(max(outside_noise-edge_noise,0)/15,1)
        center_penalty=np.linalg.norm(center/[w,h]-.5)
        clean=(mask>0)&~ink
        interior_noise=float(np.mean(texture[clean]>12)) if clean.any() else 1.
        vectors=np.roll(pts,-1,axis=0)-pts
        corner_skew=max(abs(float(np.dot(vectors[i],vectors[(i+1)%4])))/(np.linalg.norm(vectors[i])*np.linalg.norm(vectors[(i+1)%4])+1e-6) for i in range(4))
        coverage=max(np.ptp(norm[:,0]),np.ptp(norm[:,1]))
        score=.10*area+.30*uniformity+.15*contrast+.12*rectangularity-.3*center_penalty-1.8*interior_noise+.25*coverage-.4*corner_skew
        if method.startswith('paper'): score+=.12
        if method=='paper-chroma': score+=.10
        if method=='paper-layout': score+=.35
        # Long lines also occur in the backdrop and between text columns.
        # They are fallback proposals, not evidence deserving a score bonus.
        # Dense handwriting is legitimate content, not background texture.
        # Independently reward a colour transition sustained along every side,
        # so a quiet strip of brocade cannot outrank the complete paper.
        colour_support=[]
        boundary_support=[]
        for side in range(4):
            start,end=pts[side],pts[(side+1)%4]
            tangent=end-start;normal=np.array([-tangent[1],tangent[0]])
            normal/=max(np.linalg.norm(normal),1)
            base=start+np.linspace(.1,.9,100)[:,None]*tangent
            inside=base+normal*5;outside=base-normal*5
            valid=(inside[:,0]>=0)&(inside[:,0]<w)&(inside[:,1]>=0)&(inside[:,1]<h)&(outside[:,0]>=0)&(outside[:,0]<w)&(outside[:,1]>=0)&(outside[:,1]<h)
            if valid.mean()<.7:
                colour_support.append(0.);boundary_support.append(0.);continue
            inn=inside[valid].astype(int);out=outside[valid].astype(int)
            difference=np.linalg.norm(lab[inn[:,1],inn[:,0],1:]-lab[out[:,1],out[:,0],1:],axis=1)
            colour_support.append(float(np.percentile(difference,35)))
            light_difference=np.abs(light_surface[inn[:,1],inn[:,0]]-light_surface[out[:,1],out[:,0]])
            boundary_support.append(min(1,max(colour_support[-1],float(np.percentile(light_difference,35)))/8))
        score+=.18*float(np.mean(boundary_support))+.50*min(boundary_support)
        if expected_aspect and method=='lines':
            side_lengths=np.linalg.norm(vectors,axis=1)
            aspect=(side_lengths[0]+side_lengths[2])/max(side_lengths[1]+side_lengths[3],1)
            # Ignore small perspective deviations. Reject selecting a single
            # text column or coloured panel within a much larger artwork.
            # The catalogue dimensions can be wrong (including square works
            # labelled as narrow scrolls). They may disambiguate incomplete
            # line proposals, but must never override a measured paper contour.
            score-=.8*max(0,abs(np.log(aspect/expected_aspect))-.18)
        record=dict(points=norm.tolist(),score=round(float(score),3),method=method,colour_support=colour_support)
        for i,c in enumerate(candidates):
            if np.mean(np.abs(norm-np.array(c['points'])))<.018:
                if score>c['score']:candidates[i]=record
                return
        candidates.append(record)

    noise=((texture>9)&(gray>80)&~ink).astype('float32')
    local_noise=cv2.boxFilter(noise,-1,(25,25))/np.maximum(.1,cv2.boxFilter((~ink).astype('float32'),-1,(25,25)))
    fine_noise=cv2.boxFilter(((texture>3)&~ink).astype('float32'),-1,(25,25))/np.maximum(.1,cv2.boxFilter((~ink).astype('float32'),-1,(25,25)))
    # White paper and white brocade may share a colour. Their fine surface
    # texture still differs; exclude ink before measuring that texture.
    for threshold in (.06,.10,.16,.22,.30,.40):
        mask=((fine_noise<threshold)&(gray_smooth>100)).astype('uint8')*255
        mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((27,27),np.uint8))
        mask=cv2.morphologyEx(mask,cv2.MORPH_OPEN,np.ones((11,11),np.uint8))
        contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_NONE)
        for contour in contours:
            area=cv2.contourArea(contour)
            if not .065*w*h<area<.95*w*h:continue
            rect=cv2.minAreaRect(contour)
            extent=area/max(rect[1][0]*rect[1][1],1)
            if extent<.65:continue
            robust=tall_surface_quad(contour)
            if robust is not None:add_quad(robust,'paper-surface',min(1,extent+.1))
            if extent<.88:continue
            hull=cv2.convexHull(contour)
            quad=cv2.approxPolyDP(hull,.02*cv2.arcLength(hull,True),True)
            if len(quad)==4:add_quad(fit_paper_sides(contour,quad[:,0,:]),'paper-surface',extent)
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
        # Paper illumination varies along a hanging scroll. Requiring matching
        # luminance fragments its contour and can make background lines win.
        # A narrow chroma-only mask bridges shadows without merging neutral
        # brocade into warm paper. Keep the original full-colour candidates too.
        if np.linalg.norm(seed[1:]-128)>2:
            chroma_distance=np.linalg.norm(lab[:,:,1:]-seed[1:],axis=2)
            thresholds=(3,4,5) if np.linalg.norm(seed[1:]-128)>6 else (1.5,2,2.5)
            for threshold in thresholds:
                mask=((chroma_distance<threshold)&(gray_smooth>75)).astype(np.uint8)*255
                mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((17,17),np.uint8))
                mask=cv2.morphologyEx(mask,cv2.MORPH_OPEN,np.ones((7,7),np.uint8))
                contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_NONE)
                for contour in contours:
                    area=cv2.contourArea(contour)
                    if not .065*w*h<area<.96*w*h:continue
                    rect=cv2.minAreaRect(contour)
                    extent=area/max(rect[1][0]*rect[1][1],1)
                    if extent<.88:continue
                    hull=cv2.convexHull(contour)
                    quad=cv2.approxPolyDP(hull,.015*cv2.arcLength(hull,True),True)
                    if len(quad)==4:add_quad(fit_paper_sides(contour,quad[:,0,:]),'paper-chroma',extent)
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
    # Multi-panel works can have a strong coloured lower panel and a quieter
    # title above it. Combine aligned paper proposals before ranking; otherwise
    # the most colourful panel can win over the complete sheet.
    layout_proposals=sorted(candidates,key=lambda x:x['score'],reverse=True)[:40]
    for outer in layout_proposals:
        if outer['method']=='lines':continue
        p=np.asarray(outer['points'])*[w-1,h-1]
        ph=np.ptp(p[:,1]);pw=np.ptp(p[:,0])
        if ph<h*.65 or pw>ph*.8:continue
        for inner in layout_proposals:
            if inner is outer or inner['method']=='lines':continue
            q=np.asarray(inner['points'])*[w-1,h-1]
            qh=np.ptp(q[:,1]);qw=np.ptp(q[:,0])
            if not .75<pw/max(qw,1)<1.33 or ph<qh*1.18:continue
            if abs(p[:,0].mean()-q[:,0].mean())>w*.025:continue
            overlap=min(p[:,1].max(),q[:,1].max())-max(p[:,1].min(),q[:,1].min())
            if overlap<qh*.85:continue
            merged=p.copy()
            for side,indices in ((0,(0,3)),(1,(1,2))):
                top,bottom=indices
                if abs(q[bottom,1]-q[top,1])<1:continue
                x=q[top,0]+(p[[top,bottom],1]-q[top,1])*(q[bottom,0]-q[top,0])/(q[bottom,1]-q[top,1])
                merged[[top,bottom],0]=np.minimum(p[[top,bottom],0],x) if side==0 else np.maximum(p[[top,bottom],0],x)
            add_quad(merged,'paper-layout')
    if expected_aspect and expected_aspect>.4:
        # A photographed pair of couplet sheets has a narrow mounting gutter.
        # Preserve both sheets when their common outline matches the supplied
        # combined dimensions; picking the more saturated half loses a work.
        sheets=[c for c in layout_proposals if c['method'] in ('paper','paper-chroma')]
        for left in sheets:
            p=np.asarray(left['points'])*[w-1,h-1]
            ph=np.ptp(p[:,1]);pw=np.ptp(p[:,0])
            if ph<h*.5:continue
            for right in sheets:
                q=np.asarray(right['points'])*[w-1,h-1]
                qh=np.ptp(q[:,1]);qw=np.ptp(q[:,0])
                gap=q[:,0].min()-p[:,0].max()
                if not -.01*w<gap<.04*w or not .7<pw/max(qw,1)<1.4 or not .85<ph/max(qh,1)<1.18:continue
                if abs(p[:,1].mean()-q[:,1].mean())>h*.03:continue
                merged=np.array([p[0],q[1],q[2],p[3]])
                aspect=(np.linalg.norm(merged[1]-merged[0])+np.linalg.norm(merged[2]-merged[3]))/max(1,np.linalg.norm(merged[3]-merged[0])+np.linalg.norm(merged[2]-merged[1]))
                if abs(np.log(aspect/expected_aspect))<.25:add_quad(merged,'paper-layout')
    for record in candidates:
        p=np.asarray(record['points'])
        ph=np.ptp(p[:,1]);pw=np.ptp(p[:,0])
        if ph<.30 or pw>.8*ph:continue
        for parent in candidates:
            q=np.asarray(parent['points'])
            qh=np.ptp(q[:,1]);qw=np.ptp(q[:,0])
            overlap=min(p[:,1].max(),q[:,1].max())-max(p[:,1].min(),q[:,1].min())
            if qh>max(.65,ph*1.18) and .75<qw/max(pw,1e-6)<1.33 and abs(p[:,0].mean()-q[:,0].mean())<.025 and overlap>ph*.85:
                record['score']=round(record['score']-.6,3)
                break
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
            # A colour-segmented paper already has a measured boundary.
            # The broad line-recovery search can otherwise jump into a text
            # column or an internal fold, throwing away that measurement.
            limit=5 if record['method'] in ('paper-chroma','paper-surface','paper-layout') else min(12,max(5,depth*.05))
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
                noise_map=fine_noise if record['method']=='paper-surface' else local_noise
                inner_noise=float(np.median(noise_map[inn[:,1],inn[:,0]]))
                outer_noise=float(np.median(noise_map[out[:,1],out[:,0]]))
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
            coarse_points=results[0]['points']
            surface=None
            if results[0]['method'].startswith(('paper-surface','paper-layout')) and min(results[0].get('colour_support',[0]))<2:
                surface=refine_surface_boundary(original,coarse_points)
                coarse_points=surface['points']
            native=refine_native(original,coarse_points)
            if surface:native['surface_edges']=surface['surface_edges']
        coarse=results[0]
        precise={**coarse,**native,'method':coarse['method']+'+native'}
        # Keep the coarse result available for immediate comparison/recovery.
        results=([precise,coarse]+results[1:])[:4]
    for c in results:
        c['review_note']='自动边界需复核；贴边笔画与印章请放大检查'
    return results
