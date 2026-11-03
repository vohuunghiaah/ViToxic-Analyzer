// Real Chromium + IndexedDB + native extension, synthetic DOM and mock inference.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
const fs=require('node:fs/promises');
const path=require('node:path');
const os=require('node:os');
const http=require('node:http');
const prediction={label:'CLEAN',label_id:0,confidence:.8,probabilities:{CLEAN:.8,OFFENSIVE:.1,HATE:.1},token_count:4,truncated:false};
const root=path.resolve(__dirname,'..');
async function server(){
  const state={mode:'ok',calls:[],release:null};
  const app=http.createServer(async(req,res)=>{
    try{
      if(req.url.startsWith('/predict')){
        let body='';for await(const chunk of req)body+=chunk;
        const data=JSON.parse(body),texts=data.texts||[data.text];state.calls.push(texts);
        if(state.mode==='hold')await new Promise(resolve=>state.release=resolve);
        if(state.mode==='offline'){req.socket.destroy();return;}
        if(state.mode==='busy'){res.writeHead(503);res.end('{}');return;}
        const result=data.texts?{count:texts.length,predictions:texts.map(()=>prediction)}:prediction;
        res.setHeader('Content-Type','application/json');res.end(JSON.stringify(result));return;
      }
      if(req.url==='/ready'||req.url==='/model'){
        res.setHeader('Content-Type','application/json');res.end(JSON.stringify(req.url==='/ready'?{status:'ready'}:{run:'fixture',checkpoint_sha256:'fixture'}));return;
      }
      const file=req.url==='/workspace'?'workspace.html':req.url==='/'?'index.html':req.url.replace('/static/','');
      if(!/^[a-z.-]+$/.test(file)){res.writeHead(404);res.end();return;}
      const content=await fs.readFile(path.join(root,'web',file));
      res.setHeader('Content-Type',file.endsWith('.js')?'application/javascript':file.endsWith('.css')?'text/css':'text/html; charset=utf-8');res.end(content);
    }catch{res.writeHead(500);res.end();}
  });
  await new Promise(resolve=>app.listen(0,'127.0.0.1',resolve));
  return {state,url:`http://127.0.0.1:${app.address().port}`,close:()=>new Promise(resolve=>{app.close(resolve);app.closeAllConnections();})};
}
test('workspace real IndexedDB: pause/resume, errors, review, restore and stale-tab protection',async()=>{
  const api=await server(),browser=await chromium.launch(),ctx=await browser.newContext(),page=await ctx.newPage();
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  try{
    await page.goto(api.url+'/workspace#import');
    await page.waitForFunction(()=>typeof db!=='undefined'&&db);
    await page.locator('details summary').click();
    await page.locator('#paste-comments').fill(Array.from({length:20},(_,i)=>'Bình luận '+i).join('\n'));
    api.state.mode='hold';
    await page.locator('#create-session').click();
    await page.waitForFunction(()=>document.querySelector('#run-progress').textContent.includes('16 câu'));
    await page.locator('#pause-run').click();
    while(!api.state.release)await new Promise(resolve=>setTimeout(resolve,10));
    api.state.mode='ok';api.state.release();
    await page.waitForFunction(()=>!running);
    assert.equal(await page.evaluate(()=>active.rows.filter(r=>r.prediction).length),16);
    await page.locator('#resume-run').click();await page.waitForFunction(()=>!running);
    assert.equal(await page.evaluate(()=>active.rows.filter(r=>r.prediction).length),20);
    assert.deepEqual(api.state.calls.map(c=>c.length),[16,4]);
    await page.locator('#review-rows button').first().click();
    await page.locator('#review-label').selectOption('HATE');await page.locator('#review-form button[type=submit]').click();
    await page.waitForFunction(()=>!document.querySelector('#review-dialog').open);
    assert.deepEqual(await page.evaluate(()=>[active.rows[0].prediction.label,active.rows[0].reviewLabel]),['CLEAN','HATE']);
    const backup=await page.evaluate(()=>JSON.stringify(active));
    await page.reload();await page.waitForFunction(()=>sessions.length===1);
    assert.equal(await page.evaluate(()=>sessions[0].rows[0].reviewLabel),'HATE');
    await page.evaluate(()=>location.hash='import');
    await page.locator('#restore-file').setInputFiles({name:'bad.json',mimeType:'application/json',buffer:Buffer.from('{bad')});
    await page.waitForFunction(()=>document.querySelector('#desk-message').textContent==='JSON không hợp lệ.');
    assert.equal(await page.evaluate(()=>sessions.length),1);
    await page.locator('#restore-file').setInputFiles({name:'backup.json',mimeType:'application/json',buffer:Buffer.from(backup)});
    await page.waitForFunction(()=>sessions.length===2);assert.equal(await page.evaluate(()=>new Set(sessions.map(s=>s.id)).size),2);
    // Keep a stale snapshot in a second tab, then delete in the first tab.
    const other=await ctx.newPage();await other.goto(api.url+'/workspace');await other.waitForFunction(()=>sessions.length===2);
    const id=await page.evaluate(()=>active.id);
    await other.evaluate(id=>{globalThis.stale=sessions.find(s=>s.id===id);},id);
    await page.evaluate(async()=>{await ViToxicStorage.writeSession(db,active,true);});
    assert.match(await other.evaluate(async()=>{try{await ViToxicStorage.writeSession(db,stale);return 'unexpected';}catch(e){return e.message;}}),/tab khác/);
    // A failed review save must remain in the JSON backup, not only in the form.
    await page.evaluate(()=>openReview(active.rows[0]));
    await other.close();
    await page.locator('#review-note').fill('Quyết định chưa lưu cần sao lưu');
    await page.locator('#review-form button[type=submit]').click();
    await page.waitForFunction(()=>storageFailed);
    assert.equal(await page.evaluate(()=>active.rows[0].note),'Quyết định chưa lưu cần sao lưu');
    await page.locator('#close-dialog').click();
    // New session fails on 503, then offline, then resumes without duplicates.
    await page.reload();await page.waitForFunction(()=>sessions.length===1);await page.evaluate(()=>location.hash='import');
    await page.locator('details summary').click();await page.locator('#paste-comments').fill('Nội dung thử lại');
    api.state.mode='busy';await page.locator('#create-session').click();await page.waitForFunction(()=>!running&&!importing);
    assert.equal(await page.evaluate(()=>active.rows[0].prediction),null);
    assert.match(await page.locator('#desk-message').textContent(),/bận/);
    api.state.mode='offline';await page.locator('#resume-run').click();await page.waitForFunction(()=>!running);
    assert.equal(await page.locator('#resume-run').isEnabled(),true);
    api.state.mode='ok';await page.locator('#resume-run').click();await page.waitForFunction(()=>!running);
    assert.equal(await page.evaluate(()=>active.rows[0].prediction.label),'CLEAN');
    await page.locator('#desk-theme').click();const theme=await page.locator('html').getAttribute('data-theme');await page.reload();
    assert.equal(await page.locator('html').getAttribute('data-theme'),theme);
    assert.deepEqual(errors,[]);
  }finally{await browser.close();await api.close();}
});

