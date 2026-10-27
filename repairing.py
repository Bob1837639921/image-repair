"""Confirmed-crop repair workflow. Source files are never modified."""
import base64
import hashlib
import io
import json
import math
import os
import re
import urllib.request
import urllib.error
import uuid
from urllib.parse import urlparse
from PIL import Image, ImageDraw
from imaging import cv2, np, render
from ai_config import load_connection,save_connection


def crop_signature(item):
    values={key:item.get(key) for key in ('file','points','rotation','settings','trim')}
    return hashlib.sha256(json.dumps(values,sort_keys=True).encode()).hexdigest()[:20]


def region_pixels(region,size):
    if not isinstance(region,list) or len(region)!=4:raise ValueError('请先框选修复区域')
    values=[float(x) for x in region]
    if not all(math.isfinite(x) and 0<=x<=1 for x in values):raise ValueError('区域超出图片')
    x1,y1,x2,y2=values;w,h=size
    rect=(round(x1*w),round(y1*h),round(x2*w),round(y2*h))
    if rect[2]-rect[0]<4 or rect[3]-rect[1]<4:raise ValueError('选区太小，请重新框选')
    return rect


def feather(size):
    w,h=size;y,x=np.mgrid[:h,:w]
    distance=np.minimum.reduce([x,y,w-1-x,h-1-y]).astype('float32')
    return np.clip(distance/max(2,min(20,min(w,h)*.15)),0,1)


def validate_brush(brush):
    """Normalized brush strokes: size is the diameter as a fraction of image width."""
    if not isinstance(brush,dict) or not isinstance(brush.get('paths'),list):raise ValueError('涂抹数据无效，请重新涂抹')
    size=float(brush.get('size',0))
    if not math.isfinite(size) or not 0<size<=.5:raise ValueError('笔刷大小无效')
    paths=brush['paths']
    if not 1<=len(paths)<=50:raise ValueError('涂抹笔画数量无效')
    clean=[];total=0
    for path in paths:
        if not isinstance(path,list) or not 1<=len(path)<=4000:raise ValueError('涂抹笔画无效')
        points=[]
        for point in path:
            if not isinstance(point,list) or len(point)!=2:raise ValueError('涂抹坐标无效')
            x,y=float(point[0]),float(point[1])
            if not (math.isfinite(x) and math.isfinite(y) and 0<=x<=1 and 0<=y<=1):raise ValueError('涂抹超出图片')
            points.append([x,y])
        total+=len(points);clean.append(points)
    if total>20000:raise ValueError('涂抹过长，请分成几处标记')
    return dict(size=size,paths=clean)


def brush_mask(brush,size,rect):
    """Rasterize normalized brush paths into a boolean mask covering `rect`."""
    w,h=size;x1,y1,x2,y2=rect
    mask=np.zeros((y2-y1,x2-x1),'uint8');radius=max(1,round(float(brush['size'])*w/2))
    for path in brush['paths']:
        points=np.rint(np.asarray(path,'float64')*[w,h]-[x1,y1]).astype('int32')
        if len(points)>1:cv2.polylines(mask,[points.reshape(-1,1,2)],False,1,thickness=2*radius+1)
        for x,y in points:cv2.circle(mask,(int(x),int(y)),radius,1,-1)
    return mask.astype(bool),radius


def brush_alpha(mask,radius):
    """Blend weight that is 1 inside the stroke and fades to 0 at its edge only."""
    distance=cv2.distanceTransform(np.pad(mask,1).astype('uint8'),cv2.DIST_L2,3)[1:-1,1:-1]
    return np.clip(distance/max(1.,radius*.6),0,1).astype('float32')


def blemish_repair(image,rect,strength,alpha_mask=None):
    """User-authorized paper replacement using nearby measured texture, not fill."""
    x1,y1,x2,y2=rect;w,h=x2-x1,y2-y1;gap=max(3,round(min(w,h)*.12))
    box=(max(0,x1-gap*2),max(0,y1-gap*2),min(image.width,x2+gap*2),min(image.height,y2+gap*2))
    rgb=np.asarray(image.crop(box)).astype('float32')
    ring=np.ones(rgb.shape[:2],bool);ring[y1-box[1]:y2-box[1],x1-box[0]:x2-box[0]]=False
    if not ring.any():raise ValueError('瑕疵选区太大，请缩小选区并保留周边纸面')
    paper=np.median(rgb[ring],axis=0);reference=float(np.dot(paper,[.299,.587,.114]))
    best=None;best_score=float('inf');seen=set()
    for radius in (1,2,3):
        for dx,dy in ((0,-1),(0,1),(-1,0),(1,0),(-1,-1),(1,-1),(-1,1),(1,1)):
            xx=max(0,min(image.width-w,x1+dx*(w+gap)*radius));yy=max(0,min(image.height-h,y1+dy*(h+gap)*radius))
            if (xx,yy) in seen or (min(xx+w,x2)>max(xx,x1) and min(yy+h,y2)>max(yy,y1)):continue
            seen.add((xx,yy));donor=np.asarray(image.crop((xx,yy,xx+w,yy+h))).astype('float32')
            gray=cv2.cvtColor(donor,cv2.COLOR_RGB2GRAY)
            # Do not clone nearby letters or red seals into the blank repair.
            if float(np.mean(gray<max(30,reference*.68)))>.002:continue
            med=np.median(donor.reshape(-1,3),axis=0)
            chroma=np.linalg.norm((donor-med).reshape(-1,3),axis=1)
            if float(np.mean(chroma>55))>.01:continue
            light=cv2.GaussianBlur(gray,(0,0),max(1,min(8,min(w,h)*.12)))
            spread=float(np.percentile(light,95)-np.percentile(light,5))
            score=float(np.linalg.norm(med-paper))+.8*spread+.002*math.hypot(xx-x1,yy-y1)
            if score<best_score:best_score=score;best=donor+paper-med
    if best is None:raise ValueError('周边没有足够干净的纸纹，请缩小选区或使用 AI 修复')
    before=np.asarray(image.crop(rect)).astype('float32')
    alpha=(feather((w,h)) if alpha_mask is None else alpha_mask)[:,:,None]*min(1,strength*1.6)
    patch=np.rint(np.clip(before*(1-alpha)+np.clip(best,0,255)*alpha,0,255)).astype('uint8')
    out=image.copy();out.paste(Image.fromarray(patch),(x1,y1));return out


def _weighted_blur(value,weight,sigma_x,sigma_y,fallback):
    """Normalized convolution: average only pixels with weight, keep fallback where none."""
    den=cv2.GaussianBlur(weight,(0,0),sigmaX=sigma_x,sigmaY=sigma_y)
    num=cv2.GaussianBlur(value*weight,(0,0),sigmaX=sigma_x,sigmaY=sigma_y)
    return np.where(den>1e-3,num/np.maximum(den,1e-3),fallback),den


