const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(__dirname+'/static/repair.js','utf8'),nodes=new Map(),draws=[];
function node(tag='div'){
 const classes=new Set();
 const n={tag,style:{},dataset:{},children:[],hidden:false,clientWidth:300,clientHeight:250,scrollLeft:0,scrollTop:0,
  classList:{toggle(name,on){on?classes.add(name):classes.delete(name)},contains:name=>classes.has(name)},
  append(...items){items.forEach(x=>{x.parent=n;n.children.push(x)})},replaceChildren(){n.children=[]},setAttribute(){},addEventListener(){},
  querySelector(selector){return n.children.find(x=>x.tag===selector)},getContext:()=>({drawImage:(...args)=>draws.push({n,args})}),
  getBoundingClientRect(){return tag==='canvas'?{left:8-n.parent.scrollLeft,top:8-n.parent.scrollTop,width:parseFloat(n.style.width),height:parseFloat(n.style.height)}:{left:0,top:0}}
 };return n;
}
function $(id){if(!nodes.has(id))nodes.set(id,node());return nodes.get(id)}
const marks=[{id:'a',kind:'crease',region:[.2,.1,.4,.15]},{id:'b',kind:'bump',region:[.6,.45,.7,.5]},{id:'c',kind:'crease',region:[.2,.8,.5,.9]}];
const context=vm.createContext({$,document:{createElement:node},repairBusy:false,repairResultImage:{naturalWidth:500,naturalHeight:1000},repairResultBeforeImage:{naturalWidth:500,naturalHeight:1000},repairResultRegion:[.2,.1,.7,.9],repairResultRegions:marks,repairResultFull:false,repairCompareGroups:[],repairCompareActive:0});
context.repairLevelChoices=new Map();
vm.runInContext(source.slice(source.indexOf('function makeRepairLevelControl('),source.indexOf('function showRepairContextMenu(')),context);
vm.runInContext(source.slice(source.indexOf('function paintRepairResult'),source.indexOf('new ResizeObserver(fitRepairCompare)')),context);
context.paintRepairResult();assert.equal(context.repairCompareGroups.length,3);assert.equal($('repairCompare').children.length,3);assert.equal(draws.length,6);
for(let i=0;i<3;i++){
 const g=context.repairCompareGroups[i];assert.deepEqual(draws[i*2].args.slice(1),draws[i*2+1].args.slice(1));
 assert.equal(g.canvases[0].style.width,g.canvases[1].style.width);assert.ok(g.canvases[0].height<200,'detail must not use union rectangle');
 assert.ok(g.card.children[0].textContent.startsWith((i+1)+' · '));
}
assert.equal(context.repairCompareGroups[1].card.children[0].textContent,'2 · 凸起');
const accepted=[];context.acceptRepairRegion=id=>accepted.push(id);
const regionActions=context.repairCompareGroups[1].card.children[0].children[0];
assert.equal(regionActions.children.length,4);
regionActions.children[0].onclick({stopPropagation(){}});
assert.deepEqual(accepted,['b'],'per-card button must submit its own region id');
const firstWidth=context.repairCompareGroups[0].canvases[0].style.width;
context.activateRepairCompare(1);context.zoomRepairCompare(4);
assert.equal(context.repairCompareGroups[1].scale,'fit','detail zoom disabled');assert.equal($('repairCompareTools').hidden,true);
assert.equal(context.repairCompareGroups[0].canvases[0].style.width,firstWidth);
context.repairResultFull=true;context.paintRepairResult();context.zoomRepairCompare(4);
const group=context.repairCompareGroups[0];assert.equal(parseFloat(group.canvases[0].style.width),group.canvases[0].width*4);assert.equal($('repairCompareTools').hidden,false);
const view=group.views[1],canvas=group.canvases[1],before=canvas.getBoundingClientRect(),pixel=[(120-before.left)/before.width,(150-before.top)/before.height];
context.zoomRepairCompare(8,view,[120,150]);const after=canvas.getBoundingClientRect();
assert.ok(Math.abs(after.left+pixel[0]*after.width-120)<1e-7);assert.ok(Math.abs(after.top+pixel[1]*after.height-150)<1e-7);
assert.equal(group.views[0].scrollLeft,view.scrollLeft);assert.equal(group.views[0].scrollTop,view.scrollTop);
context.repairResultFull=true;context.paintRepairResult();assert.equal(context.repairCompareGroups.length,1);assert.equal(context.repairCompareGroups[0].canvases[0].width,500);assert.equal(context.repairCompareGroups[0].canvases[0].height,1000);
assert.equal($('repairCompareTitle').textContent,'完整作品对比');assert.equal(context.repairCompareGroups[0].card.children.length,1,'full view must not have a redundant inner title bar');assert.ok(context.repairCompareGroups[0].card.classList.contains('full-work'));
context.repairResultFull=false;context.paintRepairResult();assert.equal(context.repairCompareGroups.length,3);
assert.equal($('repairCompareTitle').textContent,'修复前后对比');assert.equal(context.repairCompareGroups[0].card.children.length,2,'detail keeps numbered actions');
context.repairResultRegions=[marks[0]];context.paintRepairResult();assert.equal(context.repairCompareGroups.length,1);assert.equal($('repairCompare').classList.contains('multiple'),false);
console.log('PASS: numbered detail pairs auto-fit with zoom disabled; full view retains anchored zoom/synchronized pan; full/detail toggle and single-region fallback');
