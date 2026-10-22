// Single and multiple works share one explicit, review-first AI queue.
let repairBatchState={running:false,entries:[]},repairBatchPolling=false,repairBatchDrawn='';
const batchButton=document.createElement('button');batchButton.id='openRepairBatch';batchButton.textContent='批量 AI 修复';$('openAiConfig').after(batchButton);
const batchPanel=document.createElement('details');batchPanel.id='repairBatchPanel';batchPanel.className='advanced-controls';batchPanel.innerHTML='<summary>AI 任务与待审核结果 <span id="repairBatchCount">0</span></summary><p id="repairBatchProgress" class="repair-help">先标注各幅作品，最后统一选择并开始修复。</p><div id="repairBatchEntries"></div><button id="cancelRepairBatch" hidden>停止未开始的任务</button><p class="repair-help">不会自动覆盖原图。停止队列后，正在调用的任务仍会完成，可能产生费用。</p>';repairSettings.prepend(batchPanel);
const batchDialog=document.createElement('dialog');batchDialog.id='repairBatchDialog';batchDialog.setAttribute('aria-labelledby','repairBatchTitle');batchDialog.innerHTML='<div class="ai-config-head"><h2 id="repairBatchTitle">选择 AI 修复作品</h2><button id="closeRepairBatch">关闭</button></div><div class="batch-dialog-body"><p>只选一幅可单张修复，多选可批量修复。仅包含已确认裁剪且有待处理标记的作品。</p><div class="batch-dialog-tools"><button id="repairBatchAll">全选</button><button id="repairBatchNone">全不选</button><label>同时处理 <select id="repairBatchWorkers"><option value="2">2 幅</option><option value="1">1 幅 · 较稳妥</option></select></label></div><div id="repairBatchChoices"></div><p id="repairBatchSelectionCount"></p><p class="repair-help">每个标记分别调用 AI，可能产生多次费用。保持原图像素尺寸、锁定框外像素；疑似笔画变形或明显色差将拦截。仍需逐幅审核。</p><button id="startRepairBatch" class="primary wide">开始 AI 修复</button></div>';document.body.append(batchDialog);
const batchLabels={queued:'排队中',running:'正在修复',ready:'待审核',failed:'失败',stale:'已失效',cancelled:'已停止',interrupted:'已中断',reviewed:'已审核',discarded:'已放弃'};
function drawRepairBatch(){
 const snapshot=JSON.stringify(repairBatchState);if(snapshot===repairBatchDrawn)return;repairBatchDrawn=snapshot;
 const entries=repairBatchState.entries,ready=entries.filter(e=>e.status==='ready').length,finished=entries.filter(e=>!['queued','running'].includes(e.status)).length;
 $('repairBatchCount').textContent=ready?`${ready} 待审核`:entries.length;
 batchButton.textContent=repairBatchState.running?`AI 修复中 ${finished}/${entries.length}`:ready?`AI 待审核 ${ready} 幅`:'批量 AI 修复';
 $('repairBatchProgress').textContent=entries.length?`${repairBatchState.running?'处理中':'本批已停止处理'}：${finished} / ${entries.length} 幅，${ready} 幅待审核`:'先标注各幅作品，最后统一选择并开始修复。';
 $('cancelRepairBatch').hidden=!repairBatchState.running||repairBatchState.cancel;
 $('repairBatchEntries').replaceChildren();
 for(const entry of entries){const row=document.createElement('div');row.className='repair-batch-row';const text=document.createElement('span');text.textContent=entry.name;text.title=entry.name;const state=document.createElement('small');state.textContent=batchLabels[entry.status]||entry.status;row.append(text,state);if(entry.status==='ready'){const view=document.createElement('button');view.textContent='查看';view.onclick=()=>selectRepair(entry.id);row.append(view)}if(entry.error){const error=document.createElement('p');error.textContent=entry.error;row.append(error)}$('repairBatchEntries').append(row)}
}
async function pollRepairBatch(){
 if(repairBatchPolling)return;repairBatchPolling=true;
 try{const response=await fetch('/api/repair/batch-status');if(!response.ok)return;repairBatchState=await response.json();drawRepairBatch()}catch(e){}finally{repairBatchPolling=false}
}
function updateBatchSelection(){const checked=[...$('repairBatchChoices').querySelectorAll('input:checked')];const marks=checked.reduce((sum,input)=>sum+Number(input.dataset.count),0);$('repairBatchSelectionCount').textContent=`已选 ${checked.length} 幅 · ${marks} 处标记`;$('startRepairBatch').disabled=!checked.length}
batchButton.onclick=async()=>{
 if(repairBusy||repairDraft)return toast('请先完成或放弃当前预览');
 if(workStage==='repair'&&repairSelection&&!repairSelectionKind){showRepairKindPicker();return toast('请先给刚框选的区域分类')}
 try{
  await repairMarkSaveChain;if(workStage!=='repair')await requestStage('repair');await pollRepairBatch();if(repairBatchState.running){batchPanel.open=true;return toast('批量修复正在后台进行，可在任务列表中查看')}
  const response=await fetch('/api/repair/batch-candidates');const choices=await response.json();if(!response.ok)throw Error(choices.error);$('repairBatchChoices').replaceChildren();
  for(const item of choices){const label=document.createElement('label');const input=document.createElement('input');input.type='checkbox';input.checked=true;input.value=item.id;input.dataset.count=item.regions.length;input.onchange=updateBatchSelection;const text=document.createElement('span');text.textContent=`${item.name} · ${item.regions.length} 处`;label.append(input,text);$('repairBatchChoices').append(label)}
  if(!choices.length){batchPanel.open=true;return toast('暂无待处理标记；已有结果请先审核，或继续标注作品')}
  updateBatchSelection();batchDialog.showModal();
 }catch(e){toast(e.message)}
};
$('closeRepairBatch').onclick=()=>batchDialog.close();
$('repairBatchAll').onclick=()=>{for(const input of $('repairBatchChoices').querySelectorAll('input'))input.checked=true;updateBatchSelection()};
$('repairBatchNone').onclick=()=>{for(const input of $('repairBatchChoices').querySelectorAll('input'))input.checked=false;updateBatchSelection()};
$('startRepairBatch').onclick=async()=>{const button=$('startRepairBatch');button.disabled=true;try{repairBatchState=await api('repair/batch-start',{ids:[...$('repairBatchChoices').querySelectorAll('input:checked')].map(x=>x.value),workers:Number($('repairBatchWorkers').value)});batchDialog.close();batchPanel.open=true;drawRepairBatch();toast('已开始后台修复，可以继续查看其他作品')}catch(e){toast(e.message)}finally{button.disabled=false}};
$('cancelRepairBatch').onclick=async()=>{try{repairBatchState=await api('repair/batch-cancel',{});drawRepairBatch()}catch(e){toast(e.message)}};
async function showBatchRepairResult(entry){
 if(repairBusy||repairDraft||workStage!=='repair'||current?.id!==entry.id)return;
 repairBusy=true;lastRepairMethod='ai';$('repairMethod').value='ai';const serial=++repairResultSerial,id=entry.id;
 setRepairResultState('loading','正在读取已完成的批量结果，不会再次调用 AI');
 try{const [before,after]=await Promise.all([decodedImage(`/api/repair/image/${id}?detail=1&v=${current.revision}`),decodedImage(`/api/repair/image/${id}?detail=1&v=${current.revision}&draft=${entry.draft}`)]);if(current?.id!==id||workStage!=='repair'||serial!==repairResultSerial)return;repairDraft=entry.draft;repairResultBeforeImage=before;repairResultImage=after;repairResultRegions=entry.regions;const regions=entry.regions.map(e=>e.region);repairResultRegion=[Math.min(...regions.map(r=>r[0])),Math.min(...regions.map(r=>r[1])),Math.max(...regions.map(r=>r[2])),Math.max(...regions.map(r=>r[3]))];repairResultFull=false;paintRepairResult();setRepairResultState('ready');$('repairPreview').disabled=true;$('repairAI').disabled=true}
 catch(e){setRepairResultState('error',e.message)}finally{repairBusy=false}
}
const selectWithNoBatch=selectRepair;
selectRepair=async function(id){if(repairBusy||repairDraft)return selectWithNoBatch(id);await selectWithNoBatch(id);await pollRepairBatch();if(current?.id===id){const entry=repairBatchState.entries.find(e=>e.id===id&&e.status==='ready');if(entry)await showBatchRepairResult(entry)}};
const discardWithoutBatch=$('repairDiscard').onclick;
$('repairDiscard').onclick=async()=>{if(repairBusy)return;const entry=repairBatchState.entries.find(e=>e.id===current?.id&&e.draft===repairDraft&&e.status==='ready');try{if(entry)await api('repair/batch-dismiss',{id:entry.id,draft:entry.draft});await discardWithoutBatch();await pollRepairBatch()}catch(e){toast(e.message)}};
const regenerateWithoutBatch=$('repairRegenerate')?.onclick;
if(regenerateWithoutBatch)$('repairRegenerate').onclick=async()=>{if(repairBusy)return;const entry=repairBatchState.entries.find(e=>e.id===current?.id&&e.draft===repairDraft&&e.status==='ready');try{if(entry)await api('repair/batch-dismiss',{id:entry.id,draft:entry.draft});await regenerateWithoutBatch();await pollRepairBatch()}catch(e){toast(e.message)}};
$('repairAI').title='只修复当前作品；多幅请用顶部“批量 AI 修复”';
pollRepairBatch();setInterval(pollRepairBatch,2500);
