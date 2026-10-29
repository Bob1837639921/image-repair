// Native-window behavior is installed only inside the desktop host.
(()=>{
 let initialized=false;
 function init(){
  if(initialized||!window.pywebview?.api?.get_settings)return;initialized=true;
  const api=window.pywebview.api;
  const closeDialog=document.createElement('dialog');closeDialog.className='desktop-close-dialog';
  closeDialog.innerHTML='<div class="desktop-close-top"><img src="/app-icon.svg" alt=""><button aria-label="取消关闭" class="desktop-close-cancel">×</button></div><h2>关闭画心时，你希望…</h2><p>最小化后仍会在后台运行，双击任务栏右下角的画心图标即可恢复。</p><label class="desktop-remember"><input type="checkbox" id="desktopRememberClose">记住我的选择，下次不再询问</label><div class="desktop-close-actions"><button id="desktopExit">退出程序</button><button id="desktopHide" class="primary">最小化到托盘</button></div><small>之后可在“设置 → 桌面行为”中修改。</small>';
  document.body.append(closeDialog);
  const cancel=()=>closeDialog.close();closeDialog.querySelector('.desktop-close-cancel').onclick=cancel;
  let applying=false;
  window.requestDesktopClose=async(action,remember=false)=>{
   if(applying)return;applying=true;
   const buttons=closeDialog.querySelectorAll('button');buttons.forEach(b=>b.disabled=true);
   try{
    // Flush edits before the host decides whether it is safe to exit.
    if(typeof saveChain!=='undefined')await saveChain;
    if(typeof repairMarkSaveChain!=='undefined')await repairMarkSaveChain;
    const result=await api.resolve_close(action,remember);
    if(result.ok)closeDialog.close();
   }catch(error){if(typeof toast==='function')toast('暂时无法关闭：'+error.message)}
   finally{applying=false;buttons.forEach(b=>b.disabled=false)}
  };
  closeDialog.querySelector('#desktopExit').onclick=()=>window.requestDesktopClose('exit',document.getElementById('desktopRememberClose').checked);
  closeDialog.querySelector('#desktopHide').onclick=()=>window.requestDesktopClose('tray',document.getElementById('desktopRememberClose').checked);
  window.showDesktopCloseDialog=()=>{if(!closeDialog.open)closeDialog.showModal()};
  const settings=document.getElementById('aiConfigDialog'),tabs=settings.querySelector('.settings-tabs'),content=settings.querySelector('.settings-content');
  const tab=document.createElement('button');tab.id='desktopSettingsTab';tab.textContent='桌面行为';tab.setAttribute('aria-pressed','false');tabs.append(tab);
  const panel=document.createElement('section');panel.hidden=true;panel.innerHTML='<div class="settings-eyebrow">DESKTOP</div><h3>桌面行为</h3><p class="settings-description">设置点击窗口右上角关闭按钮时的行为。</p><label class="storage-label" for="desktopCloseAction">关闭主窗口时</label><select id="desktopCloseAction"><option value="ask">每次询问</option><option value="tray">最小化到系统托盘</option><option value="exit">直接退出程序</option></select><p class="settings-description">最小化后可通过托盘图标恢复窗口；右键托盘图标可退出程序。</p><p class="settings-status" id="desktopSettingsStatus" role="status"></p>';
  content.append(panel);
  const select=panel.querySelector('select'),status=panel.querySelector('#desktopSettingsStatus');
  const refresh=async()=>{try{select.value=(await api.get_settings()).close_action}catch(error){status.textContent=error.message}};
  tab.onclick=()=>{
   if(settings.dataset.migrating==='true')return;
   [...content.children].forEach(p=>p.hidden=p!==panel);
   [...tabs.children].forEach(b=>{b.classList.toggle('active',b===tab);b.setAttribute('aria-pressed',String(b===tab))});refresh();
  };
  [...tabs.children].filter(b=>b!==tab).forEach(b=>b.addEventListener('click',()=>{panel.hidden=true;tab.classList.remove('active');tab.setAttribute('aria-pressed','false')}));
  select.onchange=async()=>{select.disabled=true;try{const result=await api.set_close_action(select.value);select.value=result.close_action;status.textContent='已保存，下次关闭窗口时生效。'}catch(error){status.textContent=error.message;await refresh()}finally{select.disabled=false}};
 }
 window.addEventListener('pywebviewready',init);init();
})();
