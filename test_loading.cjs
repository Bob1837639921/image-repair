const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(__dirname+'/static/app.js','utf8');
const nodes=new Map(),pending=[];
function element(id){const e={id,style:{},classList:{add(){},remove(){}},setAttribute(){},querySelector(){return get('viewport')},replaceWith(other){nodes.set(this.id,other)}};return e}
function get(id){if(!nodes.has(id))nodes.set(id,element(id));return nodes.get(id)}
class TestImage{constructor(){Object.assign(this,element(''));}decode(){return new Promise((resolve,reject)=>pending.push({image:this,resolve,reject}))}}
const records=['A','B','C','D'].map(id=>({id,name:id,auto_result:{},rotation:0,width:100,height:200,settings:{brightness:1,contrast:1,sharpness:1}}));
const ctx=vm.createContext({Image:TestImage,$:get,current:null,items:records,history:[],saveChain:Promise.resolve(),compare:false,previewSerial:0,drawStatus(){},drawList(){},drawCandidates(){},fit(){},fitResult(){},toast(){}});
vm.runInContext(source.slice(source.indexOf('let selectionSerial='),source.indexOf('const clone=')),ctx);
vm.runInContext(source.slice(source.indexOf('async function select('),source.indexOf('function fit(){')),ctx);
vm.runInContext(source.slice(source.indexOf('async function preview('),source.indexOf('function drawCandidates(')),ctx);
ctx.prefetchNeighbors=()=>{};
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const timeout=setTimeout(()=>{console.error('FAIL: load test left unresolved');process.exit(1)},3000);
(async()=>{
 const first=ctx.select('A');await tick();assert.equal(get('imageWrap').style.visibility,'hidden');
 const second=ctx.select('B');await tick();assert.equal(get('imageWrap').style.visibility,'hidden');
 pending[1].resolve();await second;assert.match(get('original').src,/\/B\?/);assert.equal(get('imageWrap').style.visibility,'visible');
 pending[0].resolve();await first;assert.match(get('original').src,/\/B\?/,'late A must not replace B');
 const oldPreview=ctx.preview();await tick();const third=ctx.select('C');await tick();
 pending[2].resolve();await oldPreview;assert.equal(get('result').style.visibility,'hidden','old result must stay hidden');
 pending[3].resolve();await third;assert.match(get('original').src,/\/C\?/);
 const failed=ctx.select('D');await tick();pending[4].reject(Error('load failed'));await failed;
 assert.equal(get('imageWrap').style.visibility,'hidden','never reveal old image on failure');
 assert.match(get('original').src,/\/C\?/);
 const count=pending.length;await ctx.select('B');assert.equal(pending.length,count,'decoded neighbor must be reused');
 clearTimeout(timeout);
 console.log('PASS: atomic image/quad display, out-of-order selection, stale preview, failed load');
})().catch(e=>{clearTimeout(timeout);console.error(e);process.exitCode=1});
