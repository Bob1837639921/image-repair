// Recognition is a separate, explicitly started read-and-review workflow.
(()=>{
 const button=document.createElement('button');button.id='openRecognition';button.className='recognition-entry';button.innerHTML='<span aria-hidden="true">⌕</span> 作品识别';
 const settingsButton=document.getElementById('openAiConfig');settingsButton.before(button);
 const dialog=document.createElement('dialog');dialog.id='recognitionDialog';dialog.setAttribute('aria-labelledby','recognitionTitle');
 dialog.innerHTML=`<div class="recognition-head"><div><div class="settings-eyebrow">ARTWORK READER</div><h2 id="recognitionTitle">读落款，识作品</h2></div><button id="closeRecognition" aria-label="关闭作品识别">×</button></div>
 <div class="recognition-filename" id="recognitionFilename"></div><div class="recognition-layout">
 <section class="recognition-visual"><div class="recognition-image-tools"><div id="recognitionParts"></div><button id="recognitionZoom">放大细看</button></div><div class="recognition-image-view"><img id="recognitionImage" alt="当前作品原始裁剪图"></div><p>以原图笔墨识读 · 点击局部查看落款和正文细节</p></section>
 <section class="recognition-content"><div class="recognition-state" id="recognitionState" role="status" aria-live="polite"></div>
 <div id="recognitionIntro"><div class="recognition-rule"><b>01</b><div><strong>落款优先</strong><p>先辨认实际书写者，区分书写作者与诗文作者。</p></div></div><div class="recognition-rule"><b>02</b><div><strong>正文辅助</strong><p>结合整幅与四个局部识读，存疑内容保留候选。</p></div></div><div class="recognition-rule"><b>03</b><div><strong>由你确认</strong><p>识读不会改动图片、编号或文件名。确认后保存作品资料。</p></div></div></div>
 <div id="recognitionResults" hidden><div class="recognition-results-heading"><strong>识读结果</strong><span id="recognitionReviewBadge">待你核对</span></div><div class="recognition-fields"><label>书写作者 <span id="recognitionAuthorStatus"></span><input id="recognitionCalligrapher" maxlength="200" placeholder="尚未确定，可手动填写"></label><label>作品名称 <span id="recognitionTitleStatus"></span><input id="recognitionWorkTitle" maxlength="200" placeholder="尚未确定，可手动填写"></label><label>诗文作者<input id="recognitionTextAuthor" maxlength="200" placeholder="与书写作者分开记录"></label></div><div class="recognition-evidence"><h3>落款原文</h3><p id="recognitionInscription"></p><h3>作者判断依据</h3><p id="recognitionAuthorEvidence"></p><h3>正文节选</h3><p id="recognitionExcerpt"></p><h3>作品判断依据</h3><p id="recognitionTitleEvidence"></p><div id="recognitionCandidates"></div><p id="recognitionNotes"></p></div></div>
 </section></div><div class="recognition-foot"><div><span id="recognitionConnection"></span><small>点击识别后，将整体与局部图片发送到已配置的 AI 服务。</small></div><button id="startRecognition" class="recognition-start">开始识别</button><button id="adoptRecognition" class="primary" disabled>确认并保存资料</button></div>`;
 document.body.append(dialog);
 const el=id=>document.getElementById(id);
 let selected=null,state=null,timer=null,serial=0,part='overview',dirty=false;
 function setStatus(message,loading=false,error=false){const target=el('recognitionState');target.textContent=message;target.classList.toggle('loading',loading);target.classList.toggle('error',error)}
 function showImage(){if(!selected||!state)return;el('recognitionImage').src=`/api/recognition/image/${selected.id}?signature=${encodeURIComponent(state.signature)}&part=${part}`;el('recognitionParts').querySelectorAll('button').forEach(b=>b.classList.toggle('active',b.dataset.part===part))}
 function parts(){const root=el('recognitionParts');root.replaceChildren();const values=[['overview','整体'],['0','局部 1'],['1','局部 2'],['2','局部 3'],['3','局部 4']];if(state?.candidate?.result?.signature_region&&!state.stale)values.push(['signature','落款']);for(const [value,label] of values){const b=document.createElement('button');b.type='button';b.textContent=label;b.dataset.part=value;b.onclick=()=>{part=value;showImage()};root.append(b)}}
 function fields(){return {calligrapher:el('recognitionCalligrapher').value,title:el('recognitionWorkTitle').value,text_author:el('recognitionTextAuthor').value}}
 function syncAdopt(){el('adoptRecognition').disabled=!state?.candidate||state.stale||state.job.running||!Object.values(fields()).some(x=>x.trim())}
 function draw(value){
  const previous=state?.candidate?.token;state=value;
  el('recognitionConnection').textContent=value.connection.configured?`AI · ${value.connection.model}`:'未配置 AI 连接，可从右上角设置中配置';
  el('startRecognition').disabled=value.job.running||!value.connection.configured;
  el('startRecognition').textContent=value.job.running?'正在识读…':value.candidate?'重新识别':'开始识别';
  el('recognitionIntro').hidden=!!value.candidate;el('recognitionResults').hidden=!value.candidate;
  if(value.candidate){
   const r=value.candidate.result,adopted=value.metadata?.recognition_token===value.candidate.token;
   if(previous!==value.candidate.token||!dirty){const data=adopted?value.metadata:r;el('recognitionCalligrapher').value=data.calligrapher||'';el('recognitionWorkTitle').value=data.title||'';el('recognitionTextAuthor').value=data.text_author||'';dirty=false}
   const labels={clear:'有明确依据',uncertain:'存疑，待核对',unknown:'未能确定'};
   el('recognitionAuthorStatus').textContent=labels[r.author_status];el('recognitionTitleStatus').textContent=labels[r.title_status];
   for(const [id,key] of [['recognitionInscription','inscription'],['recognitionAuthorEvidence','author_evidence'],['recognitionExcerpt','body_excerpt'],['recognitionTitleEvidence','title_evidence'],['recognitionNotes','notes']])el(id).textContent=r[key]||'未能辨认';
   el('recognitionReviewBadge').textContent=adopted?'已保存资料':'待你核对';el('recognitionReviewBadge').classList.toggle('adopted',adopted);
   const candidates=el('recognitionCandidates');candidates.replaceChildren();if(r.candidates?.length){const h=document.createElement('h3');h.textContent='存疑候选（不会自动采用）';candidates.append(h);for(const c of r.candidates){const p=document.createElement('p');p.textContent=`${{calligrapher:'书写作者',title:'作品名',text_author:'诗文作者'}[c.field]}：${c.value} · ${c.reason}`;candidates.append(p)}}
  }
  if(value.job.running)setStatus(value.job.phase==='preparing'?'正在准备整体与原图局部…':'AI 正在读落款和正文，请稍候…',true);
  else if(value.job.error)setStatus(value.job.error,false,true);
  else if(value.stale)setStatus('裁剪已变化，旧结果仅供参考；请重新识别后保存。',false,true);
  else setStatus(value.candidate?'识读已完成，请对照左侧原图核对。':'先查看画面，准备好后点击“开始识别”。');
  parts();syncAdopt();
 }
 async function refresh(runSerial){
  const response=await fetch('/api/recognition/status/'+selected.id);const value=await response.json();if(!response.ok)throw Error(value.error||'无法读取识别状态');if(runSerial!==serial)return;
  draw(value);if(value.job.running&&dialog.open)timer=setTimeout(()=>refresh(runSerial).catch(e=>setStatus(e.message,false,true)),1000);
 }
 button.onclick=async()=>{
  if(!current)return toast('请先导入并选择一幅作品');
  await saveChain;await repairMarkSaveChain;selected={id:current.id,name:current.name};state=null;dirty=false;part='overview';const runSerial=++serial;clearTimeout(timer);
  el('recognitionFilename').textContent=selected.name;el('recognitionResults').hidden=true;el('recognitionIntro').hidden=false;el('adoptRecognition').disabled=true;el('startRecognition').disabled=true;el('recognitionImage').removeAttribute('src');setStatus('正在读取当前作品…',true);dialog.showModal();
  try{await refresh(runSerial);showImage()}catch(error){setStatus(error.message,false,true)}
 };
 el('closeRecognition').onclick=()=>dialog.close();dialog.addEventListener('close',()=>{++serial;clearTimeout(timer)});dialog.addEventListener('keydown',e=>e.stopPropagation());
 el('recognitionZoom').onclick=()=>{const view=el('recognitionImage').parentElement;const zoomed=view.classList.toggle('zoomed');el('recognitionZoom').textContent=zoomed?'适合窗口':'放大细看'};
 for(const id of ['recognitionCalligrapher','recognitionWorkTitle','recognitionTextAuthor'])el(id).oninput=()=>{dirty=true;syncAdopt();el('recognitionReviewBadge').textContent='已编辑，待保存'};
 el('startRecognition').onclick=async()=>{
  if(!selected||state?.job.running)return;el('startRecognition').disabled=true;setStatus('正在提交识别…',true);
  try{await api('recognition/start',{id:selected.id,signature:state.signature});dirty=false;clearTimeout(timer);await refresh(serial)}catch(error){setStatus(error.message,false,true);el('startRecognition').disabled=false}
 };
 el('adoptRecognition').onclick=async()=>{
  el('adoptRecognition').disabled=true;
  try{const item=await api('recognition/adopt',{id:selected.id,token:state.candidate.token,signature:state.signature,fields:fields()});replace(item);dirty=false;await refresh(serial);toast('作品资料已保存，图片与原有顺序保持不变')}catch(error){setStatus(error.message,false,true);syncAdopt()}
 };
})();
