const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(__dirname+'/static/repair.js','utf8'),nodes=new Map();
function element(){const classes=new Set();return {children:[],textContent:'',attributes:{},classList:{add:k=>classes.add(k),remove:k=>classes.delete(k),contains:k=>classes.has(k)},setAttribute(k,v){this.attributes[k]=v},append(...items){for(const item of items){item.parent=this;this.children.push(item)}},remove(){if(this.parent)this.parent.children=this.parent.children.filter(x=>x!==this)},querySelectorAll(){return this.buttons||[]}}}
const $=id=>{if(!nodes.has(id))nodes.set(id,element());return nodes.get(id)};
const button=element();button.textContent='重新修复';const card=element();card.buttons=[button];const other=element();
let resolve,reject,paints=0;const messages=[];
const c=vm.createContext({$,document:{createElement:element},repairBusy:false,repairDraft:'old-preview',current:{id:'one',confirmed:true,revision:1},repairLevelChoices:new Map(),repairResultMethods:{mark:'ai'},repairCompareGroups:[{markId:'mark',card},{markId:'other',card:other}],repairResult:{querySelectorAll:()=>[button]},repairMarkSaveChain:Promise.resolve(),repairMarkSignature:'signature',api:()=>new Promise((yes,no)=>{resolve=yes;reject=no}),toast:message=>messages.push(message),syncRepairWorkflow(){},replace(item){c.current=item},loadRepairMarks(){},paintRepairSelection(){},showRepairImage:async()=>{},decodedImage:async()=>({}),repairResultSerial:0,paintRepairResult(){paints++},setRepairResultState(){},resetRepairResult(){}});
vm.runInContext(source.slice(source.indexOf('async function acceptRepairRegion('),source.indexOf('function syncRepairCompare(')),c);
(async()=>{
 $('repairResultStatus').textContent='待确认 2 处';
 const failed=c.acceptRepairRegion('mark','retry-region');
 assert.equal(card.attributes['aria-busy'],'true');assert.equal(card.children.length,1);assert.equal(other.children.length,0);
 assert.equal(button.textContent,'修复中…');assert.equal(button.disabled,true);assert.ok($('repairResultStatus').textContent.includes('AI 正在重新修复'));
 assert.equal(card.children[0].children[0].children[0].className,'repair-spinner');
 await new Promise(setImmediate);reject(Error('network failed'));await failed;
 assert.equal(card.children.length,0);assert.equal(card.attributes['aria-busy'],'false');assert.equal(button.disabled,false);assert.equal(button.textContent,'重新修复');assert.equal(c.repairDraft,'old-preview');assert.equal($('repairResultStatus').textContent,'待确认 2 处');assert.equal(paints,0,'failure preserves original comparison');
 const success=c.acceptRepairRegion('mark','retry-region');await new Promise(setImmediate);
 resolve({item:{id:'one',confirmed:true,revision:2,repair_state:{layers:[]}},draft:'new-preview',regions:[{id:'mark'}],methods:{mark:'ai'}});await success;
 assert.equal(c.repairDraft,'new-preview');assert.equal(paints,1);assert.equal(card.children.length,0);assert.equal(c.repairBusy,false);assert.equal(button.disabled,false);
 console.log('PASS: immediate per-region spinner, AI progress message and old image retained; failure cleanup; success replacement; other cards untouched');
})().catch(error=>{console.error(error);process.exitCode=1});
