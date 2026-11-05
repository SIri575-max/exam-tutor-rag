const assert=require('node:assert/strict');
const {box,point}=require('../photo_crop.js');
assert.deepEqual(box([.8,.7],[.2,.1]),[.2,.1,.8,.7]);
assert.deepEqual(box([-.2,1.2],[2,-1]),[0,0,1,1]);
assert.deepEqual(point(180,140,{left:100,top:100,width:400,height:200}),[.2,.2]);
assert.deepEqual(point(90,400,{left:100,top:100,width:400,height:200}),[0,1]);
console.log('Crop direction, clamping and scaled canvas coordinate checks passed');
