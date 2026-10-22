const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(__dirname+'/static/app.js','utf8');
function fixture(){
 const nodes=new Map(),requests=[],messages=[];
 const $=id=>{if(!nodes.has(id))nodes.set(id,{hidden:true,disabled:false,setAttribute(k,v){this[k]=v}});return nodes.get(id)};
 const ctx=vm.createContext({$,items:[{id:'a',name:'first.jpg'},{id:'skip',confirmed:true,name:'confirmed.jpg'},{id:'b',name:'second.jpg'}],current:null,busy:false,saveChain:Promise.resolve(),api:(path,body)=>new Promise((resolve,reject)=>requests.push({path,body,resolve,reject})),replace(){},toast:m=>messages.push(m)});
 const regions=[{inert:false},{inert:false}],listeners=new Map();
 ctx.document={querySelectorAll:()=>regions};
 ctx.window={addEventListener:(type,handler)=>listeners.set(type,handler),removeEventListener:type=>listeners.delete(type)};
 vm.runInContext(source.slice(source.indexOf('function lockCropWorkspace('),source.indexOf('const restoreFull=')),ctx);
 return {ctx,$,requests,messages,regions,listeners};
}
const tick=()=>new Promise(r=>setImmediate(r));
(async()=>{
 const f=fixture(),running=f.$('batchDetect').onclick();
 assert.equal(f.$('cropProgress').hidden,false);assert.equal(f.$('cropProgress')['aria-busy'],'true');
 assert.ok(f.regions.every(region=>region.inert));assert.equal(f.$('cropBackdrop').hidden,false);
 let prevented=false,stopped=false;
 f.listeners.get('keydown')({preventDefault(){prevented=true},stopImmediatePropagation(){stopped=true}});
 assert.ok(prevented&&stopped,'block document keyboard shortcuts during batch processing');
 assert.equal(f.$('cropMeter').value,0);assert.equal(f.$('cropMeter').max,2);assert.match(f.$('cropStatus').textContent,/第 1 张/);
 await tick();assert.equal(f.requests[0].body.id,'a');
 await f.$('batchDetect').onclick();assert.equal(f.requests.length,1);
 f.requests[0].resolve({id:'a'});await tick();
 assert.equal(f.$('cropMeter').value,1);assert.equal(f.$('cropFilename').textContent,'second.jpg');assert.match(f.$('cropStatus').textContent,/第 2 张/);
 assert.equal(f.requests[1].body.id,'b');f.requests[1].resolve({id:'b'});await running;
 assert.equal(f.$('cropMeter').value,2);assert.match(f.$('cropStatus').textContent,/裁剪完成/);assert.equal(f.$('cropSpinner').hidden,true);assert.equal(f.$('cropProgress')['aria-busy'],'false');assert.equal(f.ctx.busy,false);
 assert.ok(f.regions.every(region=>!region.inert));assert.equal(f.$('cropBackdrop').hidden,true);assert.equal(f.listeners.size,0);
 assert.equal(f.$('cropProgress').hidden,true,'dismiss progress when complete');assert.match(f.messages.at(-1),/已完成 2 张裁剪/);
 const bad=fixture(),failed=bad.$('batchDetect').onclick();await tick();bad.requests[0].reject(Error('connection failed'));await failed;
 assert.match(bad.$('cropStatus').textContent,/中断.*0 \/ 2/);assert.equal(bad.$('cropFilename').textContent,'first.jpg');assert.match(bad.$('cropDetail').textContent,/connection failed/);assert.equal(bad.$('detect').disabled,false);
 assert.ok(bad.regions.every(region=>!region.inert));assert.equal(bad.$('cropBackdrop').hidden,true);assert.equal(bad.listeners.size,0);
 assert.equal(bad.$('cropProgress').hidden,true,'dismiss progress on failure');assert.match(bad.messages.at(-1),/已完成 0 \/ 2 张.*connection failed/);
 console.log('PASS: immediate batch spinner, current filename/index, completed count, duplicate prevention, confirmed skip, completion and failure cleanup');
})().catch(e=>{console.error(e);process.exitCode=1});
