// Recognition is a separate, explicitly started read-and-review workflow.
(()=>{
 const button=document.createElement('button');button.id='openRecognition';button.className='recognition-entry';button.innerHTML='<span aria-hidden="true">⌕</span> 作品识别';
 const settingsButton=document.getElementById('openAiConfig');settingsButton.before(button);
 const dialog=document.createElement('dialog');dialog.id='recognitionDialog';dialog.setAttribute('aria-labelledby','recognitionTitle');
 dialog.innerHTML=`<div class="recognition-head"><div><div class="settings-eyebrow">ARTWORK READER</div><h2 id="recognitionTitle">读落款，识作品</h2></div><button id="closeRecognition" aria-label="关闭作品识别">×</button></div>
 <div class="recognition-filename" id="recognitionFilename"></div><div class="recognition-layout">
 <section class="recognition-visual"><div class="recognition-image-tools"><div id="recognitionParts"></div></div><div class="recognition-zoom-tools" role="group" aria-label="图片缩放"><button id="recognitionZoomOut" aria-label="缩小图片" title="缩小">−</button><output id="recognitionZoomPercent" aria-live="polite">加载中…</output><button id="recognitionZoomIn" aria-label="放大图片" title="放大">＋</button><span></span><button id="recognitionActualSize" title="按原始像素显示">100%</button><button id="recognitionFit">适合窗口</button></div><div id="recognitionImageView" class="recognition-image-view" tabindex="0" aria-label="作品图片，滚轮缩放，拖动平移"><div id="recognitionImageStage"><img id="recognitionImage" alt="当前作品原始裁剪图" draggable="false"></div></div><div class="signature-actions"><button id="selectSignature">圈选落款</button><button id="clearSignature" hidden>恢复自动定位</button><span id="signatureHint">可先放大，再圈选落款</span></div></section>
 <section class="recognition-content"><div class="recognition-state" id="recognitionState" role="status" aria-live="polite"></div>
 <div class="recognition-roster"><span id="recognitionRosterSource">正在读取名单…</span> <button id="manageRecognitionRoster">管理 Word 名单</button></div><div id="recognitionIntro"><div class="recognition-rule"><b>01</b><div><strong>落款优先</strong><p>先辨认实际书写者，区分书写作者与诗文作者。</p></div></div><div class="recognition-rule"><b>02</b><div><strong>正文辅助</strong><p>先识读整幅，再放大落款独立复核姓名；冲突时保留候选。</p></div></div><div class="recognition-rule"><b>03</b><div><strong>由你确认</strong><p>识读不会改动图片、编号或文件名。确认后保存作品资料。</p></div></div></div>
 <div id="recognitionResults" hidden><div class="recognition-results-heading"><strong>识读结果</strong><span id="recognitionReviewBadge">待你核对</span></div><div class="recognition-fields"><label>书写作者 <span id="recognitionAuthorStatus"></span><input id="recognitionCalligrapher" maxlength="200" placeholder="尚未确定，可手动填写"></label><label>作品名称 <span id="recognitionTitleStatus"></span><input id="recognitionWorkTitle" maxlength="200" placeholder="尚未确定，可手动填写"></label><label>诗文作者<input id="recognitionTextAuthor" maxlength="200" placeholder="与书写作者分开记录"></label></div><div class="recognition-evidence"><div id="recognitionRosterMatches"></div><h3>落款原文</h3><p id="recognitionInscription"></p><h3>作者判断依据</h3><p id="recognitionAuthorEvidence"></p><h3>正文节选</h3><p id="recognitionExcerpt"></p><h3>作品判断依据</h3><p id="recognitionTitleEvidence"></p><div id="recognitionCandidates"></div><p id="recognitionNotes"></p></div></div>
 </section></div><div class="recognition-foot"><div><span id="recognitionConnection"></span><small>发送整体及落款图片，最多两次识读；名单在本机匹配，不发送给 AI。</small></div><button id="startRecognition" class="recognition-start">开始识别</button><button id="adoptRecognition" class="primary" disabled>确认并保存资料</button></div>`;
 document.body.append(dialog);
 const el=id=>document.getElementById(id);
 const viewer=new RecognitionViewer({view:el('recognitionImageView'),stage:el('recognitionImageStage'),image:el('recognitionImage'),minus:el('recognitionZoomOut'),plus:el('recognitionZoomIn'),percent:el('recognitionZoomPercent'),actual:el('recognitionActualSize'),fit:el('recognitionFit')});
 let selected=null,state=null,timer=null,serial=0,part='overview',dirty=false;
 let region=null,selecting=false,drag=null;
 const regions=new Map(),outline=document.createElement('div');outline.className='signature-outline';outline.hidden=true;el('recognitionImageStage').append(outline);
 async function refreshRoster(){try{const response=await fetch('/api/settings/authors');if(!response.ok)throw Error();const roster=await response.json();el('recognitionRosterSource').textContent=roster.authors.length?`${roster.source} · ${roster.authors.length} 位作者`:'未设置名单，可在设置中上传 Word';}catch{el('recognitionRosterSource').textContent='名单读取失败，请检查设置'}}
 el('manageRecognitionRoster').onclick=()=>{dialog.close();window.openAuthorRosterSettings?.()};
 function paintRegion(){outline.hidden=!region||part!=='overview'||!viewer.ready;if(outline.hidden)return;Object.assign(outline.style,{left:viewer.left+region[0]*viewer.width+'px',top:viewer.top+region[1]*viewer.height+'px',width:(region[2]-region[0])*viewer.width+'px',height:(region[3]-region[1])*viewer.height+'px'})}
 viewer.onRender=paintRegion;
 function selectionMode(value){selecting=value;el('recognitionImageView').classList.toggle('selecting-signature',value);el('selectSignature').classList.toggle('active',value);el('selectSignature').textContent=value?'取消圈选':region?'重新圈选':'圈选落款';el('clearSignature').hidden=!region;el('signatureHint').textContent=value?'拖动框住落款，松开完成；不会修改图片':region?'已指定落款 · 点击重新识别生效':'可先放大，再圈选落款';paintRegion()}
 el('selectSignature').onclick=()=>{if(state?.job.running)return;if(selecting){selectionMode(false);return}part='overview';showImage();selectionMode(true)};
 el('clearSignature').onclick=()=>{region=null;if(state)regions.delete(selected.id+state.signature);selectionMode(false);setStatus('已恢复自动定位，下次识别将自动查找落款。')};
 const view=el('recognitionImageView');
 function position(e){const r=viewer.image.getBoundingClientRect();return [Math.max(0,Math.min(1,(e.clientX-r.left)/r.width)),Math.max(0,Math.min(1,(e.clientY-r.top)/r.height))]}
 view.addEventListener('pointerdown',e=>{if(!selecting||!viewer.ready||e.button!==0)return;e.preventDefault();e.stopImmediatePropagation();const r=viewer.image.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)return;drag={id:e.pointerId,start:position(e),before:region};view.setPointerCapture(e.pointerId)},true);
 view.addEventListener('pointermove',e=>{if(!drag||e.pointerId!==drag.id)return;e.preventDefault();e.stopImmediatePropagation();const p=position(e),a=drag.start;region=[Math.min(a[0],p[0]),Math.min(a[1],p[1]),Math.max(a[0],p[0]),Math.max(a[1],p[1])];paintRegion()},true);
 function finishRegion(e){if(!drag||e.pointerId!==drag.id)return;e.preventDefault();e.stopImmediatePropagation();if(e.type!=='pointerup'||!region||(region[2]-region[0])*viewer.image.naturalWidth<12||(region[3]-region[1])*viewer.image.naturalHeight<12){region=drag.before}else{regions.set(selected.id+state.signature,region);setStatus('已指定落款范围，点击“开始识别”或“重新识别”读取。')}drag=null;if(view.hasPointerCapture(e.pointerId))view.releasePointerCapture(e.pointerId);selectionMode(false)}
 view.addEventListener('pointerup',finishRegion,true);view.addEventListener('pointercancel',finishRegion,true);
 view.addEventListener('dblclick',e=>{if(selecting)e.stopImmediatePropagation()},true);
 view.addEventListener('wheel',e=>{if(drag){e.preventDefault();e.stopImmediatePropagation()}}, {capture:true,passive:false});

 function setStatus(message,loading=false,error=false){const target=el('recognitionState');target.textContent=message;target.classList.toggle('loading',loading);target.classList.toggle('error',error)}
 function showImage(){if(!selected||!state)return;viewer.setSource(`/api/recognition/image/${selected.id}?signature=${encodeURIComponent(state.signature)}&part=${part}&detail=1`,part);el('recognitionParts').querySelectorAll('button').forEach(b=>b.classList.toggle('active',b.dataset.part===part))}
 function parts(){const root=el('recognitionParts');root.replaceChildren();const values=[['overview','整体'],['0','局部 1'],['1','局部 2'],['2','局部 3'],['3','局部 4']];if(state?.candidate?.result?.signature_region&&!state.stale)values.push(['signature','落款']);for(const [value,label] of values){const b=document.createElement('button');b.type='button';b.textContent=label;b.dataset.part=value;b.classList.toggle('active',value===part);b.onclick=()=>{selectionMode(false);part=value;showImage();paintRegion()};root.append(b)}}
 function fields(){return {calligrapher:el('recognitionCalligrapher').value,title:el('recognitionWorkTitle').value,text_author:el('recognitionTextAuthor').value}}
 function syncAdopt(){el('adoptRecognition').disabled=!state?.candidate||state.stale||state.job.running||!Object.values(fields()).some(x=>x.trim())}
 function draw(value){
  const previous=state?.candidate?.token,initial=!state;state=value;
  if(initial){region=regions.get(selected.id+value.signature)||(!value.stale?value.candidate?.options?.region:null)||null;selectionMode(false)}
  for(const id of ['selectSignature','clearSignature','manageRecognitionRoster'])el(id).disabled=value.job.running;
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
   const matches=el('recognitionRosterMatches');matches.replaceChildren();
   if(r.work_matches?.length){
    const h=document.createElement('h3');h.textContent='按画面正文匹配的 Word 作品 · 需核对';matches.append(h);
    for(const work of r.work_matches){
     const b=document.createElement('button');b.type='button';b.textContent=work.name+' · '+work.title;b.disabled=value.job.running;
     b.onclick=()=>{el('recognitionCalligrapher').value=work.name;el('recognitionWorkTitle').value=work.title;dirty=true;syncAdopt();el('recognitionReviewBadge').textContent='已选 Word 记录，待保存'};
     matches.append(b);
    }
   }
   if(r.catalogue_match){const p=document.createElement('p');p.textContent=(r.catalogue_match.status==='clear'?'画面与 Word 已匹配：':'画面与 Word 待核对：')+r.catalogue_match.evidence;matches.append(p)}
   const match=r.roster_match;
   if(match&&match.status!=='none'){
    const h=document.createElement('h3');h.textContent=({exact:'与本次识读名单完全匹配',review:'本次名单近似候选 · 需人工确认',unmatched:'未匹配本次名单 · 可手动填写'})[match.status];matches.append(h);
    for(const name of match.names||[]){const b=document.createElement('button');b.textContent=name;b.type='button';b.disabled=value.job.running;b.title='选择此候选，核对后再保存';b.onclick=()=>{el('recognitionCalligrapher').value=name;dirty=true;syncAdopt();el('recognitionReviewBadge').textContent='已选候选，待保存'};matches.append(b)}
   }
   el('recognitionReviewBadge').textContent=adopted?'已保存资料':'待你核对';el('recognitionReviewBadge').classList.toggle('adopted',adopted);
   const candidates=el('recognitionCandidates');candidates.replaceChildren();if(r.candidates?.length){const h=document.createElement('h3');h.textContent='存疑候选（不会自动采用）';candidates.append(h);for(const c of r.candidates){const p=document.createElement('p');p.textContent=`${{calligrapher:'书写作者',title:'作品名',text_author:'诗文作者'}[c.field]}：${c.value} · ${c.reason}`;candidates.append(p)}}
  }
  if(value.job.running)setStatus(value.job.phase==='preparing'?'正在准备整体与原图局部…':value.job.phase==='verifying'?'正在放大落款，逐字复核书写作者…':'AI 正在读落款和正文，请稍候…',true);
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
  await saveChain;await repairMarkSaveChain;selected={id:current.id,name:current.name};state=null;dirty=false;part='overview';region=null;selectionMode(false);const runSerial=++serial;clearTimeout(timer);
  el('recognitionFilename').textContent=selected.name;el('recognitionResults').hidden=true;el('recognitionIntro').hidden=false;el('adoptRecognition').disabled=true;el('startRecognition').disabled=true;viewer.reset();setStatus('正在读取当前作品…',true);dialog.showModal();
  try{await Promise.all([refresh(runSerial),refreshRoster()]);showImage()}catch(error){setStatus(error.message,false,true)}
 };
 el('closeRecognition').onclick=()=>dialog.close();dialog.addEventListener('close',()=>{++serial;clearTimeout(timer);drag=null;selectionMode(false)});dialog.addEventListener('keydown',e=>e.stopPropagation());
 for(const id of ['recognitionCalligrapher','recognitionWorkTitle','recognitionTextAuthor'])el(id).oninput=()=>{dirty=true;syncAdopt();el('recognitionReviewBadge').textContent='已编辑，待保存'};
 el('startRecognition').onclick=async()=>{
  if(!selected||state?.job.running)return;el('startRecognition').disabled=true;setStatus('正在提交识别…',true);
  try{selectionMode(false);await api('recognition/start',{id:selected.id,signature:state.signature,options:{region}});dirty=false;clearTimeout(timer);await refresh(serial)}catch(error){setStatus(error.message,false,true);el('startRecognition').disabled=false}
 };
 el('adoptRecognition').onclick=async()=>{
  el('adoptRecognition').disabled=true;
  try{const item=await api('recognition/adopt',{id:selected.id,token:state.candidate.token,signature:state.signature,fields:fields()});replace(item);dirty=false;await refresh(serial);toast('作品资料已保存，图片与原有顺序保持不变')}catch(error){setStatus(error.message,false,true);syncAdopt()}
 };
})();
