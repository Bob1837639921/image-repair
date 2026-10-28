const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const nodes=new Map(),calls=[],messages=[];
function node(){return {children:[],hidden:false,disabled:false,open:false,classList:{add(){},remove(){},toggle(){}},append(...items){this.children.push(...items);for(const item of items)if(item?.id)nodes.set(item.id,item)},before(item){nodes.set(item.id,item)},after(item){nodes.set(item.id,item)},setAttribute(){},replaceChildren(){this.children=[]},replaceWith(item){nodes.set(this.id,item)},addEventListener(){},showModal(){this.open=true},close(){this.open=false},querySelectorAll(){return [node(),node()]},getContext(){return {drawImage(){}}}}}
const $=id=>{if(!nodes.has(id)){const n=node();n.id=id;nodes.set(id,n)}return nodes.get(id)};
const history={id:'one',revision:5,current:2,steps:[{step:0,label:'原裁剪图',regions:[]},{step:1,label:'第 1 步',regions:[{id:'a',kind:'crease',level:'light',region:[.2,.2,.3,.4]}],methods:{a:'local'}},{step:2,label:'第 2 步',regions:[{id:'b',kind:'blemish',level:'strong',region:[.4,.6,.5,.7]}],methods:{b:'ai'}}]};
let replaced=null,selected=null,resets=0;
const c=vm.createContext({$,document:{createElement:node,body:{append(item){nodes.set(item.id,item)}}},current:{id:'one',confirmed:true},repairBusy:false,repairDraft:null,repairMarkSaveChain:Promise.resolve(),fetch:async url=>({ok:true,json:async()=>history}),decodedImage:async url=>{calls.push(url);return {naturalWidth:1000,naturalHeight:2000}},api:async(path,body)=>{calls.push({path,body});return {id:'one'}},replace:item=>replaced=item,resetRepairResult:()=>resets++,selectRepair:async id=>selected=id,toast:message=>messages.push(message)});
vm.runInContext(fs.readFileSync(__dirname+'/static/repair-history.js','utf8'),c);
(async()=>{
 await $('openRepairHistory').onclick();assert.equal($('repairHistoryDialog').open,true);assert.equal($('repairHistoryList').children.length,3);assert.equal($('restoreRepairHistory').disabled,true);
 assert.ok(calls.some(url=>typeof url==='string'&&url.includes('step=1&revision=5')));
 assert.ok($('repairHistorySummary').children[1].textContent.includes('AI 修复'));
 const count=calls.length;await $('repairHistoryList').children[1].onclick();assert.equal($('restoreRepairHistory').disabled,false);assert.equal(calls.length,count+2,'selecting a step only loads images');
 assert.equal(resets,0);assert.equal(replaced,null);assert.ok($('repairHistorySummary').children[1].textContent.includes('轻度'));
 c.repairDraft='pending';await $('repairHistoryList').children[0].onclick();assert.equal($('restoreRepairHistory').disabled,true);await $('restoreRepairHistory').onclick();assert.equal(replaced,null,'pending preview blocks restoration');
 c.repairDraft=null;await $('repairHistoryList').children[1].onclick();await $('restoreRepairHistory').onclick();
 assert.equal(replaced.id,'one');assert.equal(selected,'one');assert.equal(resets,1);assert.equal(c.repairBusy,false);assert.equal($('repairHistoryDialog').open,false);
 const request=calls.find(x=>x.path);assert.equal(request.path,'repair/restore');assert.equal(request.body.step,1);assert.equal(request.body.revision,5);
 assert.equal($('closeRepairHistory').disabled,false);
 c.window={confirm:()=>false};await $('openRepairHistory').onclick();
 assert.equal($('deleteRepairHistory').disabled,false,'current repair step can be deleted');
 let countBefore=calls.filter(x=>x.path==='repair/delete-step').length;
 await $('deleteRepairHistory').onclick();assert.equal(calls.filter(x=>x.path==='repair/delete-step').length,countBefore,'cancel does not alter history');
 c.window.confirm=()=>true;await $('deleteRepairHistory').onclick();
 const deletion=calls.find(x=>x.path==='repair/delete-step');assert.equal(deletion.body.step,2);assert.equal(deletion.body.revision,5);
 await $('repairHistoryList').children[0].onclick();assert.equal($('deleteRepairHistory').disabled,true,'original crop cannot be deleted');
 console.log('PASS: history selection loads aligned comparisons without edits; pending preview guard; explicit versioned restoration and current-image reload');
})().catch(error=>{console.error(error);process.exitCode=1});
