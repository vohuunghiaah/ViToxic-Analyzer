'use strict';
const $=id=>document.getElementById(id);
let target=null,origin=null,sitePattern=null,preview=null,config={enabled:false},working=false;
function status(text){$('status').textContent=text;}
async function message(payload){const result=await chrome.runtime.sendMessage(payload);if(result?.error)throw new Error(result.error);return result;}
function showAPI(apiURL){$('api-url').value=apiURL;$('workspace-link').href=apiURL+'/workspace';}
$('save-api').onclick=async()=>{
  if(working)return;working=true;
  try{showAPI((await message({type:'setAPI',apiURL:$('api-url').value.trim()})).apiURL);status('Đã lưu địa chỉ API cho các lượt tiếp theo.');}
  catch(e){status(e.message);}finally{working=false;}
};
message({type:'getAPI'}).then(result=>showAPI(result.apiURL)).catch(e=>status(e.message));
async function engine(method,args=[]){
  const results=await chrome.scripting.executeScript({target:{tabId:target},func:(method,args)=>{
    try{return {value:globalThis.ViToxicPage[method](...args)};}catch(e){return {error:e.message};}
  },args:[method,args]});
  if(results[0]?.result?.error)throw new Error(results[0].result.error);
  if(!results[0]?.result)throw new Error('Không đọc được trang. Hãy tải lại trang và mở extension lại.');
  return results[0].result.value;
}
function inputConfig(){
  const value={selector:$('selector').value.trim(),exclude:$('exclude').value.trim()};
  for(const s of Object.values(value))if(s){if(s.length>1000)throw new Error('Selector quá dài.');try{document.querySelector(s);}catch{throw new Error('CSS selector không hợp lệ.');}}
  return value;
}
function sync(){ $('auto-toggle').textContent=config.enabled?'Tắt tự động trên website này':'Bật tự động trên website này';$('auto-toggle').setAttribute('aria-pressed',String(config.enabled)); }
async function autoStatus(){
  if(target===null||working)return;
  try{const s=await engine('status');$('auto-status').textContent=(s.auto?`Đang bật · ${s.count} nhãn${s.busy?' · Đang phân tích':''}`:'Tự động đang tắt')+(s.error?' — '+s.error:'')+(s.adapter?' · '+s.adapter:'');}catch(e){$('auto-status').textContent=e.message;}
}
async function configure(enabled){
  const fields=inputConfig();
  if(enabled&&!await chrome.permissions.request({origins:[sitePattern]}))throw new Error('Chưa được cấp quyền; tự động chưa bật.');
  config=(await message({type:'setSite',origin,enabled,...fields})).config;
  await chrome.scripting.executeScript({target:{tabId:target},files:['auto.js']});
  if(!enabled)await engine('stop',[true]);
  sync();preview=null;$('preview').replaceChildren();$('analyze').disabled=true;
  status(enabled?'Đã bật tự động cho website này, kể cả những lần tải trang sau.':'Đã tắt tự động và gỡ nhãn.');
}
$('auto-toggle').onclick=async()=>{if(working)return;working=true;try{await configure(!config.enabled);}catch(e){status(e.message);}finally{working=false;autoStatus();}};
$('save-settings').onclick=async()=>{if(working)return;working=true;try{await configure(config.enabled);status('Đã lưu cấu hình. Dùng xem trước để kiểm tra nội dung được lấy.');}catch(e){status(e.message);}finally{working=false;autoStatus();}};
async function collect(mode){
  if(working)return;working=true;preview=null;$('analyze').disabled=true;$('preview').replaceChildren();
  try{
    preview=await engine('collect',[mode,inputConfig()]);
    $('preview').replaceChildren(...preview.texts.map(text=>{const li=document.createElement('li');li.textContent=text;return li;}));
    status(`${preview.texts.length} comment riêng biệt · ${preview.adapter}.${preview.total>50?' Chỉ xem trước 50 comment đầu.':''} Khi bôi đen, lấy trọn phần nội dung của từng comment giao với vùng chọn.`);$('analyze').disabled=false;
  }catch(e){status(e.message);}finally{working=false;}
}
$('scan').onclick=()=>collect('viewport');$('selection').onclick=()=>collect('selection');
$('analyze').onclick=async()=>{
  if(!preview||working)return;working=true;const current=preview;
  document.querySelectorAll('button').forEach(b=>b.disabled=true);status('Đang phân tích danh sách…');
  try{
    const result=await message({type:'analyze',texts:current.texts});
    const applied=await engine('apply',[current.token,result.predictions]);
    status(`Đã gắn ${applied.attached} nhãn.${applied.skipped?` Bỏ qua ${applied.skipped} comment thay đổi hoặc không hợp lệ.`:''}`);
  }catch(e){status(e.message);}finally{working=false;document.querySelectorAll('button').forEach(b=>b.disabled=false);autoStatus();}
};
$('remove').onclick=async()=>{if(working)return;working=true;try{await configure(false);}catch(e){status(e.message);}finally{working=false;autoStatus();}};
(async()=>{
  try{
    const [tab]=await chrome.tabs.query({active:true,currentWindow:true});
    if(!tab?.id||!/^https?:\/\//.test(tab.url||''))throw new Error('Chỉ hỗ trợ trang HTTP/HTTPS thông thường.');
    const url=new URL(tab.url);target=tab.id;origin=url.origin;sitePattern=`${url.protocol}//${url.hostname}/*`;
    $('site-name').textContent=origin;
    config=(await message({type:'getSite',origin})).config;
    $('selector').value=config.selector||'';$('exclude').value=config.exclude||'';
    await chrome.scripting.executeScript({target:{tabId:target},files:['page.js']});
    if(config.enabled)await chrome.scripting.executeScript({target:{tabId:target},files:['auto.js']});
    sync();$('auto-toggle').disabled=false;autoStatus();
  }catch(e){status(e.message);document.querySelectorAll('button').forEach(b=>b.disabled=b.id!=='save-api');}
})();
setInterval(autoStatus,1500);
