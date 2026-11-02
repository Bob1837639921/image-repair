const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const classes=()=>({values:new Set(),add(name){this.values.add(name)},remove(name){this.values.delete(name)},toggle(name,value){if(value===undefined)value=!this.values.has(name);value?this.values.add(name):this.values.delete(name)}});
const button=()=>({classList:classes(),setAttribute(){}});
const stage={style:{}},listeners={};
const view={clientWidth:500,clientHeight:600,clientLeft:0,clientTop:0,scrollLeft:0,scrollTop:0,classList:classes(),addEventListener(name,fn){listeners[name]=fn},setAttribute(){},getBoundingClientRect(){return {left:10,top:20}},setPointerCapture(id){this.pointer=id},hasPointerCapture(id){return this.pointer===id},releasePointerCapture(){this.pointer=null},get scrollWidth(){return Math.max(500,parseFloat(stage.style.width)||0)},get scrollHeight(){return Math.max(600,parseFloat(stage.style.height)||0)}};
const image={style:{},naturalWidth:500,naturalHeight:2000,removeAttribute(){this.src=''}};
const controls={minus:button(),plus:button(),percent:button(),actual:button(),fit:button()};
let observer;
const context=vm.createContext({window:{},ResizeObserver:class{constructor(fn){observer=fn}observe(){}}});
vm.runInContext(fs.readFileSync(__dirname+'/static/recognition-viewer.js','utf8'),context);
const viewer=new context.window.RecognitionViewer({view,stage,image,...controls});
function load(key,width=500,height=2000){viewer.setSource('/image/'+key,key);image.naturalWidth=width;image.naturalHeight=height;image.onload()}
load('overview');assert.equal(viewer.mode,'fit');assert.ok(viewer.height<=566);assert.equal(view.scrollTop,0);
controls.actual.onclick();assert.equal(viewer.scale,1);assert.equal(image.style.width,'500px');assert.equal(image.style.height,'2000px');
const anchor=[260,320],u=(view.scrollLeft+250-viewer.left)/viewer.width,v=(view.scrollTop+300-viewer.top)/viewer.height;
viewer.zoom(2,anchor);assert.ok(Math.abs(viewer.left+u*viewer.width-view.scrollLeft-250)<1e-7);assert.ok(Math.abs(viewer.top+v*viewer.height-view.scrollTop-300)<1e-7);
let prevented=false;listeners.wheel({deltaY:-100,clientX:260,clientY:320,preventDefault(){prevented=true}});assert.ok(prevented);assert.ok(viewer.scale>2);
const beforePan=view.scrollTop;listeners.pointerdown({button:0,pointerId:1,clientX:250,clientY:300,preventDefault(){}});listeners.pointermove({pointerId:1,clientX:200,clientY:250});assert.equal(view.scrollTop,beforePan+50);listeners.pointerup({pointerId:1});assert.equal(view.pointer,null);
// Every tab, including the inscription, supports native-pixel and larger zoom.
for(const part of ['0','1','2','3','signature']){load(part,600,700);controls.actual.onclick();assert.equal(viewer.scale,1);controls.plus.onclick();assert.equal(viewer.scale,1.25)}
viewer.zoom(3);viewer.center(.5,.6);const savedTop=view.scrollTop;
load('overview');assert.ok(viewer.scale>2);load('signature',600,700);assert.equal(viewer.scale,3);assert.ok(Math.abs(view.scrollTop-savedTop)<1e-7);
viewer.zoom(999);assert.equal(viewer.scale,8);controls.fit.onclick();assert.equal(viewer.mode,'fit');observer();assert.equal(viewer.mode,'fit');
// A superseded load cannot replace the geometry of the newer tab.
viewer.setSource('/old','old');const oldLoad=image.onload;viewer.setSource('/new','new');image.naturalWidth=700;image.naturalHeight=1200;oldLoad();assert.equal(viewer.ready,false);image.onload();assert.equal(viewer.ready,true);assert.equal(viewer.key,'new');
viewer.reset();assert.equal(viewer.ready,false);assert.equal(viewer.snapshots.size,0);assert.equal(controls.plus.disabled,true);
console.log('PASS: all recognition views zoom, pointer anchoring, pan, tab memory, fit and stale image loads');
