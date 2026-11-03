/* Shared, dependency-free data rules; also exercised with node --test. */
(function (root) {
  'use strict';
  const LABELS = ['CLEAN', 'OFFENSIVE', 'HATE'];
  // Worst-case escaped JSON for 1,000 valid rows (text, notes and errors).
  const MAX_SESSION_BYTES = 64 * 1024 * 1024;
  function parseCSV(source, delimiter = ',') {
    const text = source.replace(/^\uFEFF/, '');
    const rows = []; let row = [], field = '', quoted = false, closed = false;
    for (let i = 0; i < text.length; i++) {
      const ch = text[i];
      if (quoted) {
        if (ch === '"' && text[i + 1] === '"') { field += '"'; i++; }
        else if (ch === '"') { quoted = false; closed = true; }
        else field += ch;
      } else if (ch === delimiter || ch === '\n' || ch === '\r') {
        row.push(field); field = ''; closed = false;
        if (ch !== delimiter) {
          if (ch === '\r' && text[i + 1] === '\n') i++;
          if (row.some(value => value.trim())) rows.push(row);
          row = [];
        }
      } else if (ch === '"') {
        if (field || closed) throw new Error('Dấu ngoặc kép không hợp lệ trong CSV.');
        quoted = true;
      } else {
        if (closed) throw new Error('Có ký tự sau dấu ngoặc kép đóng trong CSV.');
        field += ch;
      }
    }
    if (quoted) throw new Error('CSV thiếu dấu ngoặc kép đóng.');
    row.push(field);
    if (row.some(value => value.trim())) rows.push(row);
    if (rows.length < 2) throw new Error('CSV cần một hàng tiêu đề và ít nhất một hàng dữ liệu.');
    if (rows.length > 1001) throw new Error('Tối đa 1.000 bình luận mỗi phiên. Hãy chia nhỏ file.');
    if (rows[0].some(h => !h.trim()) || new Set(rows[0]).size !== rows[0].length) throw new Error('Tên cột phải có nội dung và không trùng nhau.');
    if (rows.some(r => r.length !== rows[0].length)) throw new Error('Số cột giữa các hàng không khớp. Kiểm tra dấu phân cách và ngoặc kép.');
    return { headers: rows[0], rows: rows.slice(1) };
  }
  function validateTexts(texts) {
    if (!texts.length || texts.length > 1000) throw new Error('Cần từ 1 đến 1.000 bình luận.');
    const bad = texts.findIndex(t => typeof t !== 'string' || !t.trim() || [...t].length > 5000 || /[\uD800-\uDFFF]/u.test(t));
    if (bad >= 0) throw new Error(`Bình luận ${bad + 1} trống, Unicode không hợp lệ hoặc vượt 5.000 ký tự.`);
    return texts;
  }
  function chunks(rows) {
    const result = []; let batch = [], size = 0;
    for (const row of rows) {
      const length = [...row.text].length;
      if (length > 5000) throw new Error('Bình luận vượt 5.000 ký tự.');
      if (batch.length && (batch.length === 16 || size + length > 20000)) { result.push(batch); batch = []; size = 0; }
      batch.push(row); size += length;
    }
    if (batch.length) result.push(batch);
    return result;
  }
  function validPrediction(p) {
    return p && LABELS.includes(p.label) && Number.isFinite(p.confidence) && p.confidence >= 0 && p.confidence <= 1
      && Number.isInteger(p.token_count) && p.token_count >= 0 && typeof p.truncated === 'boolean'
      && LABELS.every(k => Number.isFinite(p.probabilities?.[k]) && p.probabilities[k] >= 0 && p.probabilities[k] <= 1);
  }
  function csvCell(value) {
    let text = String(value ?? '');
    // Neutralize spreadsheet formulas, even after whitespace/control characters.
    if (/^[\s\u0000-\u001f]*[=+@-]/.test(text) || /^[\t\r\n]/.test(text)) text = "'" + text;
    return '"' + text.replaceAll('"', '""') + '"';
  }
  function exportCSV(session) {
    const header = ['id', 'text', 'predicted_label', 'confidence', 'CLEAN', 'OFFENSIVE', 'HATE', 'truncated', 'review_status', 'reviewed_label', 'note', 'error'];
    const rows = session.rows.map(r => [r.id, r.text, r.prediction?.label, r.prediction?.confidence,
      ...LABELS.map(k => r.prediction?.probabilities[k]), r.prediction?.truncated, r.status, r.reviewLabel, r.note, r.error]);
    return '\uFEFF' + [header, ...rows].map(row => row.map(csvCell).join(',')).join('\r\n');
  }
  function importSession(data) {
    if (data?.schema !== 1 || typeof data.name !== 'string' || !data.name.trim() || data.name.length > 120
      || !Array.isArray(data.rows)) throw new Error('File JSON không đúng định dạng phiên ViToxic.');
    if(data.rows.some(r=>!r || typeof r!=='object' || Array.isArray(r)))throw new Error('Hàng dữ liệu JSON không hợp lệ.');
    validateTexts(data.rows.map(r => r.text));
    for (const r of data.rows) {
      if ((r.prediction !== null && !validPrediction(r.prediction)) || !['pending', 'flagged', 'reviewed'].includes(r.status)
        || (r.reviewLabel !== null && !LABELS.includes(r.reviewLabel))
        || (r.status === 'reviewed' && !r.reviewLabel) || (r.status !== 'reviewed' && r.reviewLabel !== null)
        || typeof r.note !== 'string' || r.note.length > 2000 || typeof r.error !== 'string') throw new Error('Dữ liệu nhãn duyệt trong JSON không hợp lệ.');
    }
    return { schema: 1, name: data.name, model: data.model && typeof data.model.run === 'string'
      ? {run: data.model.run, checkpoint_sha256: String(data.model.checkpoint_sha256 || '')} : null,
      rows: data.rows.map((r, i) => ({id: i + 1, text: r.text, prediction: r.prediction, status: r.status,
        reviewLabel: r.reviewLabel, note: r.note, error: r.error.slice(0, 500)})) };
  }
  const api = {LABELS, MAX_SESSION_BYTES, parseCSV, validateTexts, chunks, validPrediction, exportCSV, importSession};
  if (typeof module !== 'undefined') module.exports = api;
  else root.ViToxicData = api;
})(globalThis);
