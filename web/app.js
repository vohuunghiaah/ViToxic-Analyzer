'use strict';

const $ = (id) => document.getElementById(id);
const input = $('comment');
const labels = { CLEAN: 'Bình thường', OFFENSIVE: 'Xúc phạm', HATE: 'Thù ghét' };
const number = new Intl.NumberFormat('vi-VN');
const percent = new Intl.NumberFormat('vi-VN', { style: 'percent', maximumFractionDigits: 1 });
const limits = { max_text_chars: 5000, max_batch_size: 32, max_batch_chars: 20000 };
let mode = 'single';
let busy = false;
let exported = null;
const drafts = { single: '', batch: '' };
const emptyState = $('result-content').firstElementChild.cloneNode(true);

function syncTheme() {
  const dark = document.documentElement.dataset.theme === 'dark';
  $('theme-toggle').setAttribute('aria-pressed', String(dark));
  $('theme-toggle').setAttribute('aria-label', dark ? 'Bật chế độ sáng' : 'Bật chế độ tối');
  $('theme-name').textContent = dark ? 'Light' : 'Dark';
}
syncTheme();
$('theme-toggle').addEventListener('click', () => {
  const theme = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = theme;
  try { localStorage.setItem('vitoxic-theme', theme); } catch {}
  syncTheme();
});
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (event) => {
  let saved;
  try { saved = localStorage.getItem('vitoxic-theme'); } catch {}
  if (!['light', 'dark'].includes(saved)) {
    document.documentElement.dataset.theme = event.matches ? 'dark' : 'light';
    syncTheme();
  }
});