def _fold_shift(R,weight,band):
    """Per-row horizontal offset of a roughly vertical fold inside `band`.

    The fold is located where the across-fold gradient is strongest, then
    median-filtered and smoothed so ink, specks and noise cannot bend it.
    Returns zeros when the fold cannot be traced reliably.
    """
    shift=np.zeros(R.shape[0],'float32')
    rows=np.nonzero(band.any(1))[0]
    if len(rows)<9:return shift
    dx=cv2.Sobel(cv2.GaussianBlur(R,(0,0),1.2),cv2.CV_32F,1,0)
    # Keep well clear of stroke ends: their crisp edges would capture the trace.
    clear=cv2.erode((weight>.5).astype('uint8'),np.ones((9,9),'uint8')).astype('float32')
    energy=cv2.GaussianBlur(dx*dx*clear,(0,0),sigmaX=.5,sigmaY=2)
    typical=float(np.median(energy[band]))
    energy=np.where(band,energy,-1)[rows]
    centre=energy.argmax(1).astype('float32');peak=energy.max(1)
    if not np.median(peak)>4*max(typical,1e-9):return shift  # no clear fold edge
    # Rows hidden by strokes have no usable edge; bridge them from good rows.
    good=peak>.25*float(np.median(peak))
    if good.sum()<9:return shift
    centre=np.interp(rows,rows[good],centre[good]).astype('float32')
    k=9;padded=np.pad(centre,k//2,mode='edge')
    centre=np.median(np.lib.stride_tricks.sliding_window_view(padded,k),axis=1)
    kernel=np.exp(-.5*(np.arange(-8,9)/3.)**2);kernel/=kernel.sum()
    centre=np.convolve(np.pad(centre,8,mode='edge'),kernel,mode='valid')
    full=np.interp(np.arange(R.shape[0]),rows,centre).astype('float32')
    return full-float(np.median(centre))


def crease_correction(rgb,gray,sel,short,long,focus=None,trace=False):
    """Direction-aware multiplicative shading field for a fold.

    Returns (log_gain, protected) or None when the selection has no dominant
    direction. A fold is coherent along its length while paper grain and ink
    are not, so the shading profile is averaged along the fold only. Deep but
    soft, elongated, fold-aligned dark lines are treated as fold, not ink.
    `focus` (box-sized bool mask, e.g. a brush stroke) replaces the rectangle
    `sel` as the analysed area. With `trace`, fold geometry is returned instead.
    """
    if focus is None:focus=np.zeros(gray.shape,bool);focus[sel]=True
    lab=cv2.cvtColor(rgb.astype('uint8'),cv2.COLOR_RGB2LAB).astype('float32')
    chroma=np.linalg.norm(lab[:,:,1:]-np.median(lab.reshape(-1,3),axis=0)[1:],axis=2)
    seal=chroma>30
    radius=max(5,min(41,round(min(gray.shape)*.12)))|1
    closed=cv2.morphologyEx(gray,cv2.MORPH_CLOSE,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(radius,radius)))
    ratio=gray/np.maximum(closed,1)
    dark=(ratio<.72)|(gray<float(np.percentile(gray,75))*.65)
    firm=(ratio<.5)|seal
    # Dominant direction from a structure tensor that ignores strokes and seals.
    lg=np.log1p(gray)
    smooth=cv2.GaussianBlur(lg,(0,0),1.5)
    gx=cv2.Sobel(smooth,cv2.CV_32F,1,0)/8;gy=cv2.Sobel(smooth,cv2.CV_32F,0,1)/8
    usable=~cv2.dilate(firm.astype('uint8'),np.ones((7,7),'uint8')).astype(bool)
    usable&=focus
    if usable.sum()<50:return None
    jxx,jyy,jxy=[float(v[usable].sum()) for v in (gx*gx,gy*gy,gx*gy)]
    # Plain grain and crossing folds measure ~0.01; a faint diagonal fold ~0.16.
    if jxx+jyy<=1e-9 or math.hypot(jxx-jyy,2*jxy)/(jxx+jyy)<.1:return None
    normal=.5*math.degrees(math.atan2(2*jxy,jxx-jyy));along_angle=normal+90
    # Soft, elongated, fold-aligned mid-dark components are the fold itself.
    candidates=(dark&~firm).astype('uint8')
    count,labels,stats,_=cv2.connectedComponentsWithStats(candidates,connectivity=8)
    edge=cv2.GaussianBlur(gray,(0,0),.7)
    gradient=np.hypot(cv2.Sobel(edge,cv2.CV_32F,1,0),cv2.Sobel(edge,cv2.CV_32F,0,1))/8
    # A fold crossing a stroke must not inherit the stroke's crisp edge.
    gradient[cv2.dilate(firm.astype('uint8'),np.ones((5,5),'uint8')).astype(bool)]=0
    gradient=cv2.dilate(gradient,np.ones((5,5),'uint8'))
    depth=closed-gray;foldlike=np.zeros(gray.shape,bool);pieces=[]
    for index in range(1,count):
        x,y,w,h,area=stats[index]
        if area<12:continue
        part=labels[y:y+h,x:x+w]==index;ys,xs=np.nonzero(part)
        cov=np.cov(np.vstack([xs,ys]).astype('float32'))
        major,minor=np.linalg.eigvalsh(cov)[::-1]
        axis=.5*math.degrees(math.atan2(2*cov[0,1],cov[0,0]-cov[1,1]))
        if 4*math.sqrt(max(major,0))<20 or math.sqrt(major/max(minor,.25))<3:continue
        if abs((axis-along_angle+90)%180-90)>20:continue
        # Ink has crisp edges; a fold shadow ramps gently. Use the strongest
        # edge around the whole component, not just its interior.
        y0,x0,y1,x1=max(0,y-3),max(0,x-3),min(gray.shape[0],y+h+3),min(gray.shape[1],x+w+3)
        ring=cv2.dilate((labels[y0:y1,x0:x1]==index).astype('uint8'),np.ones((5,5),'uint8')).astype(bool)
        soft=float(gradient[y0:y1,x0:x1][ring].max())/max(float(depth[y:y+h,x:x+w][part].max()),1)
        if soft>.45:continue
        pieces.append((xs+x,ys+y,np.s_[y:y+h,x:x+w],part))
    # A fold runs across most of the selection; a parallel faint stroke is only
    # character-sized. Group collinear pieces (crossing strokes split a fold)
    # and require them to cover at least half of the selection along the fold.
    nx,ny=math.cos(math.radians(normal)),math.sin(math.radians(normal))
    offset=lambda xs,ys:xs*nx+ys*ny
    clusters=[]
    for piece in sorted(pieces,key=lambda p:float(np.median(offset(p[0],p[1])))):
        position=float(np.median(offset(piece[0],piece[1])))
        if clusters and position-clusters[-1][0]<=4:clusters[-1][1].append(piece);clusters[-1][0]=position
        else:clusters.append([position,[piece]])
    sy,sx=np.nonzero(focus)
    for position,group in clusters:
        chord=float(np.count_nonzero(np.abs(offset(sx,sy)-position)<=2))/5
        spans=[]
        for xs,ys,_,_ in group:
            inside=focus[ys,xs]
            if inside.any():t=-xs[inside]*ny+ys[inside]*nx;spans.append((float(t.min()),float(t.max())))
        covered=0;end=-math.inf
        for start,stop in sorted(spans):
            if start>end+30:covered+=stop-start;end=stop
            elif stop>end:covered+=stop-end;end=stop
        if chord>0 and covered>=.5*chord:
            for _,_,where,part in group:foldlike[where]|=part
    protected=cv2.dilate(((dark&~foldlike)|seal).astype('uint8'),np.ones((3,3),'uint8')).astype(bool)
    # Make the fold run roughly vertically with an exact quarter turn, then
    # shear rows so it is straight and vertical. Only one sub-pixel resample is
    # made each way, so a 1-2 px seam keeps its sharpness in the correction.
    turns=0 if abs(normal)<=45 else 1
    turn=lambda a:np.ascontiguousarray(np.rot90(a,turns))
    R=turn(lg);weight=turn((~protected).astype('float32'))
    band=turn(focus)
    # Residual tilt measured again in the turned frame (always within +-45 deg).
    tx=cv2.Sobel(turn(smooth),cv2.CV_32F,1,0);ty=cv2.Sobel(turn(smooth),cv2.CV_32F,0,1)
    use=band&turn(~cv2.dilate(firm.astype('uint8'),np.ones((7,7),'uint8')).astype(bool))
    tilt=.5*math.atan2(2*float((tx*ty)[use].sum()),float((tx*tx-ty*ty)[use].sum()))
    rows,cols=np.mgrid[:R.shape[0],:R.shape[1]].astype('float32')
    centre_row=float(np.mean(np.nonzero(band.any(1))[0]))
    shift=(-math.tan(tilt)*(np.arange(R.shape[0])-centre_row)).astype('float32')
    warp=lambda a,s,mode=cv2.INTER_LINEAR,border=cv2.BORDER_REPLICATE:cv2.remap(a,cols+s[:,None],rows,mode,borderMode=border,borderValue=0)
    # Real folds wander. Trace the fold row by row on the sheared image and
    # add that to the shear, so the along-fold average follows the real line.
    shift=shift+_fold_shift(warp(R,shift),warp(weight,shift,border=cv2.BORDER_CONSTANT),warp(band.astype('float32'),shift,border=cv2.BORDER_CONSTANT)>.5)
    inside=warp(np.ones_like(R),shift,border=cv2.BORDER_CONSTANT)>.99
    R=warp(R,shift,cv2.INTER_CUBIC);weight=warp(weight,shift,border=cv2.BORDER_CONSTANT)*inside
    length=float(np.clip(long*.12,8,40))
    profile,_=_weighted_blur(R,weight,.5,length,R)
    weight=weight*(np.abs(R-profile)<.1)
    profile,den=_weighted_blur(R,weight,.5,length,profile)
    covered=((den>1e-3)&inside).astype('float32')
    across=float(np.clip(short*.35,10,60))
    level,_=_weighted_blur(profile,covered,across,.5,profile)
    level,_=_weighted_blur(profile,covered*(np.abs(profile-level)<.02),across,.5,level)
    if trace:
        # Where the fold sits in the straightened frame, and how wide it is.
        rows_in=np.nonzero((warp(band.astype('float32'),shift,border=cv2.BORDER_CONSTANT)>.5).any(1))[0]
        if len(rows_in)<2:return None
        column=np.where(inside,np.abs(level-profile),0)[rows_in].mean(0)
        centre=int(column.argmax());peak=float(column[centre]);lo=hi=centre
        # Half-peak extent; centre on it so a one-sided step shadow is covered.
        while lo>0 and column[lo-1]>.5*peak:lo-=1
        while hi<len(column)-1 and column[hi+1]>.5*peak:hi+=1
        return dict(turns=turns,shift=shift,centre=(lo+hi)/2,half=(hi-lo)/2,rows=rows_in,peak=peak)
    back=lambda a,mode=cv2.INTER_CUBIC:np.ascontiguousarray(np.rot90(warp(a,-shift,mode),-turns))
    gain=back(np.where(inside,level-profile,0).astype('float32'))
    # Faint, non-coherent dark marks (light ink) stay exactly unchanged too.
    faint=back(((R-profile<-.12)&inside).astype('float32'),cv2.INTER_LINEAR)>.5
    protected|=cv2.dilate(faint.astype('uint8'),np.ones((3,3),'uint8')).astype(bool)
    gain*=np.clip((np.abs(gain)-.004)/.012,0,1)
    gain=np.clip(gain,-.3,.45)
    guard=1-cv2.GaussianBlur(protected.astype('float32'),(0,0),1)
    return np.where(protected,0,gain*guard),protected


