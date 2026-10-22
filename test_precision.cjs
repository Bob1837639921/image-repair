// DOM-level logic tests, not a substitute for a real-browser visual check.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(__dirname+'/static/app.js','utf8');
const nodes=new Map();
function node(id){if(!nodes.has(id))nodes.set(id,{value:'1',style:{},options:[],clientWidth:700,clientHeight:600,naturalWidth:300,naturalHeight:1600,scrollLeft:0,scrollTop:0,handlers:{},classList:{add(){},remove(){}},replaceChildren(...children){this.options=children;this.value=children[0]?.value},append(child){this.options.push(child)},insertBefore(){},querySelector(){return node('viewport')},querySelectorAll(){return []},addEventListener(type,fn){this.handlers[type]=fn},removeEventListener(){},setPointerCapture(){},getBoundingClientRect(){return {left:22,top:22,width:parseFloat(this.style.width)||300,height:parseFloat(this.style.height)||1800}}});return nodes.get(id)}
const context=vm.createContext({console,document:{createElement:()=>node('new'+nodes.size),addEventListener(){}},$:node,clone:x=>JSON.parse(JSON.stringify(x)),drawQuad(){},toast(){},preview(){},markHistory(){},changed:async()=>{},current:{id:'test',width:300,height:1800,rotation:0,points:[[.1,.1],[.9,.1],[.9,.9],[.1,.9]]},compare:false,busy:false});
vm.runInContext(source.slice(source.indexOf('function fit(){'),source.indexOf('function fitResult(){')),context);
vm.runInContext(source.slice(source.indexOf('// Invert the output crop'),source.indexOf('function toast(')),context);
node('detect').insertAdjacentElement=()=>{};
vm.runInContext(source.slice(source.indexOf('// Precision editor:'),source.indexOf('// Residual borders')),context);
(async()=>{
 node('zoom').value='1';vm.runInContext('fit()',context);
 assert.equal(node('imageWrap').style.width,'300px');assert.equal(node('imageWrap').style.height,'1800px');
 node('zoom').value='4';vm.runInContext('fit()',context);assert.equal(node('imageWrap').style.height,'7200px');
 node('pixelStep').value='1';await vm.runInContext('nudgeCorner(1,0)',context);
 assert.ok(Math.abs(context.current.points[0][0]-(.1+1/299))<1e-12);
 context.current.rotation=90;const previous=context.current.points[0][0];await vm.runInContext('nudgeCorner(1,0)',context);
 assert.ok(Math.abs(context.current.points[0][0]-(previous+1/1799))<1e-12);
 vm.runInContext('fit()',context);assert.equal(node('imageWrap').style.width,'7200px');
 node('zoom').value='fit';vm.runInContext('fit()',context);assert.ok(parseFloat(node('imageWrap').style.width)<=674);
 console.log('PASS: source-pixel zoom, 400%, rotated pixel steps, fit-to-window');
})().catch(e=>{console.error(e);process.exitCode=1});