function texts() {
  // Match Python's Unicode character count, including characters outside the BMP.
  return mode === 'single' ? [input.value] : input.value.split(/\r?\n/).filter((line) => line.trim());
}
function validate() {
  const entries = texts();
  if (!entries.length || entries.some((text) => !text.trim())) return 'Hãy nhập ít nhất một bình luận có nội dung.';
  if (entries.length > limits.max_batch_size) return `Mỗi lần chỉ phân tích tối đa ${limits.max_batch_size} bình luận.`;
  if (entries.some((text) => [...text].length > limits.max_text_chars)) return `Mỗi bình luận tối đa ${number.format(limits.max_text_chars)} ký tự.`;
  if (entries.reduce((total, text) => total + [...text].length, 0) > limits.max_batch_chars) return `Tổng nội dung tối đa ${number.format(limits.max_batch_chars)} ký tự.`;
  return '';
}
function showError(message) {
  $('input-error').textContent = message;
  $('input-error').hidden = !message;
}
function countInput() {
  const entries = texts();
  const count = entries.reduce((total, text) => total + [...text].length, 0);
  $('input-count').textContent = mode === 'single'
    ? `${number.format(count)} / ${number.format(limits.max_text_chars)}`
    : `${entries.length}/${limits.max_batch_size} câu · ${number.format(count)}/${number.format(limits.max_batch_chars)}`;
  $('input-count').classList.toggle('invalid', Boolean(input.value && validate()));
}
function resetResult() {
  exported = null;
  $('result-content').replaceChildren(emptyState.cloneNode(true));
  $('result-actions').hidden = true;
  $('result-count').hidden = true;
}
input.addEventListener('input', () => { showError(''); countInput(); resetResult(); });
function changeMode(next) {
  if (busy || mode === next) return;
  drafts[mode] = input.value;
  mode = next;
  input.value = drafts[mode];
  $('single-mode').setAttribute('aria-pressed', String(mode === 'single'));
  $('batch-mode').setAttribute('aria-pressed', String(mode === 'batch'));
  input.placeholder = mode === 'single' ? 'Viết hoặc dán bình luận tiếng Việt tại đây…' : 'Mỗi dòng là một bình luận…\nDòng trống sẽ được bỏ qua.';
  $('input-help').textContent = mode === 'single' ? 'Một góc nhìn mới, bắt đầu từ một câu.' : 'Mỗi dòng một bình luận. Bỏ qua dòng trống.';
  $('submit-label').textContent = mode === 'single' ? 'Phân tích bình luận' : 'Phân tích danh sách';
  showError(''); countInput(); resetResult(); input.focus();
}
$('single-mode').addEventListener('click', () => changeMode('single'));
$('batch-mode').addEventListener('click', () => changeMode('batch'));
$('clear-button').addEventListener('click', () => {
  input.value = ''; drafts[mode] = ''; showError(''); countInput(); resetResult(); input.focus();
});
document.querySelectorAll('[data-example]').forEach((button) => button.addEventListener('click', () => {
  input.value = mode === 'batch' && input.value.trim() ? `${input.value}\n${button.dataset.example}` : button.dataset.example;
  showError(''); countInput(); resetResult(); input.focus();
}));
input.addEventListener('keydown', (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
    event.preventDefault();
    $('analyze-form').requestSubmit();
  }
});

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function setBusy(value) {
  busy = value;
  input.readOnly = value;
  document.querySelectorAll('#analyze-form button, .mode-switch button').forEach((button) => { button.disabled = value; });
  document.querySelector('.result-panel').setAttribute('aria-busy', String(value));
  $('submit-label').textContent = value ? 'Đang phân tích…' : mode === 'single' ? 'Phân tích bình luận' : 'Phân tích danh sách';
}
function validPrediction(prediction) {
  return prediction && Object.hasOwn(labels, prediction.label)
    && Number.isInteger(prediction.token_count) && prediction.token_count >= 0
    && typeof prediction.truncated === 'boolean'
    && Number.isFinite(prediction.confidence) && prediction.confidence >= 0 && prediction.confidence <= 1
    && Object.keys(labels).every((label) => Number.isFinite(prediction.probabilities?.[label])
      && prediction.probabilities[label] >= 0 && prediction.probabilities[label] <= 1);
}
function renderResults(predictions, entries, elapsed) {
  const cards = predictions.map((prediction, index) => {
    const card = element('article', 'result-card');
    if (mode === 'batch') card.append(element('p', 'result-caption', `Bình luận ${index + 1}`));
    const heading = element('h3', 'result-label');
    heading.append(element('span', `label-dot ${prediction.label.toLowerCase()}`), document.createTextNode(labels[prediction.label]));
    card.append(heading, element('p', 'result-caption', `${prediction.label} · Điểm dự đoán ${percent.format(prediction.confidence)}`));
    if (mode === 'batch') card.append(element('p', 'result-quote', entries[index]));
    for (const [label, title] of Object.entries(labels)) {
      const row = element('div', 'probability-row');
      const caption = element('div', 'probability-heading');
      caption.append(element('span', '', title), element('span', '', percent.format(prediction.probabilities[label])));
      const track = element('div', 'probability-track');
      const fill = element('div', `probability-fill ${label.toLowerCase()}`);
      fill.style.width = `${prediction.probabilities[label] * 100}%`;
      track.setAttribute('aria-hidden', 'true'); track.append(fill); row.append(caption, track); card.append(row);
    }
    card.append(element('p', 'result-detail', `${number.format(prediction.token_count)} token trước khi rút gọn · Điểm dự đoán chưa hiệu chỉnh`));
    if (prediction.truncated) card.append(element('p', 'truncation-note', 'Nội dung vượt giới hạn token. Mô hình chỉ phân tích phần đầu; kết quả không đại diện cho toàn bộ bình luận.'));
    return card;
  });
  $('result-content').replaceChildren(...cards);
  $('result-count').textContent = `${predictions.length} bình luận`;
  $('result-count').hidden = false;
  $('result-timing').textContent = `${number.format(Math.round(elapsed))} ms gồm thời gian kết nối`;
  $('result-actions').hidden = false;
}
async function request(path, options = {}, timeout = 120000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    const response = await fetch(path, { ...options, signal: controller.signal, cache: 'no-store' });
    if (!response.ok) {
      const messages = {
        413: 'Nội dung quá lớn. Hãy giảm số lượng hoặc độ dài bình luận.',
        422: 'Nội dung không hợp lệ hoặc trống sau chuẩn hóa. Hãy kiểm tra và nhập lại.',
        429: 'Có quá nhiều yêu cầu. Vui lòng chờ một lát rồi thử lại.',
        503: 'Mô hình đang bận hoặc chưa sẵn sàng. Vui lòng chờ một lát rồi thử lại.'
      };
      throw new Error(messages[response.status] || `Không thể phân tích lúc này (HTTP ${response.status}). Vui lòng thử lại sau.`);
    }
    return await response.json();
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('Kết nối quá thời gian chờ. Kiểm tra trạng thái dịch vụ rồi thử lại.');
    if (error instanceof TypeError) throw new Error('Không kết nối được dịch vụ. Kiểm tra mạng và thử lại.');
    throw error;
  } finally { clearTimeout(timer); }
}
$('analyze-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  if (busy) return;
  const error = validate();
  if (error) { showError(error); input.focus(); return; }
  const entries = texts();
  showError(''); resetResult(); setBusy(true);
  const loading = element('div', 'empty-state');
  loading.append(element('div', 'loading-mark'), element('h3', '', 'Đang đọc sắc thái…'), element('p', '', 'Mô hình đang phân tích nội dung của bạn.'));
  $('result-content').replaceChildren(loading);
  const started = performance.now();
  try {
    const response = await request(mode === 'single' ? '/predict' : '/predict/batch', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(mode === 'single' ? { text: entries[0] } : { texts: entries })
    });
    const predictions = mode === 'single' ? [response] : response.predictions;
    if (!Array.isArray(predictions) || predictions.length !== entries.length || !predictions.every(validPrediction)) {
      throw new Error('Dịch vụ trả về kết quả không hợp lệ. Vui lòng thử lại sau.');
    }
    renderResults(predictions, entries, performance.now() - started);
    exported = { created_at: new Date().toISOString(), confidence_calibrated: false,
      results: predictions.map((prediction, i) => ({ text: entries[i], ...prediction })) };
  } catch (error) { resetResult(); showError(error.message); }
  finally { setBusy(false); checkService(); }
});
$('download-button').addEventListener('click', () => {
  if (!exported) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify(exported, null, 2)], { type: 'application/json;charset=utf-8' }));
  const link = element('a'); link.href = url; link.download = 'vitoxic-results.json';
  document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
