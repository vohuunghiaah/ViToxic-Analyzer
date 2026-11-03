// DOM adapter regression tests. Synthetic YouTube markup; no network/model calls.
// Run through Playwright browser_run_code_unsafe with this file as filename.
async (page) => {
  const ctx=await page.context().browser().newContext({viewport:{width:1100,height:900}});
  const checks=[];
  const assert=(value,name)=>{if(!value)throw new Error(name);checks.push(name);};
  try {
    await ctx.route('https://www.youtube.com/**',r=>r.fulfill({contentType:'text/html; charset=utf-8',body:`<!doctype html><html><head><style>
      body{font:16px system-ui;padding:24px}ytd-comment-thread-renderer,ytd-comment-view-model,ytd-comment-renderer{display:block;margin:16px;padding:12px;border:1px solid #aaa}#content-text{display:block}#replies{margin-left:40px}
      </style></head><body><h1>YouTube DOM fixture</h1><main>
      <ytd-comment-thread-renderer><ytd-comment-view-model><a id="author-text">@TenNguoiViet</a><time>2 giờ trước</time><yt-attributed-string id="content-text"><span>Cảm ơn <a>@ban</a> đã chia sẻ.</span></yt-attributed-string><button>Trả lời</button></ytd-comment-view-model>
      <div id="replies"><ytd-comment-view-model><a id="author-text">@TenNguoiTraLoi</a><yt-attributed-string id="content-text"><span>Mình đồng ý.</span><br><span>Chúc bạn vui vẻ.</span></yt-attributed-string><button>Thích</button></ytd-comment-view-model></div></ytd-comment-thread-renderer>
      <ytd-comment-renderer><a id="author-text">@TenCu</a><yt-formatted-string id="content-text">Bình luận cấu trúc cũ.</yt-formatted-string><button>Trả lời</button></ytd-comment-renderer>
      <ytd-comment-view-model hidden><a id="author-text">@An</a><span id="content-text">Bình luận ẩn.</span></ytd-comment-view-model>
      </main><aside><div class="comment-body">Nội dung ngoài comment YouTube.</div></aside></body></html>`}));
    const p=await ctx.newPage();await p.goto('https://www.youtube.com/watch?v=vitoxic-dom-fixture');
    await p.addScriptTag({path:'D:/MachineLearning/extension/page.js'});
    const preview=await p.evaluate(()=>ViToxicPage.collect('viewport',{}));
    assert(preview.adapter==='YouTube','YouTube adapter selected automatically');
    assert(JSON.stringify(preview.texts)===JSON.stringify(['Cảm ơn @ban đã chia sẻ.','Mình đồng ý. Chúc bạn vui vẻ.','Bình luận cấu trúc cũ.']),'Modern, legacy and reply comments split; usernames and controls excluded; in-content mention preserved');
    assert(!preview.texts.some(t=>t.includes('ẩn')||t.includes('ngoài')),'Hidden comments and unrelated generic content excluded');
    const selected=await p.evaluate(()=>{const nodes=document.querySelectorAll('ytd-comment-view-model');const r=document.createRange();r.setStartBefore(nodes[0]);r.setEndAfter(nodes[1]);getSelection().removeAllRanges();getSelection().addRange(r);return ViToxicPage.collect('selection',{});});
    assert(selected.texts.length===2&&selected.texts[1]===preview.texts[1],'Multi-comment selection separates parent and reply without splitting multiline text');
    const partial=await p.evaluate(()=>{const t=document.querySelector('#content-text span').firstChild;const r=document.createRange();r.setStart(t,0);r.setEnd(t,3);getSelection().removeAllRanges();getSelection().addRange(r);return ViToxicPage.collect('selection',{});});
    assert(partial.texts.length===1&&partial.texts[0]===preview.texts[0],'Partial selection returns the whole individual comment');
    await p.evaluate(()=>{const v=ViToxicPage.collect('viewport',{});ViToxicPage.apply(v.token,v.texts.map(()=>({label:'CLEAN',confidence:.9})));});
    assert(await p.locator('[data-vitoxic-label]').count()===3,'One label attached per comment and reply');
    await p.evaluate(()=>{document.querySelector('#content-text').textContent='Nội dung chỉnh sửa.';});
    await p.waitForFunction(()=>document.querySelectorAll('[data-vitoxic-label]').length===2);
    assert(true,'Edited YouTube comment drops its stale label');
    await p.evaluate(()=>{history.pushState({},'', '/watch?v=another-fixture');document.querySelector('main').innerHTML='<ytd-comment-view-model><a id="author-text">@TacGiaMoi</a><yt-attributed-string id="content-text">Bình luận video tiếp theo.</yt-attributed-string></ytd-comment-view-model>';});
    await p.waitForFunction(()=>document.querySelectorAll('[data-vitoxic-label]').length===0);
    const next=await p.evaluate(()=>ViToxicPage.collect('viewport',{}));
    assert(next.texts.length===1&&next.texts[0]==='Bình luận video tiếp theo.','SPA video navigation detects replacement comments without reloading');
    return {checks,fixture:true};
  } finally {await ctx.close();}
}
