const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(__dirname+'/static/app.js','utf8');
const nodes=new Map(),requests=[],messages=[];
function get(id){if(!nodes.has(id))nodes.set(id,{hidden:true,disabled:false,setAttribute(key,value){this[key]=value}});return nodes.get(id)}
const ctx=vm.createContext({$:get,busy:false,current:null,window:{APP_TOKEN:'test'},toast:message=>messages.push(message),replace(){},async select(id){ctx.current={id}},fetch:()=>new Promise(resolve=>requests.push(resolve))});
vm.runInContext(source.slice(source.indexOf('function drawImportProgress('),source.indexOf("for(const id of ['importTop'")),ctx);
const tick=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
 const importing=ctx.importFiles([{name:'first.png'},{name:'ignore.txt'},{name:'second.jpg'}]);
 assert.equal(get('importProgress').hidden,false,'show progress before the first request returns');
 assert.equal(get('importTop').disabled,true);
 assert.equal(get('importMeter').max,2);assert.equal(get('importMeter').value,0);
 await ctx.importFiles([{name:'duplicate.png'}]);assert.equal(requests.length,1,'prevent duplicate imports');
 requests[0]({ok:true,json:async()=>({id:'first',candidates:[{}]})});await tick();
 assert.equal(get('importMeter').value,1);assert.equal(get('importFilename').textContent,'second.jpg');
 assert.equal(get('importProgress').hidden,false,'keep the loading indicator while the next image is pending');
 requests[1]({ok:false,json:async()=>({error:'test failure'})});await importing;
 assert.match(get('hint').textContent,/导入 1 张.*失败 1 张/);
 assert.match(get('hint').textContent,/已保留完整原图/);
 assert.doesNotMatch(get('hint').textContent,/已完成自动裁剪|已自动执行/);
 assert.equal(ctx.busy,false);assert.equal(get('importProgress').hidden,true);assert.equal(get('importTop').disabled,false);
 await ctx.importFiles([{name:'unsupported.txt'}]);assert.equal(requests.length,2);assert.equal(ctx.busy,false);
 console.log('PASS: immediate import progress, per-file updates, duplicate prevention, failure cleanup, unsupported files');
})().catch(error=>{console.error(error);process.exitCode=1});
