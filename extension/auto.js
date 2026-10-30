(() => {
  if(globalThis.__vitoxicAutoBootstrap)return;
  globalThis.__vitoxicAutoBootstrap=true;
  let previous='';
  async function refresh(){
    try{
      const {sites={}}=await chrome.storage.local.get('sites');
      const config=sites[location.origin],key=JSON.stringify(config||null);
      if(key===previous)return;previous=key;
      if(config?.enabled)globalThis.ViToxicPage.start(config);else globalThis.ViToxicPage.stop(true);
    }catch{globalThis.ViToxicPage.stop(true);}
  }
  chrome.storage.onChanged.addListener((changes,area)=>{if(area==='local'&&changes.sites)refresh();});refresh();
})();
