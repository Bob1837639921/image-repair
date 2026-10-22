// Repair uses confirmed, perspective-corrected crops and an independent queue.
let workStage='crop',repairSelection=null,repairDraft=null,repairSize=[1,1],repairSerial=0,repairBusy=false,repairPan=false;
const stages=document.createElement('div');stages.className='stage-switch';stages.innerHTML='<button id="cropStage" class="active" aria-pressed="true">1 裁剪校正</button><button id="repairStage" aria-pressed="false">2 折痕修复</button>';
document.querySelector('.brand').after(stages);
const repairPane=document.createElement('div');repairPane.id='repairPane';repairPane.className='pane';repairPane.hidden=true;
repairPane.innerHTML='<div id="repairViewport" class="viewport"><div id="repairWrap"><img id="repairImage" draggable="false"><div id="repairSelection"></div></div><div id="repairEmpty" hidden>暂无已确认裁剪的作品<br>请先在裁剪区确认图片</div></div>';
$('editor').append(repairPane);
let repairSelectionKind=null;
let repairMarks=[],repairActiveMark=null,repairMarkSignature=null,repairMarkSaveChain=Promise.resolve();
const repairMarkLayer=document.createElement('div');repairMarkLayer.id='repairMarkLayer';$('repairWrap').append(repairMarkLayer);
for(const direction of ['nw','n','ne','e','se','s','sw','w']){const handle=document.createElement('i');handle.className='repair-handle '+direction;$('repairSelection').append(handle)}
function saveRepairMarks(){
 const id=current.id,regions=repairMarks.map(mark=>({...mark,region:[...mark.region]})),signature=repairMarkSignature;
 const task=repairMarkSaveChain.catch(()=>{}).then(async()=>{const item=await api('repair/marks',{id,signature,regions});replace(item);$('repairMarksStatus').textContent='标记已保存，只在点击修复时处理'});
 repairMarkSaveChain=task;task.catch(e=>{$('repairMarksStatus').textContent='标记未保存：'+e.message;toast(e.message)});
}
function paintRepairMarks(){
 repairMarkLayer.replaceChildren();$('repairMarksList').replaceChildren();
 repairMarks.forEach((mark,index)=>{
  const name=`${index+1} · ${mark.kind==='crease'?'折痕':'凸起'}`,box=document.createElement('div');box.className='repair-mark '+mark.kind+(mark.id===repairActiveMark?' active':'');
  const [x1,y1,x2,y2]=mark.region;Object.assign(box.style,{left:x1*100+'%',top:y1*100+'%',width:(x2-x1)*100+'%',height:(y2-y1)*100+'%'});
  const badge=document.createElement('button');badge.textContent=name;badge.onpointerdown=e=>e.stopPropagation();badge.onclick=()=>selectRepairMark(mark.id);badge.oncontextmenu=e=>showRepairContextMenu(e,mark.id);box.append(badge);repairMarkLayer.append(box);
  const row=document.createElement('div');row.className='repair-mark-row '+mark.kind;const choose=document.createElement('button');choose.textContent=name;choose.onclick=()=>selectRepairMark(mark.id);choose.classList.toggle('active',mark.id===repairActiveMark);
  const remove=document.createElement('button');remove.textContent='×';remove.setAttribute('aria-label','删除标记 '+(index+1));remove.onclick=()=>deleteRepairMark(mark.id);choose.oncontextmenu=e=>showRepairContextMenu(e,mark.id);row.append(choose,remove);$('repairMarksList').append(row);
 });
 $('repairMarksCount').textContent=`已标记 ${repairMarks.length} 处`;
}
function selectRepairMark(id){if(repairBusy||repairDraft)return;const mark=repairMarks.find(x=>x.id===id);if(!mark)return;repairActiveMark=id;repairSelection=[...mark.region];repairSelectionKind=mark.kind;$('repairKind').value=mark.kind;paintRepairSelection();paintRepairMarks()}
function loadRepairMarks(info){closeRepairContextMenu();repairMarks=(info.marks||[]).map(mark=>({...mark,region:[...mark.region]}));repairMarkSignature=info.signature;repairActiveMark=null;$('repairKind').value='';paintRepairMarks();$('repairMarksStatus').textContent=info.signature?'标记后可继续框选，全部标好再点击修复':'后台待更新：请重启工具后使用多区域标记'}
const repairKindPicker=document.createElement('div');repairKindPicker.id='repairKindPicker';repairKindPicker.hidden=true;repairKindPicker.setAttribute('role','group');repairKindPicker.setAttribute('aria-label','选择这次框选的修复类型');repairKindPicker.innerHTML='<span id="repairKindPrompt">这个选区需要修复什么？</span><div><button id="repairChooseCrease" aria-pressed="false">折痕</button><button id="repairChooseBump" aria-pressed="false">凸起</button></div>';repairPane.append(repairKindPicker);
function showRepairKindPicker(){
 if(!repairSelection||repairBusy||repairDraft)return;
 const rect=$('repairSelection').getBoundingClientRect(),pane=repairPane.getBoundingClientRect(),view=$('repairViewport').getBoundingClientRect();
 repairKindPicker.hidden=false;repairKindPicker.style.left=Math.max(8,Math.min(rect.right-pane.left,view.right-pane.left-224))+'px';repairKindPicker.style.top=Math.max(48,Math.min(rect.bottom-pane.top+8,view.bottom-pane.top-100))+'px';
 $('repairKindPrompt').textContent=repairSelectionKind?'本次选区：'+(repairSelectionKind==='crease'?'折痕':'凸起'):'这个选区需要修复什么？';
 for(const [id,kind] of [['repairChooseCrease','crease'],['repairChooseBump','bump']]){$(id).classList.toggle('active',kind===repairSelectionKind);$(id).setAttribute('aria-pressed',String(kind===repairSelectionKind))}
}
function chooseRepairKind(kind){if(repairBusy||repairDraft||!repairSelection)return;if(!repairMarkSignature)return toast('请先重启工具后台以启用标记保存');if((repairSelection[2]-repairSelection[0])*repairSize[0]<4||(repairSelection[3]-repairSelection[1])*repairSize[1]<4)return toast('选区太小，请稍微扩大后标记');repairSelectionKind=kind;$('repairKind').value=kind;let mark=repairMarks.find(x=>x.id===repairActiveMark);if(mark){mark.region=[...repairSelection];mark.kind=kind}else{mark={id:Date.now().toString(36)+'-'+Math.random().toString(36).slice(2,10),region:[...repairSelection],kind};repairMarks.push(mark);repairActiveMark=mark.id}repairKindPicker.hidden=true;paintRepairSelection();paintRepairMarks();saveRepairMarks()}
$('repairChooseCrease').onclick=()=>chooseRepairKind('crease');$('repairChooseBump').onclick=()=>chooseRepairKind('bump');
const repairContextMenu=document.createElement('div');repairContextMenu.id='repairContextMenu';repairContextMenu.hidden=true;repairContextMenu.setAttribute('role','menu');repairContextMenu.setAttribute('aria-label','选框操作');
repairContextMenu.innerHTML='<span class="repair-context-title">选框操作</span><button type="button" data-kind="crease" role="menuitemradio">切换为折痕</button><button type="button" data-kind="bump" role="menuitemradio">切换为凸起</button><button type="button" id="repairDeleteMark" class="danger" role="menuitem">删除选框</button>';
document.body.append(repairContextMenu);
let repairContextTarget=null;
function closeRepairContextMenu(){repairContextMenu.hidden=true;repairContextTarget=null}
function deleteRepairMark(id){
 if(repairBusy||repairDraft)return;
 const exists=repairMarks.some(mark=>mark.id===id);
 if(exists)repairMarks=repairMarks.filter(mark=>mark.id!==id);
 if(id===null||repairActiveMark===id){repairActiveMark=null;repairSelection=null;repairSelectionKind=null;repairKindPicker.hidden=true;$('repairKind').value='';$('repairRegionText').textContent='尚未框选';paintRepairSelection()}
 paintRepairMarks();if(exists)saveRepairMarks();
}
function showRepairContextMenu(event,id){
 event.preventDefault();event.stopPropagation();closeRepairContextMenu();
 if(repairBusy||repairDraft)return toast('请先完成或放弃当前修复预览');
 const mark=repairMarks.find(mark=>mark.id===id);
 if(id!==null&&!mark)return;
 if(mark)selectRepairMark(id);
 repairKindPicker.hidden=true;repairContextTarget={item:current.id,id};
 for(const button of repairContextMenu.querySelectorAll('[data-kind]'))button.setAttribute('aria-checked',String(button.dataset.kind===repairSelectionKind));
 repairContextMenu.hidden=false;
 const bounds=repairContextMenu.getBoundingClientRect();
 repairContextMenu.style.left=Math.max(6,Math.min(event.clientX,window.innerWidth-bounds.width-6))+'px';
 repairContextMenu.style.top=Math.max(6,Math.min(event.clientY,window.innerHeight-bounds.height-6))+'px';
 repairContextMenu.querySelector('button').focus({preventScroll:true});
}
$('repairViewport').addEventListener('contextmenu',event=>{
 if(workStage!=='repair'||!current?.confirmed)return;
 const rect=$('repairWrap').getBoundingClientRect(),x=(event.clientX-rect.left)/rect.width,y=(event.clientY-rect.top)/rect.height;
 const inside=region=>region&&x>=region[0]&&x<=region[2]&&y>=region[1]&&y<=region[3];
 let mark=repairMarks.find(mark=>mark.id===repairActiveMark&&inside(mark.region));
 if(!mark)mark=[...repairMarks].reverse().find(mark=>inside(mark.region));
 if(mark)showRepairContextMenu(event,mark.id);
 else if(inside(repairSelection))showRepairContextMenu(event,null);
 else closeRepairContextMenu();
});
for(const button of repairContextMenu.querySelectorAll('button'))button.onclick=()=>{
 const target=repairContextTarget;closeRepairContextMenu();
 if(!target||target.item!==current?.id||workStage!=='repair'||repairBusy||repairDraft)return;
 if(target.id!==null){if(!repairMarks.some(mark=>mark.id===target.id))return;selectRepairMark(target.id)}
 if(button.dataset.kind)chooseRepairKind(button.dataset.kind);else deleteRepairMark(target.id);
};
document.addEventListener('pointerdown',event=>{if(!repairContextMenu.contains(event.target))closeRepairContextMenu()},true);
document.addEventListener('scroll',closeRepairContextMenu,true);window.addEventListener('resize',closeRepairContextMenu);
document.addEventListener('keydown',event=>{
 if(repairContextMenu.hidden)return;
 if(['Escape','ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(event.key)){
  event.preventDefault();event.stopImmediatePropagation();
  if(event.key==='Escape')return closeRepairContextMenu();
  const buttons=[...repairContextMenu.querySelectorAll('button')],index=buttons.indexOf(document.activeElement);
  buttons[(index+(event.key==='ArrowUp'||event.key==='ArrowLeft'?-1:1)+buttons.length)%buttons.length].focus();
 }else if(event.key==='Tab')closeRepairContextMenu();
},true);
const repairZoomBar=document.createElement('div');repairZoomBar.className='repair-zoom-bar';repairZoomBar.setAttribute('aria-label','修复画面缩放');repairZoomBar.innerHTML='<button id="repairZoomOut" title="缩小" aria-label="缩小修复图片">−</button><output id="repairZoomPercent">100%</output><button id="repairZoomIn" title="放大" aria-label="放大修复图片">＋</button><button id="repairZoomActual">100%</button><button id="repairZoomFit">适合</button><span>滚轮缩放 · 空格拖动</span>';repairPane.append(repairZoomBar);
const repairResult=document.createElement('section');repairResult.id='repairResult';repairResult.hidden=true;
repairResult.innerHTML='<div class="repair-result-head"><div><strong>修复前后对比</strong><span id="repairResultStatus" role="status" aria-live="polite"></span></div><button id="repairResultView" hidden>查看完整作品</button></div><div id="repairCompareTools" hidden><button id="repairCompareOut" aria-label="缩小对比图片">−</button><output id="repairComparePercent">100%</output><button id="repairCompareIn" aria-label="放大对比图片">＋</button><button id="repairCompareActual">100%</button><button id="repairCompareFit">适合</button><span>滚轮缩放 · 拖动联动</span></div><div id="repairResultBody" aria-busy="false"><div id="repairResultMessage"><span class="repair-spinner" aria-hidden="true"></span><strong id="repairResultMessageTitle">正在修复选区</strong><p id="repairResultMessageText">修复完成后将在这里显示结果</p><button id="repairResultRetry" hidden>重新修复</button></div><div id="repairCompare" hidden><div class="repair-compare-cell"><strong>修复前</strong><div class="repair-compare-viewport" id="repairBeforeViewport"><canvas id="repairBeforeCanvas" aria-label="修复前原图"></canvas></div></div><div class="repair-compare-cell"><strong>修复后</strong><div class="repair-compare-viewport" id="repairAfterViewport"><canvas id="repairResultCanvas" aria-label="修复后效果"></canvas></div></div></div></div><div id="repairResultActions"></div>';
repairPane.append(repairResult);
repairResult.querySelector('.repair-result-head').insertBefore($('repairCompareTools'),$('repairResultView'));
$('repairCompareTools').title='滚轮缩放 · 拖动联动；点击对比卡片可选择要缩放的区域';
let repairResultImage=null,repairResultBeforeImage=null,repairResultRegion=null,repairResultFull=false,repairResultSerial=0,repairCompareScale='fit';
let repairResultRegions=[],repairCompareGroups=[],repairCompareActive=0;
const repairSettings=document.createElement('div');repairSettings.id='repairSettings';repairSettings.hidden=true;
repairSettings.innerHTML='<div class="panel-caption">局部修复</div><p class="repair-help">拖动框选折痕或凸起。框内修复，框外保持原样。</p><div class="repair-tools"><button id="repairBox" class="active" aria-pressed="true">框选</button><button id="repairPan" aria-pressed="false">移动画面</button></div><label>缩放<select id="repairZoom"><option value="fit">适合窗口</option><option value=".5">原图 50%</option><option value="1">原图 100%</option><option value="2">原图 200%</option><option value="4">原图 400%</option></select></label><label>修复内容<select id="repairKind"><option value="crease">折痕明暗</option><option value="bump">凸起阴影</option></select></label><label>处理方式<select id="repairMethod"><option value="local">常规修复 · 本机处理</option><option value="ai">AI 精修 · 通过配置的服务</option></select></label><label>常规修复强度 <output id="repairStrengthValue">65%</output><input id="repairStrength" type="range" min="0" max="1" step=".05" value=".65"></label><p id="repairRegionText" class="repair-help">尚未框选</p><button id="repairPreview" class="primary wide">生成局部修复预览</button><div id="repairDraftActions" hidden><p class="repair-help">正在预览候选，采用前不会替换结果。</p><button id="repairAccept" class="primary wide">采用这次修复</button><button id="repairDiscard" class="wide">放弃这次预览</button></div><button id="repairBefore" class="wide">按住查看修复前</button><div class="repair-tools"><button id="repairUndo">撤销修复</button><button id="repairRedo">重做</button></div><p id="repairState" class="repair-help"></p><details class="advanced-controls"><summary>AI 连接</summary><p class="repair-help">支持 CLIProxyAPI。AI 仅在点击预览时发送选区及周边；可能产生调用费用。聊天模型需服务支持图像编辑才可用。</p><label>API Base URL<input id="repairBaseURL" type="url" value="http://127.0.0.1:8317/v1" autocomplete="off"></label><label>API Key<input id="repairKey" type="password" autocomplete="off" placeholder="只保存在本次服务内存中"></label><label>图像编辑模型<input id="repairModel" value="gpt-image-1.5" autocomplete="off"></label><button id="repairConnect" class="wide">保存连接</button><button id="repairTest" class="wide">检测连接与模型</button><p id="repairConfigState" class="repair-help"></p></details><div class="final-actions"><button id="repairComplete" class="primary wide">确认成品 / 无需修复</button></div>';
settingsPanel.append(repairSettings);
$('repairKey').placeholder='保存在本机，使用当前 Windows 账户加密';
const repairLegend=document.createElement('div');repairLegend.className='repair-legend';repairLegend.setAttribute('aria-label','选框颜色说明');repairLegend.innerHTML='<strong>选框说明</strong><div><span><i class="crease" aria-hidden="true"></i>橙色 · 折痕</span><span><i class="bump" aria-hidden="true"></i>蓝色 · 凸起</span></div><p><i class="pending" aria-hidden="true"></i>灰色虚线 · 尚未选择类型</p>';repairSettings.prepend(repairLegend);
const repairMarksPanel=document.createElement('div');repairMarksPanel.id='repairMarksPanel';repairMarksPanel.innerHTML='<strong id="repairMarksCount">已标记 0 处</strong><div id="repairMarksList"></div><p id="repairMarksStatus" class="repair-help">标记后可继续框选，全部标好再点击修复</p>';$('repairRegionText').before(repairMarksPanel);
$('repairResultActions').append($('repairDraftActions'));
const repairRegenerate=document.createElement('button');repairRegenerate.id='repairRegenerate';repairRegenerate.textContent='重新修复';
$('repairAccept').textContent='采用修复';$('repairDiscard').textContent='放弃预览';
$('repairAccept').after(repairRegenerate);
repairRegenerate.title='按当前标记和上次的修复方式重新生成预览；AI 修复会再次调用已配置的服务';
$('repairPreview').textContent='常规修复';
function resetRepairResult(){++repairResultSerial;repairResult.hidden=true;repairPane.classList.remove('has-result');repairResultImage=null;repairResultRegion=null;repairResultFull=false;$('repairDraftActions').hidden=true;$('repairPreview').disabled=false;if($('repairAI'))$('repairAI').disabled=false}
function setRepairResultState(state,message){
 repairResult.hidden=false;repairPane.classList.add('has-result');repairResult.dataset.state=state;
 $('repairResultBody').setAttribute('aria-busy',String(state==='loading'));
 $('repairResultStatus').textContent=state==='loading'?'处理中…':state==='ready'?`待采用 · ${repairResultRegions.length||1} 处修复，逐处对比 · 左侧图片尚未修改`:'修复未完成';
 $('repairResultMessage').hidden=state==='ready';$('repairCompare').hidden=state!=='ready';$('repairCompareTools').hidden=state!=='ready'||!repairResultFull;$('repairResultView').hidden=state!=='ready';$('repairResultRetry').hidden=state!=='error';
 $('repairResultMessageTitle').textContent=state==='error'?'修复失败':'正在修复选区';
 $('repairResultMessageText').textContent=message||(state==='loading'?'请稍候，完成后将在这里展示修复效果':'');
 $('repairDraftActions').hidden=state!=='ready';
 if(state==='ready')fitRepairCompare();
}
function paintRepairResult(){
 if(!repairResultImage||!repairResultBeforeImage)return;
 const im=repairResultImage,regions=repairResultFull?[null]:repairResultRegions.length?repairResultRegions:[{region:repairResultRegion}];
 repairCompareGroups=[];repairCompareActive=0;const container=$('repairCompare');container.replaceChildren();container.scrollTop=0;
 regions.forEach((mark,index)=>{
  let box=[0,0,im.naturalWidth,im.naturalHeight];
  if(mark?.region){const [x1,y1,x2,y2]=mark.region,pad=Math.max(16,Math.min(100,Math.max((x2-x1)*im.naturalWidth,(y2-y1)*im.naturalHeight)*.12));box=[Math.max(0,Math.floor(x1*im.naturalWidth-pad)),Math.max(0,Math.floor(y1*im.naturalHeight-pad)),Math.min(im.naturalWidth,Math.ceil(x2*im.naturalWidth+pad)),Math.min(im.naturalHeight,Math.ceil(y2*im.naturalHeight+pad))]}
  const card=document.createElement('section');card.className='repair-compare-group'+(mark?.kind?' '+mark.kind:'');
  const title=document.createElement('strong');title.className='repair-compare-title';title.textContent=repairResultFull?'完整作品':`${index+1} · ${mark?.kind==='bump'?'凸起':'折痕'}`;
  const pair=document.createElement('div');pair.className='repair-compare-pair';
  const group={card,views:[],canvases:[],scale:'fit'};
  for(const [label,image] of [['修复前',repairResultBeforeImage],['修复后',im]]){
   const cell=document.createElement('div');cell.className='repair-compare-cell';const head=document.createElement('strong');head.textContent=label;
   const view=document.createElement('div');view.className='repair-compare-viewport';const canvas=document.createElement('canvas');canvas.setAttribute('aria-label',title.textContent+' '+label);
   canvas.width=box[2]-box[0];canvas.height=box[3]-box[1];canvas.getContext('2d').drawImage(image,box[0],box[1],canvas.width,canvas.height,0,0,canvas.width,canvas.height);
   view.append(canvas);cell.append(head,view);pair.append(cell);group.views.push(view);group.canvases.push(canvas);
  }
  card.append(title,pair);container.append(card);repairCompareGroups.push(group);
  card.addEventListener('pointerdown',()=>activateRepairCompare(index));
  for(const view of group.views){
   view.addEventListener('wheel',e=>{if(!repairResultFull||!e.deltaY)return;e.preventDefault();activateRepairCompare(index);zoomRepairCompare(repairCompareCurrentScale()*Math.exp(-Math.max(-100,Math.min(100,e.deltaY))*.0025),view,[e.clientX,e.clientY])},{passive:false});
   view.addEventListener('scroll',()=>syncRepairCompare(group,view));
   view.onpointerdown=e=>{if(!repairResultFull||![0,1].includes(e.button))return;e.preventDefault();view.setPointerCapture(e.pointerId);const start=[e.clientX,e.clientY,view.scrollLeft,view.scrollTop];const move=ev=>{view.scrollLeft=start[2]+start[0]-ev.clientX;view.scrollTop=start[3]+start[1]-ev.clientY;syncRepairCompare(group,view)};const stop=()=>{view.removeEventListener('pointermove',move);view.removeEventListener('pointerup',stop);view.removeEventListener('pointercancel',stop)};view.addEventListener('pointermove',move);view.addEventListener('pointerup',stop);view.addEventListener('pointercancel',stop)};
  }
 });
 container.classList.toggle('multiple',regions.length>1);container.classList.toggle('details',!repairResultFull);$('repairCompareTools').hidden=!repairResultFull;activateRepairCompare(0);fitRepairCompare();
 $('repairResultView').textContent=repairResultFull?'查看各处细节':'查看完整作品';
 $('repairResultStatus').textContent=`待采用 · ${repairResultRegions.length||1} 处修复，逐处对比 · 左侧图片尚未修改`;
}
function activateRepairCompare(index){repairCompareActive=index;repairCompareGroups.forEach((group,i)=>group.card.classList.toggle('active',i===index));$('repairComparePercent').textContent=Math.round(repairCompareCurrentScale()*100)+'%'}
function syncRepairCompare(group,source){for(const other of group.views){if(other!==source){if(other.scrollLeft!==source.scrollLeft)other.scrollLeft=source.scrollLeft;if(other.scrollTop!==source.scrollTop)other.scrollTop=source.scrollTop}}}
function fitRepairCompare(){
 if(!repairResultImage||$('repairCompare').hidden)return;
 for(const group of repairCompareGroups){const canvas=group.canvases[0],scale=group.scale==='fit'?Math.max(.01,Math.min(...group.views.flatMap(view=>[(view.clientWidth-16)/canvas.width,(view.clientHeight-16)/canvas.height]))):group.scale;
  for(const c of group.canvases){c.style.width=c.width*scale+'px';c.style.height=c.height*scale+'px'}
 }
 $('repairComparePercent').textContent=Math.round(repairCompareCurrentScale()*100)+'%';
}
function zoomRepairCompare(value,source,anchor){
 if(!repairResultFull||!repairResultImage||$('repairCompare').hidden)return;
 const group=repairCompareGroups[repairCompareActive];if(!group)return;source=source||group.views[1];
 const canvas=source.querySelector('canvas'),before=canvas.getBoundingClientRect(),bounds=source.getBoundingClientRect(),point=anchor||[bounds.left+source.clientWidth/2,bounds.top+source.clientHeight/2];
 const position=[(point[0]-before.left)/before.width,(point[1]-before.top)/before.height];
 group.scale=value==='fit'?'fit':Math.max(.02,Math.min(8,value));fitRepairCompare();
 const after=canvas.getBoundingClientRect();source.scrollLeft+=after.left+position[0]*after.width-point[0];source.scrollTop+=after.top+position[1]*after.height-point[1];
 syncRepairCompare(group,source);
}
function repairCompareCurrentScale(){const c=repairCompareGroups[repairCompareActive]?.canvases[0];return c?parseFloat(c.style.width)/c.width||1:1}
new ResizeObserver(fitRepairCompare).observe($('repairCompare'));
$('repairCompareOut').onclick=()=>zoomRepairCompare(repairCompareCurrentScale()/1.25);
$('repairCompareIn').onclick=()=>zoomRepairCompare(repairCompareCurrentScale()*1.25);
$('repairCompareActual').onclick=()=>zoomRepairCompare(1);
$('repairCompareFit').onclick=()=>zoomRepairCompare('fit');
$('repairResultView').onclick=()=>{repairResultFull=!repairResultFull;paintRepairResult()};
$('repairResultRetry').onclick=()=>$('repairPreview').click();
const cropSelect=select,cropDrawList=drawList,cropDrawStatus=drawStatus,cropStep=step;
function repairQueue(){return items.filter(x=>x.confirmed)}
function updateRepairNavigation(){const queue=repairQueue(),index=queue.findIndex(x=>x.id===current?.id);$('position').textContent=`${index>=0?index+1:0} / ${queue.length}`;$('prev').disabled=queue.length<2;$('next').disabled=queue.length<2}
drawList=function(reveal=false){if(workStage==='crop')return cropDrawList(reveal);const all=items;try{items=repairQueue();cropDrawList(reveal);const visible=items.filter(x=>x.name.toLowerCase().includes($('search').value.toLowerCase()));document.querySelectorAll('#list .item em').forEach((el,i)=>{const done=visible[i]?.repair_state?.completed;el.textContent=done?'✓ 成品已确认':'○ 待修复';el.classList.toggle('done',!!done)});$('exportCount').textContent=items.filter(x=>x.repair_state?.completed).length}finally{items=all}updateRepairNavigation()};
drawStatus=function(){if(workStage==='crop')return cropDrawStatus();updateRepairNavigation()};
select=async function(id){if(workStage==='crop')return cropSelect(id);return selectRepair(id)};
step=function(delta){if(workStage==='crop')return cropStep(delta);const queue=repairQueue();if(queue.length<2)return;const i=queue.findIndex(x=>x.id===current?.id);selectRepair(queue[((i+delta)%queue.length+queue.length)%queue.length].id)};
function repairCurrentScale(){return parseFloat($('repairWrap').style.width)/repairSize[0]||1}
function fitRepair(){if(!$('repairImage').naturalWidth)return;const view=$('repairViewport'),scale=$('repairZoom').value==='fit'?Math.max(.01,Math.min((view.clientWidth-26)/repairSize[0],(view.clientHeight-26)/repairSize[1])):Number($('repairZoom').value);$('repairWrap').style.width=repairSize[0]*scale+'px';$('repairWrap').style.height=repairSize[1]*scale+'px';$('repairZoomPercent').textContent=Math.round(scale*100)+'%';paintRepairSelection()}
function zoomRepair(value,anchor){
 if(!$('repairImage').naturalWidth||!current?.confirmed||!$('repairEmpty').hidden)return;
 const view=$('repairViewport'),wrap=$('repairWrap'),bounds=view.getBoundingClientRect(),before=wrap.getBoundingClientRect();
 const point=anchor||[bounds.left+view.clientWidth/2,bounds.top+view.clientHeight/2];
 const pixel=[(point[0]-before.left)/before.width,(point[1]-before.top)/before.height];
 const control=$('repairZoom'),next=value==='fit'?'fit':String(Math.max(.02,Math.min(8,Number(value))));
 let custom=$('repairZoomCustom');if(!custom){custom=document.createElement('option');custom.id='repairZoomCustom';control.append(custom)}
 custom.value=next;custom.textContent=next==='fit'?'适合窗口':Math.round(Number(next)*100)+'%';control.value=next;
 fitRepair();const after=wrap.getBoundingClientRect();
 view.scrollLeft+=after.left+pixel[0]*after.width-point[0];view.scrollTop+=after.top+pixel[1]*after.height-point[1];
}
function paintRepairSelection(){const el=$('repairSelection');el.className=repairSelectionKind||'pending';el.hidden=!repairSelection;if(!repairSelection)return;const [x1,y1,x2,y2]=repairSelection;Object.assign(el.style,{left:x1*100+'%',top:y1*100+'%',width:(x2-x1)*100+'%',height:(y2-y1)*100+'%'});$('repairRegionText').textContent=`选区 ${Math.round((x2-x1)*repairSize[0])} × ${Math.round((y2-y1)*repairSize[1])} px`}
async function showRepairImage({before=false}={}){if(!current||workStage!=='repair')return;const serial=++repairSerial,id=current.id,revision=current.revision;const image=await decodedImage(`/api/repair/image/${id}?detail=1&v=${revision}${before?'&before=1':''}`);if(serial!==repairSerial||workStage!=='repair'||current?.id!==id)return;image.id='repairImage';image.draggable=false;$('repairImage').replaceWith(image);repairSize=[image.naturalWidth,image.naturalHeight];fitRepair();$('repairWrap').style.visibility='visible';$('repairViewport').classList.remove('loading-image')}
async function selectRepair(id){if(repairBusy)return;const item=repairQueue().find(x=>x.id===id);if(!item)return;await saveChain.catch(()=>{});current=item;repairSelection=null;repairDraft=null;++repairSerial;$('repairDraftActions').hidden=true;$('repairEmpty').hidden=true;$('repairWrap').style.visibility='hidden';$('repairViewport').classList.add('loading-image');$('repairZoom').value='fit';$('repairRegionText').textContent='尚未框选';$('title').textContent=item.name;$('title').title=item.name;drawList(true);try{const info=await(await fetch('/api/repair/info/'+id)).json();if(info.error)throw Error(info.error);if(workStage!=='repair'||current?.id!==id)return;repairSize=info.size;loadRepairMarks(info);$('resolution').textContent=`裁剪后 ${info.size[0]} × ${info.size[1]} px`;$('status').textContent=info.state.completed?'成品已确认':'待修复';$('repairState').textContent=`已采用 ${info.state.layers?.length||0} 次修复`;$('repairUndo').disabled=!info.state.layers?.length;$('repairRedo').disabled=!info.state.redo?.length;await showRepairImage()}catch(e){$('repairViewport').classList.remove('loading-image');toast(e.message)}}
async function switchStage(stage){if(repairBusy)return toast('请等待本次修复完成');await saveChain.catch(()=>{});workStage=stage;++originalSerial;++previewSerial;++repairSerial;document.body.classList.toggle('repair-mode',stage==='repair');$('cropStage').classList.toggle('active',stage==='crop');$('repairStage').classList.toggle('active',stage==='repair');$('cropStage').setAttribute('aria-pressed',String(stage==='crop'));$('repairStage').setAttribute('aria-pressed',String(stage==='repair'));$('originalPane').hidden=stage==='repair';$('resultPane').hidden=true;repairPane.hidden=stage!=='repair';repairSettings.hidden=stage!=='repair';$('editor').hidden=false;$('empty').hidden=true;$('filter').value='all';$('search').value='';compare=false;if(stage==='crop'){drawList();if(current)await cropSelect(current.id);setViewMode(false)}else{drawList();const queue=repairQueue();if(queue.length)await selectRepair(queue.some(x=>x.id===current?.id)?current.id:queue[0].id);else{$('repairWrap').style.visibility='hidden';$('repairEmpty').hidden=false;$('title').textContent='折痕修复';$('resolution').textContent='';$('status').textContent='等待确认裁剪';updateRepairNavigation()}}}
const selectRepairCore=selectRepair;
selectRepair=async function(id){if(repairBusy)return;if(repairDraft)return toast('请先采用或放弃当前修复预览');await repairMarkSaveChain.catch(()=>{});repairKindPicker.hidden=true;repairSelectionKind=null;repairMarks=[];repairActiveMark=null;resetRepairResult();return selectRepairCore(id)};
async function requestStage(stage){if(repairBusy)return toast('请等待本次修复完成');if(repairDraft)return toast('请先采用或放弃当前修复预览');++selectionSerial;await switchStage(stage);const actions=stage==='repair'?repairSettings.querySelector('.final-actions'):settingsPanel.querySelector(':scope > .final-actions');actions.append($('openExport'),$('progress'));$('export').childNodes[0].textContent=stage==='repair'?'导出成品 ':'导出已确认 ';}
$('cropStage').onclick=()=>requestStage('crop');$('repairStage').onclick=()=>requestStage('repair');
document.addEventListener('keydown',e=>{if(workStage==='repair'&&e.shiftKey&&e.key.startsWith('Arrow')){e.preventDefault();e.stopImmediatePropagation()}},true);
new ResizeObserver(fitRepair).observe($('repairViewport'));
$('repairZoom').onchange=()=>zoomRepair($('repairZoom').value);
$('repairZoomIn').onclick=()=>zoomRepair(repairCurrentScale()*1.25);
$('repairZoomOut').onclick=()=>zoomRepair(repairCurrentScale()/1.25);
$('repairZoomActual').onclick=()=>zoomRepair(1);
$('repairZoomFit').onclick=()=>zoomRepair('fit');
$('repairViewport').addEventListener('wheel',e=>{if(!e.deltaY||!$('repairImage').naturalWidth||!$('repairEmpty').hidden)return;e.preventDefault();zoomRepair(repairCurrentScale()*Math.exp(-Math.max(-100,Math.min(100,e.deltaY))*.0025),[e.clientX,e.clientY])},{passive:false});
let repairSpace=false;
document.addEventListener('keydown',e=>{if(workStage!=='repair'||e.code!=='Space'||['INPUT','SELECT','TEXTAREA'].includes(e.target.tagName)||e.target.isContentEditable)return;e.preventDefault();repairSpace=true;$('repairViewport').classList.add('panning')});
document.addEventListener('keyup',e=>{if(e.code==='Space'){repairSpace=false;$('repairViewport').classList.remove('panning')}});
window.addEventListener('blur',()=>{repairSpace=false;$('repairViewport').classList.remove('panning')});
$('repairBox').onclick=()=>{repairPan=false;$('repairBox').classList.add('active');$('repairPan').classList.remove('active');$('repairBox').setAttribute('aria-pressed','true');$('repairPan').setAttribute('aria-pressed','false')};
$('repairPan').onclick=()=>{repairPan=true;$('repairPan').classList.add('active');$('repairBox').classList.remove('active');$('repairPan').setAttribute('aria-pressed','true');$('repairBox').setAttribute('aria-pressed','false')};
// Hit testing uses screen pixels, so handles remain usable at every zoom level.
function repairRegionHit(region,x,y,rect){
 if(!region)return null;
 const [l,t,r,b]=region.map((v,i)=>v*(i%2?rect.height:rect.width));
 const px=x-rect.left,py=y-rect.top,tolerance=8;
 if(px<l-tolerance||px>r+tolerance||py<t-tolerance||py>b+tolerance)return null;
 const horizontal=Math.abs(px-l)<=tolerance?'w':Math.abs(px-r)<=tolerance?'e':'';
 const vertical=Math.abs(py-t)<=tolerance?'n':Math.abs(py-b)<=tolerance?'s':'';
 return vertical+horizontal||'move';
}
function repairEditTarget(event,rect){
 const mode=repairRegionHit(repairSelection,event.clientX,event.clientY,rect);
 if(mode)return {id:repairActiveMark,region:[...repairSelection],kind:repairSelectionKind,mode};
 for(const mark of [...repairMarks].reverse()){
  const mode=repairRegionHit(mark.region,event.clientX,event.clientY,rect);
  if(mode)return {...mark,region:[...mark.region],mode};
 }
 return null;
}
function editRepairRegion(region,mode,dx,dy,size){
 const next=[...region],bound=(v,min,max)=>Math.max(min,Math.min(max,v));
 if(mode==='move'){
  dx=bound(dx,-region[0],1-region[2]);dy=bound(dy,-region[1],1-region[3]);
  return [region[0]+dx,region[1]+dy,region[2]+dx,region[3]+dy];
 }
 const minW=Math.min(1,4/size[0]),minH=Math.min(1,4/size[1]);
 if(mode.includes('w'))next[0]=bound(region[0]+dx,0,region[2]-minW);
 if(mode.includes('e'))next[2]=bound(region[2]+dx,region[0]+minW,1);
 if(mode.includes('n'))next[1]=bound(region[1]+dy,0,region[3]-minH);
 if(mode.includes('s'))next[3]=bound(region[3]+dy,region[1]+minH,1);
 return next;
}
function repairEditCursor(mode){return mode==='move'?'move':mode?mode+'-resize':'crosshair'}
$('repairViewport').addEventListener('pointermove',event=>{
 const view=$('repairViewport');if(view.hasPointerCapture(event.pointerId))return;
 const target=repairEditTarget(event,$('repairWrap').getBoundingClientRect());
 view.style.cursor=repairPan||repairSpace?'grab':repairBusy||repairDraft?'default':repairEditCursor(target?.mode);
});
$('repairViewport').onpointerdown=e=>{
 if(![0,1].includes(e.button)||repairBusy||!current?.confirmed||!$('repairEmpty').hidden)return;
 const panGesture=repairPan||repairSpace||e.button===1;
 if(repairDraft&&!panGesture)return toast('请先采用或放弃当前预览');
 const view=$('repairViewport'),rect=$('repairWrap').getBoundingClientRect();
 if(!rect.width||!rect.height)return;
 const target=panGesture?null:repairEditTarget(e,rect);
 if(!panGesture&&!target&&(e.clientX<rect.left||e.clientX>rect.right||e.clientY<rect.top||e.clientY>rect.bottom))return;
 e.preventDefault();repairKindPicker.hidden=true;
 const previous={region:repairSelection&&[...repairSelection],kind:repairSelectionKind,id:repairActiveMark};
 const itemId=current.id,x=e.clientX,y=e.clientY,left=view.scrollLeft,top=view.scrollTop;
 const point=ev=>[Math.max(0,Math.min(1,(ev.clientX-rect.left)/rect.width)),Math.max(0,Math.min(1,(ev.clientY-rect.top)/rect.height))];
 const start=point(e);let moved=false;
 if(target){repairActiveMark=target.id;repairSelection=[...target.region];repairSelectionKind=target.kind;$('repairKind').value=target.kind||'';paintRepairSelection();paintRepairMarks()}
 view.setPointerCapture(e.pointerId);
 const move=ev=>{
  if(ev.pointerId!==e.pointerId||current?.id!==itemId||workStage!=='repair')return;
  if(panGesture){view.scrollLeft=left+x-ev.clientX;view.scrollTop=top+y-ev.clientY;return}
  if(!moved&&Math.hypot(ev.clientX-x,ev.clientY-y)<2)return;
  moved=true;
  if(target){
   repairSelection=editRepairRegion(target.region,target.mode,(ev.clientX-x)/rect.width,(ev.clientY-y)/rect.height,repairSize);
   const mark=repairMarks.find(mark=>mark.id===target.id);if(mark)mark.region=[...repairSelection];
   paintRepairMarks();
  }else{
   repairSelectionKind=null;repairActiveMark=null;$('repairKind').value='';
   const end=point(ev);repairSelection=[Math.min(start[0],end[0]),Math.min(start[1],end[1]),Math.max(start[0],end[0]),Math.max(start[1],end[1])];
  }
  view.style.cursor=repairEditCursor(target?.mode);paintRepairSelection();
 };
 const up=ev=>{
  if(ev.pointerId!==e.pointerId)return;
  view.removeEventListener('pointermove',move);view.removeEventListener('pointerup',up);view.removeEventListener('pointercancel',up);view.removeEventListener('lostpointercapture',up);
  if(view.hasPointerCapture(e.pointerId))view.releasePointerCapture(e.pointerId);
  if(panGesture||current?.id!==itemId||workStage!=='repair')return;
  if(ev.type==='pointercancel'||ev.type==='lostpointercapture'){
   const mark=target&&repairMarks.find(mark=>mark.id===target.id);if(mark)mark.region=[...target.region];
   repairSelection=previous.region;repairSelectionKind=previous.kind;repairActiveMark=previous.id;$('repairKind').value=previous.kind||'';paintRepairSelection();paintRepairMarks();return;
  }
  if(moved&&target?.id)saveRepairMarks();
  if(repairSelection&&!repairSelectionKind&&(moved||target))showRepairKindPicker();
 };
 view.addEventListener('pointermove',move);view.addEventListener('pointerup',up);view.addEventListener('pointercancel',up);view.addEventListener('lostpointercapture',up);
};
$('repairStrength').oninput=()=>{$('repairStrengthValue').textContent=Math.round(Number($('repairStrength').value)*100)+'%'};
$('repairPreview').onclick=async()=>{
 if(repairBusy)return;if(repairDraft)return toast('请先采用或放弃当前修复结果');if(!repairMarks.length&&!repairSelection)return toast('请先框选并分类需要修复的位置');
 if(repairSelection&&!repairSelectionKind){showRepairKindPicker();return toast('请先为刚框选的区域选择折痕或凸起')}
 repairKindPicker.hidden=true;
 repairBusy=true;$('repairPreview').disabled=true;$('repairPreview').textContent='正在修复…';
 const regions=repairMarks.map(mark=>({...mark,region:[...mark.region]})),id=current.id,serial=++repairResultSerial,region=[Math.min(...regions.map(x=>x.region[0])),Math.min(...regions.map(x=>x.region[1])),Math.max(...regions.map(x=>x.region[2])),Math.max(...regions.map(x=>x.region[3]))];repairResultRegions=regions;repairResultImage=null;repairResultRegion=region;repairResultFull=false;
 setRepairResultState('loading',`${$('repairMethod').value==='ai'?'AI 将按分类逐处修复':'正在处理'}本图 ${regions.length} 处标记，左侧图片保持不变`);
 try{
  await repairMarkSaveChain;
  const result=await api('repair/preview',{id,regions,method:$('repairMethod').value,strength:Number($('repairStrength').value)});
  if(current?.id!==id||workStage!=='repair'||serial!==repairResultSerial)return;
  const [beforeImage,image]=await Promise.all([decodedImage(`/api/repair/image/${id}?detail=1&v=${current.revision}`),decodedImage(`/api/repair/image/${id}?detail=1&v=${current.revision}&draft=${result.draft}`)]);
  if(current?.id!==id||workStage!=='repair'||serial!==repairResultSerial)return;
  repairDraft=result.draft;repairResultBeforeImage=beforeImage;repairResultImage=image;paintRepairResult();setRepairResultState('ready');
 }catch(e){if(serial===repairResultSerial){repairDraft=null;setRepairResultState('error',e.message)}}
 finally{repairBusy=false;$('repairPreview').disabled=!!repairDraft;$('repairPreview').textContent='常规修复'}
};
async function repairAction(action){if(repairBusy||!current?.confirmed)return;repairBusy=true;const id=current.id;try{const item=await api('repair/'+action,{id,draft:repairDraft});replace(item);repairDraft=null;repairSelection=null;await selectRepairAfterBusy(id)}catch(e){toast(e.message)}finally{repairBusy=false}}
async function selectRepairAfterBusy(id){repairBusy=false;await selectRepair(id);repairBusy=true}
$('repairAccept').onclick=()=>repairAction('accept');$('repairUndo').onclick=()=>repairAction('undo');$('repairRedo').onclick=()=>repairAction('redo');
$('repairComplete').onclick=async()=>{if(repairDraft)return toast('请先采用或放弃修复预览');await repairAction('complete')};
async function discardRepairPreview(){
 if(repairBusy)return false;
 repairBusy=true;
 try{if(repairDraft)await api('repair/discard',{id:current.id,draft:repairDraft});repairDraft=null;resetRepairResult();fitRepair();return true}
 catch(e){toast(e.message);return false}
 finally{repairBusy=false;aiRepairButton.disabled=!!repairDraft}
}
$('repairDiscard').onclick=discardRepairPreview;
$('repairBefore').onpointerdown=e=>{e.preventDefault();$('repairBefore').setPointerCapture(e.pointerId);showRepairImage({before:true})};
for(const event of ['pointerup','pointercancel','lostpointercapture'])$('repairBefore').addEventListener(event,()=>showRepairImage());
$('repairConnect').onclick=async()=>{try{const fields={base_url:$('repairBaseURL').value,model:$('repairModel').value};if($('repairKey').value)fields.key=$('repairKey').value;const result=await api('repair/config',fields);$('repairKey').value='';$('repairConfigState').textContent=result.configured?'连接已保存到本机，重启后自动读取':'地址和模型已保存，尚未配置 Key'}catch(e){toast(e.message)}};
$('repairTest').onclick=async()=>{try{const result=await api('repair/test',{});$('repairConfigState').textContent=result.note+'。模型：'+result.models.join('、')}catch(e){$('repairConfigState').textContent=e.message}};
fetch('/api/repair/config').then(r=>r.json()).then(config=>{$('repairBaseURL').value=config.base_url;$('repairModel').value=config.model;$('repairConfigState').textContent=config.warning||(config.persisted?'已读取本机保存的 AI 连接':config.configured?'已配置连接，点击保存可记住配置':'尚未配置 AI 连接，填写并保存后无需重复输入')});
const cropExport=$('export').onclick;$('export').onclick=()=>workStage==='crop'?cropExport():api('export',{format:$('format').value,stage:'repair'}).then(pollJob).catch(e=>toast(e.message));

// Connection settings are global; repair controls remain in the sidebar.
const aiConfig=document.createElement('dialog');aiConfig.id='aiConfigDialog';
aiConfig.setAttribute('aria-labelledby','aiConfigTitle');
aiConfig.innerHTML='<div class="ai-config-head"><h2 id="aiConfigTitle">AI 配置</h2><button id="closeAiConfig" aria-label="关闭 AI 配置">关闭</button></div><div id="aiConfigBody"></div>';
document.body.append(aiConfig);
const aiConfigButton=document.createElement('button');aiConfigButton.id='openAiConfig';aiConfigButton.textContent='AI 配置';aiConfigButton.setAttribute('aria-haspopup','dialog');
document.querySelector('.header-imports').after(aiConfigButton);
aiConfigButton.onclick=()=>aiConfig.showModal();$('closeAiConfig').onclick=()=>aiConfig.close();
aiConfig.addEventListener('click',e=>{if(e.target===aiConfig){const r=aiConfig.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)aiConfig.close()}});
const connection=repairSettings.querySelector('details.advanced-controls');
const configHelp=document.createElement('p');configHelp.className='repair-help';configHelp.textContent='配置 AI 修复使用的图像编辑服务。';$('aiConfigBody').append(configHelp);
for(const id of ['repairBaseURL','repairKey','repairModel'])$('aiConfigBody').append($(id).closest('label'));
$('aiConfigBody').append($('repairConnect'),$('repairTest'),$('repairConfigState'));
connection.remove();
$('repairKind').closest('label').hidden=true;
const noRepairKind=document.createElement('option');noRepairKind.value='';noRepairKind.textContent='选择一个标记后可修改类型';$('repairKind').prepend(noRepairKind);$('repairKind').value='';
$('repairKind').onchange=()=>{if(!$('repairKind').value||!repairActiveMark)return;chooseRepairKind($('repairKind').value)};
$('repairMethod').value='local';$('repairMethod').closest('label').hidden=true;
$('repairPreview').classList.remove('primary');
const aiRepairButton=document.createElement('button');aiRepairButton.id='repairAI';aiRepairButton.className='primary wide';aiRepairButton.textContent='AI 修复';
$('repairPreview').after(aiRepairButton);
const repairActions=document.createElement('div');repairActions.className='repair-action-row';$('repairPreview').before(repairActions);repairActions.append($('repairPreview'),aiRepairButton);
$('repairBefore').hidden=true;$('repairRedo').hidden=true;
const runRepairPreview=$('repairPreview').onclick;
let lastRepairMethod='local';
async function startRepairWith(method){
 if(repairBusy)return;if(repairDraft)return toast('请先采用或放弃当前修复结果');
 lastRepairMethod=method;$('repairMethod').value=method;
 aiRepairButton.disabled=true;aiRepairButton.textContent=method==='ai'?'AI 正在修复…':'AI 修复';
 try{await runRepairPreview()}finally{aiRepairButton.disabled=!!repairDraft;aiRepairButton.textContent='AI 修复'}
}
$('repairPreview').onclick=()=>startRepairWith('local');
aiRepairButton.onclick=()=>startRepairWith('ai');
$('repairResultRetry').onclick=()=>startRepairWith(lastRepairMethod);
repairRegenerate.onclick=async()=>{
 if(repairBusy)return;
 if(!await discardRepairPreview())return;
 return startRepairWith(lastRepairMethod);
};

