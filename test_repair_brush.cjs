const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(__dirname+'/static/repair.js','utf8');
const c=vm.createContext({repairSize:[1000,500]});
vm.runInContext(source.slice(source.indexOf('function repairAppendPoint('),source.indexOf('function paintRepairBrushes(')),c);
// Recording densifies long jumps so the eraser can cut anywhere along a stroke.
const path=[];c.repairAppendPoint(path,[.1,.5],4);c.repairAppendPoint(path,[.1005,.5],4);assert.equal(path.length,1,'sub-spacing moves are skipped');
c.repairAppendPoint(path,[.2,.5],4);assert.equal(path.length,26);for(let i=1;i<path.length;i++)assert.ok((path[i][0]-path[i-1][0])*1000<=4+1e-9);
// Region = stroke bounds plus radius and margin, clipped, never below backend minimum.
const brush={size:.02,paths:[path]};const region=c.repairBrushRegion(brush);
assert.ok(Math.abs(region[0]-(.1-12/1000))<1e-9&&Math.abs(region[2]-(.2+12/1000))<1e-9);
assert.ok(Math.abs(region[1]-(.5-12/500))<1e-9&&Math.abs(region[3]-(.5+12/500))<1e-9);
const edge=c.repairBrushRegion({size:.004,paths:[[[0,0]]]});assert.ok(edge[0]===0&&edge[1]===0&&(edge[2]-edge[0])*1000>=6-1e-9&&(edge[3]-edge[1])*500>=6-1e-9);
// Erasing the middle splits the stroke in two and updates its region.
const mark={id:'a',kind:'crease',region,brush:{size:.02,paths:[c.densifyRepairPath([[.1,.5],[.3,.5]],4)]}};
assert.equal(c.eraseRepairBrush(mark,[.2,.5],20),true);assert.equal(mark.brush.paths.length,2);
assert.ok(mark.brush.paths[0].every(p=>p[0]<.2-.019)&&mark.brush.paths[1].every(p=>p[0]>.2+.019));
assert.equal(c.eraseRepairBrush(mark,[.9,.9],20),false,'missing the stroke changes nothing');
// Erasing everything leaves no paths (the caller then deletes the mark).
for(let x=.1;x<=.3;x+=.01)c.eraseRepairBrush(mark,[x,.5],30);assert.equal(mark.brush.paths.length,0);
console.log('brush geometry ok');