def local_repair(image,region,strength=.65,kind='crease',brush=None):
    if kind not in ('crease','bump','blemish'):raise ValueError('请选择折痕、凸起或瑕疵去除')
    strength=float(strength)
    if not math.isfinite(strength) or not 0<=strength<=1:raise ValueError('强度范围为 0–1')
    rect=region_pixels(region,image.size);x1,y1,x2,y2=rect
    stroke=None
    if brush:
        # Painted marks: repair only inside the stroke, feathered at its edge.
        stroke,brush_radius=brush_mask(brush,image.size,rect)
        if not stroke.any():raise ValueError('涂抹区域为空，请重新涂抹')
        stroke_alpha=brush_alpha(stroke,brush_radius)
    if kind=='blemish':return blemish_repair(image,rect,strength,stroke_alpha if brush else None)
    short=min(x2-x1,y2-y1)
    pad=max(32,min(320,short))
    box=(max(0,x1-pad),max(0,y1-pad),min(image.width,x2+pad),min(image.height,y2+pad))
    rgb=np.asarray(image.crop(box)).astype('float32');gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
    left,top=x1-box[0],y1-box[1];w,h=x2-x1,y2-y1
    if kind=='crease':
        focus=None
        if brush:focus=np.zeros(gray.shape,bool);focus[top:top+h,left:left+w]=stroke
        field=crease_correction(rgb,gray,np.s_[top:top+h,left:left+w],short,max(w,h),focus)
        if field is not None:
            # Shadows scale all channels, so correct multiplicatively.
            fixed=np.clip(rgb*np.exp(field[0]*strength)[:,:,None],0,255)
            before=rgb[top:top+h,left:left+w];after=fixed[top:top+h,left:left+w]
            alpha=(feather((w,h)) if stroke is None else stroke_alpha)[:,:,None]
            patch=np.rint(before*(1-alpha)+after*alpha).astype('uint8')
            out=image.copy();out.paste(Image.fromarray(patch),(x1,y1));return out
    # Close dark strokes out of the illumination estimate, not the output.
    radius=max(5,min(41,round(min(rgb.shape[:2])*.12)))|1
    closed=cv2.morphologyEx(gray,cv2.MORPH_CLOSE,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(radius,radius)))
    lab=cv2.cvtColor(rgb.astype('uint8'),cv2.COLOR_RGB2LAB).astype(float)
    bg_color=np.median(lab.reshape(-1,3),axis=0)
    chroma=np.linalg.norm(lab[:,:,1:]-bg_color[1:],axis=2)
    protected=(gray<closed*.72)|(gray<float(np.percentile(gray,75))*.65)|(chroma>30)
    # Estimate illumination only from paper, never from ink/seals. Normalized
    # convolution avoids dark stroke halos without blurring the output pixels.
    protected=cv2.dilate(protected.astype('uint8'),np.ones((3,3),'uint8')).astype(bool)
    paper=(~protected).astype('float32')
    if not np.any(paper):return image.copy()
    def illumination(sigma):
        weight=cv2.GaussianBlur(paper,(0,0),sigma)
        value=cv2.GaussianBlur(gray*paper,(0,0),sigma)
        return np.divide(value,weight,out=np.full_like(gray,float(np.median(gray[~protected]))),where=weight>1e-4)
    # Broad bulges and narrow folds require different spatial scales. Grain is
    # kept in the original RGB pixels; only a smooth, additive light field moves.
    detail_scale=max(6,min(28,short*.06)) if kind=='bump' else max(2.5,min(6,short*.025))
    bg=illumination(detail_scale)
    smooth=illumination(max(detail_scale*3,short*.65))
    delta=smooth-bg
    if kind=='crease':
        # Ignore tiny variations rather than treating ordinary grain as a fold.
        delta*=np.clip((np.abs(delta)-1)/3,0,1)
        delta=cv2.GaussianBlur(delta,(0,0),1)
    delta=np.clip(delta,-35,35)
    # A soft protection margin suppresses transitions next to strokes; pixels
    # classified as ink/seals remain exactly unchanged.
    guard=1-cv2.GaussianBlur(protected.astype('float32'),(0,0),2)
    delta*=np.where(protected,0,guard)*strength
    fixed=np.clip(rgb+delta[:,:,None],0,255)
    left,top=x1-box[0],y1-box[1];w,h=x2-x1,y2-y1
    before=rgb[top:top+h,left:left+w];after=fixed[top:top+h,left:left+w]
    alpha=(feather((w,h)) if stroke is None else stroke_alpha)[:,:,None]
    patch=np.rint(before*(1-alpha)+after*alpha).astype('uint8')
    out=image.copy();out.paste(Image.fromarray(patch),(x1,y1));return out


