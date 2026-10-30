'use strict';
const API='http://127.0.0.1:8001/predict/batch';
let inferenceTail=Promise.resolve(),queued=0,settingsTail=Promise.resolve();
function siteURL(value){const url=new URL(value);if(!['http:','https:'].includes(url.protocol)||url.username||url.password)throw new Error('Website không hợp lệ.');return url;}
function pattern(origin){const url=siteURL(origin);return `${url.protocol}//${url.hostname}/*`;}
async function scriptId(origin){const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(origin));return 'vitoxic-'+Array.from(new Uint8Array(bytes)).map(x=>x.toString(16).padStart(2,'0')).join('');}
async function permitted(origin){return chrome.permissions.contains({origins:[pattern(origin)]});}
async function setSite(message){
  const origin=siteURL(message.origin).origin;
  const {sites={}}=await chrome.storage.local.get('sites');
  const config={enabled:message.enabled===true,selector:String(message.selector||'').trim(),exclude:String(message.exclude||'').trim()};
  if(config.selector.length>1000||config.exclude.length>1000)throw new Error('Selector quá dài.');
  const id=await scriptId(origin),registered=await chrome.scripting.getRegisteredContentScripts({ids:[id]});
  if(config.enabled){
    if(!await permitted(origin))throw new Error('Chưa được cấp quyền cho website này.');
    const script={id,matches:[pattern(origin)],js:['page.js','auto.js'],runAt:'document_idle',persistAcrossSessions:true};
    if(registered.length)await chrome.scripting.updateContentScripts([script]);else await chrome.scripting.registerContentScripts([script]);
  }else if(registered.length)await chrome.scripting.unregisterContentScripts({ids:[id]});
  sites[origin]=config;await chrome.storage.local.set({sites});return {config};
}
async function authorizeAuto(sender){
  if(sender.id!==chrome.runtime.id||!sender.tab||sender.frameId!==0)throw new Error('Nguồn yêu cầu không hợp lệ.');
  const origin=siteURL(sender.url).origin;
  const {sites={}}=await chrome.storage.local.get('sites');
  if(!sites[origin]?.enabled||!await permitted(origin))throw new Error('Tự động chưa bật hoặc quyền truy cập đã bị thu hồi.');
}
async function infer(texts,auto){
  const limit=auto?8:50;
  if(!Array.isArray(texts)||!texts.length||texts.length>limit||texts.some(t=>typeof t!=='string'||!t.trim()||[...t].length>5000))throw new Error(`Cần 1–${limit} bình luận, tối đa 5.000 ký tự mỗi câu.`);
  async function request(batch){
    let response;
    for(let attempt=0;attempt<4;attempt++){
      response=await fetch(API,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({texts:batch}),signal:AbortSignal.timeout(25000)});
      if(response.status!==503||attempt===3)break;
      await new Promise(resolve=>setTimeout(resolve,1000));
    }
    if(response.status===422&&batch.length>1){const results=[];for(const text of batch)results.push(...await request([text]));return results;}
    if(response.status===422)return [{error:'Nội dung không hợp lệ sau chuẩn hóa.'}];
    if(!response.ok)throw new Error(response.status===503?'Model đang bận. Sẽ thử lại sau.':`API trả HTTP ${response.status}.`);
    const data=await response.json();
    if(data.predictions?.length!==batch.length||data.predictions.some(p=>!['CLEAN','OFFENSIVE','HATE'].includes(p.label)||!Number.isFinite(p.confidence)||p.confidence<0||p.confidence>1))throw new Error('API trả kết quả không hợp lệ.');
    return data.predictions;
  }
  const predictions=[];let batch=[],size=0;
  for(const text of texts){const n=[...text].length;if(batch.length===8||size+n>20000){predictions.push(...await request(batch));batch=[];size=0;}batch.push(text);size+=n;}
  if(batch.length)predictions.push(...await request(batch));return {predictions};
}
chrome.runtime.onMessage.addListener((message,sender,sendResponse)=>{
  const popup=sender.id===chrome.runtime.id&&sender.url===chrome.runtime.getURL('popup.html');
  if(!['analyze','autoAnalyze','getSite','setSite'].includes(message?.type))return;
  if(message.type!=='autoAnalyze'&&!popup)return;
  const task=async()=>{
    if(message.type==='getSite'){const {sites={}}=await chrome.storage.local.get('sites');return {config:sites[siteURL(message.origin).origin]||{enabled:false,selector:'',exclude:''}};}
    if(message.type==='setSite')return setSite(message);
    if(message.type==='autoAnalyze')await authorizeAuto(sender);
    return infer(message.texts,message.type==='autoAnalyze');
  };
  let promise;
  if(['analyze','autoAnalyze'].includes(message.type)){
    if(queued>=8){sendResponse({error:'Nhiều tab đang chờ phân tích. Sẽ thử lại sau.'});return;}
    queued++;promise=inferenceTail.then(task);inferenceTail=promise.catch(()=>{}).finally(()=>queued--);
  }else if(message.type==='setSite'){promise=settingsTail.then(task);settingsTail=promise.catch(()=>{});}
  else promise=task();
  promise.then(sendResponse,error=>sendResponse({error:error.name==='TimeoutError'?'API quá thời gian chờ. Kiểm tra Docker.':error instanceof TypeError?'Không kết nối được ViToxic tại 127.0.0.1:8001. Hãy khởi động Docker.':error.message}));
  return true;
});
async function reconcile(){
  const {sites={}}=await chrome.storage.local.get('sites');
  for(const [origin,config] of Object.entries(sites))if(config.enabled){
    try{await setSite({origin,...config,enabled:await permitted(origin)});}catch{/* Popup exposes configuration/permission failures on the next operation. */}
  }
}
chrome.runtime.onInstalled.addListener(()=>{settingsTail=settingsTail.then(reconcile).catch(()=>{});});
chrome.runtime.onStartup.addListener(()=>{settingsTail=settingsTail.then(reconcile).catch(()=>{});});
chrome.permissions.onRemoved.addListener(()=>{settingsTail=settingsTail.then(reconcile).catch(()=>{});});