test('native extension: YouTube fixture, multiline, edits, SPA, disable, configured API',async()=>{
  const api=await server(),profile=await fs.mkdtemp(path.join(os.tmpdir(),'vitoxic-browser-'));
  const extension=path.join(root,'extension');
  const ctx=await chromium.launchPersistentContext(profile,{headless:true,channel:'chromium',args:[`--disable-extensions-except=${extension}`,`--load-extension=${extension}`]});
  try{
    const worker=ctx.serviceWorkers()[0]||await ctx.waitForEvent('serviceworker');
    const id=worker.url().split('/')[2];
    // Synthetic YouTube DOM; no live YouTube data or model predictions.
    const page=await ctx.newPage();
    await ctx.route('https://www.youtube.com/**',r=>r.fulfill({contentType:'text/html; charset=utf-8',body:'<html><body><ytd-comment-view-model><span class="author">Author</span><div id="content-text">xin<br>chào</div><ytd-comment-view-model><span class="author">Reply author</span><div id="content-text">Trả lời riêng</div></ytd-comment-view-model></ytd-comment-view-model></body></html>'}));
    await page.goto('https://www.youtube.com/watch?v=fixture');
    // Native service-worker APIs inject into the fixture; permissions dialog is not tested.
    await worker.evaluate(async()=>{await chrome.permissions.request({origins:['https://www.youtube.com/*']});}).catch(()=>{});
    const popup=await ctx.newPage();await popup.goto(`chrome-extension://${id}/popup.html`);
    const configured=await popup.evaluate(async apiURL=>chrome.runtime.sendMessage({type:'setAPI',apiURL}),api.url);
    assert.equal(configured.apiURL,api.url);
    // Use a granted loopback fixture origin if Chromium requires a gesture for YouTube permission.
    const allowed=await worker.evaluate(()=>chrome.permissions.contains({origins:['https://www.youtube.com/*']}));
    if(!allowed){
      await page.goto(api.url+'/static/comments-demo.html');
      await page.setContent('<ytd-comment-view-model><span class="author">Author</span><div data-comment-body>xin<br>chào</div><ytd-comment-view-model><span class="author">Reply author</span><div data-comment-body>Trả lời riêng</div></ytd-comment-view-model></ytd-comment-view-model>');
    }
    const origin=new URL(page.url()).origin;
    const tab=await worker.evaluate(async origin=> (await chrome.tabs.query({})).find(t=>t.url?.startsWith(origin)),origin);
    assert.ok(tab,'fixture tab must be visible under the granted host permission');
    const configuredSite=await popup.evaluate(async origin=>chrome.runtime.sendMessage({type:'setSite',origin,enabled:true}),origin);
    assert.equal(configuredSite.config?.enabled,true,configuredSite.error);
    await worker.evaluate(async tabId=>chrome.scripting.executeScript({target:{tabId},files:['page.js','auto.js']}),tab.id);
    await popup.close();await page.bringToFront();
    await page.waitForFunction(()=>document.querySelectorAll('[data-vitoxic-label]').length===2);
    assert.deepEqual(api.state.calls.flat(),['xin chào','Trả lời riêng']);
    const selector=allowed?'#content-text':'[data-comment-body]';
    await page.locator('.author').first().evaluate(n=>n.textContent='Changed author');
    await page.waitForTimeout(800);assert.equal(api.state.calls.length,1);
    await page.locator(selector).first().evaluate(n=>n.textContent='Đã sửa');
    await page.waitForFunction(()=>document.querySelectorAll('[data-vitoxic-label]').length===2);
    assert.ok(api.state.calls.flat().includes('Đã sửa'));
    await page.locator(selector).last().evaluate(n=>n.parentElement.remove());
    await page.waitForFunction(()=>document.querySelectorAll('[data-vitoxic-label]').length===1);
    await page.evaluate(selector=>{dispatchEvent(new Event('yt-navigate-start'));history.pushState({},'', '?v=next');document.querySelector(selector).textContent='Video mới';dispatchEvent(new Event('yt-navigate-finish'));},selector);
    await page.waitForFunction(()=>document.querySelectorAll('[data-vitoxic-label]').length===1);
    assert.ok(api.state.calls.flat().includes('Video mới'));
    const p=await ctx.newPage();await p.goto(`chrome-extension://${id}/popup.html`);
    await p.evaluate(async origin=>chrome.runtime.sendMessage({type:'setSite',origin,enabled:false}),origin);
    await page.waitForFunction(()=>!document.querySelector('[data-vitoxic-label]'));
    const count=api.state.calls.length;await page.locator(selector).evaluate(n=>n.textContent='Sau tắt');await page.waitForTimeout(1200);
    assert.equal(api.state.calls.length,count);
  }finally{
    await ctx.close();await api.close();
    const resolved=path.resolve(profile),temp=path.resolve(os.tmpdir());
    if(path.dirname(resolved)===temp&&path.basename(resolved).startsWith('vitoxic-browser-'))await fs.rm(resolved,{recursive:true,force:true});
  }
});

