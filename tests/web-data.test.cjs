const {test}=require('node:test');
const assert=require('node:assert/strict');
const D=require('../web/data.js');
test('CSV preserves Vietnamese, quoted commas, multiline content, escaped quotes and BOM',()=>{
  const p=D.parseCSV('\uFEFFid,text\r\n1,"Xin chào, bạn"\r\n2,"Hai\ndòng ""trích dẫn"""\r\n');
  assert.deepEqual(p.rows,[['1','Xin chào, bạn'],['2','Hai\ndòng "trích dẫn"']]);
});
test('CSV rejects malformed quotes, uneven columns, duplicate headers and oversized sessions',()=>{
  for(const csv of ['text\n"bad','a,b\n1','a,a\n1,2','a\n"x"y'])assert.throws(()=>D.parseCSV(csv));
  assert.throws(()=>D.parseCSV('text\n'+Array(1001).fill('hello').join('\n')));
  assert.deepEqual(D.parseCSV('id;text\n1;xin chào',';').rows,[['1','xin chào']]);
});
test('Unicode and request chunks respect backend limits without dropping or duplicating rows',()=>{
  D.validateTexts(['😊'.repeat(5000)]);assert.throws(()=>D.validateTexts(['a'.repeat(5001)]));assert.throws(()=>D.validateTexts(['\ud800']));
  const rows=Array.from({length:35},(_,i)=>({id:i,text:'😊'.repeat(5000)}));const chunks=D.chunks(rows);
  assert.deepEqual(chunks.flat(),rows);assert.ok(chunks.every(c=>c.length<=16&&c.reduce((n,r)=>n+[...r.text].length,0)<=20000));
});
test('CSV export separates human and model labels and neutralizes spreadsheet formulas',()=>{
  const csv=D.exportCSV({rows:[{id:1,text:' =HYPERLINK("bad")',prediction:{label:'CLEAN',confidence:.9,probabilities:{CLEAN:.9,OFFENSIVE:.08,HATE:.02},truncated:false},status:'reviewed',reviewLabel:'HATE',note:'\t=1+1'}]});
  assert.match(csv,/' =HYPERLINK/);assert.match(csv,/"CLEAN"/);assert.match(csv,/"reviewed","HATE"/);assert.match(csv,/'\t=1\+1/);
});
test('JSON restoration rejects invalid review state and preserves separate model predictions',()=>{
  const data={schema:1,name:'Test',rows:[{text:'Xin chào',prediction:null,status:'reviewed',reviewLabel:'CLEAN',note:'',error:''}]};
  assert.equal(D.importSession(data).rows[0].reviewLabel,'CLEAN');
  assert.throws(()=>D.importSession({...data,rows:[{...data.rows[0],reviewLabel:null}]}));
  assert.throws(()=>D.importSession({...data,rows:[{...data.rows[0],status:'pending'}]}));
});
