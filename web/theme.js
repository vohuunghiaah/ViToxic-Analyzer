// Apply the saved preference before paint. Storage may be disabled by the browser.
(() => {
  let theme;
  try { theme = localStorage.getItem('vitoxic-theme'); } catch {}
  document.documentElement.dataset.theme = ['light', 'dark'].includes(theme)
    ? theme : (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
})();
