// Playwright browser harness: pass this function to browser_run_code_unsafe.
// Uses a separate Chromium profile, a synthetic DOM and the real local API.
async (page) => {
  const ctx=await page.context().browser().browserType().launchPersistentContext('D:/MachineLearning/tmp/extension-auto-qa-profile',{
    headless:true,executablePath:'C:/Users/Quyen/AppData/Local/ms-playwright/chromium-1193/chrome-win/chrome.exe',
    viewport:{width:1000,height:800},args:['--disable-extensions-except=D:/MachineLearning/extension','--load-extension=D:/MachineLearning/extension']
  });
  const checks=[],requests=[];
  const assert=(value,name)=>{if(!value)throw new Error(name);checks.push(name);};
  try{
    const worker=ctx.serviceWorkers()[0]||await ctx.waitForEvent('serviceworker');
    const id=worker.url().split('/')[2],url='http://127.0.0.1:8088/comments';
    ctx.on('request',r=>{if(r.url()==='http://127.0.0.1:8001/predict/batch')requests.push(r.postDataJSON().texts);});
    await ctx.route(url,r=>r.fulfill({contentType:'text/html; charset=utf-8',body:`<!doctype html><html><head><meta charset="utf-8"><style>body{font:16px system-ui;padding:30px;max-width:780px}article{border:1px solid #ccc;padding:20px;margin:20px 0}.comment-author{font-weight:bold}.gap{height:1200px}</style></head><body><h1>Fixture: bình luận và metadata</h1><main><article class="comment"><div class="comment-author">Nguyễn An</div><div class="comment-body"><span class="username">@An</span><p>Cảm ơn bạn đã chia sẻ.</p><button>Trả lời</button></div></article><article class="comment"><div class="comment-author">Trần Bình</div><div class="comment-body"><p>Mình không đồng ý.</p><p>Bạn có thể giải thích thêm không?</p><time>2 giờ trước</time></div></article><div class="gap"></div><article class="comment"><div class="comment-author">Tên ngoài màn hình</div><div class="comment-body">Bình luận ở cuối trang.</div></article></main></body></html>`}));
    const target=await ctx.newPage();await target.goto(url);
    const targetTab=await worker.evaluate(async url=>(await chrome.tabs.query({})).find(t=>t.url===url),url);
    async function popup(){
      const p=await ctx.newPage();
      await p.addInitScript(tab=>{const original=chrome.tabs.query.bind(chrome.tabs);chrome.tabs.query=async query=>query.active?[tab]:original(query);},targetTab);
      await p.goto('chrome-extension://'+id+'/popup.html');await p.locator('#auto-toggle:not([disabled])').waitFor();return p;
    }
    let p=await popup();
    // Fresh profile or rerun: disable any saved configuration first.
    if(await p.locator('#auto-toggle').getAttribute('aria-pressed')==='true')await p.locator('#auto-toggle').click();
    await target.evaluate(()=>{const comments=document.querySelectorAll('article');const range=document.createRange();range.setStartBefore(comments[0]);range.setEndAfter(comments[1]);getSelection().removeAllRanges();getSelection().addRange(range);});
    await p.locator('#selection').click();await p.locator('#analyze:not([disabled])').waitFor();
    const preview=await p.locator('#preview li').allTextContents();
    assert(preview.length===2,'Selection splits into two comments');
    assert(preview[0]==='Cảm ơn bạn đã chia sẻ.','Author and reply button excluded');
    assert(preview[1]==='Mình không đồng ý. Bạn có thể giải thích thêm không?','Multiline comment remains one item; timestamp excluded');
    await p.locator('#auto-toggle').click();await p.waitForFunction(()=>document.querySelector('#auto-toggle').getAttribute('aria-pressed')==='true');
    await p.close();await target.bringToFront();
    await target.waitForFunction(()=>document.querySelectorAll('[data-vitoxic-label]').length===2,{},{timeout:30000});
    assert(await target.locator('article').nth(2).locator('[data-vitoxic-label]').count()===0,'Offscreen comment is not analyzed');
    assert(requests.flat().every(t=>!t.includes('Nguyễn An')&&!t.includes('Trả lời')&&!t.includes('2 giờ trước')),'Only comment content reaches API');
    const before=requests.length;
    await target.evaluate(()=>document.querySelectorAll('.comment-author')[0].textContent='Tên đã thay đổi');
    await target.waitForTimeout(1500);
    assert(requests.length===before,'Metadata-only changes do not repeat inference');
    await target.evaluate(()=>{const article=document.createElement('article');article.className='comment';article.innerHTML='<div class="comment-author">Người mới</div><div class="comment-body">Chúc bạn một ngày vui vẻ.</div>';document.querySelector('main').prepend(article);});
    await target.waitForFunction(()=>document.querySelectorAll('[data-vitoxic-label]').length===3);
    assert(true,'New visible comment is labeled with popup closed');
    await target.locator('article').last().scrollIntoViewIfNeeded();
    await target.waitForFunction(()=>document.querySelectorAll('[data-vitoxic-label]').length===4);
    assert(true,'Scroll reveals and analyzes offscreen comment');
    await target.reload();await target.bringToFront();
    await target.waitForFunction(()=>document.querySelectorAll('[data-vitoxic-label]').length>0);
    assert(true,'Persistent registration runs on reload without popup');
    await target.evaluate(()=>scrollTo(0,0));
    await target.waitForFunction(()=>document.querySelectorAll('article')[0].querySelector('[data-vitoxic-label]'));
    await target.evaluate(()=>document.querySelector('.comment-body p').textContent='Nội dung mới sau chỉnh sửa.');
    await target.waitForFunction(()=>document.querySelector('article [data-vitoxic-label]'));
    await target.waitForTimeout(1000);
    assert(requests.flat().includes('Nội dung mới sau chỉnh sửa.'),'Edited comment is analyzed again');
    p=await popup();await p.locator('#remove').click();await p.waitForFunction(()=>document.querySelector('#auto-toggle').getAttribute('aria-pressed')==='false');
    await p.close();await target.bringToFront();await target.waitForFunction(()=>!document.querySelector('[data-vitoxic-label]'));
    const afterDisable=requests.length;await target.reload();await target.waitForTimeout(1200);
    assert(!await target.locator('[data-vitoxic-label]').count()&&requests.length===afterDisable,'Disable removes badges and stops automatic work after reload');
    // Test label palette independently of predictions, clearly using synthetic labels.
    await target.evaluate(()=>{document.querySelector('.gap').style.height='0';scrollTo(0,0);});
    p=await popup();await p.locator('#scan').click();await p.locator('#analyze:not([disabled])').waitFor();
    const colors=await p.evaluate(async tabId=>{
      const [{result}]=await chrome.scripting.executeScript({target:{tabId},func:()=>{
        const preview=ViToxicPage.collect('viewport',{});
        ViToxicPage.apply(preview.token,preview.texts.map((_,i)=>({label:['CLEAN','OFFENSIVE','HATE'][i%3],confidence:.8})));
        return [...document.querySelectorAll('[data-vitoxic-label]')].map(n=>({label:n.dataset.vitoxicLabel,background:getComputedStyle(n.shadowRoot.querySelector('span')).backgroundColor}));
      }});return result;
    },targetTab.id);
    assert(colors.length===3&&new Set(colors.map(c=>c.background)).size===3,'All three label classes have distinct light backgrounds');
    await p.close();await target.bringToFront();await target.screenshot({path:'D:/MachineLearning/outputs/stage4/extension-auto-light.png',fullPage:false});
    await target.emulateMedia({colorScheme:'dark'});
    const darkColors=await target.locator('[data-vitoxic-label]').evaluateAll(nodes=>nodes.map(n=>({label:n.dataset.vitoxicLabel,background:getComputedStyle(n.shadowRoot.querySelector('span')).backgroundColor})));
    assert(darkColors.length===3&&new Set(darkColors.map(c=>c.background)).size===3&&darkColors.every((c,i)=>c.background!==colors[i].background),'All three label classes adapt to dark mode');
    await target.screenshot({path:'D:/MachineLearning/outputs/stage4/extension-auto-dark.png',fullPage:false});
    return {checks,requests:requests.length,colors,darkColors};
  }catch(error){throw new Error(`${error.message}\nCompleted checks: ${checks.join('; ')}\nRequests: ${JSON.stringify(requests)}\n${error.stack}`);}finally{await ctx.close();}
}
