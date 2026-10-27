const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(__dirname+'/static/repair.js','utf8');
const nodes=new Map(),groups=[];let saves=0;
function node(){const classes=new Set();return {dataset:{},style:{},children:[],hidden:false,textContent:'',getBoundingClientRect(){return {left:0,top:0,right:600,bottom:500,width:160,height:40}},classList:{toggle(k,on){on?classes.add(k):classes.delete(k)},contains:k=>classes.has(k)},setAttribute(k,v){this[k]=v},append(...items){this.children.push(...items)},replaceChildren(){this.children=[]},querySelectorAll(){return this.children.filter(c=>c.dataset.level)}}}
const panel=node();nodes.set('repairMarkLevel',panel);
const marks=[{id:'a',kind:'crease',region:[.1,.1,.4,.3]},{id:'b',kind:'bump',region:[.5,.6,.9,.8]}];
const layer=node();
const c=vm.createContext({$:id=>{if(!nodes.has(id))nodes.set(id,node());return nodes.get(id)},repairLevelEditorId:null,repairMarkLayer:layer,document:{createElement(){return node()},querySelectorAll(){return groups}},repairLevelChoices:new Map(),repairMarks:marks,repairActiveMark:'a',repairDraft:null,repairBusy:false,repairReadOnly:false,repairResultRegions:[],repairCompareGroups:[],saveRepairMarks(){saves++}});
vm.runInContext(source.slice(source.indexOf('function makeRepairLevelControl('),source.indexOf('function showRepairContextMenu(')),c);
vm.runInContext(source.slice(source.indexOf('function paintRepairMarks('),source.indexOf('function selectRepairMark(')),c);
c.paintRepairMarks();assert.equal(panel.hidden,true,'no duplicate strength panel in the sidebar');
assert.ok(layer.children[0].children[0].textContent.includes('标准'),'default strength visible in marker badge');
assert.equal(layer.children[0].children.length,1,'selected marker never opens controls over the image');
assert.equal(layer.children[1].children.length,1,'unselected marker only shows label');
let row=nodes.get('repairMarksList').children[0];
assert.equal(row.children[0].textContent,'1 · 折痕','short location label');
assert.equal(row.children[1].textContent,'标准','separate grade button');
row.children[1].onclick();row=nodes.get('repairMarksList').children[0];
assert.equal(row.children[3].className,'repair-mark-grade-editor','grade button opens choices only in sidebar');
const group=c.makeRepairLevelControl(marks[0]);groups.push(group);
assert.deepEqual(group.children.map(b=>b.textContent),['轻度','标准','加强']);
assert.equal(group.children[1]['aria-pressed'],'true','standard is selected by default');
group.children[2].onclick({stopPropagation(){}});assert.equal(marks[0].level,'strong');assert.equal(marks[1].level,undefined);assert.equal(saves,1);
assert.equal(group.children[2]['aria-pressed'],'true');
c.repairDraft='draft';c.repairResultRegions=[{...marks[0]}];
group.children[0].onclick({stopPropagation(){}});assert.equal(c.repairLevelChoices.get('a'),'light');assert.equal(marks[0].level,'strong');assert.equal(saves,1,'pending choices must not invalidate the candidate');
assert.ok(nodes.get('repairMarksList').children[0].children[1].classList.contains('pending'));
group.children[2].onclick({stopPropagation(){}});assert.equal(c.repairLevelChoices.size,0,'returning to candidate level clears pending change');
c.repairBusy=true;group.children[0].onclick({stopPropagation(){}});assert.equal(c.repairLevelChoices.size,0);
c.repairBusy=false;c.repairReadOnly=true;group.children[0].onclick({stopPropagation(){}});assert.equal(c.repairLevelChoices.size,0);
c.repairActiveMark=null;c.syncRepairLevelControls();assert.equal(panel.hidden,true);
// Selecting a location at high zoom pans to its centre without changing zoom.
const view={scrollWidth:2000,scrollHeight:3000,clientWidth:500,clientHeight:500,scrollLeft:0,scrollTop:0,getBoundingClientRect:()=>({left:0,top:0,right:500,bottom:500})};
const focusNodes={repairViewport:view,repairWrap:{getBoundingClientRect:()=>({left:0,top:0,width:2000,height:3000})},repairKind:{}};
const f=vm.createContext({$:id=>focusNodes[id],repairMarks:marks,repairBusy:false,repairDraft:null,repairLevelEditorId:'a',repairCompareGroups:[],paintRepairSelection(){},paintRepairMarks(){}});
vm.runInContext(source.slice(source.indexOf('function focusRepairRegion('),source.indexOf('async function acceptRepairRegion(')),f);
vm.runInContext(source.slice(source.indexOf('function selectRepairMark('),source.indexOf('function loadRepairMarks(')),f);
f.selectRepairMark('b');assert.equal(f.repairActiveMark,'b');assert.equal(f.repairLevelEditorId,null);
assert.equal(view.scrollLeft,1150);assert.equal(view.scrollTop,1850);
view.scrollWidth=500;view.scrollHeight=500;view.scrollLeft=0;view.scrollTop=0;f.selectRepairMark('a');assert.equal(view.scrollLeft,0);assert.equal(view.scrollTop,0);
console.log('PASS: compact location/grade buttons; no image popup; explicit sidebar grade editor; default standard; independent grades; zoomed location centring');
// First-use prompt must fit entirely outside the selected content.
const viewport={left:0,top:0,right:800,bottom:600},popup={width:180,height:70};
for(const region of [{left:100,top:100,right:250,bottom:200},{left:580,top:100,right:780,bottom:260},{left:0,top:20,right:800,bottom:400},{left:0,top:200,right:800,bottom:600}]){
 const place=c.repairLevelPlacement(region,viewport,popup);assert.ok(place);
 assert.ok(place.left>=8&&place.top>=8&&place.left+popup.width<=792&&place.top+popup.height<=592);
 assert.ok(!(place.left<region.right&&place.left+popup.width>region.left&&place.top<region.bottom&&place.top+popup.height>region.top),'prompt never covers selected content');
}
assert.equal(c.repairLevelPlacement(viewport,viewport,popup),null,'no space means use sidebar instead');
console.log('PASS: first-use strength prompt selects a non-overlapping side or falls back when no space');
