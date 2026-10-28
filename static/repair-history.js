// History is a read-only comparison until the explicit restore action.
(()=>{
 const button=document.createElement('button');button.id='openRepairHistory';button.textContent='修复历史';button.title='查看每一步的前后变化，或恢复到指定步骤';$('repairUndo').after(button);
 const dialog=document.createElement('dialog');dialog.id='repairHistoryDialog';dialog.setAttribute('aria-labelledby','repairHistoryTitle');
 dialog.innerHTML='<div class="ai-config-head"><h2 id="repairHistoryTitle">修复历史</h2><button id="closeRepairHistory">关闭</button></div><div class="repair-history-layout"><nav id="repairHistoryList" aria-label="修复步骤"></nav><section class="repair-history-content"><div id="repairHistorySummary"></div><div class="repair-history-pair"><div><strong>这一步修复前</strong><div><img id="repairHistoryBefore" alt="该步骤修复前"></div></div><div><strong>这一步修复后</strong><div><img id="repairHistoryAfter" alt="该步骤修复后"></div></div></div><p id="repairHistoryStatus" role="status"></p></section></div><div class="repair-history-footer"><span>查看历史不会修改当前工作图</span><button id="restoreRepairHistory" class="primary" disabled>恢复到此步骤</button></div>';
 document.body.append(dialog);
 const deleteButton=document.createElement('button');deleteButton.id='deleteRepairHistory';deleteButton.className='repair-history-delete';deleteButton.textContent='删除此步骤';deleteButton.disabled=true;$('restoreRepairHistory').before(deleteButton);
 let history=null,selected=0,serial=0,restoring=false;
 const kinds={crease:'折痕',bump:'凸起',blemish:'瑕疵'},levels={light:'轻度',standard:'标准',strong:'加强'};
 function drawList(){
  const list=$('repairHistoryList');list.replaceChildren();
  for(const step of history.steps){
   const row=document.createElement('button');row.type='button';row.classList.toggle('active',step.step===selected);row.setAttribute('aria-pressed',String(step.step===selected));
   const title=document.createElement('strong');title.textContent=step.label+(step.step===history.current?' · 当前':'');
   const detail=document.createElement('small');detail.textContent=step.step===0?'未修复的裁剪底图':`${step.regions.length||'未知'} 处修复${step.step>history.current?' · 可重做':''}`;
   row.append(title,detail);row.onclick=()=>showStep(step.step);list.append(row);
  }
 }
 async function showStep(index){
  if(restoring)return;selected=index;const version=++serial,entry=history.steps[index];drawList();
  $('restoreRepairHistory').disabled=true;$('repairHistoryStatus').textContent='正在加载此步骤…';
  deleteButton.disabled=true;
  $('repairHistorySummary').replaceChildren();
  const heading=document.createElement('strong');heading.textContent=entry.label+(index===history.current?' · 当前工作图':'');$('repairHistorySummary').append(heading);
  const description=document.createElement('p');description.textContent=entry.regions.map((mark,i)=>`${i+1}. ${kinds[mark.kind]||mark.kind} · ${levels[mark.level]||'默认强度'} · ${entry.methods?.[mark.id]==='ai'?'AI 修复':entry.methods?.[mark.id]==='local'?'常规修复':'方式未记录'}`).join('；')||(index===0?'最初确认的裁剪图，原照片始终保留。':'此旧步骤未记录标记明细。');
  if(entry.time)description.textContent+=' · '+new Date(entry.time).toLocaleString('zh-CN');$('repairHistorySummary').append(description);
  const cells=dialog.querySelectorAll('.repair-history-pair > div > div');cells.forEach(cell=>cell.classList.add('loading-image'));
  try{
   const url=step=>`/api/repair/image/${history.id}?step=${step}&revision=${history.revision}&detail=1`;
   const [before,after]=await Promise.all([decodedImage(url(Math.max(0,index-1))),decodedImage(url(index))]);
   if(version!==serial||!dialog.open)return;
   // Show the changed regions with surrounding paper, rather than a tiny full
   // scroll. Multiple regions share a union so before and after remain aligned.
   let box=[0,0,after.naturalWidth,after.naturalHeight];
   if(entry.regions.length){
    const bounds=[Math.min(...entry.regions.map(m=>m.region[0])),Math.min(...entry.regions.map(m=>m.region[1])),Math.max(...entry.regions.map(m=>m.region[2])),Math.max(...entry.regions.map(m=>m.region[3]))];
    const w=after.naturalWidth,h=after.naturalHeight,pad=Math.max(24,Math.min(140,Math.max((bounds[2]-bounds[0])*w,(bounds[3]-bounds[1])*h)*.3));
    box=[Math.max(0,Math.floor(bounds[0]*w-pad)),Math.max(0,Math.floor(bounds[1]*h-pad)),Math.min(w,Math.ceil(bounds[2]*w+pad)),Math.min(h,Math.ceil(bounds[3]*h+pad))];
   }
   for(const [id,image] of [['repairHistoryBefore',before],['repairHistoryAfter',after]]){
    const canvas=document.createElement('canvas');canvas.width=box[2]-box[0];canvas.height=box[3]-box[1];canvas.id=id;canvas.setAttribute('aria-label',id.endsWith('Before')?'该步骤修复前':'该步骤修复后');canvas.getContext('2d').drawImage(image,...[box[0],box[1],canvas.width,canvas.height],0,0,canvas.width,canvas.height);$(id).replaceWith(canvas);
   }
   $('repairHistoryStatus').textContent=repairDraft?'当前存在待审核预览，可查看历史；采用或放弃预览后才能恢复。':index===history.current?'这是当前使用的步骤。':'恢复后，后续步骤保留，可再次从历史恢复。';
   $('restoreRepairHistory').disabled=!!repairDraft||index===history.current;
   deleteButton.disabled=!!repairDraft||index===0;
  }catch(error){if(version===serial)$('repairHistoryStatus').textContent=error.message}
  finally{if(version===serial)cells.forEach(cell=>cell.classList.remove('loading-image'))}
 }
 button.onclick=async()=>{
  if(repairBusy||!current?.confirmed)return;
  const id=current.id;
  try{await repairMarkSaveChain;const response=await fetch('/api/repair/history/'+id);const value=await response.json();if(!response.ok)throw Error(value.error);if(current?.id!==id)return;history=value;dialog.showModal();await showStep(history.current)}catch(error){toast(error.message)}
 };
 $('closeRepairHistory').onclick=()=>{if(!restoring){++serial;dialog.close()}};
 dialog.addEventListener('cancel',event=>{if(restoring)event.preventDefault();else ++serial});
 $('restoreRepairHistory').onclick=async()=>{
  if(restoring||repairBusy||repairDraft||!history||selected===history.current)return;
  restoring=true;repairBusy=true;$('restoreRepairHistory').disabled=true;$('closeRepairHistory').disabled=true;
  try{
   const item=await api('repair/restore',{id:history.id,revision:history.revision,step:selected});replace(item);dialog.close();resetRepairResult();repairBusy=false;await selectRepair(item.id);toast(`已恢复到${selected===0?'原裁剪图':'第 '+selected+' 步'}，后续步骤保留`);
  }catch(error){$('repairHistoryStatus').textContent=error.message}
  finally{restoring=false;repairBusy=false;$('closeRepairHistory').disabled=false;if(dialog.open)$('restoreRepairHistory').disabled=false}
 };
 deleteButton.onclick=async()=>{
  if(restoring||repairBusy||repairDraft||!history||selected===0)return;
  if(!window.confirm(`删除第 ${selected} 步并移除这一步的修复效果？后续不重叠的步骤会保留，原裁剪图不会删除。`))return;
  restoring=true;repairBusy=true;deleteButton.disabled=true;$('restoreRepairHistory').disabled=true;$('closeRepairHistory').disabled=true;
  try{
   const item=await api('repair/delete-step',{id:history.id,revision:history.revision,step:selected});replace(item);resetRepairResult();repairBusy=false;await selectRepair(item.id);
   const response=await fetch('/api/repair/history/'+item.id),value=await response.json();if(!response.ok)throw Error(value.error);
   history=value;restoring=false;await showStep(Math.min(selected,history.steps.length-1));toast('已删除该修复步骤，后续不重叠步骤保留');
  }catch(error){$('repairHistoryStatus').textContent=error.message;deleteButton.disabled=selected===0||!!repairDraft;$('restoreRepairHistory').disabled=selected===history.current||!!repairDraft}
  finally{restoring=false;repairBusy=false;$('closeRepairHistory').disabled=false}
 };
})();