const selectBeforePendingRestore=selectRepair;
selectRepair=async function(id){
 if(repairBusy||repairDraft)return selectBeforePendingRestore(id);
 await selectBeforePendingRestore(id);
 const serial=repairResultSerial;
 let ownsBusy=false;
 const active=()=>current?.id===id&&workStage==='repair'&&serial===repairResultSerial;
 if(!active())return;
 try{
  const response=await fetch('/api/repair/pending/'+id);
  if(!response.ok)throw new Error('无法读取待采用的修复预览');
  const pending=await response.json();
  if(!pending||!active()||repairBusy||repairDraft)return;
  repairBusy=true;ownsBusy=true;
  setRepairResultState('loading','正在恢复待采用的修复预览，不会重新生成');
  const regions=pending.regions;
  const [before,image]=await Promise.all([decodedImage(`/api/repair/image/${id}?detail=1&v=${current.revision}`),decodedImage(`/api/repair/image/${id}?detail=1&v=${current.revision}&draft=${pending.draft}`)]);
  if(!active())return;
  repairResultRegions=regions;repairResultRegion=[Math.min(...regions.map(x=>x.region[0])),Math.min(...regions.map(x=>x.region[1])),Math.max(...regions.map(x=>x.region[2])),Math.max(...regions.map(x=>x.region[3]))];
  repairResultFull=false;repairDraft=pending.draft;repairResultBeforeImage=before;repairResultImage=image;
  lastRepairMethod=pending.method;$('repairMethod').value=pending.method;$('repairStrength').value=pending.strength;$('repairStrength').oninput();
  paintRepairResult();setRepairResultState('ready');
 }catch(e){if(active()){resetRepairResult();toast(e.message)}}
 finally{if(ownsBusy){repairBusy=false;$('repairPreview').disabled=!!repairDraft;aiRepairButton.disabled=!!repairDraft}}
};