def snap_crease(image,region,brush):
    """Trace locally across the user's path; unsupported parts stay untouched.

    Searching in path normals avoids the old global dominant-line fit jumping
    between nearby folds. Ink/seal gaps are deliberately not interpolated.
    """
    rect=region_pixels(region,image.size);x1,y1,x2,y2=rect
    radius=max(1,round(float(brush['size'])*image.width/2))
    pad=max(16,min(100,radius+12))
    box=(max(0,x1-pad),max(0,y1-pad),min(image.width,x2+pad),min(image.height,y2+pad))
    rgb=np.asarray(image.crop(box)).astype('float32');gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
    closed=cv2.morphologyEx(gray,cv2.MORPH_CLOSE,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(15,15)))
    lab=cv2.cvtColor(rgb.astype('uint8'),cv2.COLOR_RGB2LAB).astype('float32')
    chroma=np.linalg.norm(lab[:,:,1:]-np.median(lab.reshape(-1,3),axis=0)[1:],axis=2)
    ink=(gray<closed*.72)|(chroma>30)
    clear=1-cv2.dilate(ink.astype('uint8'),np.ones((9,9),'uint8')).astype('float32')
    light=cv2.GaussianBlur(np.log1p(gray),(0,0),1.2)
    gx=cv2.Sobel(light,cv2.CV_32F,1,0)/8;gy=cv2.Sobel(light,cv2.CV_32F,0,1)/8
    reach=min(48,max(2,radius*.7));offsets=np.arange(-math.floor(reach),math.floor(reach)+1,dtype='float32')
    along=np.arange(-4,5,dtype='float32')
    paths=[];confidences=[];widths=[]
    for path in brush['paths']:
        original=np.asarray(path,'float32')*[image.width,image.height]-box[:2]
        if len(original)<2:paths.append(path);confidences.extend([False]);continue
        distances=np.r_[0,np.cumsum(np.linalg.norm(np.diff(original,axis=0),axis=1))]
        keep=np.r_[True,np.diff(distances)>1e-4];original=original[keep];distances=distances[keep]
        if len(original)<2:paths.append(path);confidences.extend([False]);continue
        samples=np.linspace(0,distances[-1],min(2000,max(2,math.ceil(distances[-1]/4)+1)))
        points=np.column_stack([np.interp(samples,distances,original[:,axis]) for axis in (0,1)])
        tangent=np.gradient(points,axis=0);tangent/=np.maximum(np.linalg.norm(tangent,axis=1)[:,None],1e-6)
        normal=np.column_stack([-tangent[:,1],tangent[:,0]])
        shifts=np.zeros(len(points));good=np.zeros(len(points),bool)
        for i,(point,t,n) in enumerate(zip(points,tangent,normal)):
            xy=point+offsets[:,None,None]*n+along[None,:,None]*t
            mx=xy[:,:,0].astype('float32');my=xy[:,:,1].astype('float32')
            sample=lambda a:cv2.remap(a,mx,my,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
            valid=sample(clear)*(mx>=0)*(my>=0)*(mx<gray.shape[1]-1)*(my<gray.shape[0]-1)
            gradients=sample(gx)*n[0]+sample(gy)*n[1]
            weight=valid.sum(1)
            signed=(gradients*valid).sum(1)/np.maximum(weight,1)
            energy=np.abs(signed)
            # Grain is incoherent along the fold; require a coherent local edge.
            coherence=np.abs((gradients*valid).sum(1))/np.maximum((np.abs(gradients)*valid).sum(1),1e-6)
            noise=max(.0015,float(np.median(energy)))
            score=energy*np.exp(-.6*(offsets/max(reach,1))**2)
            score[(weight<7)|(coherence<.7)]=0
            peak=int(score.argmax())
            if peak in (0,len(offsets)-1) or energy[peak]<max(.004,noise*3):continue
            # Never move the user's mark onto a letter, including obscured folds.
            origin=sample(clear)[len(offsets)//2]
            if origin.min()<.99:continue
            lo=hi=peak
            while lo>0 and energy[lo-1]>.4*energy[peak]:lo-=1
            while hi<len(offsets)-1 and energy[hi+1]>.4*energy[peak]:hi+=1
            # A narrow ridge has two opposite slopes. Centre on both sides,
            # rather than snapping to whichever edge happens to be darker.
            paired=(signed*signed[peak]<0)&(energy>.4*energy[peak])&(weight>=7)&(coherence>=.7)
            paired&=(np.abs(offsets-offsets[peak])<=min(10,max(4,radius*.5)))
            if paired.any():
                mate=int(np.where(paired,score,-1).argmax())
                lo=min(lo,mate);hi=max(hi,mate)
            shifts[i]=float((offsets[lo]+offsets[hi])/2);good[i]=True
            widths.append(float(hi-lo+8))
        # Isolated detections are often specks. Only smooth contiguous confident
        # runs; do not pull uncertain sections across ink or missing folds.
        for start in np.nonzero(good&~np.r_[False,good[:-1]])[0]:
            end=start
            while end<len(good) and good[end]:end+=1
            if end-start<3:good[start:end]=False;continue
            run=shifts[start:end];padded=np.pad(run,1,mode='edge')
            shifts[start:end]=np.median(np.lib.stride_tricks.sliding_window_view(padded,3),axis=1)
        shifts[~good]=0
        adjusted=points+shifts[:,None]*normal
        normalized=np.clip((adjusted+box[:2])/[image.width,image.height],0,1)
        paths.append(normalized.tolist());confidences.extend(good.tolist())
    if not any(confidences):return None
    # The current brush format has one width. Retain it whenever any section
    # could not be fitted, so uncertain paper is not silently excluded.
    diameter=2*radius
    if all(confidences) and widths:diameter=min(diameter,max(8,float(np.percentile(widths,90))))
    points=np.concatenate([np.asarray(path)*[image.width,image.height] for path in paths]);r=diameter/2+2
    lower=np.maximum(0,(points.min(0)-r)/[image.width,image.height]);upper=np.minimum(1,(points.max(0)+r)/[image.width,image.height])
    return dict(brush=dict(size=diameter/image.width,paths=paths),region=[*lower.tolist(),*upper.tolist()])


REPAIR_LEVELS={'light':.3,'standard':.65,'strong':1.0}


def mark_strength(mark,default=.65):
    level=mark.get('level')
    if level is not None and (not isinstance(level,str) or level not in REPAIR_LEVELS):raise ValueError('修复等级须为轻度、标准或加强')
    return REPAIR_LEVELS[level] if level else default


def repair_prompt(kind,annotation=None):
    task={'crease':'Repair a localized paper fold: reduce the narrow bright ridge, dark crease line and paired fold shadow, blending into the adjacent paper texture without blurring ink.',
          'bump':'Repair a localized paper bulge: even the broad highlight/shadow gradient caused by the raised paper while preserving natural paper grain. Do not treat it as a thin crack or erase intentional strokes.',
          'blemish':'The user marked a blank-paper blemish for stronger restoration. Remove the localized particle, speck, stain or dent with its highlight and shadow. Reconstruct natural paper grain from adjacent clean paper, not a flat colour or blurred patch. Keep intentional ink, seals and gold rules unchanged.'}[kind]
    intensity={'light':'Use a light correction, reducing the defect gently while retaining some original shading.',
               'standard':'Use a standard correction, clearly reducing the defect while retaining natural paper texture.',
               'strong':'Use a strong correction, removing as much of the marked defect as possible while preserving ink and natural paper texture.'}.get((annotation or {}).get('level'),'')
    return ('Conservative archival restoration of a Chinese calligraphy photograph. The user explicitly classified this masked region as '+kind+'. '+task+' '+intensity+
            ' Modify only the transparent mask. Surrounding pixels are reference only. Preserve the exact shape, position, thickness and tonal variation of every ink stroke, inscription and seal, including faint ink and strokes crossing the defect. Preserve the original paper colour, ink colour, seal colour, white balance, exposure, saturation, printed patterns and grain; match the adjacent unmasked paper with no colour cast or visible patch seams. Do not apply global colour grading or change resolution, aspect ratio or composition. Added canvas padding is reference only and must not move the artwork. Do not invent or reconstruct illegible characters, remove seals, whiten the paper, sharpen, recolour, rotate, warp or redraw the artwork. If a detail cannot be distinguished from ink, leave it unchanged. No added text or borders. '+
            ('User annotation metadata (original image normalized coordinates): '+json.dumps({k:v for k,v in annotation.items() if k!='brush'},ensure_ascii=False) if annotation else ''))


def validate_regions(regions,size):
    if not isinstance(regions,list) or not 1<=len(regions)<=100:raise ValueError('请标记 1–100 个修复区域')
    result=[];ids=set()
    for index,mark in enumerate(regions):
        if not isinstance(mark,dict) or mark.get('kind') not in ('crease','bump','blemish'):raise ValueError('每个区域都需要选择折痕、凸起或瑕疵去除')
        region_pixels(mark.get('region'),size)
        key=str(mark.get('id',index+1))
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',key) or key in ids:raise ValueError('标记编号无效或重复')
        clean=dict(id=key,region=[float(v) for v in mark['region']],kind=mark['kind'])
        if mark.get('level') is not None:
            mark_strength(mark);clean['level']=mark['level']
        if mark.get('brush') is not None:clean['brush']=validate_brush(mark['brush'])
        ids.add(key);result.append(clean)
    return result


def verify_ai_patch(before,after):
    """Conservative rejection heuristic, not a guarantee of unchanged calligraphy."""
    a=np.asarray(before.convert('RGB'));b=np.asarray(after.convert('RGB'))
    if a.shape!=b.shape:raise ValueError('AI 结果尺寸不一致，已拒绝使用')
    gray=cv2.cvtColor(a,cv2.COLOR_RGB2GRAY);other=cv2.cvtColor(b,cv2.COLOR_RGB2GRAY)
    threshold=max(12,float(np.percentile(gray,75))*.55)
    ink=(gray<threshold).astype('uint8');new=(other<threshold).astype('uint8');kernel=np.ones((3,3),'uint8')
    lost=int(np.count_nonzero(ink&(1-cv2.dilate(new,kernel))));added=int(np.count_nonzero(new&(1-cv2.dilate(ink,kernel))))
    limit=max(8,int(ink.sum()*.04))
    if lost>limit or added>limit:raise ValueError('AI 结果疑似改动笔画或印章，已拦截；请缩小选区或改用常规修复')
    lab=cv2.cvtColor(a,cv2.COLOR_RGB2LAB).astype(float);lab_new=cv2.cvtColor(b,cv2.COLOR_RGB2LAB).astype(float)
    paper=(gray>=np.percentile(gray,45))&(ink==0)
    if paper.sum()>20:
        cast=np.median(lab_new[:,:,1:][paper]-lab[:,:,1:][paper],axis=0)
        if np.linalg.norm(cast)>7:raise ValueError('AI 结果出现明显纸色色差，已拦截；请重试或缩小选区')


def protected_ink(image):
    pixels=np.asarray(image.convert('RGB'));gray=cv2.cvtColor(pixels,cv2.COLOR_RGB2GRAY)
    paper=cv2.morphologyEx(gray,cv2.MORPH_CLOSE,np.ones((21,21),np.uint8))
    ink=gray<np.maximum(65,paper.astype(float)*.72)
    red=(pixels[:,:,0].astype(float)-pixels[:,:,1]>20)&(pixels[:,:,0].astype(float)-pixels[:,:,2]>15)
    return cv2.dilate((ink|red).astype('uint8'),np.ones((9,9),np.uint8))>0


def image_data_url(image):
    buffer=io.BytesIO();image.save(buffer,'PNG')
    return 'data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode()


def ai_repair(image,region,key,kind='crease',base_url='https://api.openai.com/v1',model='gpt-image-1.5',annotation=None):
    if not key:raise ValueError('请先在 AI 连接中配置 OpenAI API Key')
    x1,y1,x2,y2=region_pixels(region,image.size)
    pad=max(32,min(200,max(x2-x1,y2-y1)//4))
    box=(max(0,x1-pad),max(0,y1-pad),min(image.width,x2+pad),min(image.height,y2+pad))
    context=image.crop(box);ratio=context.width/context.height
    units=(3,2) if ratio>1.2 else (2,3) if ratio<.83 else (1,1)
    unit=math.ceil(max(context.width/units[0],context.height/units[1]));canvas_size=(units[0]*unit,units[1]*unit)
    offset=((canvas_size[0]-context.width)//2,(canvas_size[1]-context.height)//2)
    colour=tuple(int(v) for v in np.median(np.asarray(context).reshape(-1,3),axis=0))
    canvas=Image.new('RGB',canvas_size,colour);canvas.paste(context,offset)
    mask=Image.new('RGBA',canvas_size,(255,255,255,255))
    ImageDraw.Draw(mask).rectangle((x1-box[0]+offset[0],y1-box[1]+offset[1],x2-box[0]-1+offset[0],y2-box[1]-1+offset[1]),fill=(0,0,0,0))
    brush=(annotation or {}).get('brush')
    if brush:
        # Only the painted stroke is editable; the rest of the box stays opaque.
        stroke,_=brush_mask(brush,image.size,(x1,y1,x2,y2))
        pixels=np.array(mask);inner=pixels[y1-box[1]+offset[1]:y2-box[1]+offset[1],x1-box[0]+offset[0]:x2-box[0]+offset[0]]
        inner[~stroke,3]=255;mask=Image.fromarray(pixels)
    protected=protected_ink(canvas)
    mask_pixels=np.array(mask);mask_pixels[protected,3]=255;mask=Image.fromarray(mask_pixels)
    output_size='1536x1024' if units==(3,2) else '1024x1536' if units==(2,3) else '1024x1024'
    fields={'model':model,'prompt':repair_prompt(kind,annotation),'input_fidelity':'high','quality':'high','size':output_size,'output_format':'png'}
    boundary='repair-'+uuid.uuid4().hex;chunks=[]
    for name,value in fields.items():chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    for name,im in [('image',canvas),('mask',mask)]:
        buf=io.BytesIO();im.save(buf,'PNG')
        chunks.extend([f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{name}.png"\r\nContent-Type: image/png\r\n\r\n'.encode(),buf.getvalue(),b'\r\n'])
    chunks.append(f'--{boundary}--\r\n'.encode())
    request=urllib.request.Request(base_url+'/images/edits',data=b''.join(chunks),headers={'Authorization':'Bearer '+key,'Content-Type':'multipart/form-data; boundary='+boundary})
    responses=not model.startswith(('gpt-image','grok-imagine','image-'))
    if responses:
        body=dict(model=model,input=[dict(role='user',content=[dict(type='input_text',text=repair_prompt(kind,annotation)+' Keep exact canvas framing and dimensions. No padding or borders. Only edit transparent mask pixels; opaque pixels and ink are protected.'),dict(type='input_image',image_url=image_data_url(canvas))])],tools=[dict(type='image_generation',size=output_size,quality='high',input_image_mask=dict(image_url=image_data_url(mask)))],tool_choice=dict(type='image_generation'),store=False)
        request=urllib.request.Request(base_url+'/responses',data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(request,timeout=300) as response:result=json.load(response)
    except urllib.error.HTTPError as error:
        note='代理未提供图像编辑接口，请检查模型及 /images/edits 支持情况' if error.code in (404,405) else '请检查图像编辑模型、Key、权限及额度'
        raise ValueError(f'AI 服务请求失败（HTTP {error.code}），{note}') from None
    except (OSError,TimeoutError):raise ValueError('AI 服务连接超时或网络不可用，请重试') from None
    raw=next((entry.get('result') for entry in result.get('output',[]) if entry.get('type')=='image_generation_call' and entry.get('result')),None) if responses else result.get('data',[{}])[0].get('b64_json')
    if not raw:raise ValueError('AI 未返回图像，请重试')
    with Image.open(io.BytesIO(base64.b64decode(raw))) as generated:
        if abs((generated.width/generated.height)/(canvas.width/canvas.height)-1)>.01:raise ValueError('AI 返回宽高比例改变，已拒绝拉伸结果，避免字体变形')
        generated=generated.convert('RGB').resize(canvas_size,Image.Resampling.LANCZOS)
    patch=generated.crop((x1-box[0]+offset[0],y1-box[1]+offset[1],x2-box[0]+offset[0],y2-box[1]+offset[1]))
    verify_ai_patch(image.crop((x1,y1,x2,y2)),patch)
    before=np.asarray(image.crop((x1,y1,x2,y2))).astype(float);after=np.asarray(patch).astype(float)
    allowed=(np.asarray(mask)[:,:,3]==0)[y1-box[1]+offset[1]:y2-box[1]+offset[1],x1-box[0]+offset[0]:x2-box[0]+offset[0]]
    # Smooth only the AI correction field, retaining the original paper grain.
    correction=cv2.GaussianBlur((after-before).astype('float32'),(0,0),2)
    after=np.clip(before+correction,0,255)
    distance=cv2.distanceTransform(allowed.astype('uint8'),cv2.DIST_L2,3)
    alpha=(feather(patch.size)*np.minimum(distance/4,1))[:,:,None]
    out=image.copy();out.paste(Image.fromarray(np.rint(before*(1-alpha)+after*alpha).astype('uint8')),(x1,y1));return out


class RepairService:
    def __init__(self,data,find,source,lock,save,items):
        self.folder=data/'repairs';self.folder.mkdir(exist_ok=True)
        self.find=find;self.source=source;self.lock=lock;self.save=save;self.items=items
        self.drafts={};self.key=os.environ.get('OPENAI_API_KEY','')
        self.draft_path=self.folder/'drafts.json'
        try:
            if self.draft_path.exists():self.drafts=json.loads(self.draft_path.read_text('utf-8'))
        except (ValueError,OSError):self.drafts={}
        self.base_url='http://127.0.0.1:8317/v1';self.model='gpt-image-1.5'
        self.config_path=data/'ai-connection.json';self.config_warning='';self.persisted=False
        try:
            saved=load_connection(self.config_path)
            if saved:self.base_url=saved['base_url'];self.model=saved['model'];self.key=saved['key'] or self.key;self.persisted=bool(saved['key'])
        except (ValueError,OSError,KeyError,TypeError):self.config_warning='本机 AI 配置无法读取，请重新填写并保存；原配置文件已保留'

    def config(self):return dict(configured=bool(self.key),base_url=self.base_url,model=self.model,persisted=self.persisted,warning=self.config_warning)

    def save_drafts(self):
        with self.lock:
            temporary=self.draft_path.with_suffix('.tmp');temporary.write_text(json.dumps(self.drafts,ensure_ascii=False),'utf-8');os.replace(temporary,self.draft_path)

    def valid_draft(self,item,token):
        draft=self.drafts.get(token)
        return bool(draft and draft['id']==item['id'] and draft['signature']==crop_signature(item) and draft['layers']==self.state(item).get('layers',[]) and draft.get('marks',self.marks(item))==self.marks(item) and (self.folder/draft['file']).exists())

    def pending(self,item):
        with self.lock:
            for token,draft in reversed(list(self.drafts.items())):
                if draft.get('origin')=='single' and self.valid_draft(item,token):
                    return dict(draft=token,regions=draft['regions'],method=draft['method'],strength=draft.get('strength',.65))
        return None

    def state(self,item):
        state=item.get('repair_state',{})
        return state if state.get('signature')==crop_signature(item) else {}

    def marks(self,item):
        marks=item.get('repair_marks',{})
        return marks.get('regions',[]) if marks.get('signature')==crop_signature(item) else []

    def image(self,item,before=False):
        state=self.state(item)
        if not before and state.get('layers'):
            with Image.open(self.folder/state['layers'][-1]) as im:return im.convert('RGB')
        signature=crop_signature(item);path=self.folder/(item['id']+'_'+signature+'_base.png')
        if path.exists():
            with Image.open(path) as im:return im.convert('RGB')
        im=render(self.source(item),item['points'],item['rotation'],item['settings'],trim=item.get('trim'));im.save(path,'PNG');return im

    def complete(self,item):return bool(item.get('confirmed') and self.state(item).get('completed'))

    def compose_regions(self,item,draft,regions):
        image=self.image(item)
        for mark in regions:
            rect=region_pixels(mark['region'],image.size)
            patch=draft.get('patches',{}).get(mark['id'])
            if patch:
                with np.load(self.folder/patch['file'],allow_pickle=False) as data:delta=data['delta'].astype('int32')
                pixels=np.asarray(image.crop(rect)).astype('int32')
                image.paste(Image.fromarray(np.clip(pixels+delta,0,255).astype('uint8')),(rect[0],rect[1]))
            else:
                for other in draft['regions']:
                    r=region_pixels(other['region'],image.size)
                    if other['id']!=mark['id'] and min(rect[2],r[2])>max(rect[0],r[0]) and min(rect[3],r[3])>max(rect[1],r[1]):
                        image.close();raise ValueError('旧预览存在重叠选区，请重新修复后逐处操作')
                with Image.open(self.folder/draft['file']) as result:image.paste(result.crop(rect),(rect[0],rect[1]))
        return image

    def payload(self,key,detail=False,before=False,draft=None):
        item=self.find(key)
        if not item.get('confirmed'):raise ValueError('请先确认裁剪，再进入修复')
        if draft:
            candidate=self.drafts.get(draft)
            if not self.valid_draft(item,draft):raise ValueError('修复预览已失效')
            with Image.open(self.folder/candidate['file']) as im:image=im.convert('RGB')
        else:image=self.image(item,before)
        with image:
            if not detail:image.thumbnail((1600,1600))
            buf=io.BytesIO();image.save(buf,'PNG' if detail else 'JPEG',**({} if detail else {'quality':94}));return buf.getvalue()

    def post(self,action,body,ai_config=None):
        if action=='config':
            key=str(body.get('key',self.key)).strip()
            if len(key)>8192 or '\n' in key or '\r' in key:raise ValueError('API Key 格式不正确')
            base=str(body.get('base_url',self.base_url)).strip().rstrip('/')
            parsed=urlparse(base)
            if parsed.username or parsed.password or parsed.query or parsed.fragment or not (parsed.scheme=='https' or parsed.scheme=='http' and parsed.hostname in ('localhost','127.0.0.1','::1')):raise ValueError('代理地址须为 HTTPS 或本机 HTTP 地址')
            model=str(body.get('model',self.model)).strip()
            if not model or len(model)>150:raise ValueError('请填写图像编辑模型名')
            with self.lock:
                save_connection(self.config_path,base,model,key)
                self.key=key;self.base_url=base;self.model=model;self.persisted=bool(key);self.config_warning=''
            return self.config()
        if action=='test':
            request=urllib.request.Request(self.base_url+'/models',headers={'Authorization':'Bearer '+self.key})
            try:
                with urllib.request.urlopen(request,timeout=15) as response:models=json.load(response)
            except urllib.error.HTTPError as e:raise ValueError(f'连接失败（HTTP {e.code}），请检查代理及 Key') from None
            except (OSError,ValueError):raise ValueError('无法连接模型服务，请检查地址和代理状态') from None
            return dict(models=[x.get('id') for x in models.get('data',[]) if x.get('id')],note='已连通模型列表，图像编辑能力以实际修复请求为准')
        item=self.find(body['id'])
        if not item.get('confirmed'):raise ValueError('请先确认裁剪，再进入修复')
        signature=crop_signature(item);state=self.state(item)
        if action=='snap':
            brush=validate_brush(body.get('brush'))
            with self.image(item) as image:
                region_pixels(body.get('region'),image.size)
                snapped=snap_crease(image,body['region'],brush)
            return dict(snapped=True,**snapped) if snapped else dict(snapped=False,brush=brush,region=body['region'])
        if action=='discard':
            with self.lock:
                draft=self.drafts.get(body.get('draft'))
                if draft and draft['id']!=item['id']:raise ValueError('预览不属于当前作品')
                self.drafts.pop(body.get('draft'),None);self.save_drafts()
            return dict(discarded=True)
        if action=='marks':
            if body.get('signature')!=signature:raise ValueError('裁剪已改变，请重新加载后标记')
            regions=body.get('regions')
            if regions!=[]:
                with self.image(item) as im:regions=validate_regions(regions,im.size)
            with self.lock:
                target=next(x for x in self.items if x['id']==item['id'])
                if not target.get('confirmed') or crop_signature(target)!=signature:raise ValueError('裁剪已改变，请重新标记')
                pending=[d for token,d in self.drafts.items() if self.valid_draft(target,token)]
                if any(any(mark not in regions for mark in d['regions']) for d in pending):raise ValueError('请先采用或放弃该位置的预览，再编辑标记')
                if self.state(target) and regions!=self.marks(target):target['repair_state']['completed']=False
                target['repair_marks']=dict(signature=signature,regions=regions)
                for draft in pending:draft['marks']=regions
                if pending:self.save_drafts()
                self.save()
                return json.loads(json.dumps(target))
        if action in ('discard-region','retry-region'):
            token=body.get('draft')
            with self.lock:
                if not self.valid_draft(item,token):raise ValueError('预览已失效，请重新加载')
                snapshot=json.loads(json.dumps(self.drafts[token]))
            mark=next((m for m in snapshot['regions'] if m['id']==body.get('mark_id')),None)
            if mark is None:raise ValueError('该修复区域已处理或不存在')
            original_regions=json.loads(json.dumps(snapshot['regions']))
            regions=[m for m in snapshot['regions'] if m['id']!=mark['id']] if action=='discard-region' else snapshot['regions']
            if action=='retry-region':
                if 'level' in body:
                    mark_strength({'level':body['level']})
                    if body['level'] is None:mark.pop('level',None)
                    else:mark['level']=body['level']
                with self.image(item) as base:
                    method=body.get('method',snapshot.get('patches',{}).get(mark['id'],{}).get('method',snapshot.get('method','local')))
                    if method not in ('local','ai'):raise ValueError('修复方式不正确')
                    if method=='ai':
                        key,url,model=ai_config or (self.key,self.base_url,self.model)
                        result=ai_repair(base,mark['region'],key,mark['kind'],url,model,mark)
                    else:result=local_repair(base,mark['region'],mark_strength(mark,snapshot.get('strength',.65)),mark['kind'],mark.get('brush'))
                    if result.size!=base.size:raise ValueError('修复结果像素尺寸改变，已拒绝保存')
                    rect=region_pixels(mark['region'],base.size)
                    delta=np.asarray(result.crop(rect)).astype('int16')-np.asarray(base.crop(rect)).astype('int16');result.close()
                    filename=uuid.uuid4().hex+'.npz';np.savez_compressed(self.folder/filename,delta=delta)
                    snapshot.setdefault('patches',{})[mark['id']]=dict(file=filename,rect=list(rect),method=method)
            with self.lock:
                target=next(x for x in self.items if x['id']==item['id'])
                if not self.valid_draft(target,token) or self.drafts[token]['regions']!=original_regions:raise ValueError('预览已变化，请重新加载')
                if regions:
                    with self.compose_regions(target,snapshot,regions) as candidate:
                        filename=uuid.uuid4().hex+'.png';candidate.save(self.folder/filename,'PNG')
                    if action=='retry-region' and 'level' in body:
                        updated=[dict(mark) if m['id']==mark['id'] else m for m in self.marks(target)]
                        target['repair_marks']=dict(signature=signature,regions=updated)
                        snapshot['marks']=updated;self.save()
                    snapshot.update(file=filename,regions=regions);self.drafts[token]=snapshot
                else:self.drafts.pop(token)
                self.save_drafts()
                return dict(item=json.loads(json.dumps(target)),draft=token if regions else None,regions=regions)
        if action=='preview':
            method=body.get('method','local');kind=body.get('kind','crease')
            if method not in ('local','ai') or kind not in ('crease','bump','blemish'):raise ValueError('修复方式不正确')
            replacing=body.get('replace_draft')
            if replacing and not self.valid_draft(item,replacing):raise ValueError('原预览已失效，请重新加载')
            with self.image(item) as image:
                regions=validate_regions(body['regions'],image.size) if 'regions' in body else validate_regions([dict(region=body.get('region'),kind=kind)],image.size)
                repaired=image.copy();patches={};token=uuid.uuid4().hex
                for index,mark in enumerate(regions):
                    if method=='ai':
                        key,base,model=ai_config or (self.key,self.base_url,self.model)
                        result=ai_repair(repaired,mark['region'],key,mark['kind'],base,model,dict(index=index+1,total=len(regions),**mark))
                    else:result=local_repair(repaired,mark['region'],mark_strength(mark,body.get('strength',.65)),mark['kind'],mark.get('brush'))
                    rect=region_pixels(mark['region'],image.size)
                    delta=np.asarray(result.crop(rect)).astype('int16')-np.asarray(repaired.crop(rect)).astype('int16')
                    patch_file=token+'_'+str(index)+'.npz'
                    np.savez_compressed(self.folder/patch_file,delta=delta)
                    patches[mark['id']]=dict(file=patch_file,rect=list(rect))
                    repaired.close();repaired=result
                    if repaired.size!=image.size:raise ValueError('修复结果像素尺寸改变，已拒绝保存')
                name=token+'.png';repaired.save(self.folder/name,'PNG');size=list(repaired.size)
                repaired.close()
            with self.lock:
                origin='batch' if body.get('origin')=='batch' else 'single'
                if origin=='single':
                    for old in list(self.drafts):
                        if old!=replacing and self.drafts[old]['id']==item['id'] and self.drafts[old].get('origin')=='single':self.drafts.pop(old)
                self.drafts[token]=dict(id=item['id'],signature=signature,layers=list(state.get('layers',[])),file=name,regions=regions,patches=patches,marks=self.marks(item),origin=origin,method=method,strength=body.get('strength',.65));self.save_drafts()
            return dict(draft=token,width=size[0],height=size[1],method=method,regions=regions)
        with self.lock:
            target=next(x for x in self.items if x['id']==item['id'])
            if not target.get('confirmed') or crop_signature(target)!=signature:raise ValueError('裁剪已改变，请重新进入修复')
            latest=self.state(target)
            if list(latest.get('layers',[]))!=list(state.get('layers',[])):raise ValueError('修复已改变，请重新加载')
            if not latest:
                if target.get('repair_state'):target.setdefault('repair_history',[]).append(target['repair_state'])
                latest=dict(signature=signature,layers=[],redo=[],completed=False);target['repair_state']=latest
            if action in ('accept','accept-region'):
                draft=self.drafts.get(body.get('draft'))
                if not self.valid_draft(target,body.get('draft')):raise ValueError('预览已失效，请重新生成')
                selected=draft['regions']
                name=draft['file']
                if action=='accept-region':
                    selected=[mark for mark in draft['regions'] if mark['id']==body.get('mark_id')]
                    if not selected:raise ValueError('该修复区域已采用或不存在')
                    mark=selected[0]
                    with self.image(target) as base:
                        rect=region_pixels(mark['region'],base.size)
                        patch=draft.get('patches',{}).get(mark['id'])
                        if patch:
                            with np.load(self.folder/patch['file'],allow_pickle=False) as data:delta=data['delta'].astype('int32')
                            pixels=np.asarray(base.crop(rect)).astype('int32')
                            base.paste(Image.fromarray(np.clip(pixels+delta,0,255).astype('uint8')),(rect[0],rect[1]))
                        else:
                            # Older disjoint previews can be adopted without another AI call.
                            for other in draft['regions']:
                                r=region_pixels(other['region'],base.size)
                                if other['id']!=mark['id'] and min(rect[2],r[2])>max(rect[0],r[0]) and min(rect[3],r[3])>max(rect[1],r[1]):raise ValueError('旧预览存在重叠选区，请重新修复后逐处采用')
                            with Image.open(self.folder/draft['file']) as result:base.paste(result.crop(rect),(rect[0],rect[1]))
                        name=uuid.uuid4().hex+'.png';base.save(self.folder/name,'PNG')
                marks_before=self.marks(target)
                marks_after=[mark for mark in marks_before if mark not in selected]
                target['repair_marks']=dict(signature=signature,regions=marks_after)
                latest['layers'].append(name);latest['redo']=[];latest['completed']=False
                latest.setdefault('details',{})[name]=dict(regions=selected,marks_before=marks_before,marks_after=marks_after)
                remaining=[mark for mark in draft['regions'] if mark not in selected]
                if remaining:
                    draft.update(regions=remaining,marks=marks_after,layers=list(latest['layers']))
                else:self.drafts.pop(body['draft'])
                self.save_drafts()
            elif action=='undo':
                if latest['layers']:
                    layer=latest['layers'].pop();latest.setdefault('redo',[]).append(layer)
                    detail=latest.get('details',{}).get(layer,{})
                    if 'marks_before' in detail:target['repair_marks']=dict(signature=signature,regions=detail['marks_before'])
                latest['completed']=False
            elif action=='redo':
                if latest.get('redo'):
                    layer=latest['redo'].pop();latest['layers'].append(layer)
                    detail=latest.get('details',{}).get(layer,{})
                    if 'marks_after' in detail:target['repair_marks']=dict(signature=signature,regions=detail['marks_after'])
                latest['completed']=False
            elif action=='complete':
                if any(self.valid_draft(target,token) for token in self.drafts):raise ValueError('请先采用或放弃待确认预览，再确认成品')
                latest['completed']=True
            else:raise ValueError('未知修复操作')
            target['revision']+=1;self.save()
            if action=='accept-region':return dict(item=json.loads(json.dumps(target)),draft=body['draft'] if remaining else None,regions=remaining)
            return json.loads(json.dumps(target))
