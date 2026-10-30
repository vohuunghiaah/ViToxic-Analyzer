'use strict';
const D = window.ViToxicData;
const $ = id => document.getElementById(id);
const labelNames = {CLEAN:'Bình thường', OFFENSIVE:'Xúc phạm', HATE:'Thù ghét'};
const statusNames = {pending:'Chờ duyệt', flagged:'Cần xem xét', reviewed:'Đã duyệt'};
const fmt = new Intl.NumberFormat('vi-VN');
const pct = n => (n * 100).toLocaleString('vi-VN', {maximumFractionDigits:1}) + '%';
const titles = {overview:'Tổng quan', import:'Nhập dữ liệu', review:'Kiểm duyệt', history:'Lịch sử', integration:'Extension & tích hợp'};
let db, sessions = [], active = null, parsed = null, page = 1, running = false, pause = false, editing = null;
let fileVersion = 0, storageFailed = false;
let importing = false;
function el(tag, cls, text) { const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n; }
function message(text, error=false) { $('desk-message').textContent=text;$('desk-message').hidden=!text;$('desk-message').dataset.error=String(error); }
function openDB() {
  return new Promise((resolve,reject)=>{
    const request=indexedDB.open('vitoxic-workspace',1);
    request.onupgradeneeded=()=>request.result.createObjectStore('sessions',{keyPath:'id'});
    request.onsuccess=()=>{request.result.onversionchange=()=>request.result.close();resolve(request.result);};
    request.onerror=()=>reject(new Error('Không mở được bộ nhớ trình duyệt. Kiểm tra chế độ riêng tư hoặc quyền lưu dữ liệu.'));
  });
}
function transaction(action, value) {
  if(!db)return Promise.reject(new Error('Bộ nhớ chưa sẵn sàng. Hãy tải lại trang.'));
  return new Promise((resolve,reject)=>{
    const tx=db.transaction('sessions',action==='getAll'?'readonly':'readwrite');
    const store=tx.objectStore('sessions'); const req=value===undefined?store[action]():store[action](value);
    tx.oncomplete=()=>resolve(req.result);
    tx.onerror=tx.onabort=()=>reject(new Error('Không lưu được dữ liệu. Hãy xuất JSON để sao lưu và kiểm tra dung lượng trình duyệt.'));
  });
}
async function persist(session) {
  const updated={...session,updatedAt:new Date().toISOString(),revision:(session.revision||0)+1};
  try {
    await new Promise((resolve,reject)=>{
      if(!db){reject(new Error('Bộ nhớ chưa sẵn sàng.'));return;}
      const tx=db.transaction('sessions','readwrite'),store=tx.objectStore('sessions'),get=store.get(session.id);
      let conflict=false;
      get.onsuccess=()=>{
        if((get.result?.revision||0)!==(session.revision||0)){conflict=true;tx.abort();return;}
        store.put(updated);
      };
      tx.oncomplete=resolve;
      tx.onerror=tx.onabort=()=>reject(new Error(conflict?'Phiên đã thay đổi ở tab khác. Xuất JSON nếu cần giữ thay đổi rồi tải lại trang.':'Không lưu được dữ liệu. Hãy sao lưu JSON và kiểm tra dung lượng trình duyệt.'));
    });
    Object.assign(session,updated);storageFailed=false;
  }
  catch(error){storageFailed=true;throw error;}
  const index=sessions.findIndex(s=>s.id===session.id);
  if(index<0)sessions.push(session);else sessions[index]=session;
}
function download(name, content, type) {
  const url=URL.createObjectURL(new Blob([content],{type}));const link=el('a');link.href=url;link.download=name;
  document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function sortedSessions(){return [...sessions].sort((a,b)=>b.updatedAt.localeCompare(a.updatedAt));}
function sessionCounts(s){return {total:s.rows.length,done:s.rows.filter(r=>r.prediction).length,reviewed:s.rows.filter(r=>r.status==='reviewed').length};}
function renderDashboard(){
  const rows=sessions.flatMap(s=>s.rows),done=rows.filter(r=>r.prediction);
  const stats=[['Phiên dữ liệu',sessions.length],['Bình luận',rows.length],['Đã phân tích',done.length],['Chờ / cần xem xét',rows.filter(r=>r.status!=='reviewed').length]];
  $('stats').replaceChildren(...stats.map(([title,n])=>{const card=el('div','stat');card.append(el('span','',title),el('strong','',fmt.format(n)));return card;}));
  $('distribution').replaceChildren(...D.LABELS.map(label=>{
    const count=done.filter(r=>r.prediction.label===label).length,ratio=done.length?count/done.length:0;
    const row=el('div','distribution-row'),heading=el('div');heading.append(el('span','',labelNames[label]),el('span','',`${count} · ${pct(ratio)}`));
    const track=el('div','probability-track'),fill=el('div',`probability-fill ${label.toLowerCase()}`);fill.style.width=`${ratio*100}%`;track.append(fill);row.append(heading,track);return row;
  }));
  $('recent-sessions').replaceChildren(...sortedSessions().slice(0,4).map(s=>{
    const row=el('div','recent-row'),info=el('div');info.append(el('strong','',s.name),el('p','',`${s.rows.length} bình luận`));
    const button=el('button','secondary-button','Mở');button.onclick=()=>selectSession(s.id);row.append(info,button);return row;
  }));
  if(!sessions.length)$('recent-sessions').append(el('p','empty-list','Chưa có phiên. Nhập CSV để bắt đầu.'));
}
function navigate(){
  const view=location.hash.slice(1) in titles?location.hash.slice(1):'overview';
  Object.keys(titles).forEach(key=>{$('view-'+key).hidden=key!==view;document.querySelector(`[data-view="${key}"]`).setAttribute('aria-current',key===view?'page':'false');});
  $('view-title').textContent=titles[view];
  if(view==='overview')renderDashboard();if(view==='history')renderHistory();if(view==='review')renderReview();
}
function selectSession(id){
  if(running && active?.id!==id){message('Hãy dừng phân tích phiên hiện tại trước khi mở phiên khác.',true);return;}
  if(storageFailed){message('Dữ liệu chưa lưu được. Hãy sao lưu JSON và tải lại trang trước khi đổi phiên.',true);return;}
  active=sessions.find(s=>s.id===id);page=1;
  ['search-comments','label-filter','status-filter'].forEach(id=>$(id).value='');$('confidence-filter').value='1';
  location.hash='review';renderReview();
}
function renderHistory(){
  $('history-list').replaceChildren(...sortedSessions().map(s=>{
    const count=sessionCounts(s),row=el('article','history-row'),info=el('div'),actions=el('div','toolbar');
    info.append(el('h3','',s.name),el('p','',`${count.total} bình luận · ${count.done} đã phân tích · ${count.reviewed} đã duyệt`),el('p','',new Date(s.updatedAt).toLocaleString('vi-VN')));
    const open=el('button','secondary-button','Mở phiên');open.onclick=()=>selectSession(s.id);
    const remove=el('button','secondary-button danger-button','Xóa');remove.disabled=running;remove.onclick=async()=>{
      if(!confirm(`Xóa phiên “${s.name}” và các nhãn duyệt? Hãy sao lưu JSON trước nếu cần giữ dữ liệu.`))return;
      try{await transaction('delete',s.id);sessions=sessions.filter(item=>item.id!==s.id);if(active?.id===s.id)active=null;renderHistory();message('Đã xóa phiên.');}catch(e){message(e.message,true);}
    };
    actions.append(open,remove);row.append(info,actions);return row;
  }));
  if(!sessions.length)$('history-list').append(el('p','empty-list','Chưa có phiên đã lưu.'));
}
function filteredRows(){
  const query=$('search-comments').value.toLocaleLowerCase('vi'),label=$('label-filter').value,status=$('status-filter').value,max=Number($('confidence-filter').value);
  return (active?.rows||[]).filter(r=>r.text.toLocaleLowerCase('vi').includes(query)
    && (!label || (label==='unprocessed'?!r.prediction:r.prediction?.label===label))
    && (!status||r.status===status) && (max===1 || (r.prediction && r.prediction.confidence<=max)));
}
function pill(label){const node=el('span','pill',labelNames[label]||'Chưa phân tích');node.dataset.label=label||'';return node;}
function renderReview(){
  const count=active?sessionCounts(active):null;
  $('active-name').textContent=active?.name||'Chưa chọn phiên';
  $('active-info').textContent=count?`${count.total} bình luận · ${count.done} đã phân tích · ${count.reviewed} đã duyệt`:'Tạo phiên mới hoặc mở phiên trong lịch sử.';
  $('resume-run').disabled=!active||running||count?.done===count?.total||storageFailed;
  $('export-csv').disabled=$('export-json').disabled=!active;
  const rows=filteredRows(),pages=Math.max(1,Math.ceil(rows.length/20));page=Math.min(page,pages);
  $('review-rows').replaceChildren(...rows.slice((page-1)*20,page*20).map(r=>{
    const tr=el('tr');tr.append(el('td','',r.id));const text=el('td');text.append(el('div','comment-excerpt',r.text));if(r.error)text.append(el('small','',r.error));
    const pred=el('td');pred.append(pill(r.prediction?.label));if(r.prediction)pred.append(el('small','',pct(r.prediction.confidence)+(r.prediction.truncated?' · Rút gọn':'')));
    const reviewed=el('td');reviewed.append(r.reviewLabel?pill(r.reviewLabel):document.createTextNode('—'));
    const action=el('td'),button=el('button','secondary-button','Xem / duyệt');button.disabled=running;button.onclick=()=>openReview(r);action.append(button);
    tr.append(text,pred,reviewed,el('td','',statusNames[r.status]),action);return tr;
  }));
  if(!rows.length){const tr=el('tr'),td=el('td','empty-list',active?'Không có bình luận khớp bộ lọc.':'Chưa chọn phiên dữ liệu.');td.colSpan=6;tr.append(td);$('review-rows').append(tr);}
  $('page-info').textContent=`${rows.length} kết quả · Trang ${page}/${pages}`;$('prev-page').disabled=page<=1;$('next-page').disabled=page>=pages;
}
function openReview(row){
  editing=row;$('dialog-title').textContent=`Bình luận #${row.id}`;$('dialog-text').textContent=row.text;
  $('dialog-prediction').textContent=row.prediction?`Mô hình: ${row.prediction.label} (${pct(row.prediction.confidence)}). ${D.LABELS.map(k=>k+': '+pct(row.prediction.probabilities[k])).join(' · ')}. ${row.prediction.truncated?'Văn bản đã bị rút gọn; cần đọc đầy đủ ngữ cảnh.':''}`:'Chưa có dự đoán. Bạn vẫn có thể gán nhãn thủ công.';
  $('review-status').value=row.status;$('review-label').value=row.reviewLabel||'';$('review-note').value=row.note;$('review-error').textContent='';$('review-dialog').showModal();
}
$('close-dialog').onclick=()=>$('review-dialog').close();
$('review-label').onchange=()=>{if($('review-label').value)$('review-status').value='reviewed';};
$('review-status').onchange=()=>{if($('review-status').value!=='reviewed')$('review-label').value='';};
$('review-form').onsubmit=async event=>{
  event.preventDefault();const status=$('review-status').value,label=$('review-label').value;
  if(status==='reviewed'&&!label){$('review-error').textContent='Chọn nhãn xác nhận trước khi đánh dấu đã duyệt.';return;}
  const updated=structuredClone(active),row=updated.rows.find(r=>r.id===editing.id);
  row.status=status;row.reviewLabel=status==='reviewed'?label:null;row.note=$('review-note').value;
  try{await persist(updated);active=updated;$('review-dialog').close();renderReview();message('Đã lưu quyết định. Nhãn mô hình được giữ nguyên.');}catch(e){$('review-error').textContent=e.message;}
};
function previewColumn(){
  if(!parsed)return;const index=Number($('text-column').value);
  $('preview-count').textContent=`${parsed.rows.length} bình luận · Xem trước 5 hàng đầu`;
  $('preview-lines').replaceChildren(...parsed.rows.slice(0,5).map(r=>el('li','',r[index])));
}
async function readFile(){
  const version=++fileVersion;parsed=null;$('csv-preview').hidden=true;
  const file=$('csv-file').files[0];if(!file)return;
  try{
    if(file.size>2*1024*1024)throw new Error('File CSV vượt 2 MB. Hãy chia nhỏ file.');
    const text=new TextDecoder('utf-8',{fatal:true}).decode(await file.arrayBuffer());
    if(version!==fileVersion)return;
    parsed=D.parseCSV(text,$('delimiter').value==='tab'?'\t':$('delimiter').value);
    $('text-column').replaceChildren(...parsed.headers.map((h,i)=>{const o=el('option','',h);o.value=i;return o;}));
    const guess=parsed.headers.findIndex(h=>/^(text|comment|content|bình luận|nội dung)$/i.test(h.trim()));if(guess>=0)$('text-column').value=guess;
    if(!$('session-name').value)$('session-name').value=file.name.replace(/\.csv$/i,'').slice(0,120);
    $('csv-preview').hidden=false;previewColumn();message('Đã đọc CSV. Kiểm tra cột và nội dung trước khi phân tích.');
  }catch(e){if(version===fileVersion)message(e instanceof TypeError?'File không phải UTF-8. Hãy xuất CSV UTF-8 từ Excel.':e.message,true);}
}
$('csv-file').onchange=readFile;$('delimiter').onchange=readFile;$('text-column').onchange=previewColumn;
$('clear-file').onclick=()=>{fileVersion++;$('csv-file').value='';parsed=null;$('csv-preview').hidden=true;};
$('sample-csv').onclick=()=>download('vitoxic-sample.csv','\uFEFFid,comment\r\n1,"Cảm ơn bạn, bài viết rất hữu ích!"\r\n2,"Mình không đồng ý với quan điểm này."','text/csv;charset=utf-8');
async function newSession(payload){
  if(running)throw new Error('Hãy dừng phiên đang chạy trước.');
  if(storageFailed)throw new Error('Phiên hiện tại chưa lưu được. Hãy sao lưu JSON và tải lại trang trước khi tạo phiên mới.');
  const now=new Date().toISOString(),session={...payload,id:crypto.randomUUID(),createdAt:now,updatedAt:now};
  await persist(session);active=session;selectSession(session.id);return session;
}
$('create-session').onclick=async()=>{
  if(importing)return;
  if(running){message('Hãy dừng phiên đang chạy trước.',true);return;}
  importing=true;$('create-session').disabled=true;
  try{
    let texts;
    if($('csv-file').files.length){if(!parsed)throw new Error('CSV chưa hợp lệ hoặc chưa đọc xong.');texts=parsed.rows.map(r=>r[Number($('text-column').value)]);}
    else texts=$('paste-comments').value.split(/\r?\n/).filter(t=>t.trim());
    D.validateTexts(texts);
    await newSession({schema:1,name:$('session-name').value.trim()||'Phiên '+new Date().toLocaleString('vi-VN'),model:null,
      rows:texts.map((text,i)=>({id:i+1,text,prediction:null,status:'pending',reviewLabel:null,note:'',error:''}))});
    await runAnalysis();
  }catch(e){message(e.message,true);}finally{importing=false;$('create-session').disabled=running;}
};
$('restore-file').onchange=async()=>{
  const file=$('restore-file').files[0];if(!file)return;
  if(importing||running){message('Hãy chờ phiên hiện tại hoàn tất hoặc dừng trước khi khôi phục.',true);$('restore-file').value='';return;}
  importing=true;
  try{if(file.size>10*1024*1024)throw new Error('File JSON vượt 10 MB.');await newSession(D.importSession(JSON.parse(await file.text())));message('Đã khôi phục thành một phiên mới.');}catch(e){message(e instanceof SyntaxError?'JSON không hợp lệ.':e.message,true);}finally{importing=false;$('restore-file').value='';}
};
async function api(path,payload){
  for(let attempt=0;attempt<4;attempt++){
    const response=await fetch(path,{method:payload?'POST':'GET',headers:payload?{'Content-Type':'application/json'}:{},body:payload?JSON.stringify(payload):undefined,signal:AbortSignal.timeout(120000),cache:'no-store'});
    if(response.status===503&&attempt<3){await new Promise(resolve=>setTimeout(resolve,1000*(attempt+1)));continue;}
    if(!response.ok){const e=new Error(response.status===503?'Mô hình đang bận. Bấm phân tích phần còn lại để thử lại.':response.status===422?'Nội dung không hợp lệ sau chuẩn hóa.':`Dịch vụ trả HTTP ${response.status}. Thử lại khi dịch vụ sẵn sàng.`);e.status=response.status;throw e;}
    return response.json();
  }
}
async function predictRows(rows){
  try{
    const result=await api('/predict/batch',{texts:rows.map(r=>r.text)});
    if(result.predictions?.length!==rows.length||!result.predictions.every(D.validPrediction))throw new Error('Kết quả API không hợp lệ.');
    rows.forEach((row,i)=>{row.prediction=result.predictions[i];row.error='';});
  }catch(e){
    if(e.status!==422)throw e;
    // Isolate invalid normalized text so one bad row does not discard a whole batch.
    for(const row of rows){
      if(pause)break;
      try{const result=await api('/predict',{text:row.text});if(!D.validPrediction(result))throw new Error('Kết quả API không hợp lệ.');row.prediction=result;row.error='';}
      catch(error){if(error.status!==422)throw error;row.error=error.message;}
    }
  }
}
async function runAnalysis(){
  if(!active||running||storageFailed)return;
  running=true;pause=false;$('run-banner').hidden=false;$('pause-run').disabled=false;$('create-session').disabled=true;
  message('Đang xử lý theo từng lượt nhỏ. Giữ tab này mở; mỗi lượt hoàn tất được lưu ngay.');renderReview();
  try{
    await navigator.locks.request('vitoxic-analysis',{ifAvailable:true},async lock=>{
      if(!lock)throw new Error('Một tab khác đang phân tích. Hãy chờ tab đó hoàn tất.');
      const metadata=await api('/model');
      if(active.model?.checkpoint_sha256 && active.model.checkpoint_sha256!==metadata.checkpoint_sha256)throw new Error('Model đã thay đổi. Hãy tạo phiên mới để không trộn kết quả của các model.');
      active.model={run:metadata.run,checkpoint_sha256:metadata.checkpoint_sha256};await persist(active);
      const pending=active.rows.filter(r=>!r.prediction);
      for(const batch of D.chunks(pending)){
        if(pause)break;
        const done=active.rows.filter(r=>r.prediction).length;
        $('run-progress').textContent=`${done}/${active.rows.length} đã phân tích · Đang xử lý ${batch.length} câu`;
        await predictRows(batch);await persist(active);renderReview();
      }
      const count=sessionCounts(active),errors=active.rows.filter(r=>r.error).length;
      message(`${pause?'Đã dừng và lưu tiến độ':'Đã xử lý phiên'}: ${count.done}/${count.total} có kết quả${errors?`; ${errors} câu không hợp lệ`:''}.`);
    });
  }catch(e){
    if(!storageFailed){try{await persist(active);}catch(storageError){message(storageError.message,true);}}
    if(!storageFailed)message(e.name==='TimeoutError'?'Hết thời gian chờ. Tiến độ đã lưu; có thể tiếp tục sau.':e.message||'Không kết nối được API.',true);
    else message('Không lưu được tiến độ. Hãy sao lưu JSON ngay trước khi đóng trang.',true);
  }finally{running=false;$('run-banner').hidden=true;$('create-session').disabled=false;renderReview();checkReady();}
}
$('resume-run').onclick=runAnalysis;$('pause-run').onclick=()=>{pause=true;$('pause-run').disabled=true;$('run-progress').textContent='Đang chờ lượt hiện tại hoàn tất và lưu…';};
window.addEventListener('beforeunload',event=>{if(running||storageFailed){event.preventDefault();event.returnValue='';}});
$('export-csv').onclick=()=>{if(active)download('vitoxic-reviewed.csv',D.exportCSV(active),'text/csv;charset=utf-8');};
$('export-json').onclick=()=>{if(active)download('vitoxic-session.json',JSON.stringify(active,null,2),'application/json');};
['search-comments','label-filter','status-filter','confidence-filter'].forEach(id=>$(id).addEventListener('input',()=>{page=1;renderReview();}));
$('prev-page').onclick=()=>{page--;renderReview();};$('next-page').onclick=()=>{page++;renderReview();};
$('desk-theme').onclick=()=>{const theme=document.documentElement.dataset.theme==='dark'?'light':'dark';document.documentElement.dataset.theme=theme;try{localStorage.setItem('vitoxic-theme',theme);}catch{}};
async function checkReady(){try{const r=await fetch('/ready',{cache:'no-store',signal:AbortSignal.timeout(5000)});if(!r.ok)throw new Error();const d=await r.json();$('connection').textContent=d.busy?'Mô hình đang bận':'Mô hình sẵn sàng';}catch{$('connection').textContent='API chưa kết nối';}}
window.addEventListener('hashchange',navigate);
window.addEventListener('focus',async()=>{if(db&&!running&&!storageFailed&&!$('review-dialog').open){try{sessions=await transaction('getAll');if(active)active=sessions.find(s=>s.id===active.id)||null;navigate();}catch(e){message(e.message,true);}}});
(async()=>{try{db=await openDB();sessions=await transaction('getAll');navigate();}catch(e){message(e.message,true);$('create-session').disabled=true;}checkReady();})();
setInterval(()=>{if(!document.hidden&&!running)checkReady();},30000);
