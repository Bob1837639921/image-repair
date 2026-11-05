// One native-pixel viewer shared by the overview, detail tiles and inscription.
class RecognitionViewer {
 constructor({view,stage,image,minus,plus,percent,actual,fit}){
  Object.assign(this,{view,stage,image,minus,plus,percent,actual,fit});
  this.scale=1;this.mode='fit';this.key=null;this.ready=false;this.snapshots=new Map();this.serial=0;
  this.controls=[minus,plus,actual,fit];this.sync();
  minus.onclick=()=>this.zoom(this.scale/1.25);plus.onclick=()=>this.zoom(this.scale*1.25);
  actual.onclick=()=>this.zoom(1);fit.onclick=()=>this.zoom('fit');
  view.addEventListener('wheel',e=>{if(!this.ready||!e.deltaY)return;e.preventDefault();this.zoom(this.scale*Math.exp(-Math.max(-120,Math.min(120,e.deltaY))*.002),[e.clientX,e.clientY])},{passive:false});
  view.addEventListener('dblclick',e=>{if(this.ready)this.zoom(this.mode==='fit'?1:'fit',[e.clientX,e.clientY])});
  let pan=null;
  view.addEventListener('pointerdown',e=>{if(!this.ready||e.button!==0)return;e.preventDefault();pan={id:e.pointerId,x:e.clientX,y:e.clientY,left:view.scrollLeft,top:view.scrollTop};view.setPointerCapture(e.pointerId);view.classList.add('panning')});
  view.addEventListener('pointermove',e=>{if(pan?.id===e.pointerId){view.scrollLeft=pan.left-(e.clientX-pan.x);view.scrollTop=pan.top-(e.clientY-pan.y)}});
  const release=e=>{if(pan?.id!==e.pointerId)return;pan=null;view.classList.remove('panning');if(view.hasPointerCapture(e.pointerId))view.releasePointerCapture(e.pointerId)};
  view.addEventListener('pointerup',release);view.addEventListener('pointercancel',release);view.addEventListener('lostpointercapture',()=>{pan=null;view.classList.remove('panning')});
  view.addEventListener('keydown',e=>{if(['+','=','-','0','1'].includes(e.key)){e.preventDefault();this.zoom(e.key==='0'?'fit':e.key==='1'?1:this.scale*(e.key==='-'?1/1.25:1.25))}});
  this.observer=new ResizeObserver(()=>{if(this.ready)this.zoom(this.mode==='fit'?'fit':this.scale)});this.observer.observe(view);
 }
 reset(){++this.serial;this.snapshots.clear();this.key=null;this.ready=false;this.image.onload=null;this.image.onerror=null;this.image.removeAttribute('src');this.image.hidden=true;this.view.scrollLeft=0;this.view.scrollTop=0;this.stage.style.width='100%';this.stage.style.height='100%';this.sync()}
 save(){if(this.ready&&this.key)this.snapshots.set(this.key,{mode:this.mode,scale:this.scale,u:(this.view.scrollLeft+this.view.clientWidth/2-this.left)/this.width,v:(this.view.scrollTop+this.view.clientHeight/2-this.top)/this.height})}
 setSource(url,key){
  if(this.key===key&&this.url===url)return;
  this.save();const serial=++this.serial;this.key=key;this.url=url;this.ready=false;this.image.hidden=true;this.view.setAttribute('aria-busy','true');this.sync();
  this.image.onload=()=>{if(serial!==this.serial)return;this.ready=true;this.image.hidden=false;this.view.setAttribute('aria-busy','false');const snapshot=this.snapshots.get(key);this.zoom(snapshot?.mode==='manual'?snapshot.scale:'fit');if(snapshot?.mode==='manual')this.center(snapshot.u,snapshot.v)};
  this.image.onerror=()=>{if(serial!==this.serial)return;this.view.setAttribute('aria-busy','false');this.percent.textContent='加载失败'};
  this.image.src=url;
 }
 fitScale(){return Math.min(1,(Math.max(1,this.view.clientWidth-34))/this.image.naturalWidth,(Math.max(1,this.view.clientHeight-34))/this.image.naturalHeight)}
 render(){
  this.width=this.image.naturalWidth*this.scale;this.height=this.image.naturalHeight*this.scale;
  for(let pass=0;pass<2;pass++){
   const w=this.view.clientWidth,h=this.view.clientHeight;
   this.left=Math.max(16,(w-this.width)/2);this.top=Math.max(16,(h-this.height)/2);
   this.stage.style.width=Math.max(w,this.width+32)+'px';this.stage.style.height=Math.max(h,this.height+32)+'px';
   Object.assign(this.image.style,{width:this.width+'px',height:this.height+'px',left:this.left+'px',top:this.top+'px'});
  }
  this.sync();this.onRender?.();
 }
 center(u=.5,v=.5){this.view.scrollLeft=Math.max(0,Math.min(this.view.scrollWidth-this.view.clientWidth,this.left+u*this.width-this.view.clientWidth/2));this.view.scrollTop=Math.max(0,Math.min(this.view.scrollHeight-this.view.clientHeight,this.top+v*this.height-this.view.clientHeight/2))}
 zoom(value,point){
  if(!this.ready)return;
  const rect=this.view.getBoundingClientRect();const x=point?point[0]-rect.left-(this.view.clientLeft||0):this.view.clientWidth/2,y=point?point[1]-rect.top-(this.view.clientTop||0):this.view.clientHeight/2;
  const u=this.width?(this.view.scrollLeft+x-this.left)/this.width:.5,v=this.height?(this.view.scrollTop+y-this.top)/this.height:.5;
  this.mode=value==='fit'?'fit':'manual';this.scale=value==='fit'?this.fitScale():Math.min(8,Math.max(.02,Number(value)||1));this.render();
  if(value==='fit'){this.view.scrollLeft=0;this.view.scrollTop=0}else{this.view.scrollLeft=Math.max(0,Math.min(this.view.scrollWidth-this.view.clientWidth,this.left+u*this.width-x));this.view.scrollTop=Math.max(0,Math.min(this.view.scrollHeight-this.view.clientHeight,this.top+v*this.height-y))}
 }
 sync(){for(const b of this.controls)b.disabled=!this.ready;this.percent.textContent=this.ready?Math.round(this.scale*100)+'%':'加载中…';this.percent.setAttribute('aria-label','当前缩放比例');this.actual.classList.toggle('active',this.ready&&this.mode==='manual'&&Math.abs(this.scale-1)<.001);this.fit.classList.toggle('active',this.ready&&this.mode==='fit');this.view.classList.toggle('can-pan',this.ready&&(this.width>this.view.clientWidth||this.height>this.view.clientHeight))}
}
window.RecognitionViewer=RecognitionViewer;
