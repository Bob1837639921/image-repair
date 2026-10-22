const $=id=>document.getElementById(id);
let items=[],current=null,compare=false,busy=false,history=[],saveChain=Promise.resolve(),previewSerial=0;
let selectionSerial=0,originalSerial=0;
const decodedCache=new Map();
async function decodedImage(url){if(decodedCache.has(url)){const entry=decodedCache.get(url);decodedCache.delete(url);decodedCache.set(url,entry);return entry}const image=new Image();image.src=url;const pending=image.decode().then(()=>image).catch(e=>{decodedCache.delete(url);throw e});decodedCache.set(url,pending);while(decodedCache.size>10)decodedCache.delete(decodedCache.keys().next().value);return pending}
function prefetchNeighbors(){if(!current||items.length<2)return;const index=items.findIndex(x=>x.id===current.id);if(index<0)return;const seen=new Set([current.id]);for(const offset of [1,-1,2]){const item=items[((index+offset)%items.length+items.length)%items.length];if(seen.has(item.id))continue;seen.add(item.id);decodedImage('/api/image/'+item.id+'?mode=original&r='+item.rotation).catch(()=>{});decodedImage('/api/image/'+item.id+'?mode=result&v='+item.revision).catch(()=>{})}}
async function loadOriginal(detail=false,upgrade=false){
 if(!current)return;
 const serial=++originalSerial,id=current.id,rotation=current.rotation,wrap=$('imageWrap'),view=$('originalPane').querySelector('.viewport');
 const scroll=[view.scrollLeft,view.scrollTop];
 if(!upgrade){wrap.style.visibility='hidden';wrap.style.pointerEvents='none';view.setAttribute('aria-busy','true');view.classList.add('loading-image')}
 try{
  const image=await decodedImage('/api/image/'+id+'?mode='+(detail?'detail':'original')+'&r='+rotation);
  if(serial!==originalSerial||current?.id!==id||current.rotation!==rotation)return;
  image.id='original';image.draggable=false;image.onload=fit;$('original').replaceWith(image);fit();view.scrollLeft=upgrade?scroll[0]:0;view.scrollTop=upgrade?scroll[1]:0;
  wrap.style.visibility='visible';wrap.style.pointerEvents='';
 }catch(e){if(serial===originalSerial)toast('图片加载失败，请重新选择该作品')}
 finally{if(serial===originalSerial){view.setAttribute('aria-busy','false');view.classList.remove('loading-image')}}
}
function ensureDetail(){if(current&&$('zoom').value!=='fit'&&!$('original').src.includes('mode=detail'))loadOriginal(true,true)}
const clone=x=>JSON.parse(JSON.stringify(x));
// Invert the output crop through the same projective map as the renderer.
function cropPoints(item){
 const p=item.points,t=item.trim||{};if(!Object.values(t).some(v=>Number(v)>0))return p;
 const dims=item.rotation%180?[item.height,item.width]:[item.width,item.height];
 const pixel=p.map(([x,y])=>[x*(dims[0]-1),y*(dims[1]-1)]);
 const distance=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1]);
 const roundEven=x=>{const f=Math.floor(x);return x-f===.5?f+(f%2):Math.round(x)};
 const width=Math.max(2,roundEven(Math.max(distance(pixel[1],pixel[0]),distance(pixel[2],pixel[3])))+1);
 const height=Math.max(2,roundEven(Math.max(distance(pixel[3],pixel[0]),distance(pixel[2],pixel[1])))+1);
 const left=roundEven(width*(t.left||0))/(width-1),right=(width-roundEven(width*(t.right||0))-1)/(width-1);
 const top=roundEven(height*(t.top||0))/(height-1),bottom=(height-roundEven(height*(t.bottom||0))-1)/(height-1);
 const dx1=p[1][0]-p[2][0],dx2=p[3][0]-p[2][0],dx3=p[0][0]-p[1][0]+p[2][0]-p[3][0];
 const dy1=p[1][1]-p[2][1],dy2=p[3][1]-p[2][1],dy3=p[0][1]-p[1][1]+p[2][1]-p[3][1];
 const det=dx1*dy2-dx2*dy1,g=(dx3*dy2-dx2*dy3)/det,h=(dx1*dy3-dx3*dy1)/det;
 const a=p[1][0]-p[0][0]+g*p[1][0],b=p[3][0]-p[0][0]+h*p[3][0];
 const d=p[1][1]-p[0][1]+g*p[1][1],e=p[3][1]-p[0][1]+h*p[3][1];
 return [[left,top],[right,top],[right,bottom],[left,bottom]].map(([x,y])=>[(a*x+b*y+p[0][0])/(g*x+h*y+1),(d*x+e*y+p[0][1])/(g*x+h*y+1)]);
}
function bakeTrim(){current.points=clone(cropPoints(current));current.trim={};if(typeof syncTrim==='function')syncTrim()}
function toast(message){$('toast').textContent=message;$('toast').style.display='block';clearTimeout(window.toastTimer);window.toastTimer=setTimeout(()=>$('toast').style.display='none',4500)}
async function api(path,body){const r=await fetch('/api/'+path,{method:'POST',headers:{'X-App-Token':window.APP_TOKEN,'Content-Type':'application/json'},body:JSON.stringify(body)});const v=await r.json();if(!r.ok)throw Error(v.error);return v}
function replace(item){const i=items.findIndex(x=>x.id===item.id);if(i>=0)items[i]=item;else items.push(item);if(current?.id===item.id)current=item;drawList()}
function drawList(reveal=false){const list=$('list'),previousScroll=list.scrollTop;const confirmed=items.filter(x=>x.confirmed).length;$('count').textContent=items.length;const counter=$('position');if(counter){const i=items.findIndex(x=>x.id===current?.id);counter.textContent=`${i>=0?i+1:0} / ${items.length}`;}$('exportCount').textContent=confirmed;$('list').replaceChildren();const term=$('search').value.toLowerCase();items.filter(x=>x.name.toLowerCase().includes(term)&&($('filter').value==='all'||x.confirmed===($('filter').value==='confirmed'))).forEach(x=>{const b=document.createElement('button');b.className='item'+(x.id===current?.id?' selected':'');if(x.id===current?.id)b.setAttribute('aria-current','true');const im=document.createElement('img');im.src='/api/image/'+x.id+'?mode=thumb&r='+x.rotation;im.loading='lazy';const info=document.createElement('div');info.className='info';const name=document.createElement('strong');name.textContent=x.name;name.title=x.name;const size=document.createElement('small');size.textContent=`${x.width} × ${x.height} px`;const status=document.createElement('em');status.textContent=x.confirmed?'✓ 已确认':'○ 待检查';status.className=x.confirmed?'done':'';info.append(name,size,status);b.append(im,info);b.onclick=()=>select(x.id);$('list').append(b)});list.scrollTop=previousScroll;if(reveal)revealCurrentItem()}
function revealCurrentItem(){const list=$('list'),selected=list.querySelector('.item.selected');if(!selected)return;const view=list.getBoundingClientRect(),row=selected.getBoundingClientRect(),top=view.top+list.clientTop,bottom=top+list.clientHeight;if(row.top<top)list.scrollTop+=row.top-top;else if(row.bottom>bottom)list.scrollTop+=row.bottom-bottom}
function markHistory(){history.push(clone(current));if(history.length>30)history.shift()}
function persist(){const snapshot=clone(current);saveChain=saveChain.catch(()=>{}).then(async()=>{const updated=await api('update',snapshot);const latest=items.find(x=>x.id===updated.id);if(latest)latest.revision=updated.revision;return updated});return saveChain}
function changed(){current.confirmed=false;drawStatus();drawList();return persist()}
function drawStatus(){$('status').textContent=current?.confirmed?'已确认':'待检查';$('status').classList.toggle('done',!!current?.confirmed);$('confirm').textContent=current?.confirmed?'已确认 · 下一张':'确认并保留';const i=items.findIndex(x=>x.id===current?.id);$('prev').disabled=i<0||items.length<2;$('next').disabled=i<0||items.length<2;const position=$('position');if(position)position.textContent=i>=0?`${i+1} / ${items.length}`:''}
async function select(id){
 const serial=++selectionSerial;++originalSerial;++previewSerial;
 $('imageWrap').style.visibility='hidden';$('imageWrap').style.pointerEvents='none';$('result').style.visibility='hidden';
 await saveChain.catch(()=>{});if(serial!==selectionSerial)return;
 current=items.find(x=>x.id===id);history=[];if(!current)return;
 $('zoom').value='fit';$('empty').hidden=true;$('editor').hidden=false;$('title').textContent=current.name;$('title').title=current.name;$('resolution').textContent=`原图 ${current.width} × ${current.height} px`;
 const view=$('originalPane').querySelector('.viewport');view.classList.add('loading-image');view.setAttribute('aria-busy','true');
 drawStatus();drawList(true);
 try{
  if(serial!==selectionSerial)return;
  $('meta').textContent=`原图 ${current.width} × ${current.height} px · 参数自动保存`;
  drawStatus();for(const key of ['brightness','contrast','sharpness']){$(key).value=current.settings[key];$(key+'Value').textContent=Number(current.settings[key]).toFixed(2)}
  drawCandidates();if(typeof syncTrim==='function')syncTrim();
  const loading=loadOriginal();if(compare)preview();await loading;if(serial===selectionSerial)prefetchNeighbors();
 }catch(e){if(serial===selectionSerial){toast('自动处理未完成：'+e.message);view.classList.remove('loading-image');view.setAttribute('aria-busy','false')}}
}
function fit(){if(!current||!$('original').naturalWidth)return;const view=$('originalPane').querySelector('.viewport');const im=$('original');const dims=sourceDimensions();const scale=$('zoom').value==='fit'?Math.max(.01,Math.min((view.clientWidth-26)/dims[0],(view.clientHeight-26)/dims[1])):Number($('zoom').value);$('imageWrap').style.width=dims[0]*scale+'px';$('imageWrap').style.height=dims[1]*scale+'px';drawQuad()}
function fitResult(){const im=$('result');if(!im.naturalWidth)return;const view=$('resultPane').querySelector('.viewport');const scale=Math.min((view.clientWidth-26)/im.naturalWidth,(view.clientHeight-26)/im.naturalHeight);if(scale>0){im.style.width=im.naturalWidth*scale+'px';im.style.height=im.naturalHeight*scale+'px'}}
function drawQuad(){if(!current)return;const svg=$('overlay');svg.setAttribute('viewBox','0 0 1000 1000');svg.setAttribute('preserveAspectRatio','none');svg.replaceChildren();const make=(tag,attrs)=>{const e=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,v]of Object.entries(attrs))e.setAttribute(k,v);svg.append(e);return e};const p=cropPoints(current).map(x=>x.map(v=>v*1000));make('path',{d:`M0 0H1000V1000H0Z M${p.map(x=>x.join(' ')).join(' L')}Z`,fill:'#14251e66','fill-rule':'evenodd','pointer-events':'none'});make('polygon',{points:p.map(x=>x.join(',')).join(' '),fill:'none',stroke:'#e3b779','stroke-width':2,'vector-effect':'non-scaling-stroke'});p.forEach((v,i)=>{const r=$('overlay').getBoundingClientRect();const c=make('ellipse',{cx:v[0],cy:v[1],rx:7/r.width*1000,ry:7/r.height*1000,fill:'#fff9ed',stroke:'#306d5d','stroke-width':2,'vector-effect':'non-scaling-stroke'});c.style.cursor='grab';c.onpointerdown=e=>{e.preventDefault();markHistory();const before=clone(current);bakeTrim();svg.setPointerCapture(e.pointerId);const move=ev=>{const rect=svg.getBoundingClientRect();current.points[i]=[Math.max(0,Math.min(1,(ev.clientX-rect.left)/rect.width)),Math.max(0,Math.min(1,(ev.clientY-rect.top)/rect.height))];drawQuad()};const up=async()=>{svg.removeEventListener('pointermove',move);svg.removeEventListener('pointerup',up);svg.removeEventListener('pointercancel',up);try{await changed();if(compare)preview()}catch(err){current.points=before.points;current.trim=before.trim;syncTrim();drawQuad();toast(err.message)}};svg.addEventListener('pointermove',move);svg.addEventListener('pointerup',up);svg.addEventListener('pointercancel',up)}})}
async function preview(){if(!current)return;const serial=++previewSerial,id=current.id;$('result').style.visibility='hidden';await saveChain.catch(()=>{});if(serial!==previewSerial||current?.id!==id)return;try{const image=await decodedImage('/api/image/'+id+'?mode=result&v='+current.revision);if(serial!==previewSerial||current?.id!==id)return;image.id='result';image.onload=fitResult;$('result').replaceWith(image);fitResult();$('result').style.visibility='visible'}catch(e){if(serial===previewSerial)toast('效果预览加载失败，请重试')}}
function drawCandidates(){const select=$('candidates');select.replaceChildren();(current?.candidates||[]).forEach((x,i)=>{const o=document.createElement('option');o.value=i;const label=x.method==='before-native'?'精定位前':x.method?.endsWith('native')?'原图精定位':i===1&&current.candidates[0]?.method?.endsWith('native')?'粗定位备选':'候选边界';o.textContent=`${label} ${i+1}${i===0?' · 优先建议':''}`;select.append(o)});select.hidden=!current?.candidates?.length}
async function detectOne(){if(!current||busy)return;busy=true;markHistory();$('detect').disabled=true;try{await saveChain;const result=await api('detect',{id:current.id});replace(result);drawCandidates();drawQuad();drawStatus();if(compare)preview();toast(result.candidates.length?'已找到候选边界，请检查后确认':'没有找到可靠边界，请手动拖动四角')}catch(e){toast(e.message)}finally{busy=false;$('detect').disabled=false}}
async function importFiles(files){if(busy)return toast('请等待当前操作完成');busy=true;const accepted=[...files].filter(f=>/\.(jpe?g|png|tiff?|bmp|webp)$/i.test(f.name));let failed=0,detected=0;for(let i=0;i<accepted.length;i++){const f=accepted[i];$('hint').textContent=`正在导入并自动处理 ${i+1} / ${accepted.length}：${f.name}`;try{const r=await fetch('/api/import?name='+encodeURIComponent(f.name),{method:'POST',headers:{'X-App-Token':window.APP_TOKEN},body:f});const item=await r.json();if(!r.ok)throw Error(item.error);if(item.candidates?.length)detected++;replace(item);if(!current)await select(item.id)}catch(e){failed++;toast(f.name+'：'+e.message)}}busy=false;$('hint').textContent=`导入 ${accepted.length-failed} 张，${detected} 张已完成自动裁剪${failed?'，失败 '+failed+' 张':''}。识别、精定位和去残边已自动执行。`;toast($('hint').textContent)}
for(const id of ['importTop','importFiles','importEmpty'])$(id).onclick=()=>$('fileInput').click();$('importFolder').onclick=()=>$('folderInput').click();for(const id of ['fileInput','folderInput'])$(id).onchange=e=>{importFiles(e.target.files);e.target.value=''};
document.addEventListener('dragover',e=>{e.preventDefault();document.body.classList.add('dragging')});document.addEventListener('dragleave',e=>{if(!e.relatedTarget)document.body.classList.remove('dragging')});document.addEventListener('drop',e=>{e.preventDefault();document.body.classList.remove('dragging');importFiles(e.dataTransfer.files)});
$('search').oninput=drawList;$('filter').onchange=drawList;$('original').onload=fit;new ResizeObserver(fit).observe($('originalPane'));$('zoom').onchange=fit;
$('result').onload=fitResult;new ResizeObserver(fitResult).observe($('resultPane'));
function setViewMode(value){compare=value;$('resultPane').hidden=!value;$('editTab').classList.toggle('active',!value);$('compareTab').classList.toggle('active',value);$('editTab').setAttribute('aria-pressed',String(!value));$('compareTab').setAttribute('aria-pressed',String(value));document.querySelector('.workspace').classList.toggle('comparing',value);fit();if(value)preview()}
$('editTab').onclick=()=>setViewMode(false);$('compareTab').onclick=()=>setViewMode(true);
$('detect').onclick=detectOne;$('candidates').onchange=async()=>{if(!current)return;markHistory();current.points=clone(current.candidates[Number($('candidates').value)].points);drawQuad();await changed();if(compare)preview()};
$('full').onclick=async()=>{if(!current)return;markHistory();current.points=[[0,0],[1,0],[1,1],[0,1]];drawQuad();await changed();if(compare)preview()};$('rotate').onclick=async()=>{if(!current)return;markHistory();current.rotation=(current.rotation+90)%360;current.points=[[0,0],[1,0],[1,1],[0,1]];current.candidates=[];const loading=loadOriginal();await changed();await loading;drawCandidates();if(compare)preview()};
$('undo').onclick=async()=>{if(!history.length)return;const old=history.pop();old.confirmed=false;replace(old);await persist();const keep=history;await select(old.id);history=keep};
for(const key of ['brightness','contrast','sharpness']){$(key).onpointerdown=()=>{if(current)markHistory()};$(key).oninput=()=>{$(key+'Value').textContent=Number($(key).value).toFixed(2)};$(key).onchange=async()=>{if(!current)return;current.settings[key]=Number($(key).value);await changed();if(compare)preview()}}
$('resetSettings').onclick=async()=>{if(!current)return;markHistory();current.settings={brightness:1,contrast:1,sharpness:1};for(const k of Object.keys(current.settings)){$(k).value=1;$(k+'Value').textContent='1.00'}await changed();if(compare)preview()};
function step(delta){if(!current||items.length<2)return;const i=items.findIndex(x=>x.id===current.id);if(i<0)return;const next=((i+delta)%items.length+items.length)%items.length;select(items[next].id)}$('prev').onclick=()=>step(-1);$('next').onclick=()=>step(1);
$('confirm').onclick=async()=>{if(!current)return;if(current.confirmed)return step(1);try{current.confirmed=true;await persist();drawStatus();drawList();toast('已确认，可导出；修改裁剪后会重新进入待检查')}catch(e){current.confirmed=false;drawStatus();toast(e.message)}};
$('batchDetect').onclick=async()=>{if(busy)return;busy=true;const pending=items.filter(x=>!x.confirmed);try{await saveChain;for(let i=0;i<pending.length;i++){$('hint').textContent=`批量识别 ${i+1} / ${pending.length}`;replace(await api('detect',{id:pending[i].id}))}if(current){drawQuad();drawCandidates();drawStatus()}toast('识别完成，请逐张检查候选边界')}catch(e){toast(e.message)}finally{busy=false;$('hint').textContent='自动识别完成后仍需人工确认，尤其注意贴边笔画。'}};
async function pollJob(){const job=await(await fetch('/api/job')).json();if(job.total){$('progress').hidden=false;$('progress').textContent=job.running?`正在导出 ${job.done} / ${job.total}`:`导出完成：${job.total-job.errors.length} 张${job.errors.length?'，失败 '+job.errors.length+' 张：'+job.errors.join('；'):''}`;$('export').disabled=job.running;$('openExport').hidden=!job.folder}if(job.running)setTimeout(pollJob,900)}
$('export').onclick=async()=>{try{await saveChain;await api('export',{format:$('format').value});pollJob()}catch(e){toast(e.message)}};$('openExport').onclick=()=>api('open-export',{}).catch(e=>toast(e.message));
document.addEventListener('keydown',e=>{if(['INPUT','SELECT','TEXTAREA'].includes(e.target.tagName)||e.target.isContentEditable||e.shiftKey||e.ctrlKey||e.metaKey)return;if(e.key==='ArrowRight'){e.preventDefault();step(1)}if(e.key==='ArrowLeft'){e.preventDefault();step(-1)}});
// Precision editor: zoom uses source pixels, never a multiple of a thumbnail.
let activeCorner=0,nudging=false;
const refineButton=document.createElement('button');refineButton.id='refineNative';refineButton.className='wide';refineButton.textContent='⌖ 原图精定位当前边界';$('detect').insertAdjacentElement('afterend',refineButton);
refineButton.onclick=async()=>{if(!current||busy)return;busy=true;markHistory();refineButton.disabled=true;const id=current.id;try{await saveChain;const result=await api('refine',{id});replace(result);if(current?.id===id){drawCandidates();drawQuad();drawStatus();if(compare)preview()}toast('原图精定位完成；可切换“精定位前”对比，弱边缘保持原位')}catch(e){toast(e.message)}finally{busy=false;refineButton.disabled=false}};
const originalView=$('originalPane').querySelector('.viewport');
function sourceDimensions(){return current?.rotation%180?[current.height,current.width]:[current?.width||1,current?.height||1]}
$('zoom').replaceChildren(...[['fit','适合窗口'],['0.5','原图 50%'],['1','原图 100%'],['2','原图 200%'],['4','原图 400%']].map(([value,label])=>{const o=document.createElement('option');o.value=value;o.textContent=label;return o}));
const precision=document.createElement('div');precision.className='precision-controls';
precision.innerHTML='<label>定位角点 <select id="cornerSelect" aria-label="选择微调角点"><option value="0">左上</option><option value="1">右上</option><option value="2">右下</option><option value="3">左下</option></select></label><button id="focusCorner" title="把选中角点移到窗口中央">定位</button><label>步长 <select id="pixelStep"><option value="1">1 像素</option><option value="5">5 像素</option><option value="10">10 像素</option></select></label><button data-dx="-1" data-dy="0" aria-label="角点左移">←</button><button data-dx="0" data-dy="-1" aria-label="角点上移">↑</button><button data-dx="0" data-dy="1" aria-label="角点下移">↓</button><button data-dx="1" data-dy="0" aria-label="角点右移">→</button><span>拖动画面平移 · Ctrl＋滚轮缩放 · Shift＋方向键微调</span>';
$('originalPane').insertBefore(precision,originalView);
function focusCorner(){if(!current)return;const r=$('imageWrap').getBoundingClientRect(),v=originalView.getBoundingClientRect(),p=cropPoints(current)[activeCorner];originalView.scrollLeft+=r.left+p[0]*r.width-v.left-originalView.clientWidth/2;originalView.scrollTop+=r.top+p[1]*r.height-v.top-originalView.clientHeight/2}
const basicDrawQuad=drawQuad;
drawQuad=function(){basicDrawQuad();const r=$('overlay').getBoundingClientRect();if(!r.width||!r.height)return;$('overlay').querySelectorAll('ellipse').forEach((el,i)=>{el.setAttribute('fill',i===activeCorner?'#e7a947':'#fff9ed');el.setAttribute('rx',10/r.width*1000);el.setAttribute('ry',10/r.height*1000)})};
$('cornerSelect').onchange=()=>{activeCorner=Number($('cornerSelect').value);drawQuad();focusCorner()};
$('focusCorner').onclick=focusCorner;
$('zoom').onchange=()=>{fit();focusCorner();ensureDetail()};
$('original').onload=()=>{fit()};
$('overlay').addEventListener('pointerdown',e=>{const corners=[...$('overlay').querySelectorAll('ellipse')];const index=corners.indexOf(e.target);if(index>=0){activeCorner=index;$('cornerSelect').value=String(index)}},true);
originalView.addEventListener('wheel',e=>{if(!e.ctrlKey||!current)return;e.preventDefault();const before=$('imageWrap').getBoundingClientRect();const x=(e.clientX-before.left)/before.width,y=(e.clientY-before.top)/before.height;const scale=before.width/sourceDimensions()[0];const levels=[.125,.25,.5,1,2,4];const next=e.deltaY<0?(levels.find(v=>v>scale+.001)||4):([...levels].reverse().find(v=>v<scale-.001)||.125);if(![...$('zoom').options].some(o=>o.value===String(next))){const option=document.createElement('option');option.value=String(next);option.textContent='原图 '+next*100+'%';$('zoom').append(option)}$('zoom').value=String(next);fit();const after=$('imageWrap').getBoundingClientRect();originalView.scrollLeft+=after.left+x*after.width-e.clientX;originalView.scrollTop+=after.top+y*after.height-e.clientY;ensureDetail()},{passive:false});
originalView.addEventListener('pointerdown',e=>{if(e.button!==0||e.target.tagName.toLowerCase()==='ellipse')return;const left=originalView.scrollLeft,top=originalView.scrollTop,x=e.clientX,y=e.clientY;originalView.setPointerCapture(e.pointerId);originalView.classList.add('panning');e.preventDefault();const move=ev=>{originalView.scrollLeft=left+x-ev.clientX;originalView.scrollTop=top+y-ev.clientY};const end=()=>{originalView.removeEventListener('pointermove',move);originalView.removeEventListener('pointerup',end);originalView.removeEventListener('pointercancel',end);originalView.classList.remove('panning')};originalView.addEventListener('pointermove',move);originalView.addEventListener('pointerup',end);originalView.addEventListener('pointercancel',end)});
async function nudgeCorner(dx,dy,multiplier=1){if(!current||busy||nudging)return;nudging=true;const id=current.id,before=clone(current),dims=sourceDimensions(),amount=Number($('pixelStep').value)*multiplier;markHistory();bakeTrim();current.points[activeCorner]=[Math.max(0,Math.min(1,current.points[activeCorner][0]+dx*amount/(dims[0]-1))),Math.max(0,Math.min(1,current.points[activeCorner][1]+dy*amount/(dims[1]-1)))];drawQuad();try{await changed();if(compare)preview()}catch(e){if(current?.id===id){current.points=before.points;current.trim=before.trim;syncTrim();drawQuad()}toast(e.message)}finally{nudging=false}}
precision.querySelectorAll('[data-dx]').forEach(button=>button.onclick=()=>nudgeCorner(Number(button.dataset.dx),Number(button.dataset.dy)));
document.addEventListener('keydown',e=>{if(['INPUT','SELECT','TEXTAREA'].includes(e.target.tagName)||e.target.isContentEditable||!e.shiftKey||e.altKey||e.ctrlKey||e.metaKey)return;const direction={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]}[e.key];if(direction&&current){e.preventDefault();nudgeCorner(...direction)}});
// Residual borders are cropped after perspective correction, in output space.
const trimPanel=document.createElement('details');trimPanel.className='trim-panel';trimPanel.open=true;
trimPanel.innerHTML='<summary>去残边</summary><button id="autoTrim" class="wide">自动去残边</button><div class="trim-fields">'+[['left','左'],['top','上'],['right','右'],['bottom','下']].map(([key,label])=>`<label>${label} <input id="trim-${key}" type="number" min="0" max="5" step="0.05" value="0" aria-label="${label}侧收边百分比"> %</label>`).join('')+'</div><button id="resetTrim" class="text-button">恢复全部边缘</button><p>校正后向内收边；在效果对比中查看。每边最多 5%。</p>';
document.querySelector('.settings').prepend(trimPanel);
function syncTrim(){drawQuad();for(const side of ['left','top','right','bottom'])$('trim-'+side).value=Number(((current?.trim?.[side]||0)*100).toFixed(3))}
async function showTrimPreview(){if(!compare)$('compareTab').click();else await preview()}
for(const side of ['left','top','right','bottom'])$('trim-'+side).onchange=async()=>{if(!current||busy)return;const value=Number($('trim-'+side).value);if(!Number.isFinite(value)||value<0||value>5){syncTrim();return toast('收边范围为 0–5%')}markHistory();current.trim={...current.trim,[side]:value/100};await changed();showTrimPreview()};
$('resetTrim').onclick=async()=>{if(!current||busy)return;markHistory();current.trim={};syncTrim();await changed();showTrimPreview()};
$('autoTrim').onclick=async()=>{if(!current||busy)return;busy=true;const id=current.id;markHistory();$('autoTrim').disabled=true;try{await saveChain;const result=await api('trim',{id});replace(result.item);if(current?.id===id){syncTrim();drawStatus();showTrimPreview()}toast(result.note)}catch(e){toast(e.message)}finally{busy=false;$('autoTrim').disabled=false}};
// Keep the image as the primary workspace; infrequent controls live in panels.
const mainToolbar=document.querySelector('.toolbar');
const primaryActions=document.createElement('div');primaryActions.className='primary-actions';
primaryActions.append($('detect'),refineButton,$('confirm'));
mainToolbar.prepend(primaryActions);
$('detect').textContent='自动识别';refineButton.textContent='精定位';
const settingsPanel=document.querySelector('.settings');
settingsPanel.hidden=false;
precision.hidden=false;
settingsPanel.prepend(mainToolbar,precision);
// The default workflow runs all stages; separate operations stay optional.
const advanced=document.createElement('details');advanced.className='advanced-controls';advanced.innerHTML='<summary>高级调整</summary>';
settingsPanel.append(advanced);
advanced.append(refineButton,$('candidates'),precision,trimPanel,$('rotate'),$('full'));
trimPanel.open=false;
const autoState=document.createElement('p');autoState.id='autoState';autoState.className='auto-state';primaryActions.after(autoState);
function drawAutoState(){autoState.textContent=current?.auto_result?.needs_review?'建议检查：'+current.auto_result.note:current?.auto_result?'自动处理完成':''}
const previousDrawStatus=drawStatus;drawStatus=function(){previousDrawStatus();drawAutoState()};
$('detect').textContent='重新自动处理';advanced.append($('detect'));
$('detect').onclick=async()=>{if(!current||busy)return;busy=true;const id=current.id;markHistory();$('detect').disabled=true;$('detect').textContent='处理中…';try{await saveChain;const result=await api('process',{id});replace(result);if(current?.id===id){drawCandidates();syncTrim();drawQuad();drawStatus();showTrimPreview()}toast(result.auto_result.needs_review?'已自动处理，部分边界建议检查':'自动处理完成')}catch(e){toast(e.message)}finally{busy=false;$('detect').disabled=false;$('detect').textContent='重新自动处理'}};
$('batchDetect').textContent='批量自动处理待检查图片';
$('batchDetect').onclick=async()=>{if(busy)return;busy=true;const pending=items.filter(x=>!x.confirmed);try{await saveChain;for(let i=0;i<pending.length;i++){$('hint').textContent=`自动处理 ${i+1} / ${pending.length}`;replace(await api('process',{id:pending[i].id}))}if(current){drawCandidates();syncTrim();drawQuad();drawStatus();showTrimPreview()}toast('批量自动处理完成')}catch(e){toast(e.message)}finally{busy=false;$('hint').textContent='识别、精定位和去残边已合并，异常边界会提示检查。'}};
const restoreFull=$('full').onclick;$('full').onclick=()=>{if(window.confirm('重置为整张照片？之后需要重新识别或调整全部四角。'))restoreFull()};
// Compact controls with one prominent mode switch and a single primary action.
const tabs=document.querySelector('.tabs');tabs.setAttribute('role','group');tabs.setAttribute('aria-label','查看模式');
$('editTab').setAttribute('aria-pressed','true');$('compareTab').setAttribute('aria-pressed','false');
mainToolbar.prepend(tabs);
const modeLabel=document.createElement('div');modeLabel.className='panel-caption';modeLabel.textContent='查看方式';mainToolbar.prepend(modeLabel);
const appearance=document.createElement('details');appearance.className='advanced-controls';appearance.innerHTML='<summary>画面微调</summary>';
const appearanceBlock=$('brightness').closest('.block');appearance.append(appearanceBlock);settingsPanel.insertBefore(appearance,advanced);
const exportOptions=document.createElement('details');exportOptions.className='advanced-controls';exportOptions.innerHTML='<summary>导出选项</summary>';exportOptions.append($('format').closest('label'));settingsPanel.append(exportOptions);
advanced.append($('batchDetect'));$('batchDetect').textContent='重新处理未确认图片';
const stateBlock=document.createElement('div');stateBlock.className='processing-state';stateBlock.append(autoState);mainToolbar.after(stateBlock);
const finalActions=document.createElement('div');finalActions.className='final-actions';finalActions.append($('confirm'),$('openExport'),$('progress'));settingsPanel.append(finalActions);
primaryActions.remove();
for(const block of [...settingsPanel.querySelectorAll(':scope > .block')])block.remove();
for(const node of [...settingsPanel.querySelectorAll(':scope > .eyebrow,:scope > h2')])node.remove();
$('importFiles').remove();$('importFolder').textContent='导入文件夹';$('importTop').textContent='导入图片';
const importActions=document.createElement('div');importActions.className='header-imports';$('importTop').before(importActions);importActions.append($('importTop'),$('importFolder'));document.querySelector('.imports').remove();
$('export').childNodes[0].textContent='导出已确认 ';
$('undo').title='撤销当前作品上一次调整';$('zoom').setAttribute('aria-label','画面缩放');
$('prev').title='上一张（←）';$('next').title='下一张（→）';
const position=document.createElement('span');position.id='position';position.setAttribute('aria-live','polite');position.title='当前作品 / 全部作品';position.textContent='0 / 0';$('count').hidden=true;document.querySelector('.side-title').append(position);
new ResizeObserver(()=>{fit();fitResult()}).observe(originalView);
async function pollPreparation(){
 const job=await(await fetch('/api/prepare-job')).json();
 if(job.total&&!busy)$('hint').textContent=job.running?`正在后台准备 ${job.done} / ${job.total}，完成后可连续翻图`:`全部 ${job.total} 张已准备${job.errors.length?'，失败 '+job.errors.length+' 张':''}`;
 if(!job.running){
  const fresh=await(await fetch('/api/items')).json();await saveChain.catch(()=>{});
  for(const item of fresh){const existing=items.find(x=>x.id===item.id);if(!existing||item.revision>existing.revision){if(current?.id!==item.id)replace(item)}}
  prefetchNeighbors();return;
 }
 setTimeout(()=>pollPreparation().catch(e=>toast(e.message)),1000);
}
window.addEventListener('unhandledrejection',e=>{toast(e.reason?.message||'操作未完成，请重试');e.preventDefault()});
(async()=>{items=await(await fetch('/api/items')).json();drawList();if(items.length)select(items[0].id);pollJob();pollPreparation()})().catch(e=>toast(e.message));
