const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(__dirname+'/static/app.js','utf8');
const context=vm.createContext({clone:x=>JSON.parse(JSON.stringify(x))});
vm.runInContext(source.slice(source.indexOf('// Invert the output crop'),source.indexOf('function toast(')),context);
const item={points:[[.15,.05],[.81,.12],[.9,.94],[.08,.88]],width:3024,height:4032,rotation:0,trim:{left:.017,top:.013,right:.025,bottom:.006}};
// Independent golden coordinates from inverse OpenCV render homography.
const expected=[[.16071118749146704,.05997040507560412],[.7949053203275886,.12701267655089518],[.8795952204891748,.9324974010898414],[.09477659937230509,.8748804338486342]];
const result=context.cropPoints(item);
result.forEach((p,i)=>p.forEach((v,j)=>assert.ok(Math.abs(v-expected[i][j])<1e-6)));
context.current=JSON.parse(JSON.stringify(item));vm.runInContext('bakeTrim()',context);
assert.equal(Object.keys(context.current.trim).length,0);
assert.deepEqual(JSON.parse(JSON.stringify(context.current.points)),JSON.parse(JSON.stringify(result)));
assert.deepEqual(JSON.parse(JSON.stringify(context.cropPoints(context.current))),JSON.parse(JSON.stringify(result)),'moving final corners must not trim twice');
assert.deepEqual(context.cropPoints({...item,trim:{}}),item.points);
console.log('PASS: effective outline matches exported perspective crop; no double trim after editing');
