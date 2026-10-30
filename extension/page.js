/* Isolated content-script world; no site JavaScript or private fields are read. */
(() => {
  'use strict';
  if (globalThis.ViToxicPage?.version === 2) return;
  globalThis.__vitoxicLocalReviewV1?.observer?.disconnect();
  globalThis.__vitoxicLocalReviewV1?.badges?.forEach(b => b.remove());
  const excluded = '[data-vitoxic-label],script,style,button,input,textarea,select,time,[hidden],[aria-hidden="true"],'
    + '[itemprop="author"],.comment-author,.comment__author,.comment-user,.username,.author,.author-name,'
    + '.comment-actions,.comment-meta,.comment-metadata,.comment-timestamp,.reply-button,.vote-count';
  const containers = '.comment,[data-comment-id],shreddit-comment,ytd-comment-view-model,ytd-comment-renderer';
  const adapters = [
    { name: 'YouTube', host: /(^|\.)youtube\.com$/, selector: 'ytd-comment-view-model #content-text, ytd-comment-renderer #content-text' },
    { name: 'Reddit', host: /(^|\.)reddit\.com$/, selector: 'shreddit-comment [slot="comment"], .thing.comment > .entry > .usertext > .usertext-body' },
    { name: 'Nội dung bình luận có cấu trúc', selector: '[data-comment-body],[data-comment-text],.demo-comment,.comment-body,.comment-content,.comment-text,.comment__body,[itemprop="comment"] [itemprop="text"]' }
  ];
  const state = { config: {}, auto: false, generation: 0, busy: false, records: new Map(), cache: new Map(),
    preview: null, error: '', adapter: '', timer: null, observer: null, nextTry: 0, failures: 0 };
  function validateSelectors(config) {
    for (const selector of [config.selector, config.exclude]) if (typeof selector === 'string' && selector.trim()) {
      if (selector.length > 1000) throw new Error('Selector quá dài (tối đa 1.000 ký tự).');
      try { document.querySelector(selector); } catch { throw new Error('CSS selector không hợp lệ.'); }
    }
  }
  function visible(node, viewport) {
    if (!(node instanceof HTMLElement) || node.closest('[data-vitoxic-label],input,textarea,select,[contenteditable]:not([contenteditable="false"]),[hidden],[aria-hidden="true"]')) return false;
    if (['BODY','HTML','SCRIPT','STYLE','IFRAME'].includes(node.tagName)) return false;
    const style = getComputedStyle(node), rect = node.getBoundingClientRect();
    if (!node.getClientRects().length || style.visibility === 'hidden' || style.display === 'none' || style.opacity === '0') return false;
    return !viewport || (rect.bottom > 0 && rect.right > 0 && rect.top < innerHeight && rect.left < innerWidth);
  }
  function readText(node, config) {
    const rules = config.exclude?.trim() ? excluded + ',' + config.exclude : excluded;
    if (node.matches(rules)) return '';
    const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT), base=node.closest(containers);
    const parts = []; let text;
    while ((text = walker.nextNode())) {
      const parent = text.parentElement;
      if (!parent || parent.closest(rules)) continue;
      const nested=parent.closest(containers);
      if(nested && nested!==base && node.contains(nested))continue;
      const range=document.createRange();range.selectNodeContents(text);
      if(!range.getClientRects().length || getComputedStyle(parent).visibility==='hidden')continue;
      parts.push(text.nodeValue);
    }
    return parts.join(' ').replace(/\s+/g, ' ').trim();
  }
  function discover(config = {}, viewport = false) {
    validateSelectors(config);
    let nodes = [], name = '';
    const candidates = config.selector?.trim() ? [{name:'Cấu hình website',selector:config.selector}] : adapters;
    for (const adapter of candidates) {
      if (adapter.host && !adapter.host.test(location.hostname)) continue;
      nodes = Array.from(document.querySelectorAll(adapter.selector));
      if (nodes.length) { name = adapter.name; break; }
    }
    if (nodes.length > 5000) throw new Error('Selector quá rộng; hãy chọn riêng phần nội dung bình luận.');
    const set = new Set(nodes);
    nodes = nodes.filter(node => { for (let p=node.parentElement;p;p=p.parentElement) if(set.has(p)&&p.closest(containers)===node.closest(containers)) return false; return true; });
    const items = nodes.filter(node => visible(node, viewport)).map(node => ({node,text:readText(node,config)})).filter(item=>item.text);
    state.adapter = name || 'Chưa nhận diện được website';
    return items;
  }
  function collect(mode, config = {}) {
    const items = discover(config, false);
    let selected;
    if (mode === 'selection') {
      const selection = getSelection();
      if (!selection?.rangeCount || selection.isCollapsed) throw new Error('Hãy bôi đen các bình luận cần phân tích trước.');
      const range = selection.getRangeAt(0);
      selected = items.filter(item => range.intersectsNode(item.node));
      if (!selected.length) throw new Error('Không xác định được ranh giới bình luận trong vùng bôi đen. Hãy cấu hình selector phần nội dung; không gộp tên và nhiều bình luận thành một câu.');
    } else selected = items.filter(item => visible(item.node, true));
    if (!selected.length) throw new Error('Chưa tìm thấy nội dung bình luận trong màn hình. Cuộn đến comment hoặc cấu hình selector cho website này.');
    const total = selected.length; selected = selected.slice(0,50);
    if (selected.some(item=>[...item.text].length>5000)) throw new Error('Có bình luận vượt 5.000 ký tự. Hãy thu hẹp selector về phần nội dung.');
    const token = crypto.randomUUID(); state.preview = {token,items:selected,config:{...config}};
    return {token,texts:selected.map(item=>item.text),total,adapter:state.adapter};
  }
  function removeRecord(node) { const old=state.records.get(node);old?.badge?.remove();state.records.delete(node); }
  function attach(item, prediction, config) {
    removeRecord(item.node);
    if (!['CLEAN','OFFENSIVE','HATE'].includes(prediction?.label) || !Number.isFinite(prediction.confidence)) return;
    const names={CLEAN:'Bình thường',OFFENSIVE:'Xúc phạm',HATE:'Thù ghét'},icons={CLEAN:'✓',OFFENSIVE:'!',HATE:'×'};
    const badge=document.createElement('span');badge.setAttribute('data-vitoxic-label',prediction.label);
    badge.style.setProperty('display','inline-block','important');
    const shadow=badge.attachShadow({mode:'open'}),style=document.createElement('style'),text=document.createElement('span');
    style.textContent=`:host{all:initial;display:inline-block}span{display:inline-flex;align-items:center;gap:6px;font:600 12px/1.6 system-ui,sans-serif;padding:4px 10px;margin:5px 0;border:1px solid;border-radius:7px;box-sizing:border-box}.CLEAN{color:#14532d;background:#dcfce7;border-color:#4ade80}.OFFENSIVE{color:#78350f;background:#fef3c7;border-color:#f59e0b}.HATE{color:#881337;background:#ffe4e6;border-color:#fb7185}@media(prefers-color-scheme:dark){.CLEAN{color:#bbf7d0;background:#143524;border-color:#4ade80}.OFFENSIVE{color:#fde68a;background:#422b0c;border-color:#fbbf24}.HATE{color:#fecdd3;background:#451723;border-color:#fb7185}}`;
    text.className=prediction.label;
    text.textContent=`${icons[prediction.label]} ViToxic · ${names[prediction.label]} · ${(prediction.confidence*100).toFixed(1)}%${prediction.truncated?' · Đã rút gọn':''}`;
    text.title='Điểm dự đoán chưa hiệu chỉnh. Cần người xem xét ngữ cảnh.';
    shadow.append(style,text);item.node.after(badge);state.records.set(item.node,{text:item.text,badge,config:{...config}});observe();
  }
  function cleanup() {
    for(const [node,record] of state.records) if(!node.isConnected || readText(node,record.config)!==record.text || (record.badge&&!record.badge.isConnected)) removeRecord(node);
  }
  function observe() {
    if(state.observer)return;
    state.observer=new MutationObserver(mutations=>{
      const relevant=mutations.some(m=>!m.target.closest?.('[data-vitoxic-label]') && (m.type!=='childList'||Array.from([...m.addedNodes,...m.removedNodes]).some(n=>!(n.nodeType===1&&n.hasAttribute('data-vitoxic-label')))));
      if(!relevant)return;cleanup();schedule();
    });
    state.observer.observe(document.body,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['hidden','aria-hidden','class','style']});
  }
  function apply(token, predictions) {
    const preview=state.preview;
    if(!preview||preview.token!==token||preview.items.length!==predictions.length)throw new Error('Nội dung xem trước đã thay đổi. Hãy lấy lại bình luận.');
    let attached=0;
    preview.items.forEach((item,i)=>{
      if(item.node.isConnected && readText(item.node,preview.config)===item.text){attach(item,predictions[i],preview.config);if(predictions[i]?.label)attached++;}
    });
    return {attached,skipped:predictions.length-attached};
  }
  function schedule(delay=350) {
    if(!state.auto||state.timer)return;
    state.timer=setTimeout(()=>{state.timer=null;tick();},delay);
  }
  async function tick() {
    if(!state.auto||state.busy||document.hidden)return;
    if(Date.now()<state.nextTry){schedule(Math.max(1000,state.nextTry-Date.now()));return;}
    state.busy=true;const generation=state.generation,config={...state.config};
    try{
      cleanup();const all=discover(config,true),pending=[];
      for(const item of all){
        if(state.records.has(item.node))continue;
        if([...item.text].length>5000){state.records.set(item.node,{text:item.text,config,error:true});state.error='Bỏ qua bình luận vượt 5.000 ký tự.';continue;}
        const cached=state.cache.get(item.text);
        if(cached&&Date.now()-cached.at<300000){attach(item,cached.prediction,config);continue;}
        pending.push(item);if(pending.length===8)break;
      }
      if(!all.length)state.error='Chưa có bình luận được nhận diện trong màn hình. Cuộn đến comment hoặc cấu hình selector.';
      if(pending.length){
        const result=await chrome.runtime.sendMessage({type:'autoAnalyze',texts:pending.map(item=>item.text)});
        if(generation!==state.generation||!state.auto)return;
        if(result?.error)throw new Error(result.error);
        if(result?.predictions?.length!==pending.length)throw new Error('Kết quả API không hợp lệ.');
        state.error='';state.failures=0;
        pending.forEach((item,i)=>{
          if(!item.node.isConnected||readText(item.node,config)!==item.text)return;
          const prediction=result.predictions[i];
          if(prediction.error){state.records.set(item.node,{text:item.text,config,error:true});state.error='Một số bình luận không hợp lệ sau chuẩn hóa.';return;}
          state.cache.set(item.text,{prediction,at:Date.now()});if(state.cache.size>500)state.cache.delete(state.cache.keys().next().value);
          attach(item,prediction,config);
        });schedule(500);
      }
    }catch(error){state.error=error.message;state.failures++;state.nextTry=Date.now()+Math.min(60000,5000*2**Math.min(state.failures,4));schedule(state.nextTry-Date.now());}
    finally{state.busy=false;}
  }
  function start(config={}) {
    validateSelectors(config);state.generation++;state.config={...config};state.auto=true;state.error='';state.nextTry=0;
    clearTimeout(state.timer);state.timer=null;clearLabels();observe();schedule(50);return status();
  }
  function stop(clear=false) {state.auto=false;state.generation++;clearTimeout(state.timer);state.timer=null;state.nextTry=0;if(clear)clearLabels();return status();}
  function clearLabels(){for(const node of state.records.keys())removeRecord(node);state.preview=null;}
  function status(){return {auto:state.auto,busy:state.busy,count:Array.from(state.records.values()).filter(r=>r.badge?.isConnected).length,error:state.error,adapter:state.adapter};}
  for(const event of ['scroll','resize','visibilitychange'])addEventListener(event,()=>schedule(),{passive:true});
  setInterval(()=>schedule(),3000);
  globalThis.ViToxicPage={version:2,collect,apply,start,stop,status,clearLabels,discover};
})();
