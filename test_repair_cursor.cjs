const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(__dirname+'/static/repair.js','utf8');
let imageRect={left:100,top:100,right:300,bottom:500,width:200,height:400};
const wrap={style:{width:'200px',height:'400px',visibility:'visible'},getBoundingClientRect:()=>imageRect};
const viewport={clientLeft:1,clientTop:1,clientWidth:343,clientHeight:543,scrollLeft:10,scrollTop:20,getBoundingClientRect:()=>({left:50,top:50,right:400,bottom:600})};
const cursor={hidden:true,style:{}};
const c=vm.createContext({$:id=>id==='repairWrap'?wrap:viewport,repairBrushCursor:cursor,repairBrushMode:'brush',repairBrushKind:'crease',repairBrushSize:24,repairEraserSize:40,repairSize:[1000,2000]});
vm.runInContext(source.slice(source.indexOf('function placeRepairBrushCursor('),source.indexOf('const repairBoxPointerDown=')),c);
c.placeRepairBrushCursor({clientX:200,clientY:200});assert.equal(cursor.hidden,false);assert.equal(cursor.style.left,'200px');assert.equal(cursor.style.width,'4.8px');
c.placeRepairBrushCursor({clientX:299,clientY:200});assert.ok(parseFloat(cursor.style.clipPath.split(' ')[1])>0,'clip brush to image edge');
for(let i=0;i<100;i++){
 c.placeRepairBrushCursor({clientX:398,clientY:55});assert.equal(cursor.hidden,true,'scrollbar corner never shows a brush');
 c.placeRepairBrushCursor({clientX:200,clientY:200});
}
assert.equal(wrap.style.width,'200px');assert.equal(wrap.style.height,'400px');assert.equal(viewport.scrollLeft,10);assert.equal(viewport.scrollTop,20);
imageRect={left:-300,top:-100,right:500,bottom:1500,width:800,height:1600};
c.placeRepairBrushCursor({clientX:397,clientY:200});assert.equal(cursor.hidden,true,'scrollbar excluded even when zoomed image extends beneath it');
c.placeRepairBrushCursor({clientX:390,clientY:200});assert.equal(cursor.hidden,false);
c.repairBrushMode='eraser';c.placeRepairBrushCursor({clientX:390,clientY:200});assert.equal(cursor.className,'eraser');assert.equal(cursor.style.width,'32px');
wrap.style.visibility='hidden';c.placeRepairBrushCursor({clientX:200,clientY:200});assert.equal(cursor.hidden,true,'no floating cursor during image loading');
assert.ok(source.includes('repairPane.append(repairBrushCursor)'),'cursor lives outside scrollable image');
assert.match(fs.readFileSync(__dirname+'/static/style.css','utf8'),/#repairBrushCursor\{position:fixed;/);
console.log('PASS: brush/eraser cursor excludes scrollbars and outside/loading images; clips at edges; never changes image size or scroll position');
