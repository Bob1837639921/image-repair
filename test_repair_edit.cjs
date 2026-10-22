const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(__dirname+'/static/repair.js','utf8');
const nodes=new Map(),listeners=new Map();let captured=false,saves=0,pickers=0;
const rect={left:0,top:0,right:1000,bottom:1000,width:1000,height:1000};
const view={style:{},scrollLeft:0,scrollTop:0,addEventListener(name,fn){if(!listeners.has(name))listeners.set(name,new Set());listeners.get(name).add(fn)},removeEventListener(name,fn){listeners.get(name)?.delete(fn)},setPointerCapture(){captured=true},hasPointerCapture(){return captured},releasePointerCapture(){captured=false}};
function $(id){if(id==='repairViewport')return view;if(!nodes.has(id))nodes.set(id,{hidden:true,style:{},getBoundingClientRect:()=>rect});return nodes.get(id)}
const c=vm.createContext({$,repairBusy:false,repairDraft:null,repairPan:false,repairSpace:false,current:{id:'image',confirmed:true},workStage:'repair',repairMarks:[{id:'a',kind:'bump',region:[.2,.2,.5,.5]}],repairSelection:null,repairSelectionKind:null,repairActiveMark:null,repairSize:[1000,1000],repairKindPicker:{hidden:true},paintRepairSelection(){},paintRepairMarks(){},saveRepairMarks(){saves++},showRepairKindPicker(){pickers++},toast(){throw Error('Unexpected toast')}});
vm.runInContext(source.slice(source.indexOf('function repairRegionHit('),source.indexOf("$('repairStrength').oninput")),c);
const event=(x,y,type='pointermove')=>({clientX:x,clientY:y,pointerId:1,button:0,type,preventDefault(){}});
function emit(type,x,y){for(const fn of [...listeners.get(type)||[]])fn(event(x,y,type))}
function drag(x,y,endX,endY,cancel=false){view.onpointerdown(event(x,y,'pointerdown'));emit('pointermove',endX,endY);emit(cancel?'pointercancel':'pointerup',endX,endY)}
const close=(actual,expected)=>Array.from(actual).forEach((v,i)=>assert.ok(Math.abs(v-expected[i])<1e-9,`${actual} != ${expected}`));
// Saved regions can be selected and moved without changing type or id.
drag(300,300,400,350);close(c.repairMarks[0].region,[.3,.25,.6,.55]);assert.equal(saves,1);assert.equal(c.repairActiveMark,'a');assert.equal(c.repairSelectionKind,'bump');
// A second drag after release resizes the same box.
drag(600,550,700,650);close(c.repairMarks[0].region,[.3,.25,.7,.65]);assert.equal(saves,2);assert.equal(c.repairMarks.length,1);
// Cancel restores both the visible selection and persisted mark, without saving.
drag(400,400,450,450,true);close(c.repairMarks[0].region,[.3,.25,.7,.65]);close(c.repairSelection,[.3,.25,.7,.65]);assert.equal(saves,2);
// Drawing and editing an unclassified rectangle also works after release.
drag(800,800,950,950);assert.equal(c.repairActiveMark,null);assert.equal(pickers,1);
drag(850,850,800,800);close(c.repairSelection,[.75,.75,.9,.9]);assert.equal(pickers,2);assert.equal(saves,2);
close(c.editRepairRegion([.2,.2,.5,.5],'move',2,-2,[1000,1000]),[.7,0,1,.3]);
close(c.editRepairRegion([.2,.2,.5,.5],'nw',2,2,[1000,1000]),[.496,.496,.5,.5]);
assert.equal(c.repairRegionHit([.2,.2,.5,.5],200,200,rect),'nw');
assert.equal(c.repairRegionHit([.2,.2,.5,.5],300,200,rect),'n');
c.repairBusy=true;drag(800,800,850,850);assert.equal(saves,2);
assert.equal(captured,false);for(const name of ['pointerup','pointercancel','lostpointercapture'])assert.equal(listeners.get(name)?.size||0,0);
console.log('PASS: repeat move/resize after release, stable type/id, cancel rollback, pending selection editing, bounds and busy guard');
