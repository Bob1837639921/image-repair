const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(__dirname+'/static/repair.js','utf8'),nodes=new Map(),states=[];
const retryCalls=[],regenerateContext=vm.createContext({repairRegenerate:{},repairBusy:false,repairDraft:'previous-draft',lastRepairMethod:'ai',resetRepairResult(){retryCalls.push('reset')},startRepairWith(method){retryCalls.push(method)}});
vm.runInContext(source.slice(source.indexOf('repairRegenerate.onclick=')),regenerateContext);
regenerateContext.repairRegenerate.onclick();assert.equal(regenerateContext.repairDraft,null);assert.deepEqual(retryCalls,['reset','ai']);
regenerateContext.repairBusy=true;regenerateContext.repairRegenerate.onclick();assert.equal(retryCalls.length,2,'must not start duplicate processing');
function $(id){if(!nodes.has(id))nodes.set(id,{value:id==='repairStrength'?'.65':'local'});return nodes.get(id)}
let resolveRequest,rejectRequest,leftLoads=0;
const context=vm.createContext({$,current:{id:'sample',revision:3},workStage:'repair',repairBusy:false,repairDraft:null,repairSelection:[.2,.3,.4,.5],repairResultSerial:0,repairResultImage:null,repairResultRegion:null,repairResultFull:false,toast(){},setRepairResultState:s=>states.push(s),paintRepairResult(){},showRepairImage(){leftLoads++},api:()=>new Promise((resolve,reject)=>{resolveRequest=resolve;rejectRequest=reject}),decodedImage:async()=>({naturalWidth:500,naturalHeight:1000})});
vm.runInContext(source.slice(source.indexOf("$('repairPreview').onclick=async"),source.indexOf('async function repairAction')),context);
let typePrompts=0;const bodies=[],baseApi=context.api;
Object.assign(context,{repairSelectionKind:null,repairMarks:[],repairMarkSaveChain:Promise.resolve(),repairKindPicker:{hidden:true},showRepairKindPicker(){typePrompts++},api:(path,body)=>{bodies.push(body);return baseApi()}});
(async()=>{
 await $('repairPreview').onclick();assert.equal(typePrompts,1);assert.equal(bodies.length,0,'unclassified regions must not silently use crease');
 context.repairSelectionKind='crease';
 context.repairMarks=[{id:'one',region:[.2,.3,.4,.5],kind:'crease'}];
 const pending=$('repairPreview').onclick();assert.deepEqual(states,['loading']);assert.equal($('repairPreview').disabled,true);
 await new Promise(resolve=>setImmediate(resolve));assert.equal(bodies.at(-1).regions[0].kind,'crease');
 resolveRequest({draft:'candidate'});await pending;assert.deepEqual(states,['loading','ready']);assert.equal(leftLoads,0);assert.equal(context.repairDraft,'candidate');assert.equal($('repairPreview').disabled,true);
 context.repairDraft=null;context.repairSelectionKind='bump';context.repairMarks[0].kind='bump';const failed=$('repairPreview').onclick();await new Promise(resolve=>setImmediate(resolve));assert.equal(bodies.at(-1).regions[0].kind,'bump');rejectRequest(new Error('test failure'));await failed;assert.equal(states.at(-1),'error');assert.equal($('repairPreview').disabled,false);assert.equal(context.repairDraft,null);
 const stale=$('repairPreview').onclick();await new Promise(resolve=>setImmediate(resolve));context.current={id:'different'};resolveRequest({draft:'stale'});await stale;assert.equal(context.repairDraft,null);
 console.log('PASS: immediate loading card, separate result, unchanged left image, retry and stale response guard');
})().catch(e=>{console.error(e);process.exitCode=1});
