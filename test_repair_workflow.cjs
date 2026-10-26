const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(__dirname+'/static/repair.js','utf8'),nodes=new Map(),loads=[];
const classes=()=>({values:new Map(),toggle(name,value){this.values.set(name,value)}});
const sourceGroup={hidden:true};
function $(id){if(!nodes.has(id))nodes.set(id,{parentElement:sourceGroup,classList:classes(),setAttribute(name,value){this[name]=value}});return nodes.get(id)}
const c=vm.createContext({$,repairBusy:false,repairReadOnly:false,repairDraft:'preview',repairKindPicker:{hidden:false},repairCanvasPane:{classList:classes()},current:{repair_state:{layers:['first.png']}},closeRepairContextMenu(){},showRepairImage:async()=>loads.push(c.repairReadOnly),toast(){throw Error('Unexpected error')}});
c.repairSourceBar={hidden:true};c.repairSelection=null;
vm.runInContext(source.slice(source.indexOf('async function switchRepairSource('),source.indexOf("$('repairWorkView').onclick=")),c);
(async()=>{
 await c.switchRepairSource(true);assert.deepEqual(loads,[true]);assert.equal(c.repairReadOnly,true);assert.equal($('repairOriginalView')['aria-pressed'],'true');assert.match($('repairWorkStatus').textContent,/只读/);assert.equal(c.repairDraft,'preview');
 await c.switchRepairSource(false);assert.deepEqual(loads,[true,false]);assert.equal($('repairWorkStatus').hidden,true);assert.equal($('repairWorkStatus').textContent,'');assert.equal(c.repairCanvasPane.classList.values.get('readonly'),false);assert.equal(c.repairKindPicker.hidden,true);
 c.repairBusy=true;await c.switchRepairSource(true);assert.deepEqual(loads,[true,false]);
 assert.equal(sourceGroup.hidden,false,'adopted changes expose version comparison');
 c.current={repair_state:{layers:[]}};c.repairReadOnly=true;c.syncRepairWorkflow();
 assert.equal(sourceGroup.hidden,true,'no adopted changes means no redundant version toggle');assert.equal(c.repairReadOnly,false,'undoing all repairs must not leave the editor read-only');
 assert.equal(c.repairSourceBar.hidden,true,'empty header must not reserve height');assert.equal($('repairState').hidden,true);assert.equal($('repairRegionText').hidden,true);
 console.log('PASS: source toggle preserves pending preview; original is read-only; work status reports adopted changes; busy prevents conflicting loads');
})().catch(e=>{console.error(e);process.exitCode=1});