test('YouTube adapter handles legacy/new DOM and fails closed on unknown structure',async()=>{
  const browser=await chromium.launch(),page=await browser.newPage();
  try{
    await page.route('https://www.youtube.com/**',r=>r.fulfill({contentType:'text/html; charset=utf-8',body:'<ytd-comment-view-model><span class="author">Tác giả</span><div id="content-text">Dòng một<br>Dòng hai</div><ytd-comment-renderer><span class="author">Người trả lời</span><div id="content-text">Reply riêng</div></ytd-comment-renderer></ytd-comment-view-model>'}));
    await page.goto('https://www.youtube.com/watch?v=fixture');
    await page.addScriptTag({path:path.join(root,'extension/page.js')});
    assert.deepEqual(await page.evaluate(()=>ViToxicPage.collect('viewport').texts),['Dòng một Dòng hai','Reply riêng']);
    await page.locator('#content-text').first().evaluate(n=>n.id='unknown-new-dom');
    assert.deepEqual(await page.evaluate(()=>ViToxicPage.collect('viewport').texts),['Reply riêng']);
    await page.locator('#content-text').evaluate(n=>n.id='unknown-reply');
    assert.equal(await page.evaluate(()=>ViToxicPage.discover().length),0);
    assert.deepEqual(await page.evaluate(()=>ViToxicPage.collect('viewport',{selector:'#unknown-new-dom, #unknown-reply'}).texts),['Dòng một Dòng hai','Reply riêng']);
  }finally{await browser.close();}
});
