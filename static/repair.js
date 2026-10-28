// Repair uses confirmed, perspective-corrected crops and an independent queue.
let workStage='crop',repairSelection=null,repairDraft=null,repairSize=[1,1],repairSerial=0,repairBusy=false,repairPan=false;
const stages=document.createElement('div');stages.className='stage-switch';stages.innerHTML='<button id="cropStage" class="active" aria-pressed="true">1 裁剪校正</button><button id="repairStage" aria-pressed="false">2 折痕修复</button>';
document.querySelector('.brand').after(stages);
const repairPane=document.createElement('div');repairPane.id='repairPane';repairPane.className='pane';repairPane.hidden=true;
repairPane.innerHTML='<div id="repairViewport" class="viewport"><div id="repairWrap"><img id="repairImage" draggable="false"><div id="repairSelection"></div></div><div id="repairEmpty" hidden>暂无已确认裁剪的作品<br>请先在裁剪区确认图片</div></div>';
$('editor').append(repairPane);
let repairSelectionKind=null;
let repairMarks=[],repairActiveMark=null,repairMarkSignature=null,repairMarkSaveChain=Promise.resolve();
let repairReadOnly=false,repairDrawKind=null;
const repairLevelChoices=new Map();
let repairLevelEditorId=null;
const repairCanvasPane=document.createElement('section');repairCanvasPane.className='repair-canvas-pane';
$('repairViewport').before(repairCanvasPane);
const repairSourceBar=document.createElement('div');repairSourceBar.className='repair-source-bar';repairSourceBar.innerHTML='<div role="group" aria-label="图片版本" hidden><button id="repairWorkView" class="active" aria-pressed="true">当前工作图</button><button id="repairOriginalView" aria-pressed="false">原裁剪图</button></div><span id="repairWorkStatus">原裁剪图始终保留</span>';
repairSourceBar.hidden=true;
repairCanvasPane.append(repairSourceBar,$('repairViewport'));
async function switchRepairSource(original){
 if(repairBusy)return;
 repairReadOnly=original;repairKindPicker.hidden=true;closeRepairContextMenu();syncRepairWorkflow();
 try{await showRepairImage()}catch(error){toast(error.message)}
}
function syncRepairWorkflow(){
 const adopted=(current?.repair_state?.layers||[]).length;
 if($('openRepairHistory'))$('openRepairHistory').textContent='修复历史'+(adopted?' · '+adopted+' 步':'');
 $('repairWorkView').parentElement.hidden=adopted===0;
 if(!adopted)repairReadOnly=false;
 $('repairWorkView').classList.toggle('active',!repairReadOnly);$('repairOriginalView').classList.toggle('active',repairReadOnly);
 $('repairWorkView').setAttribute('aria-pressed',String(!repairReadOnly));$('repairOriginalView').setAttribute('aria-pressed',String(repairReadOnly));
 repairCanvasPane.classList.toggle('readonly',repairReadOnly);repairCanvasPane.classList.toggle('reviewing',!!repairDraft);
 repairSourceBar.hidden=adopted===0;
 $('repairWorkStatus').hidden=!repairReadOnly;
 $('repairWorkStatus').textContent=repairReadOnly?'只读对照 · 原裁剪图未修改':'';
 $('repairState').hidden=adopted===0;
 $('repairRegionText').hidden=!repairSelection;
}
$('repairWorkView').onclick=()=>switchRepairSource(false);$('repairOriginalView').onclick=()=>switchRepairSource(true);
const repairMarkLayer=document.createElement('div');repairMarkLayer.id='repairMarkLayer';$('repairWrap').append(repairMarkLayer);
for(const direction of ['nw','n','ne','e','se','s','sw','w']){const handle=document.createElement('i');handle.className='repair-handle '+direction;$('repairSelection').append(handle)}
function saveRepairMarks(){
 const id=current.id,regions=repairMarks.map(mark=>({...mark,region:[...mark.region]})),signature=repairMarkSignature;
 const task=repairMarkSaveChain.catch(()=>{}).then(async()=>{const item=await api('repair/marks',{id,signature,regions});replace(item);$('repairMarksStatus').hidden=true});
 repairMarkSaveChain=task;task.catch(e=>{$('repairMarksStatus').hidden=false;$('repairMarksStatus').textContent='标记未保存：'+e.message;toast(e.message)});
}
function paintRepairMarks(){
 repairMarkLayer.replaceChildren();$('repairMarksList').replaceChildren();
 repairMarks.forEach((mark,index)=>{
  const level=repairLevelChoices.get(mark.id)||mark.level||'standard',levelName={light:'轻度',standard:'标准',strong:'加强'}[level];
  const name=`${index+1} · ${mark.kind==='blemish'?'瑕疵去除':mark.kind==='crease'?'折痕':'凸起'}`,box=document.createElement('div');box.className='repair-mark '+mark.kind+(mark.brush?' brush':'')+(mark.id===repairActiveMark?' active':'');
  const [x1,y1,x2,y2]=mark.region;Object.assign(box.style,{left:x1*100+'%',top:y1*100+'%',width:(x2-x1)*100+'%',height:(y2-y1)*100+'%'});
  const badge=document.createElement('button');badge.textContent=name+' · '+levelName;badge.onpointerdown=e=>e.stopPropagation();badge.onclick=()=>selectRepairMark(mark.id);badge.oncontextmenu=e=>showRepairContextMenu(e,mark.id);box.append(badge);repairMarkLayer.append(box);
  const row=document.createElement('div');row.className='repair-mark-row '+mark.kind;const choose=document.createElement('button');choose.textContent=name;choose.onclick=()=>selectRepairMark(mark.id);choose.classList.toggle('active',mark.id===repairActiveMark);
  const grade=document.createElement('button');grade.className='repair-mark-grade';grade.textContent=levelName;grade.classList.toggle('pending',repairLevelChoices.has(mark.id));grade.setAttribute('aria-label','修改标记 '+(index+1)+' 强度：'+levelName);grade.setAttribute('aria-expanded',String(repairLevelEditorId===mark.id));grade.disabled=repairBusy||repairReadOnly;grade.title=repairLevelChoices.has(mark.id)?'等级已调整，待重新修复':'修改此处修复强度';
  grade.onclick=()=>{if(repairBusy||repairReadOnly)return;repairLevelEditorId=repairLevelEditorId===mark.id?null:mark.id;paintRepairMarks()};
  const remove=document.createElement('button');remove.textContent='×';remove.setAttribute('aria-label','删除标记 '+(index+1));remove.onclick=()=>deleteRepairMark(mark.id);choose.oncontextmenu=e=>showRepairContextMenu(e,mark.id);row.append(choose,grade,remove);
  if(repairLevelEditorId===mark.id&&!repairReadOnly&&!repairBusy){const editor=document.createElement('div');editor.className='repair-mark-grade-editor';editor.append(makeRepairLevelControl(mark));row.append(editor)}
  $('repairMarksList').append(row);
 });
 $('repairMarksCount').textContent=`已标记 ${repairMarks.length} 处`;
 $('repairMarksPanel').hidden=repairMarks.length===0;
 if(typeof syncRepairLevelControls==='function')syncRepairLevelControls();
}
function selectRepairMark(id){if(repairBusy)return;repairLevelEditorId=null;focusRepairRegion(id);const i=repairCompareGroups.findIndex(g=>g.markId===id);if(repairDraft&&i>=0){activateRepairCompare(i);repairCompareGroups[i].card.scrollIntoView({block:'nearest',behavior:'smooth'})}}
function loadRepairMarks(info){repairLevelEditorId=null;closeRepairContextMenu();repairMarks=(info.marks||[]).map(mark=>({...mark,region:[...mark.region]}));repairMarkSignature=info.signature;repairActiveMark=null;$('repairKind').value='';paintRepairMarks();$('repairMarksStatus').hidden=!!info.signature;if(!info.signature)$('repairMarksStatus').textContent='后台待更新：请重启工具后使用多区域标记'}
const repairKindPicker=document.createElement('div');repairKindPicker.id='repairKindPicker';repairKindPicker.hidden=true;repairKindPicker.setAttribute('role','group');repairKindPicker.setAttribute('aria-label','选择这次框选的修复类型');repairKindPicker.innerHTML='<span id="repairKindPrompt">这个选区需要修复什么？</span><div><button id="repairChooseCrease" aria-pressed="false">折痕</button><button id="repairChooseBump" aria-pressed="false">凸起</button><button id="repairCancelSelection" class="danger" aria-label="删除当前选框">删除选框</button></div>';repairPane.append(repairKindPicker);
const chooseBlemish=document.createElement('button');chooseBlemish.id='repairChooseBlemish';chooseBlemish.textContent='瑕疵去除';chooseBlemish.setAttribute('aria-pressed','false');chooseBlemish.title='强修复：用于允许替换纹理的颗粒、污点或空白纸面';$('repairCancelSelection').before(chooseBlemish);chooseBlemish.onclick=()=>chooseRepairKind('blemish');
function showRepairKindPicker(){
 if(!repairSelection||repairBusy||repairReadOnly)return;
 const rect=$('repairSelection').getBoundingClientRect(),pane=repairPane.getBoundingClientRect(),view=$('repairViewport').getBoundingClientRect();
 repairKindPicker.hidden=false;repairKindPicker.style.left=Math.max(8,Math.min(rect.right-pane.left,view.right-pane.left-224))+'px';repairKindPicker.style.top=Math.max(48,Math.min(rect.bottom-pane.top+8,view.bottom-pane.top-140))+'px';
 $('repairKindPrompt').textContent=repairSelectionKind?'本次选区：'+(repairSelectionKind==='blemish'?'瑕疵去除':repairSelectionKind==='crease'?'折痕':'凸起'):'请选择选框类型';
 for(const [id,kind] of [['repairChooseCrease','crease'],['repairChooseBump','bump'],['repairChooseBlemish','blemish']]){$(id).classList.toggle('active',kind===repairSelectionKind);$(id).setAttribute('aria-pressed',String(kind===repairSelectionKind))}
}
function chooseRepairKind(kind){
 const brushMark=repairMarks.find(x=>x.id===repairActiveMark&&x.brush);
 if(brushMark){if(repairBusy)return;if(repairDraft&&repairResultRegions.some(mark=>mark.id===brushMark.id))return toast('请先采用或放弃此处预览，再修改类型');brushMark.kind=kind;repairSelectionKind=kind;$('repairKind').value=kind;repairKindPicker.hidden=true;paintRepairMarks();saveRepairMarks();return}
 if(repairBusy||!repairSelection)return;
 if(repairDraft&&repairResultRegions.some(mark=>mark.id===repairActiveMark))return toast('请先采用或放弃此处预览，再修改类型');
 if(!repairMarkSignature)return toast('请先重启工具后台以启用标记保存');
 if((repairSelection[2]-repairSelection[0])*repairSize[0]<4||(repairSelection[3]-repairSelection[1])*repairSize[1]<4)return toast('选区太小，请稍微扩大后标记');
 repairSelectionKind=kind;$('repairKind').value=kind;
 let mark=repairMarks.find(x=>x.id===repairActiveMark);const created=!mark;
 if(mark){mark.region=[...repairSelection];mark.kind=kind}else{mark={id:Date.now().toString(36)+'-'+Math.random().toString(36).slice(2,10),region:[...repairSelection],kind,level:'standard'};repairMarks.push(mark);repairActiveMark=mark.id}
 repairKindPicker.hidden=true;paintRepairSelection();paintRepairMarks();saveRepairMarks();
 if(created)showRepairLevelPrompt(mark.id);
}
$('repairChooseCrease').onclick=()=>chooseRepairKind('crease');$('repairChooseBump').onclick=()=>chooseRepairKind('bump');
$('repairCancelSelection').onclick=()=>deleteRepairMark(repairActiveMark);
const repairContextMenu=document.createElement('div');repairContextMenu.id='repairContextMenu';repairContextMenu.hidden=true;repairContextMenu.setAttribute('role','menu');repairContextMenu.setAttribute('aria-label','选框操作');
repairContextMenu.innerHTML='<span class="repair-context-title">选框操作</span><button type="button" data-kind="crease" role="menuitemradio">切换为折痕</button><button type="button" data-kind="bump" role="menuitemradio">切换为凸起</button><button type="button" data-kind="blemish" role="menuitemradio">切换为瑕疵去除</button><button type="button" id="repairDeleteMark" class="danger" role="menuitem">删除选框</button>';
document.body.append(repairContextMenu);
const repairContextLevels=document.createElement('div');repairContextLevels.id='repairContextLevels';$('repairDeleteMark').before(repairContextLevels);
let repairContextTarget=null;
function closeRepairContextMenu(){repairContextMenu.hidden=true;repairContextTarget=null}
function deleteRepairMark(id){
 if(repairBusy||(repairDraft&&id!==null))return;
 const exists=repairMarks.some(mark=>mark.id===id);
 if(exists)repairMarks=repairMarks.filter(mark=>mark.id!==id);
 if(id===null||repairActiveMark===id){repairActiveMark=null;repairSelection=null;repairSelectionKind=null;repairKindPicker.hidden=true;$('repairKind').value='';$('repairRegionText').textContent='尚未框选';paintRepairSelection()}
 paintRepairMarks();if(exists)saveRepairMarks();
}
function deleteAllRepairMarks(){
 if(repairBusy)return toast('请等待本次修复完成');
 if(repairReadOnly)return toast('请切换到当前工作图后删除标记');
 if(repairDraft)return toast('请先采用或放弃当前修复预览，再删除全部标记');
 const count=repairMarks.length;
 repairMarks=[];repairActiveMark=null;repairSelection=null;repairSelectionKind=null;
 repairKindPicker.hidden=true;closeRepairContextMenu();$('repairKind').value='';
 $('repairRegionText').textContent='尚未框选';paintRepairSelection();paintRepairMarks();
 if(count)saveRepairMarks();
 toast('已删除当前图片的全部修复标记');
}
function makeRepairLevelControl(mark){
 const group=document.createElement('div');group.className='repair-level-control';group.dataset.markId=mark.id;group.setAttribute('role','group');group.setAttribute('aria-label','此处修复强度');
 const chosen=repairLevelChoices.get(mark.id)||mark.level||'standard';
 for(const [level,label] of [['light','轻度'],['standard','标准'],['strong','加强']]){
  const button=document.createElement('button');button.type='button';button.textContent=label;button.dataset.level=level;
  button.classList.toggle('active',chosen===level);button.setAttribute('aria-pressed',String(chosen===level));
  button.onclick=event=>{event.stopPropagation();setRepairMarkLevel(mark.id,level)};group.append(button);
 }
 return group;
}
function syncRepairLevelControls(){
 const panel=$('repairMarkLevel');if(!panel)return;
 if(panel.hidden)return;
 const mark=repairMarks.find(m=>m.id===panel.dataset.markId);
 if(!mark||repairActiveMark!==mark.id||repairBusy||repairReadOnly){panel.hidden=true;return}
 positionRepairLevelPrompt(mark);
}
function repairLevelPlacement(rect,view,size){
 const gap=10,clamp=(v,a,b)=>Math.max(a,Math.min(v,b));
 const minX=view.left+8,maxX=view.right-size.width-8,minY=view.top+8,maxY=view.bottom-size.height-8;
 if(maxX<minX||maxY<minY)return null;
 const y=clamp((rect.top+rect.bottom-size.height)/2,minY,maxY),x=clamp(rect.left,minX,maxX);
 for(const [left,top] of [[rect.right+gap,y],[rect.left-size.width-gap,y],[x,rect.bottom+gap],[x,rect.top-size.height-28]]){
  if(left>=minX&&left<=maxX&&top>=minY&&top<=maxY&&!(left<rect.right&&left+size.width>rect.left&&top<rect.bottom&&top+size.height>rect.top))return {left,top};
 }
 return null;
}
function positionRepairLevelPrompt(mark){
 const panel=$('repairMarkLevel'),wrap=$('repairWrap').getBoundingClientRect(),view=$('repairViewport').getBoundingClientRect(),pane=repairPane.getBoundingClientRect();
 const [x1,y1,x2,y2]=mark.region,rect={left:wrap.left+x1*wrap.width,right:wrap.left+x2*wrap.width,top:wrap.top+y1*wrap.height,bottom:wrap.top+y2*wrap.height};
 const position=repairLevelPlacement(rect,{left:view.left,right:view.right,top:view.top+56,bottom:view.bottom},panel.getBoundingClientRect());
 if(position){panel.style.left=position.left-pane.left+'px';panel.style.top=position.top-pane.top+'px';return}
 panel.hidden=true;repairLevelEditorId=mark.id;paintRepairMarks();
 if(typeof setSettingsCollapsed==='function')setSettingsCollapsed(false);
 const row=[...$('repairMarksList').children].find(el=>el.querySelector('.repair-level-control')?.dataset.markId===mark.id);
 row?.scrollIntoView({block:'nearest'});
}
function showRepairLevelPrompt(id){
 if(repairBusy||repairReadOnly)return;
 const mark=repairMarks.find(m=>m.id===id);if(!mark)return;
 const panel=$('repairMarkLevel');panel.replaceChildren();panel.dataset.markId=id;
 const label=document.createElement('span');label.textContent='修复强度 · 默认标准';panel.append(label,makeRepairLevelControl(mark));panel.hidden=false;
 positionRepairLevelPrompt(mark);
}
function setRepairMarkLevel(id,level){
 if(repairBusy||repairReadOnly)return;
 const mark=repairMarks.find(m=>m.id===id);if(!mark)return;
 const candidate=repairResultRegions.find(m=>m.id===id);
 if(repairDraft&&candidate){
  if((candidate.level||'standard')===level)repairLevelChoices.delete(id);else repairLevelChoices.set(id,level);
 }else{mark.level=level;saveRepairMarks()}
 const prompt=$('repairMarkLevel');if(prompt)prompt.hidden=true;
 if(typeof closeRepairContextMenu==='function')closeRepairContextMenu();
 repairLevelEditorId=null;
 document.querySelectorAll('.repair-level-control').forEach(group=>{
  if(group.dataset.markId!==id)return;
  const chosen=repairLevelChoices.get(id)||mark.level||'standard';
  group.querySelectorAll('button').forEach(button=>{button.classList.toggle('active',button.dataset.level===chosen);button.setAttribute('aria-pressed',String(button.dataset.level===chosen))});
 });
 syncRepairLevelControls();
 if(typeof paintRepairMarks==='function')paintRepairMarks();
 const card=repairCompareGroups.find(g=>g.markId===id)?.card;
 if(card){card.classList.toggle('level-pending',repairLevelChoices.has(id));const note=card.querySelector('.repair-level-note');if(note)note.textContent=repairLevelChoices.has(id)?'待重新修复':'强度'}
}
function showRepairContextMenu(event,id){
 event.preventDefault();event.stopPropagation();closeRepairContextMenu();
 if(repairReadOnly)return toast('原裁剪图仅供对照，请切换到当前工作图编辑');
 if(repairBusy||repairDraft)return toast('请先完成或放弃当前修复预览');
 const mark=repairMarks.find(mark=>mark.id===id);
 if(id!==null&&!mark)return;
 if(mark)selectRepairMark(id);
 repairContextLevels.replaceChildren();repairContextLevels.hidden=!mark;
 if(mark){const label=document.createElement('span');label.textContent='修复强度';repairContextLevels.append(label,makeRepairLevelControl(mark))}
 repairKindPicker.hidden=true;repairContextTarget={item:current.id,id};
 for(const button of repairContextMenu.querySelectorAll('[data-kind]'))button.setAttribute('aria-checked',String(button.dataset.kind===repairSelectionKind));
 repairContextMenu.hidden=false;
 const bounds=repairContextMenu.getBoundingClientRect();
 repairContextMenu.style.left=Math.max(6,Math.min(event.clientX,window.innerWidth-bounds.width-6))+'px';
 repairContextMenu.style.top=Math.max(6,Math.min(event.clientY,window.innerHeight-bounds.height-6))+'px';
 if(mark){
  const wrap=$('repairWrap').getBoundingClientRect(),view=$('repairViewport').getBoundingClientRect(),[x1,y1,x2,y2]=mark.region;
  const position=repairLevelPlacement({left:wrap.left+x1*wrap.width,right:wrap.left+x2*wrap.width,top:wrap.top+y1*wrap.height,bottom:wrap.top+y2*wrap.height},view,bounds);
  if(position){repairContextMenu.style.left=position.left+'px';repairContextMenu.style.top=position.top+'px'}
 }
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
repairResult.querySelector('.repair-result-head strong').id='repairCompareTitle';
repairResult.querySelector('.repair-result-head').insertBefore($('repairCompareTools'),$('repairResultView'));
$('repairCompareTools').title='滚轮缩放 · 拖动联动；点击对比卡片可选择要缩放的区域';
let repairResultImage=null,repairResultBeforeImage=null,repairResultRegion=null,repairResultFull=false,repairResultSerial=0,repairCompareScale='fit';
let repairResultRegions=[],repairCompareGroups=[],repairCompareActive=0;
let repairResultMethods={};
const repairSettings=document.createElement('div');repairSettings.id='repairSettings';repairSettings.hidden=true;
repairSettings.innerHTML='<div class="panel-caption">局部修复</div><p class="repair-help">涂抹折痕或凸起，修复只作用于涂抹处；框选适合大面积凸起。</p><div class="repair-tools"><button id="repairBox" class="active" aria-pressed="true">框选</button><button id="repairPan" aria-pressed="false">移动画面</button></div><label>缩放<select id="repairZoom"><option value="fit">适合窗口</option><option value=".5">原图 50%</option><option value="1">原图 100%</option><option value="2">原图 200%</option><option value="4">原图 400%</option></select></label><label>修复内容<select id="repairKind"><option value="crease">折痕明暗</option><option value="bump">凸起阴影</option><option value="blemish">瑕疵去除</option></select></label><label>处理方式<select id="repairMethod"><option value="local">常规修复 · 本机处理</option><option value="ai">AI 精修 · 通过配置的服务</option></select></label><label>常规修复强度 <output id="repairStrengthValue">65%</output><input id="repairStrength" type="range" min="0" max="1" step=".05" value=".65"></label><p id="repairRegionText" class="repair-help">尚未框选</p><button id="repairPreview" class="primary wide">生成局部修复预览</button><div id="repairDraftActions" hidden><p class="repair-help">正在预览候选，采用前不会替换结果。</p><button id="repairAccept" class="primary wide">采用这次修复</button><button id="repairDiscard" class="wide">放弃这次预览</button></div><button id="repairBefore" class="wide">按住查看修复前</button><div class="repair-tools"><button id="repairUndo">撤销修复</button><button id="repairRedo">重做</button></div><p id="repairState" class="repair-help"></p><details class="advanced-controls"><summary>AI 连接</summary><p class="repair-help">支持 CLIProxyAPI。AI 仅在点击预览时发送选区及周边；可能产生调用费用。聊天模型需服务支持图像编辑才可用。</p><label>API Base URL<input id="repairBaseURL" type="url" value="http://127.0.0.1:8317/v1" autocomplete="off"></label><label>API Key<input id="repairKey" type="password" autocomplete="off" placeholder="只保存在本次服务内存中"></label><label>图像编辑模型<input id="repairModel" value="gpt-6.1-sol" autocomplete="off"></label><button id="repairConnect" class="wide">保存连接</button><button id="repairTest" class="wide">检测连接与模型</button><p id="repairConfigState" class="repair-help"></p></details><div class="final-actions"><button id="repairComplete" class="primary wide">确认成品 / 无需修复</button></div>';
settingsPanel.append(repairSettings);
$('repairKey').placeholder='保存在本机，使用当前 Windows 账户加密';
const blemishTool=document.createElement('button');blemishTool.id='repairBlemishTool';blemishTool.textContent='圈瑕疵';blemishTool.setAttribute('aria-pressed','false');blemishTool.title='拖动圈选允许强修复的颗粒、污点或空白纸面';$('repairPan').after(blemishTool);
blemishTool.onclick=()=>{if(repairReadOnly)return toast('请先切换到当前工作图');repairDrawKind='blemish';repairPan=false;repairSelection=null;repairActiveMark=null;repairKindPicker.hidden=true;paintRepairSelection();for(const id of ['repairBox','repairPan','repairBlemishTool']){$(id).classList.toggle('active',id==='repairBlemishTool');$(id).setAttribute('aria-pressed',String(id==='repairBlemishTool'))}toast('拖动圈出瑕疵；仅用于允许重修的空白纸面，避免圈入字迹和印章')};
const repairLegend=document.createElement('div');repairLegend.className='repair-legend';repairLegend.setAttribute('aria-label','选框颜色说明');repairLegend.innerHTML='<strong>选框说明</strong><div><span><i class="crease" aria-hidden="true"></i>橙色 · 折痕</span><span><i class="bump" aria-hidden="true"></i>蓝色 · 凸起</span></div><p><i class="pending" aria-hidden="true"></i>灰色虚线 · 尚未选择类型</p>';repairSettings.prepend(repairLegend);
const blemishLegend=document.createElement('span');blemishLegend.innerHTML='<i class="blemish" aria-hidden="true"></i>紫色 · 瑕疵去除（强修复）';repairLegend.querySelector('div').append(blemishLegend);
const repairMarksPanel=document.createElement('div');repairMarksPanel.id='repairMarksPanel';repairMarksPanel.innerHTML='<strong id="repairMarksCount">已标记 0 处</strong><div id="repairMarksList"></div><p id="repairMarksStatus" class="repair-help">标记后可继续框选，全部标好再点击修复</p>';$('repairRegionText').before(repairMarksPanel);
const repairMarkLevel=document.createElement('div');repairMarkLevel.id='repairMarkLevel';repairMarkLevel.hidden=true;repairMarkLevel.setAttribute('role','group');repairMarkLevel.setAttribute('aria-label','首次标记修复强度');repairMarkLevel.onpointerdown=event=>event.stopPropagation();repairPane.append(repairMarkLevel);
document.addEventListener('pointerdown',event=>{if(!repairMarkLevel.contains(event.target))repairMarkLevel.hidden=true},true);
document.addEventListener('scroll',()=>{if(!repairMarkLevel.hidden)syncRepairLevelControls()},true);window.addEventListener('resize',()=>{if(!repairMarkLevel.hidden)syncRepairLevelControls()});
const repairMarksHead=document.createElement('div');repairMarksHead.className='repair-marks-head';
const repairDeleteAll=document.createElement('button');repairDeleteAll.id='repairDeleteAll';repairDeleteAll.type='button';repairDeleteAll.className='danger';repairDeleteAll.textContent='删除全部';repairDeleteAll.title='删除当前图片的所有选框和涂抹标记';repairDeleteAll.onclick=deleteAllRepairMarks;
repairMarksHead.append($('repairMarksCount'),repairDeleteAll);repairMarksPanel.prepend(repairMarksHead);
$('repairResultActions').append($('repairDraftActions'));
const repairRegenerate=document.createElement('button');repairRegenerate.id='repairRegenerate';repairRegenerate.textContent='重新修复';
$('repairAccept').textContent='采用剩余全部';$('repairDiscard').textContent='放弃剩余预览';
$('repairAccept').after(repairRegenerate);
repairRegenerate.title='按当前标记和上次的修复方式重新生成预览；AI 修复会再次调用已配置的服务';
$('repairPreview').textContent='常规修复';
function resetRepairResult(){repairLevelChoices.clear();++repairResultSerial;repairResult.hidden=true;repairPane.classList.remove('has-result');repairResultImage=null;repairResultRegion=null;repairResultFull=false;$('repairDraftActions').hidden=true;$('repairPreview').disabled=false;if($('repairAI'))$('repairAI').disabled=false}
function setRepairResultState(state,message){
 repairResult.hidden=false;repairPane.classList.add('has-result');repairResult.dataset.state=state;
 $('repairResultBody').setAttribute('aria-busy',String(state==='loading'));
 $('repairResultStatus').textContent=state==='loading'?'处理中…':state==='ready'?`待确认 ${repairResultRegions.length||1} 处 · 候选尚未应用到工作图`:'修复未完成';
 $('repairResultMessage').hidden=state==='ready';$('repairCompare').hidden=state!=='ready';$('repairCompareTools').hidden=state!=='ready'||!repairResultFull;$('repairResultView').hidden=state!=='ready';$('repairResultRetry').hidden=state!=='error';
 $('repairResultMessageTitle').textContent=state==='error'?'修复失败':'正在修复选区';
 $('repairResultMessageText').textContent=message||(state==='loading'?'请稍候，完成后将在这里展示修复效果':'');
 $('repairDraftActions').hidden=state!=='ready';
 if(state==='ready')fitRepairCompare();syncRepairWorkflow();
}
function paintRepairResult(){
 if(!repairResultImage||!repairResultBeforeImage)return;
 const im=repairResultImage,regions=repairResultFull?[null]:repairResultRegions.length?repairResultRegions:[{region:repairResultRegion}];
 repairCompareGroups=[];repairCompareActive=0;const container=$('repairCompare');container.replaceChildren();container.scrollTop=0;
 regions.forEach((mark,index)=>{
  let box=[0,0,im.naturalWidth,im.naturalHeight];
  if(mark?.region){const [x1,y1,x2,y2]=mark.region,pad=Math.max(16,Math.min(100,Math.max((x2-x1)*im.naturalWidth,(y2-y1)*im.naturalHeight)*.12));box=[Math.max(0,Math.floor(x1*im.naturalWidth-pad)),Math.max(0,Math.floor(y1*im.naturalHeight-pad)),Math.min(im.naturalWidth,Math.ceil(x2*im.naturalWidth+pad)),Math.min(im.naturalHeight,Math.ceil(y2*im.naturalHeight+pad))]}
  const card=document.createElement('section');card.className='repair-compare-group'+(mark?.kind?' '+mark.kind:'');
  card.classList.toggle('full-work',repairResultFull);
  const title=document.createElement('strong');title.className='repair-compare-title';title.textContent=repairResultFull?'完整作品':`${index+1} · ${mark?.kind==='blemish'?'瑕疵去除':mark?.kind==='bump'?'凸起':'折痕'}`;
  if(mark?.id&&typeof repairResultMethods!=='undefined'&&repairResultMethods[mark.id]){const badge=document.createElement('span');badge.className='repair-method-badge';badge.textContent=repairResultMethods[mark.id]==='ai'?'AI':'常规';badge.title='此候选实际使用的修复方式';title.append(badge)}
  if(mark?.id){const actions=document.createElement('div');actions.className='repair-region-actions';for(const [label,action] of [['采用此处','accept-region'],['重新修复','retry-region'],['AI 修复','ai-region'],['放弃此处','discard-region']]){const button=document.createElement('button');button.className='repair-accept-region';button.textContent=label;button.onclick=event=>{event.stopPropagation();acceptRepairRegion(mark.id,action)};if(action==='retry-region')button.title='仅重新生成这一处；AI 修复会再次调用服务';if(action==='ai-region')button.title='仅将此处交给 AI，成功后替换此处候选，失败保留原候选；可能产生调用费用';actions.append(button)}title.append(actions)}
  if(mark?.id){
   const controls=document.createElement('div');controls.className='repair-level-row';
   const note=document.createElement('span');note.className='repair-level-note';note.textContent=repairLevelChoices.has(mark.id)?'待重新修复':'强度';
   controls.append(note,makeRepairLevelControl(mark));title.append(controls);card.classList.toggle('level-pending',repairLevelChoices.has(mark.id));
  }
  const pair=document.createElement('div');pair.className='repair-compare-pair';
  const group={card,markId:mark?.id,views:[],canvases:[],scale:'fit'};
  for(const [label,image] of [['修复前',repairResultBeforeImage],['修复后',im]]){
   const cell=document.createElement('div');cell.className='repair-compare-cell';const head=document.createElement('strong');head.textContent=label;
   const view=document.createElement('div');view.className='repair-compare-viewport';const canvas=document.createElement('canvas');canvas.setAttribute('aria-label',(repairResultFull?'完整作品':`${index+1} · ${mark?.kind==='blemish'?'瑕疵去除':mark?.kind==='bump'?'凸起':'折痕'}`)+' '+label);
   canvas.width=box[2]-box[0];canvas.height=box[3]-box[1];canvas.getContext('2d').drawImage(image,box[0],box[1],canvas.width,canvas.height,0,0,canvas.width,canvas.height);
   view.append(canvas);cell.append(head,view);pair.append(cell);group.views.push(view);group.canvases.push(canvas);
  }
  if(!repairResultFull)card.append(title);card.append(pair);container.append(card);repairCompareGroups.push(group);
  card.addEventListener('pointerdown',()=>{activateRepairCompare(index);focusRepairRegion(mark?.id)});
  for(const view of group.views){
   view.addEventListener('wheel',e=>{if(!repairResultFull||!e.deltaY)return;e.preventDefault();activateRepairCompare(index);zoomRepairCompare(repairCompareCurrentScale()*Math.exp(-Math.max(-100,Math.min(100,e.deltaY))*.0025),view,[e.clientX,e.clientY])},{passive:false});
   view.addEventListener('scroll',()=>syncRepairCompare(group,view));
   view.onpointerdown=e=>{if(!repairResultFull||![0,1].includes(e.button))return;e.preventDefault();view.setPointerCapture(e.pointerId);const start=[e.clientX,e.clientY,view.scrollLeft,view.scrollTop];const move=ev=>{view.scrollLeft=start[2]+start[0]-ev.clientX;view.scrollTop=start[3]+start[1]-ev.clientY;syncRepairCompare(group,view)};const stop=()=>{view.removeEventListener('pointermove',move);view.removeEventListener('pointerup',stop);view.removeEventListener('pointercancel',stop)};view.addEventListener('pointermove',move);view.addEventListener('pointerup',stop);view.addEventListener('pointercancel',stop)};
  }
 });
 container.classList.toggle('multiple',regions.length>1);container.classList.toggle('details',!repairResultFull);$('repairCompareTools').hidden=!repairResultFull;activateRepairCompare(0);fitRepairCompare();
 container.classList.toggle('full-work',repairResultFull);$('repairCompareTitle').textContent=repairResultFull?'完整作品对比':'修复前后对比';
 $('repairResultView').textContent=repairResultFull?'查看各处细节':'查看完整作品';
 $('repairResultStatus').textContent=`待确认 ${repairResultRegions.length||1} 处 · 候选尚未应用到工作图`;
}
function activateRepairCompare(index){repairCompareActive=index;repairCompareGroups.forEach((group,i)=>group.card.classList.toggle('active',i===index));$('repairComparePercent').textContent=Math.round(repairCompareCurrentScale()*100)+'%'}
function focusRepairRegion(id){
 const mark=repairMarks.find(m=>m.id===id);if(!mark)return;
 repairActiveMark=id;repairSelection=mark.brush?null:[...mark.region];repairSelectionKind=mark.kind;$('repairKind').value=mark.kind;paintRepairSelection();paintRepairMarks();
 const wrap=$('repairWrap').getBoundingClientRect(),view=$('repairViewport'),bounds=view.getBoundingClientRect(),[x1,y1,x2,y2]=mark.region;
 if(view.scrollWidth>view.clientWidth+1)view.scrollLeft+=wrap.left+(x1+x2)/2*wrap.width-(bounds.left+bounds.right)/2;
 if(view.scrollHeight>view.clientHeight+1)view.scrollTop+=wrap.top+(y1+y2)/2*wrap.height-(bounds.top+bounds.bottom)/2;
}
async function acceptRepairRegion(markId,action='accept-region'){
 if(repairBusy||!repairDraft||!current?.confirmed)return;
 if(action==='accept-region'&&repairLevelChoices.has(markId))return toast('此处等级已调整，请先点击“重新修复”后再采用');
 repairBusy=true;const id=current.id;
 repairResult.querySelectorAll('button').forEach(button=>button.disabled=true);
 const finishLoading=showRepairRegionLoading(markId,action);
 try{
  await repairMarkSaveChain;
  const result=await api('repair/'+(action==='ai-region'?'retry-region':action),{id,draft:repairDraft,mark_id:markId,...(action==='ai-region'?{method:'ai'}:{}),...(['retry-region','ai-region'].includes(action)&&repairLevelChoices.has(markId)?{level:repairLevelChoices.get(markId)}:{})});
  repairLevelChoices.delete(markId);
  replace(result.item);repairDraft=result.draft;repairResultRegions=result.regions;repairSelection=null;repairSelectionKind=null;
  repairResultMethods=result.methods||repairResultMethods;
  loadRepairMarks({marks:result.item.repair_marks?.regions||[],signature:repairMarkSignature});paintRepairSelection();
  $('repairUndo').disabled=!result.item.repair_state?.layers?.length;$('repairState').textContent=`已采用 ${result.item.repair_state?.layers?.length||0} 次修复`;
  repairReadOnly=false;syncRepairWorkflow();await showRepairImage();
  if(repairDraft){
   repairResultBeforeImage=await decodedImage(`/api/repair/image/${id}?detail=1&v=${current.revision}`);
   repairResultImage=await decodedImage(`/api/repair/image/${id}?detail=1&v=${current.revision}&draft=${repairDraft}&review=${++repairResultSerial}`);
   repairBusy=false;paintRepairResult();setRepairResultState('ready');
  }else resetRepairResult();
  toast(action==='accept-region'?'已采用此处修复，并移除对应标记':action==='retry-region'||action==='ai-region'?'此处已重新生成，其余预览保留':'已放弃此处预览，标记保留，可继续调整');
 }catch(error){toast(error.message)}
 finally{finishLoading();repairBusy=false;syncRepairWorkflow();repairResult.querySelectorAll('button').forEach(button=>button.disabled=false);$('repairPreview').disabled=!!repairDraft;if($('repairAI'))$('repairAI').disabled=false}
}
function showRepairRegionLoading(markId,action){
 const card=repairCompareGroups.find(group=>group.markId===markId)?.card||$('repairResultBody');
 const retry=['retry-region','ai-region'].includes(action),ai=action==='ai-region'||repairResultMethods[markId]==='ai';
 const label=retry?(ai?'AI 正在重新修复此处':'正在重新修复此处'):action==='accept-region'?'正在采用此处修复':'正在放弃此处预览';
 const oldStatus=$('repairResultStatus').textContent;
 $('repairResultStatus').textContent=label+'…';card.setAttribute('aria-busy','true');card.classList.add('repair-region-loading');
 const overlay=document.createElement('div');overlay.className='repair-region-loading-overlay';overlay.setAttribute('role','status');overlay.setAttribute('aria-live','polite');
 const panel=document.createElement('div');panel.className='repair-region-loading-panel';
 const spinner=document.createElement('span');spinner.className='repair-spinner';spinner.setAttribute('aria-hidden','true');
 const title=document.createElement('strong');title.textContent=label+'…';
 const note=document.createElement('span');note.textContent=retry?'保留旧效果作参照，完成后自动更新。'+(ai?'AI 处理可能需要一些时间。':''):'请稍候，正在更新工作图。';
 panel.append(spinner,title,note);overlay.append(panel);card.append(overlay);
 const originalButtons=[];
 for(const button of card.querySelectorAll('.repair-region-actions button')){
  if(button.textContent===(action==='ai-region'?'AI 修复':action==='retry-region'?'重新修复':action==='accept-region'?'采用此处':'放弃此处')){originalButtons.push([button,button.textContent]);button.textContent=retry?'修复中…':'处理中…';button.classList.add('is-loading')}
 }
 return ()=>{
  overlay.remove();card.classList.remove('repair-region-loading');card.setAttribute('aria-busy','false');
  for(const [button,text] of originalButtons){button.textContent=text;button.classList.remove('is-loading')}
  if($('repairResultStatus').textContent===label+'…')$('repairResultStatus').textContent=oldStatus;
 };
}
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
function fitRepair(){if(!$('repairImage').naturalWidth)return;const view=$('repairViewport'),padding=getComputedStyle(view),width=view.clientWidth-parseFloat(padding.paddingLeft)-parseFloat(padding.paddingRight)-2,height=view.clientHeight-parseFloat(padding.paddingTop)-parseFloat(padding.paddingBottom)-2,scale=$('repairZoom').value==='fit'?Math.max(.01,Math.min(width/repairSize[0],height/repairSize[1])):Number($('repairZoom').value);$('repairWrap').style.width=repairSize[0]*scale+'px';$('repairWrap').style.height=repairSize[1]*scale+'px';$('repairZoomPercent').textContent=Math.round(scale*100)+'%';paintRepairSelection()}
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
function paintRepairSelection(){const el=$('repairSelection');el.className=repairSelectionKind||'pending';el.hidden=!repairSelection;$('repairRegionText').hidden=!repairSelection;if(!repairSelection)return;const [x1,y1,x2,y2]=repairSelection;Object.assign(el.style,{left:x1*100+'%',top:y1*100+'%',width:(x2-x1)*100+'%',height:(y2-y1)*100+'%'});$('repairRegionText').textContent=`选区 ${Math.round((x2-x1)*repairSize[0])} × ${Math.round((y2-y1)*repairSize[1])} px`}
async function showRepairImage({before=repairReadOnly}={}){if(!current||workStage!=='repair')return;const serial=++repairSerial,id=current.id,revision=current.revision;const image=await decodedImage(`/api/repair/image/${id}?detail=1&v=${revision}${before?'&before=1':''}`);if(serial!==repairSerial||workStage!=='repair'||current?.id!==id)return;image.id='repairImage';image.draggable=false;$('repairImage').replaceWith(image);repairSize=[image.naturalWidth,image.naturalHeight];fitRepair();$('repairWrap').style.visibility='visible';$('repairViewport').classList.remove('loading-image');syncRepairWorkflow()}
async function selectRepair(id){if(repairBusy)return;const item=repairQueue().find(x=>x.id===id);if(!item)return;await saveChain.catch(()=>{});current=item;repairSelection=null;repairDraft=null;++repairSerial;$('repairDraftActions').hidden=true;$('repairEmpty').hidden=true;$('repairWrap').style.visibility='hidden';$('repairViewport').classList.add('loading-image');$('repairZoom').value='fit';$('repairRegionText').textContent='尚未框选';$('title').textContent=item.name;$('title').title=item.name;drawList(true);try{const info=await(await fetch('/api/repair/info/'+id)).json();if(info.error)throw Error(info.error);if(workStage!=='repair'||current?.id!==id)return;repairSize=info.size;loadRepairMarks(info);$('resolution').textContent=`裁剪后 ${info.size[0]} × ${info.size[1]} px`;$('status').textContent=info.state.completed?'成品已确认':'待修复';$('repairState').textContent=`已采用 ${info.state.layers?.length||0} 次修复`;$('repairUndo').disabled=!info.state.layers?.length;$('repairRedo').disabled=!info.state.redo?.length;await showRepairImage()}catch(e){$('repairViewport').classList.remove('loading-image');toast(e.message)}}
async function switchStage(stage){if(repairBusy)return toast('请等待本次修复完成');await saveChain.catch(()=>{});workStage=stage;++originalSerial;++previewSerial;++repairSerial;document.body.classList.toggle('repair-mode',stage==='repair');$('cropStage').classList.toggle('active',stage==='crop');$('repairStage').classList.toggle('active',stage==='repair');$('cropStage').setAttribute('aria-pressed',String(stage==='crop'));$('repairStage').setAttribute('aria-pressed',String(stage==='repair'));$('originalPane').hidden=stage==='repair';$('resultPane').hidden=true;repairPane.hidden=stage!=='repair';repairSettings.hidden=stage!=='repair';$('editor').hidden=false;$('empty').hidden=true;$('filter').value='all';$('search').value='';compare=false;if(stage==='crop'){drawList();if(current)await cropSelect(current.id);setViewMode(false)}else{drawList();const queue=repairQueue();if(queue.length)await selectRepair(queue.some(x=>x.id===current?.id)?current.id:queue[0].id);else{$('repairWrap').style.visibility='hidden';$('repairEmpty').hidden=false;$('title').textContent='折痕修复';$('resolution').textContent='';$('status').textContent='等待确认裁剪';updateRepairNavigation()}}}
const selectRepairCore=selectRepair;
selectRepair=async function(id){if(repairBusy)return;if(repairDraft)return toast('请先采用或放弃当前修复预览');await repairMarkSaveChain.catch(()=>{});repairReadOnly=false;repairKindPicker.hidden=true;repairSelectionKind=null;repairMarks=[];repairActiveMark=null;resetRepairResult();return selectRepairCore(id)};
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
for(const id of ['repairBox','repairPan']){const action=$(id).onclick;$(id).onclick=()=>{repairDrawKind=null;blemishTool.classList.remove('active');blemishTool.setAttribute('aria-pressed','false');action()}}
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
  if(mark.brush)continue; // painted strokes are edited with the brush/eraser, not handles
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
 view.style.cursor=repairPan||repairSpace?'grab':repairBusy||repairReadOnly?'default':repairEditCursor(repairDrawKind?null:target?.mode);
});
$('repairViewport').onpointerdown=e=>{
 if(![0,1].includes(e.button)||repairBusy||!current?.confirmed||!$('repairEmpty').hidden)return;
 const panGesture=repairPan||repairSpace||e.button===1;
 if(repairReadOnly&&!panGesture)return toast('原裁剪图仅供对照，请切换到当前工作图进行标记');
 const view=$('repairViewport'),rect=$('repairWrap').getBoundingClientRect();
 if(!rect.width||!rect.height)return;
 const target=panGesture||repairDrawKind?null:repairEditTarget(e,rect);
 if(repairDraft&&!panGesture&&target){selectRepairMark(target.id);return}
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
  if(moved&&!target&&repairDrawKind==='blemish'){chooseRepairKind('blemish');return}
  if(repairSelection&&!repairSelectionKind&&(moved||target))showRepairKindPicker();
 };
 view.addEventListener('pointermove',move);view.addEventListener('pointerup',up);view.addEventListener('pointercancel',up);view.addEventListener('lostpointercapture',up);
};
$('repairStrength').oninput=()=>{$('repairStrengthValue').textContent=Math.round(Number($('repairStrength').value)*100)+'%'};
// Brush marking: paint folds and bumps precisely. Each stroke is one mark whose
// brush = {size: diameter / image width, paths: [[[x,y],...]]} in normalized
// image coordinates; the backend repairs only inside the painted stroke.
let repairBrushMode='brush',repairBrushKind='crease',repairBrushSize=24,repairEraserSize=40,repairSnap=true,repairBrushLive=null;
const SVG_NS='http://www.w3.org/2000/svg';
const repairBrushLayer=document.createElementNS(SVG_NS,'svg');repairBrushLayer.id='repairBrushLayer';repairBrushLayer.setAttribute('preserveAspectRatio','none');repairBrushLayer.setAttribute('aria-hidden','true');
$('repairWrap').insertBefore(repairBrushLayer,repairMarkLayer);
const repairBrushCursor=document.createElement('div');repairBrushCursor.id='repairBrushCursor';repairBrushCursor.hidden=true;repairPane.append(repairBrushCursor);
const repairIcon=path=>`<svg viewBox="0 0 24 24" aria-hidden="true">${path}</svg>`;
const repairIcons={
 brush:repairIcon('<path d="M14.5 4.5l5 5-8.2 8.2a3 3 0 01-2.1.9H5.5v-3.7a3 3 0 01.9-2.1z"/><path d="M12.5 6.5l5 5"/>'),
 eraser:repairIcon('<path d="M8.5 19.5h11"/><path d="M4.6 14.6l8.8-8.8a2 2 0 012.8 0l3 3a2 2 0 010 2.8l-7.7 7.7a2 2 0 01-1.4.6H8.3a2 2 0 01-1.4-.6l-2.3-2.3a1.7 1.7 0 010-2.4z"/><path d="M9 10l5 5"/>'),
 box:repairIcon('<rect x="4.5" y="6.5" width="15" height="11" rx="1" stroke-dasharray="3 2.2"/>'),
 pan:repairIcon('<path d="M12 3.5v17M3.5 12h17"/><path d="M9.5 6L12 3.5 14.5 6M9.5 18l2.5 2.5 2.5-2.5M6 9.5L3.5 12 6 14.5M18 9.5l2.5 2.5-2.5 2.5"/>'),
 blemish:repairIcon('<circle cx="12" cy="12" r="7" stroke-dasharray="3 2.2"/><circle cx="12" cy="12" r="1.6" fill="currentColor" stroke="none"/>')
};
const brushTool=document.createElement('button');brushTool.id='repairBrushTool';brushTool.innerHTML=repairIcons.brush+'<span>涂抹</span>';brushTool.title='涂抹标记折痕、凸起或瑕疵（默认工具）';
const eraserTool=document.createElement('button');eraserTool.id='repairEraserTool';eraserTool.innerHTML=repairIcons.eraser+'<span>橡皮擦</span>';eraserTool.title='擦掉涂抹标记的一部分';
$('repairBox').innerHTML=repairIcons.box+'<span>框选</span>';$('repairPan').innerHTML=repairIcons.pan+'<span>移动</span>';blemishTool.innerHTML=repairIcons.blemish+'<span>圈瑕疵</span>';
$('repairBox').title='拖动框选，适合大面积凸起';$('repairPan').title='拖动画面（也可按住空格或鼠标中键）';
const repairToolGroup=$('repairBox').parentElement;repairToolGroup.classList.add('repair-tool-palette');repairToolGroup.setAttribute('role','toolbar');repairToolGroup.setAttribute('aria-label','标记工具');
repairToolGroup.prepend(brushTool,eraserTool);
const repairBrushPanel=document.createElement('div');repairBrushPanel.id='repairBrushPanel';
repairBrushPanel.innerHTML='<div class="repair-kind-chips" role="radiogroup" aria-label="涂抹类型"><button data-kind="crease" role="radio" aria-checked="true" class="crease active">折痕</button><button data-kind="bump" role="radio" aria-checked="false" class="bump">凸起</button><button data-kind="blemish" role="radio" aria-checked="false" class="blemish">瑕疵</button></div><label class="repair-brush-size"><span id="repairBrushSizeLabel">笔刷大小</span> <output id="repairBrushSizeValue">24 px</output><input id="repairBrushSize" type="range" min="4" max="200" step="1" value="24" aria-describedby="repairBrushHint"></label><label class="repair-snap"><input id="repairSnap" type="checkbox" checked> <span>自动吸附到折痕</span></label><p id="repairBrushHint" class="repair-help">按 [ 缩小、] 放大笔刷。折痕涂个大概即可，松开后会自动收紧到折痕线上。</p>';
repairToolGroup.after(repairBrushPanel);
function setRepairTool(tool){
 if(tool!=='pan'&&repairReadOnly){toast('请先切换到当前工作图');return}
 repairBrushMode=tool==='brush'||tool==='eraser'?tool:null;repairPan=tool==='pan';repairDrawKind=tool==='blemish'?'blemish':null;
 for(const [id,name] of [['repairBrushTool','brush'],['repairEraserTool','eraser'],['repairBox','box'],['repairPan','pan'],['repairBlemishTool','blemish']]){$(id).classList.toggle('active',name===tool);$(id).setAttribute('aria-pressed',String(name===tool))}
 repairBrushPanel.hidden=!repairBrushMode;repairBrushPanel.classList.toggle('erasing',tool==='eraser');
 $('repairBrushSizeLabel').textContent=tool==='eraser'?'橡皮擦大小':'笔刷大小';
 $('repairBrushSize').value=tool==='eraser'?repairEraserSize:repairBrushSize;syncRepairBrushSize();
 if(tool==='blemish'){repairSelection=null;repairActiveMark=null;repairKindPicker.hidden=true;paintRepairSelection();paintRepairMarks();toast('拖动圈出瑕疵；仅用于允许重修的空白纸面，避免圈入字迹和印章')}
 if(repairBrushMode){repairKindPicker.hidden=true}
 repairBrushCursor.hidden=true;
}
function syncRepairBrushSize(){const value=Number($('repairBrushSize').value);if(repairBrushMode==='eraser')repairEraserSize=value;else repairBrushSize=value;$('repairBrushSizeValue').textContent=value+' px'}
brushTool.onclick=()=>setRepairTool('brush');eraserTool.onclick=()=>setRepairTool('eraser');
$('repairBox').onclick=()=>setRepairTool('box');$('repairPan').onclick=()=>setRepairTool('pan');blemishTool.onclick=()=>setRepairTool('blemish');
$('repairBrushSize').oninput=syncRepairBrushSize;
$('repairSnap').onchange=()=>{repairSnap=$('repairSnap').checked};
for(const chip of repairBrushPanel.querySelectorAll('[data-kind]'))chip.onclick=()=>{repairBrushKind=chip.dataset.kind;for(const other of repairBrushPanel.querySelectorAll('[data-kind]')){other.classList.toggle('active',other===chip);other.setAttribute('aria-checked',String(other===chip))}if(repairBrushMode!=='brush')setRepairTool('brush')};
document.addEventListener('keydown',e=>{
 if(workStage!=='repair'||!repairBrushMode||['INPUT','SELECT','TEXTAREA'].includes(e.target.tagName)||e.target.isContentEditable||e.ctrlKey||e.metaKey||e.altKey)return;
 if(e.key!=='['&&e.key!==']')return;
 e.preventDefault();const input=$('repairBrushSize'),value=Number(input.value);
 input.value=String(Math.max(4,Math.min(200,Math.round(e.key===']'?Math.max(value+1,value*1.18):Math.min(value-1,value/1.18)))));syncRepairBrushSize();
});
function newRepairMarkId(){return Date.now().toString(36)+'-'+Math.random().toString(36).slice(2,10)}
function repairBrushPoint(ev,rect){return [Math.max(0,Math.min(1,(ev.clientX-rect.left)/rect.width)),Math.max(0,Math.min(1,(ev.clientY-rect.top)/rect.height))]}
// Points are densified so the eraser can cut long segments anywhere.
function repairAppendPoint(path,point,spacing,size=repairSize){
 const last=path[path.length-1];if(!last){path.push(point);return}
 const distance=Math.hypot((point[0]-last[0])*size[0],(point[1]-last[1])*size[1]);if(distance<spacing)return;
 const steps=Math.ceil(distance/spacing);for(let i=1;i<=steps&&path.length<4000;i++)path.push([last[0]+(point[0]-last[0])*i/steps,last[1]+(point[1]-last[1])*i/steps]);
}
function densifyRepairPath(path,spacing,size=repairSize){const out=[];for(const point of path)repairAppendPoint(out,point,spacing,size);return out}
function repairBrushRegion(brush,size=repairSize){
 const radius=brush.size*size[0]/2+2;let x1=1,y1=1,x2=0,y2=0;
 for(const path of brush.paths)for(const [x,y] of path){x1=Math.min(x1,x);y1=Math.min(y1,y);x2=Math.max(x2,x);y2=Math.max(y2,y)}
 const region=[Math.max(0,x1-radius/size[0]),Math.max(0,y1-radius/size[1]),Math.min(1,x2+radius/size[0]),Math.min(1,y2+radius/size[1])];
 for(const [a,b,axis] of [[0,2,0],[1,3,1]]){const minimum=6/size[axis];if(region[b]-region[a]<minimum){const centre=(region[a]+region[b])/2;region[a]=Math.max(0,Math.min(1-minimum,centre-minimum/2));region[b]=Math.min(1,region[a]+minimum)}}
 return region;
}
// Remove stroke points inside the eraser circle; split paths where they are cut.
function eraseRepairBrush(mark,centre,radius,size=repairSize){
 const paths=[];let changed=false;
 for(const path of mark.brush.paths){let piece=[];for(const point of path){if(Math.hypot((point[0]-centre[0])*size[0],(point[1]-centre[1])*size[1])<=radius){changed=true;if(piece.length)paths.push(piece);piece=[]}else piece.push(point)}if(piece.length)paths.push(piece)}
 if(!changed)return false;
 mark.brush={size:mark.brush.size,paths:paths.slice(0,50)};if(paths.length)mark.region=repairBrushRegion(mark.brush,size);return true;
}
function paintRepairBrushes(){
 const [w,h]=repairSize;repairBrushLayer.setAttribute('viewBox',`0 0 ${w} ${h}`);repairBrushLayer.replaceChildren();
 const draw=(mark,className)=>{
  const group=document.createElementNS(SVG_NS,'g');group.setAttribute('class','repair-brush '+mark.kind+className);
  for(const path of mark.brush.paths){const line=document.createElementNS(SVG_NS,'polyline');const points=path.length===1?[path[0],[path[0][0]+.1/w,path[0][1]]]:path;line.setAttribute('points',points.map(([x,y])=>(x*w).toFixed(1)+','+(y*h).toFixed(1)).join(' '));line.setAttribute('stroke-width',String(mark.brush.size*w));group.append(line)}
  repairBrushLayer.append(group);
 };
 for(const mark of repairMarks)if(mark.brush)draw(mark,mark.id===repairActiveMark?' active':'');
 if(repairBrushLive)draw(repairBrushLive,' live');
}
const paintRepairMarksBoxes=paintRepairMarks;
paintRepairMarks=function(){paintRepairMarksBoxes();paintRepairBrushes()};
async function snapRepairMark(markId){
 const itemId=current?.id,mark=repairMarks.find(m=>m.id===markId);if(!mark?.brush)return;
 const sent=JSON.stringify(mark.brush);
 try{
  await repairMarkSaveChain.catch(()=>{});
  const result=await api('repair/snap',{id:itemId,region:mark.region,brush:mark.brush});
  const target=repairMarks.find(m=>m.id===markId);
  if(current?.id!==itemId||!target||JSON.stringify(target.brush)!==sent)return; // edited meanwhile
  if(!result.snapped)return toast('未检测到明显折痕，保留原涂抹');
  if(repairDraft&&repairResultRegions.some(m=>m.id===markId))return;
  const spacing=Math.max(2,result.brush.size*repairSize[0]/6);
  target.brush={size:result.brush.size,paths:result.brush.paths.map(path=>densifyRepairPath(path,spacing))};target.region=repairBrushRegion(target.brush);
  paintRepairMarks();saveRepairMarks();toast('已吸附到折痕');
 }catch(error){toast('吸附失败，保留原涂抹：'+error.message)}
}
function startRepairBrushStroke(e){
 const view=$('repairViewport'),rect=$('repairWrap').getBoundingClientRect();if(!rect.width||!rect.height)return;
 const bounds=view.getBoundingClientRect(),left=bounds.left+view.clientLeft,top=bounds.top+view.clientTop;
 if(e.clientX<left||e.clientX>=left+view.clientWidth||e.clientY<top||e.clientY>=top+view.clientHeight)return;
 if(!repairMarkSignature)return toast('请先重启工具后台以启用标记保存');
 if(e.clientX<rect.left||e.clientX>rect.right||e.clientY<rect.top||e.clientY>rect.bottom)return;
 e.preventDefault();repairKindPicker.hidden=true;closeRepairContextMenu();
 const itemId=current.id,eraser=repairBrushMode==='eraser',spacing=Math.max(2,repairBrushSize/6);let erased=false;
 if(!eraser){repairBrushLive={id:newRepairMarkId(),kind:repairBrushKind,brush:{size:Math.min(.5,repairBrushSize/repairSize[0]),paths:[[repairBrushPoint(e,rect)]]}};repairActiveMark=null;repairSelection=null;repairSelectionKind=null;paintRepairSelection()}
 const erase=ev=>{
  const centre=repairBrushPoint(ev,rect);
  for(const mark of repairMarks){if(!mark.brush||(repairDraft&&repairResultRegions.some(m=>m.id===mark.id)))continue;if(eraseRepairBrush(mark,centre,repairEraserSize/2))erased=true}
  if(erased)repairMarks=repairMarks.filter(mark=>!mark.brush||mark.brush.paths.length);
 };
 if(eraser)erase(e);
 paintRepairMarks();view.setPointerCapture(e.pointerId);
 const move=ev=>{
  if(ev.pointerId!==e.pointerId||current?.id!==itemId||workStage!=='repair')return;
  placeRepairBrushCursor(ev);
  for(const sample of ev.getCoalescedEvents?.()||[ev]){if(eraser)erase(sample);else repairAppendPoint(repairBrushLive.brush.paths[0],repairBrushPoint(sample,rect),spacing)}
  paintRepairMarks();
 };
 const up=ev=>{
  if(ev.pointerId!==e.pointerId)return;
  view.removeEventListener('pointermove',move);view.removeEventListener('pointerup',up);view.removeEventListener('pointercancel',up);view.removeEventListener('lostpointercapture',up);
  if(view.hasPointerCapture(e.pointerId))view.releasePointerCapture(e.pointerId);
  const live=repairBrushLive;repairBrushLive=null;
  if(current?.id!==itemId||workStage!=='repair'){paintRepairMarks();return}
  if(eraser){paintRepairMarks();if(erased)saveRepairMarks();return}
  if(ev.type==='pointercancel'||!live){paintRepairMarks();return}
  const mark={id:live.id,kind:live.kind,level:'standard',region:repairBrushRegion(live.brush),brush:live.brush};
  repairMarks.push(mark);repairActiveMark=mark.id;repairSelectionKind=mark.kind;$('repairKind').value=mark.kind;
  paintRepairMarks();saveRepairMarks();
  showRepairLevelPrompt(mark.id);
  if(mark.kind==='crease'&&repairSnap)snapRepairMark(mark.id);
 };
 view.addEventListener('pointermove',move);view.addEventListener('pointerup',up);view.addEventListener('pointercancel',up);view.addEventListener('lostpointercapture',up);
}
function placeRepairBrushCursor(ev){
 const wrap=$('repairWrap'),rect=wrap.getBoundingClientRect(),view=$('repairViewport'),bounds=view.getBoundingClientRect();
 const left=Math.max(rect.left,bounds.left+view.clientLeft),top=Math.max(rect.top,bounds.top+view.clientTop),right=Math.min(rect.right,bounds.left+view.clientLeft+view.clientWidth),bottom=Math.min(rect.bottom,bounds.top+view.clientTop+view.clientHeight);
 if(wrap.style.visibility==='hidden'||rect.width<=0||ev.clientX<left||ev.clientX>=right||ev.clientY<top||ev.clientY>=bottom){repairBrushCursor.hidden=true;return}
 const diameter=Math.max(2,(repairBrushMode==='eraser'?repairEraserSize:repairBrushSize)*rect.width/repairSize[0]),x=ev.clientX-diameter/2,y=ev.clientY-diameter/2;
 repairBrushCursor.hidden=false;
 repairBrushCursor.className=repairBrushMode==='eraser'?'eraser':repairBrushKind;
 Object.assign(repairBrushCursor.style,{width:diameter+'px',height:diameter+'px',left:ev.clientX+'px',top:ev.clientY+'px',clipPath:`inset(${Math.max(0,top-y)}px ${Math.max(0,x+diameter-right)}px ${Math.max(0,y+diameter-bottom)}px ${Math.max(0,left-x)}px)`});
}
const repairBoxPointerDown=$('repairViewport').onpointerdown;
$('repairViewport').onpointerdown=e=>{
 const panGesture=repairPan||repairSpace||e.button===1;
 if(e.button===0&&!panGesture&&repairBrushMode&&!repairBusy&&!repairReadOnly&&current?.confirmed&&$('repairEmpty').hidden)return startRepairBrushStroke(e);
 return repairBoxPointerDown(e);
};
$('repairViewport').addEventListener('pointermove',e=>{
 const show=workStage==='repair'&&!!repairBrushMode&&!repairPan&&!repairSpace&&!repairBusy&&!repairReadOnly&&$('repairEmpty').hidden;
 if(!show){repairBrushCursor.hidden=true;return}
 $('repairViewport').style.cursor='crosshair';placeRepairBrushCursor(e);
});
$('repairViewport').addEventListener('pointerleave',()=>{repairBrushCursor.hidden=true});
setRepairTool('brush');
$('repairPreview').onclick=async()=>{
 if(repairDraft&&repairLevelChoices.size)return toast('有折痕等级已调整，请先在对应卡片点击“重新修复”');
 if(repairBusy)return;if(repairDraft&&$('repairMethod').value!=='ai')return toast('当前已有预览，可逐处采用或直接点击 AI 修复');if(!repairMarks.length&&!repairSelection)return toast('请先框选并分类需要修复的位置');
 if(repairSelection&&!repairSelectionKind){showRepairKindPicker();return toast('请先为刚框选的区域选择折痕或凸起')}
 repairKindPicker.hidden=true;
 const previous=repairDraft?{draft:repairDraft,image:repairResultImage,before:repairResultBeforeImage,regions:repairResultRegions,region:repairResultRegion,full:repairResultFull}:null;let generatedDraft=null;
 repairBusy=true;$('repairPreview').disabled=true;$('repairPreview').textContent='正在修复…';
 const regions=repairMarks.map(mark=>({...mark,region:[...mark.region]})),id=current.id,serial=++repairResultSerial,region=[Math.min(...regions.map(x=>x.region[0])),Math.min(...regions.map(x=>x.region[1])),Math.max(...regions.map(x=>x.region[2])),Math.max(...regions.map(x=>x.region[3]))];repairResultRegions=regions;repairResultImage=null;repairResultRegion=region;repairResultFull=false;
 setRepairResultState('loading',`${$('repairMethod').value==='ai'?'AI 将按分类逐处修复':'正在处理'}本图 ${regions.length} 处标记，左侧图片保持不变`);
 try{
  await repairMarkSaveChain;
  const result=await api('repair/preview',{id,regions,method:$('repairMethod').value,strength:Number($('repairStrength').value),...(previous?{replace_draft:previous.draft}:{})});generatedDraft=result.draft;
  if(current?.id!==id||workStage!=='repair'||serial!==repairResultSerial)return;
  const [beforeImage,image]=await Promise.all([decodedImage(`/api/repair/image/${id}?detail=1&v=${current.revision}`),decodedImage(`/api/repair/image/${id}?detail=1&v=${current.revision}&draft=${result.draft}`)]);
  if(current?.id!==id||workStage!=='repair'||serial!==repairResultSerial)return;
  repairDraft=result.draft;repairResultBeforeImage=beforeImage;repairResultImage=image;
  repairResultMethods=Object.fromEntries(regions.map(mark=>[mark.id,result.method||$('repairMethod').value]));paintRepairResult();setRepairResultState('ready');
  if(previous)await api('repair/discard',{id,draft:previous.draft}).catch(()=>{});
 }catch(e){if(serial===repairResultSerial){if(previous){repairDraft=previous.draft;repairResultImage=previous.image;repairResultBeforeImage=previous.before;repairResultRegions=previous.regions;repairResultRegion=previous.region;repairResultFull=previous.full;paintRepairResult();setRepairResultState('ready');toast('AI 修复未完成，已保留原预览：'+e.message)}else{repairDraft=null;setRepairResultState('error',e.message)}if(generatedDraft)await api('repair/discard',{id,draft:generatedDraft}).catch(()=>{})}}
 finally{repairBusy=false;$('repairPreview').disabled=!!repairDraft;$('repairPreview').textContent='常规修复';syncRepairWorkflow()}
};
async function repairAction(action){if(repairBusy||!current?.confirmed)return;if(action==='accept'&&repairLevelChoices.size)return toast('有折痕等级尚未生效，请先逐处点击“重新修复”');repairBusy=true;const id=current.id;try{const item=await api('repair/'+action,{id,draft:repairDraft});replace(item);repairDraft=null;repairSelection=null;await selectRepairAfterBusy(id)}catch(e){toast(e.message)}finally{repairBusy=false}}
async function selectRepairAfterBusy(id){repairBusy=false;await selectRepair(id);repairBusy=true}
$('repairAccept').onclick=()=>repairAction('accept');$('repairUndo').onclick=()=>repairAction('undo');$('repairRedo').onclick=()=>repairAction('redo');
$('repairComplete').onclick=async()=>{if(repairDraft)return toast('请先采用或放弃修复预览');await repairAction('complete')};
async function discardRepairPreview(){
 if(repairBusy)return false;
 repairBusy=true;
 try{if(repairDraft)await api('repair/discard',{id:current.id,draft:repairDraft});repairDraft=null;resetRepairResult();fitRepair();return true}
 catch(e){toast(e.message);return false}
 finally{repairBusy=false;syncRepairWorkflow();aiRepairButton.disabled=false}
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
aiConfig.innerHTML='<div class="ai-config-head"><h2 id="aiConfigTitle">设置</h2><button id="closeAiConfig" aria-label="关闭设置">关闭</button></div><div id="aiConfigBody"></div>';
document.body.append(aiConfig);
const aiConfigButton=document.createElement('button');aiConfigButton.id='openAiConfig';aiConfigButton.title='设置';aiConfigButton.setAttribute('aria-label','设置');aiConfigButton.setAttribute('aria-haspopup','dialog');
aiConfigButton.innerHTML='<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9.5 2h5l.5 2.5 2 1.2 2.4-.8 2.5 4.3L19.5 11v2l2.4 1.8-2.5 4.3-2.4-.8-2 1.2-.5 2.5h-5L9 19.5l-2-1.2-2.4.8-2.5-4.3L4.5 13v-2L2.1 9.2l2.5-4.3 2.4.8 2-1.2z"/><circle cx="12" cy="12" r="3.2"/></svg>';
document.querySelector('.header-imports').after(aiConfigButton);
aiConfigButton.onclick=()=>aiConfig.showModal();$('closeAiConfig').onclick=()=>aiConfig.close();
aiConfig.addEventListener('click',e=>{if(e.target===aiConfig&&aiConfig.dataset.migrating!=='true'){const r=aiConfig.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)aiConfig.close()}});
const connection=repairSettings.querySelector('details.advanced-controls');
const configHelp=document.createElement('p');configHelp.className='repair-help';configHelp.textContent='配置 AI 修复使用的图像编辑服务。';$('aiConfigBody').append(configHelp);
for(const id of ['repairBaseURL','repairKey','repairModel'])$('aiConfigBody').append($(id).closest('label'));
$('aiConfigBody').append($('repairConnect'),$('repairTest'),$('repairConfigState'));
connection.remove();
$('repairKind').closest('label').hidden=true;
const noRepairKind=document.createElement('option');noRepairKind.value='';noRepairKind.textContent='选择一个标记后可修改类型';$('repairKind').prepend(noRepairKind);$('repairKind').value='';
const blemishKind=document.createElement('option');blemishKind.value='blemish';blemishKind.textContent='瑕疵去除';$('repairKind').append(blemishKind);
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
 if(repairBusy)return;if(repairDraft&&method!=='ai')return toast('当前已有预览，可逐处采用或直接点击 AI 修复');
 lastRepairMethod=method;$('repairMethod').value=method;
 aiRepairButton.disabled=true;aiRepairButton.textContent=method==='ai'?'AI 正在修复…':'AI 修复';
 try{await runRepairPreview()}finally{aiRepairButton.disabled=false;aiRepairButton.textContent='AI 修复'}
}
$('repairPreview').onclick=()=>startRepairWith('local');
aiRepairButton.onclick=()=>startRepairWith('ai');
$('repairResultRetry').onclick=()=>startRepairWith(lastRepairMethod);
repairRegenerate.onclick=async()=>{
 if(repairBusy)return;
 if(repairLevelChoices.size)return toast('有折痕等级已调整，请先在对应卡片点击“重新修复”');
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
  repairResultMethods=pending.methods||Object.fromEntries(regions.map(mark=>[mark.id,pending.method]));
  paintRepairResult();setRepairResultState('ready');
 }catch(e){if(active()){resetRepairResult();toast(e.message)}}
 finally{if(ownsBusy){repairBusy=false;$('repairPreview').disabled=!!repairDraft;aiRepairButton.disabled=false}}
};