async function checkService() {
  const status = $('service-status');
  try {
    const response = await request('/ready', {}, 6000);
    if (response.status !== 'ready') throw new Error('Not ready');
    status.dataset.state = response.busy ? 'busy' : 'ready';
    status.lastElementChild.textContent = response.busy ? 'Mô hình đang xử lý yêu cầu khác' : 'Mô hình sẵn sàng';
  } catch {
    status.dataset.state = 'error';
    status.lastElementChild.textContent = 'Dịch vụ chưa sẵn sàng · sẽ tự kiểm tra lại';
  }
}
async function loadMetadata() {
  try {
    const metadata = await request('/model', {}, 6000);
    for (const key of Object.keys(limits)) {
      if (Number.isInteger(metadata.limits?.[key]) && metadata.limits[key] > 0) limits[key] = metadata.limits[key];
    }
    if (Number.isInteger(metadata.max_length) && metadata.max_length > 0) {
      $('model-limit').textContent = `Mô hình đọc tối đa ${metadata.max_length} token (đơn vị mã hóa), bao gồm token đặc biệt. Bình luận dài sẽ được rút gọn.`;
    }
    countInput();
  } catch { /* Default limits match the bundled API. Readiness shows connection failures. */ }
}
countInput(); checkService(); loadMetadata();
setInterval(() => { if (!document.hidden && !busy) checkService(); }, 30000);
