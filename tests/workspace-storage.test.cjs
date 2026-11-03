const {test}=require('node:test');
const assert=require('node:assert/strict');
const {IDBFactory}=require('fake-indexeddb');
const {writeSession}=require('../web/storage.js');
async function database(){
  return new Promise((resolve,reject)=>{
    const request=new IDBFactory().open('test',1);
    request.onupgradeneeded=()=>request.result.createObjectStore('sessions',{keyPath:'id'});
    request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);
  });
}
test('stale tab cannot resurrect a deleted session or delete a newer revision',async()=>{
  const db=await database(),first=await writeSession(db,{id:'one',rows:[]});
  const second=await writeSession(db,{...first,name:'edited elsewhere'});
  await assert.rejects(writeSession(db,first,true),/tab khác/);
  await assert.rejects(writeSession(db,first),/tab khác/);
  await writeSession(db,second,true);
  await assert.rejects(writeSession(db,second),/tab khác/);
  db.close();
});
test('concurrent new sessions with the same id and concurrent edits have one winner',async()=>{
  const db=await database();
  const creates=await Promise.allSettled([writeSession(db,{id:'one'}),writeSession(db,{id:'one'})]);
  assert.equal(creates.filter(r=>r.status==='fulfilled').length,1);
  const first=creates.find(r=>r.status==='fulfilled').value;
  const edits=await Promise.allSettled([writeSession(db,{...first,name:'A'}),writeSession(db,{...first,name:'B'})]);
  assert.equal(edits.filter(r=>r.status==='fulfilled').length,1);db.close();
});
