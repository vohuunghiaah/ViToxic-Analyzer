/* Atomic optimistic concurrency for edits AND deletes across browser tabs. */
(function(root){
  'use strict';
  function writeSession(db, session, remove=false){
    return new Promise((resolve,reject)=>{
      if(!db){reject(new Error('Bộ nhớ chưa sẵn sàng.'));return;}
      const updated={...session,updatedAt:new Date().toISOString(),revision:(session.revision||0)+1};
      const tx=db.transaction('sessions','readwrite'),store=tx.objectStore('sessions'),get=store.get(session.id);
      let conflict=false;
      get.onsuccess=()=>{
        const stored=get.result;
        // Missing records may only be created by a new session, never a stale tab.
        if((!stored && (remove || session.revision)) || (stored && (!session.revision || stored.revision!==session.revision))){
          conflict=true;tx.abort();return;
        }
        if(remove)store.delete(session.id);else store.put(updated);
      };
      tx.oncomplete=()=>resolve(updated);
      tx.onerror=tx.onabort=()=>reject(new Error(conflict
        ?'Phiên đã thay đổi hoặc bị xóa ở tab khác. Xuất JSON nếu cần giữ thay đổi rồi tải lại trang.'
        :'Không lưu được dữ liệu. Hãy sao lưu JSON và kiểm tra dung lượng trình duyệt.'));
    });
  }
  if(typeof module!=='undefined')module.exports={writeSession};else root.ViToxicStorage={writeSession};
})(globalThis);
