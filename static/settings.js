// Global settings: storage and the existing AI connection share one entry point.
(()=>{
 const dialog=$('aiConfigDialog'),trigger=$('openAiConfig'),aiBody=$('aiConfigBody');
 document.querySelector('header').append(trigger);
 dialog.classList.add('app-settings');
 const layout=document.createElement('div');layout.className='settings-layout';
 const tabs=document.createElement('nav');tabs.className='settings-tabs';tabs.setAttribute('aria-label','设置分类');
 tabs.innerHTML='<button id="storageSettingsTab" class="active" aria-pressed="true">文件存储</button><button id="aiSettingsTab" aria-pressed="false">AI 配置</button>';
 const content=document.createElement('div');content.className='settings-content';
 const storage=document.createElement('section');storage.id='storageSettingsPanel';storage.setAttribute('aria-labelledby','storageSettingsTitle');
 storage.innerHTML='<div class="settings-eyebrow">LOCAL STORAGE</div><h3 id="storageSettingsTitle">文件存储</h3><p class="settings-description">照片、裁剪、修复记录和导出文件统一保存在这里。</p><div class="storage-current"><span>当前存储位置</span><output id="storageCurrentPath">正在读取…</output></div><label class="storage-label" for="storagePath">新的存储位置</label><div class="storage-path-field"><input id="storagePath" type="text" autocomplete="off" spellcheck="false" placeholder="例如 D:\\画心数据"><button id="chooseStorageFolder">选择文件夹</button></div><p class="settings-description storage-hint">选择新的或空的文件夹。迁移会保留照片和编辑进度，旧目录保留为备份，确认无误后可手动清理。</p><div class="storage-actions"><button id="applyStoragePath" class="primary">迁移并使用此位置</button></div><div id="storageProgress" hidden><progress id="storageProgressMeter" max="1" value="0" aria-label="文件迁移进度"></progress></div><p id="storageSettingsStatus" class="settings-status" role="status" aria-live="polite"></p>';
 const aiTitle=document.createElement('h3');aiTitle.textContent='AI 配置';aiBody.prepend(aiTitle);aiBody.hidden=true;
 const aiActions=document.createElement('div');aiActions.className='settings-ai-actions';
 $('repairConnect').classList.add('primary');$('repairConnect').classList.remove('wide');$('repairTest').classList.remove('wide');
 aiActions.append($('repairConnect'),$('repairTest'));$('repairConfigState').before(aiActions);
 content.append(storage,aiBody);layout.append(tabs,content);dialog.append(layout);
 let state=null,editing=false,polling=false,choosing=false,refreshSerial=0;
 const normalize=path=>(path||'').trim().replace(/[\\/]+$/,'').toLowerCase();
 function tab(ai){
  storage.hidden=ai;aiBody.hidden=!ai;
  for(const [id,active] of [['storageSettingsTab',!ai],['aiSettingsTab',ai]]){$(id).classList.toggle('active',active);$(id).setAttribute('aria-pressed',String(active))}
 }
 $('storageSettingsTab').onclick=()=>tab(false);$('aiSettingsTab').onclick=()=>tab(true);
 function sync(){
  const moving=!!state?.running;dialog.dataset.migrating=String(moving);
  $('closeAiConfig').disabled=moving;$('aiSettingsTab').disabled=moving;
  $('storagePath').disabled=moving||choosing||state?.can_change===false;
  $('chooseStorageFolder').disabled=moving||choosing||state?.can_change===false;
  $('applyStoragePath').disabled=!state||moving||choosing||state.can_change===false||!$('storagePath').value.trim()||normalize($('storagePath').value)===normalize(state.path);
  $('applyStoragePath').textContent=moving?'正在迁移…':'迁移并使用此位置';
 }
 function draw(value){
  state=value;$('storageCurrentPath').textContent=value.path;
  if(!editing||value.phase==='complete'&&normalize(value.path)===normalize(value.destination)){$('storagePath').value=value.path;editing=false}
  const moving=!!value.running,status=$('storageSettingsStatus');
  $('storageProgress').hidden=!moving;$('storageProgressMeter').max=Math.max(1,value.total);$('storageProgressMeter').value=value.done;
  status.classList.toggle('error',value.phase==='error');
  status.textContent=moving?(value.phase==='switch'?'正在切换存储位置…':`正在复制并校验文件 ${value.done} / ${value.total||'…'}，请等待完成。`):value.phase==='error'?'迁移未完成，原目录继续使用。'+value.error:value.phase==='complete'?`已切换到新位置，无需重启。旧目录备份：${value.previous}`:value.can_change===false?'当前启动通过环境变量指定了目录，暂不支持在此修改。':'修改后将迁移现有文件，并自动用于以后启动。';
  sync();
 }
 async function refresh(){const serial=++refreshSerial,response=await fetch('/api/settings/storage');const value=await response.json();if(!response.ok)throw Error(value.error||'无法读取存储设置');if(serial===refreshSerial)draw(value);return state||value}
 async function poll(){
  if(polling)return;polling=true;
  try{while(state?.running){await new Promise(resolve=>setTimeout(resolve,600));try{await refresh()}catch(error){$('storageSettingsStatus').textContent='正在重新连接以确认迁移状态，请保持窗口打开。';await new Promise(resolve=>setTimeout(resolve,1500))}}}
  finally{polling=false}
 }
 trigger.onclick=async()=>{dialog.showModal();try{await refresh();if(state.running){tab(false);poll()}}catch(error){$('storageSettingsStatus').textContent=error.message}};
 $('closeAiConfig').onclick=()=>{if(!state?.running)dialog.close()};
 dialog.addEventListener('cancel',event=>{if(state?.running)event.preventDefault()});
 $('storagePath').oninput=()=>{editing=true;sync()};
 $('chooseStorageFolder').onclick=async()=>{
  choosing=true;sync();
  try{const result=await api('settings/choose-folder',{});if(result.path){$('storagePath').value=result.path;editing=true}}
  catch(error){$('storageSettingsStatus').textContent=error.message}
  finally{choosing=false;sync()}
 };
 $('applyStoragePath').onclick=async()=>{
  if(busy||repairBusy)return toast('请等待当前图片处理完成');
  try{
   await saveChain;await repairMarkSaveChain;
   ++refreshSerial;
   $('applyStoragePath').disabled=true;
   const value=await api('settings/storage',{path:$('storagePath').value});draw(value);if(value.running)poll();
  }catch(error){$('storageSettingsStatus').classList.add('error');$('storageSettingsStatus').textContent=error.message;sync()}
 };
 refresh().then(value=>{if(value.running){dialog.showModal();tab(false);poll()}}).catch(()=>{});
})();
