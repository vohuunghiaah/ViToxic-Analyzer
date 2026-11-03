const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
function harness(fetch, {sites={}, allowed=true, apiURL}={}){
  let listener;
  const scripts=new Map(),event={addListener:()=>{}};
  const chrome={runtime:{id:'test',getURL:p=>'chrome-extension://test/'+p,onMessage:{addListener:f=>listener=f},onInstalled:event,onStartup:event},
    storage:{local:{get:async()=>({sites,...(apiURL===undefined?{}:{apiURL})}),set:async value=>{if(value.sites)sites=value.sites;if(value.apiURL)apiURL=value.apiURL}}},
    permissions:{contains:async()=>allowed,onRemoved:event},
    scripting:{getRegisteredContentScripts:async({ids})=>ids.flatMap(id=>scripts.has(id)?[scripts.get(id)]:[]),
      registerContentScripts:async entries=>entries.forEach(e=>scripts.set(e.id,e)),updateContentScripts:async entries=>entries.forEach(e=>scripts.set(e.id,e)),
      unregisterContentScripts:async({ids})=>ids.forEach(id=>scripts.delete(id))}};
  vm.runInNewContext(fs.readFileSync(require.resolve('../extension/background.js'),'utf8'),{chrome,fetch,AbortSignal,URL,TextEncoder,crypto:require('node:crypto').webcrypto,setTimeout:f=>f()});
  const call=(msg,sender={id:'test',url:chrome.runtime.getURL('popup.html')})=>new Promise(resolve=>listener(msg,sender,resolve));
  return {listener,call,scripts,send:texts=>call({type:'analyze',texts})};
}
test('extension only accepts its own popup and never accepts a destination URL from a page',()=>{
  const h=harness(()=>{throw new Error('must not fetch')});
  assert.equal(h.listener({type:'analyze',texts:['Hi']},{id:'test',url:'https://example.org'},()=>{}),undefined);
});
test('automatic requests require an enabled origin, host permission and top-frame content script',async()=>{
  let count=0;const fetch=async()=>{count++;return {ok:true,status:200,json:async()=>({predictions:[{label:'CLEAN',confidence:.8}]})}};
  const sender={id:'test',url:'https://comments.example/post',tab:{id:1},frameId:0};
  const msg={type:'autoAnalyze',texts:['Xin chào']};
  assert.ok((await harness(fetch).call(msg,sender)).error);
  assert.ok((await harness(fetch,{sites:{'https://comments.example':{enabled:true}},allowed:false}).call(msg,sender)).error);
  assert.ok((await harness(fetch,{sites:{'https://comments.example':{enabled:true}}}).call(msg,{...sender,frameId:1})).error);
  assert.equal(count,0);
  assert.equal((await harness(fetch,{sites:{'https://comments.example':{enabled:true}}}).call(msg,sender)).predictions.length,1);
  assert.equal(count,1);
});
test('site enable registers persistent injection and disable removes it',async()=>{
  const h=harness(()=>{throw new Error('no inference')});
  const site={type:'setSite',origin:'https://comments.example',enabled:true,selector:'.comment-body',exclude:'.nickname'};
  assert.equal((await h.call(site)).config.enabled,true);assert.equal(h.scripts.size,1);
  const script=[...h.scripts.values()][0];assert.equal(script.persistAcrossSessions,true);assert.deepEqual([...script.js],['page.js','auto.js']);
  assert.equal((await h.call({...site,enabled:false})).config.enabled,false);assert.equal(h.scripts.size,0);
});
test('automatic inference serializes concurrent tabs and isolates invalid comments',async()=>{
  let busy=0,peak=0;
  const h=harness(async(url,options)=>{
    busy++;peak=Math.max(peak,busy);await new Promise(resolve=>setTimeout(resolve,5));busy--;
    const texts=JSON.parse(options.body).texts;
    if(texts.includes('bad'))return {status:422,ok:false};
    return {status:200,ok:true,json:async()=>({predictions:texts.map(()=>({label:'CLEAN',confidence:.9}))})};
  });
  const [a,b]=await Promise.all([h.send(['ok','bad']),h.send(['good'])]);
  assert.equal(peak,1);assert.equal(a.predictions[0].label,'CLEAN');assert.ok(a.predictions[1].error);assert.equal(b.predictions.length,1);
});
test('extension chunks by count and Unicode character limit and uses fixed loopback API',async()=>{
  const calls=[];const h=harness(async(url,options)=>{const texts=JSON.parse(options.body).texts;calls.push({url,texts});return {ok:true,status:200,json:async()=>({predictions:texts.map(()=>({label:'CLEAN',confidence:.8}))})};});
  const result=await h.send(Array(18).fill('😊'.repeat(5000)));
  assert.equal(result.predictions.length,18);assert.equal(calls.length,5);
  assert.ok(calls.every(c=>c.url==='http://127.0.0.1:8001/predict/batch'&&c.texts.length<=8&&c.texts.reduce((n,t)=>n+[...t].length,0)<=20000));
});
test('extension rejects oversized input and reports busy after bounded retries',async()=>{
  let calls=0;const h=harness(async()=>{calls++;return {status:503,ok:false};});
  assert.ok((await h.send(['x'.repeat(5001)])).error);assert.equal(calls,0);
  assert.ok((await h.send(['Xin chào'])).error);assert.equal(calls,4);
});

test('API settings allow only literal loopback and validated ports',async()=>{
  const requests=[],h=harness(async(url,options)=>{requests.push({url,options});return {ok:true,status:200,json:async()=>({predictions:[{label:'CLEAN',confidence:.8}]})};});
  assert.equal((await h.call({type:'getAPI'})).apiURL,'http://127.0.0.1:8001');
  for(const url of ['http://127.0.0.1:1','http://127.0.0.1:65535/','http://127.0.0.1:8002','http://127.0.0.1']){
    assert.equal((await h.call({type:'setAPI',apiURL:url})).apiURL,new URL(url).origin);
  }
  for(const url of ['https://127.0.0.1:8001','http://example.org','http://localhost:8001','http://127.1:8001','http://2130706433','http://127.0.0.1.evil.test','http://127.0.0.1@evil.test','http://user@127.0.0.1','http://127.0.0.1:0','http://127.0.0.1:65536','http://127.0.0.1/predict','http://127.0.0.1?x=1','http://127.0.0.1#x',' http://127.0.0.1',null]){
    assert.ok((await h.call({type:'setAPI',apiURL:url})).error,String(url));
  }
  await h.call({type:'setAPI',apiURL:'http://127.0.0.1:8002'});
  await h.call({type:'analyze',texts:['ok'],apiURL:'http://evil.test'});
  assert.equal(requests[0].url,'http://127.0.0.1:8002/predict/batch');
  assert.equal(requests[0].options.redirect,'error');
  assert.equal(h.listener({type:'setAPI',apiURL:'http://127.0.0.1:8003'},{id:'test',url:'https://youtube.com',tab:{id:1},frameId:0},()=>{}),undefined);
});

test('tampered stored API or missing loopback permission never reaches fetch',async()=>{
  let calls=0;
  for(const options of [{apiURL:'http://evil.test'},{allowed:false}]){
    const h=harness(async()=>{calls++;},options);
    assert.ok((await h.send(['ok'])).error);
  }
  assert.equal(calls,0);
});
