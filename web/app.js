import { $, el, esc, load, save } from './util.js';
import { AuthError, api, getJson, token, url } from './api.js';
import { QUIPS, ROBOT, setRobot, trackPointer } from './robot.js';

const EXAMPLES = ['Văn bản 1866 thay thế văn bản nào?', 'Cho vay ngắn hạn mua máy móc thiết bị tối đa bao nhiêu % giá trị hàng hóa?',
  'Lãi suất cho vay người dưới 35 tuổi mua nhà ở xã hội là bao nhiêu?'];
const DOC_STATUS = {ready: 'Sẵn sàng', processing: 'Đang xử lý', failed: 'Lỗi'};
const STEP_LABEL = {extract: 'Đọc/OCR trang', chunk: 'Chia đoạn', embed: 'Lập chỉ mục đoạn'};
// Overall bar: OCR is most of the work (0-80%), indexing the rest (80-100%).
function progressOf(d) {
  const frac = d.total ? Math.min(1, d.done / d.total) : 0;
  const pct = d.stage === 'embed' ? 80 + 20 * frac : d.stage === 'extract' ? 80 * frac : 0;
  const label = d.stage === 'queued' || !STEP_LABEL[d.stage] ? 'Đang chờ…'
    : `${STEP_LABEL[d.stage]}${d.total ? ` ${d.done}/${d.total} · ${Math.round(100 * frac)}%` : '…'}`;
  return {pct: Math.max(3, Math.round(pct)), label};
}

let docs = null, cfg, settings, ctrl = null, busy = false, quip = 0, pollTimer = null, sourceOpener = null;
const history = [];
const messageSources = {};  // message index -> {S1: source}
const root = document.documentElement;
const pageRange = s => `${s.pageStart}${s.pageEnd !== s.pageStart ? '-' + s.pageEnd : ''}`;
const errorBox = (text, cls = '') => `<div class="errbox ${cls}" role="alert">${esc(text)}</div>`;

// Identity comes from the server (.env), never from this file.
function applyBranding({orgName, author, logos}) {
  const title = orgName ? `${orgName} Internal Chatbot` : 'Internal Chatbot';
  document.title = title;
  $('#appTitle').textContent = title;
  const header = logos.header
    ? el('img', {class: 'logo', src: url(logos.header), alt: orgName || 'Logo'})
    : el('div', {class: 'logo ph', role: 'img', 'aria-label': 'Chỗ đặt logo'}, 'LOGO');
  $('#logoSlot').replaceChildren(header);

  const light = logos['footer-light'] || logos['footer-dark'], dark = logos['footer-dark'] || logos['footer-light'];
  const footerLogos = [];
  if (light) footerLogos.push(el('img', {class: 'f-logo f-light', src: url(light), alt: orgName || 'Logo'}));
  if (dark) footerLogos.push(el('img', {class: 'f-logo f-dark', src: url(dark), alt: orgName || 'Logo'}));
  $('#footerLogos').replaceChildren(...footerLogos);
  $('#author').textContent = author || '';
  $('#siteFooter').hidden = !footerLogos.length && !author;
}

// Theme
function applyTheme(theme) { if (theme) root.dataset.theme = theme; }
applyTheme(load('theme', null));
$('#themeBtn').onclick = () => {
  const dark = root.dataset.theme ? root.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
  const next = dark ? 'light' : 'dark';
  applyTheme(next); save('theme', next);
};

// Settings
function fillModels() {
  $('#sModel').innerHTML = cfg.providers[$('#sProvider').value].models.map(m => `<option>${esc(m)}</option>`).join('');
}
function fillSettings() {
  $('#sProvider').innerHTML = Object.entries(cfg.providers).map(([k, v]) => `<option value="${esc(k)}">${esc(v.label)}</option>`).join('');
  $('#sProvider').value = settings.provider; fillModels();
  $('#sModel').value = settings.model; $('#sTokens').value = settings.max_output_tokens; $('#sTokens').max = cfg.max_output_tokens_cap;
  $('#sStyle').value = settings.style; $('#sFont').value = String(settings.fontScale); $('#sTemp').value = settings.temperature;
  fillEndpoints();
}
function fillEndpoints() {
  $('#epBox').hidden = !cfg.customEndpoints;
  $('#epList').innerHTML = Object.entries(cfg.providers).filter(([, v]) => v.custom)
    .map(([k, v]) => `<li><span>${esc(v.label)}</span><button class="btn" type="button" data-ep="${esc(k)}">Xóa</button></li>`).join('');
}
async function reloadConfig(select) {
  cfg = await getJson('/api/config');
  if (select) Object.assign(settings, {provider: select, model: cfg.providers[select].models[0]});
  if (!cfg.providers[settings.provider]) Object.assign(settings, {provider: cfg.default_provider, model: cfg.providers[cfg.default_provider].models[0]});
  fillSettings();
}
async function endpointCall(path, options) {
  const err = $('#epErr'); err.hidden = true;
  try {
    const r = await api(path, options);
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || 'Không thực hiện được');
    return await r.json();
  } catch (x) { err.textContent = x.message; err.hidden = false; }
}
$('#epAdd').onclick = async () => {
  const model = $('#epModel').value.trim(), key = $('#epKey').value;
  const res = await endpointCall('/api/endpoints', {method: 'POST', headers: {'content-type': 'application/json'},
    body: JSON.stringify({url: $('#epUrl').value, label: model, api_key: key || null, models: model ? [model] : []})});
  if (!res) return;
  ['#epUrl', '#epModel', '#epKey'].forEach(s => { $(s).value = ''; });
  await reloadConfig(res.key);
};
$('#epList').onclick = async e => {
  const key = e.target.dataset?.ep;
  if (key && await endpointCall(`/api/endpoints/${encodeURIComponent(key)}`, {method: 'DELETE'})) await reloadConfig();
};
$('#epBox').addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); $('#epAdd').click(); } });
$('#sProvider').onchange = fillModels;
// Text size: a root multiplier, so every rem-based size follows. Preview while the dialog is open, revert on cancel.
const applyFont = scale => document.documentElement.style.setProperty('--fs', scale);
applyFont(load('settings', {}).fontScale ?? 1.125);
$('#sFont').addEventListener('change', e => applyFont(+e.target.value));
$('#settings').addEventListener('close', () => applyFont(settings.fontScale));
$('#settingsBtn').onclick = () => { fillSettings(); $('#settings').showModal(); };
$('#settingsForm').addEventListener('submit', e => {
  if (e.submitter?.value !== 'ok') return;
  settings = {provider: $('#sProvider').value, model: $('#sModel').value,
    max_output_tokens: Math.min(cfg.max_output_tokens_cap, Math.max(100, +$('#sTokens').value || 1200)),
    style: $('#sStyle').value, fontScale: +$('#sFont').value || 1.125, temperature: Math.min(1, Math.max(0, +$('#sTemp').value || 0))};
  save('settings', settings);
});

// Sidebar width: drag the edge or use ← → on it; the width is remembered.
const MIN_W = 240, MAX_W = 560;
const setAsideW = w => { w = Math.min(MAX_W, Math.max(MIN_W, Math.round(w))); document.documentElement.style.setProperty('--aside-w', w + 'px'); $('#resizer').setAttribute('aria-valuenow', w); return w; };
let asideW = setAsideW(load('aside.w', 360));
$('#resizer').addEventListener('pointerdown', e => {
  e.preventDefault(); $('#resizer').setPointerCapture(e.pointerId); $('#resizer').classList.add('drag');
  const left = $('#app').getBoundingClientRect().left;
  const move = ev => { asideW = setAsideW(ev.clientX - left); };
  const stop = () => { $('#resizer').classList.remove('drag'); $('#resizer').removeEventListener('pointermove', move); $('#resizer').removeEventListener('pointerup', stop); save('aside.w', asideW); };
  $('#resizer').addEventListener('pointermove', move); $('#resizer').addEventListener('pointerup', stop);
});
$('#resizer').addEventListener('keydown', e => {
  if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
  e.preventDefault(); asideW = setAsideW(asideW + (e.key === 'ArrowRight' ? 16 : -16)); save('aside.w', asideW);
});

// Documents
// Documents the user switched off for this browser; new documents start selected.
const extOf = d => (d.name.match(/\.(\w+)$/)?.[1] || 'file').toUpperCase();
const unsel = new Set(load('docs.unselected', []));
const saveSel = () => save('docs.unselected', [...unsel]);
const selectedIds = () => docs && docs.filter(d => d.status === 'ready' && !unsel.has(d.id)).map(d => d.id);
function showCount(err) {
  const ready = docs ? docs.filter(d => d.status === 'ready').length : 0;
  $('#docCount').textContent = err || (docs ? `Đang dùng ${selectedIds().length}/${ready} tài liệu` : '');
  $('#docCount').classList.toggle('err', !!err);
}
async function refreshDocs() {
  try { docs = await getJson('/api/documents'); }
  catch (x) {
    if (x instanceof AuthError) return; $('#docs').innerHTML = '<li class="doc"><span class="status err">Không tải được danh sách tài liệu.</span></li>'; return; }
  for (const id of unsel) if (!docs.some(d => d.id === id)) unsel.delete(id);  // forget deleted documents
  saveSel(); showCount();
  $('#docs').innerHTML = docs.length ? docs.map(d => `<li class="doc ${esc(d.status)}${d.status === 'ready' && unsel.has(d.id) ? ' off' : ''}">
      <input type="checkbox" class="pick" data-id="${esc(d.id)}" aria-label="Dùng tài liệu này khi trả lời"${d.status === 'ready' ? (unsel.has(d.id) ? '' : ' checked') : ' disabled'}>
      <button type="button" class="open" data-id="${esc(d.id)}" title="${esc(d.title || d.name)}"><span class="ext">${esc(extOf(d))}</span><span class="tt">${esc(d.title || d.name)}</span></button>
      <button type="button" class="del" data-id="${esc(d.id)}" aria-label="Xóa tài liệu" title="Xóa tài liệu">✕</button>
      <div class="meta">${[d.doc_no && 'Số ' + esc(d.doc_no), d.issued && esc(d.issued), d.pages && d.pages + ' trang'].filter(Boolean).join(' • ')}${d.status === 'ready' ? '' : `${d.doc_no || d.issued || d.pages ? ' • ' : ''}<b class="st ${esc(d.status)}">${DOC_STATUS[d.status] || esc(d.status)}</b>`}</div>
      ${d.status === 'processing' ? (p => `<div class="prog" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${p.pct}" aria-label="Tiến trình xử lý"><i style="width:${p.pct}%"></i></div><div class="pt">${esc(p.label)} · tổng ${p.pct}%</div>`)(progressOf(d)) : ''}
      ${d.error ? `<div class="pt err">${esc(d.error)}</div>` : ''}</li>`).join('')
    : '<li class="doc empty"><span class="status">Chưa có tài liệu. Tải một tệp lên để bắt đầu.</span></li>';
  clearTimeout(pollTimer);
  if (docs.some(d => d.status === 'processing')) pollTimer = setTimeout(refreshDocs, 1500);
}
$('#docs').addEventListener('change', e => {
  const box = e.target.closest('.pick'); if (!box) return;
  box.checked ? unsel.delete(box.dataset.id) : unsel.add(box.dataset.id);
  saveSel(); showCount();
});
$('#docs').addEventListener('click', async e => {
  const open = e.target.closest('.open');
  if (open) return openDocument(docs.find(x => x.id === open.dataset.id));
  const btn = e.target.closest('.del'); if (!btn) return;
  const d = docs.find(x => x.id === btn.dataset.id);
  if (!d || !confirm(`Xóa "${d.title || d.name}" khỏi hệ thống? Việc này không hoàn tác được.`)) return;
  btn.disabled = true;
  try {
    const r = await api(`/api/documents/${encodeURIComponent(d.id)}`, {method: 'DELETE'});
    if (!r.ok && r.status !== 404) throw new Error(`Lỗi máy chủ (${r.status})`);
  } catch (x) { if (x instanceof AuthError) return; btn.disabled = false; return showCount(x.message); }
  refreshDocs();
});
const selectAll = on => { for (const d of docs || []) on ? unsel.delete(d.id) : unsel.add(d.id); saveSel(); refreshDocs(); };
$('#selAll').onclick = () => selectAll(true); $('#selNone').onclick = () => selectAll(false);
$('#uploadBtn').onclick = () => $('#file').click();
$('#file').onchange = async e => {
  const file = e.target.files[0]; e.target.value = '';
  if (!file) return;
  const err = $('#uploadErr'); err.hidden = true;
  const fail = text => { err.textContent = text; err.hidden = false; };
  if (file.size > cfg.max_upload_mb * 1048576) return fail(`File quá ${cfg.max_upload_mb} MB.`);
  const form = new FormData(); form.append('file', file);
  $('#uploadBtn').disabled = true;
  try {
    const r = await api('/api/documents', {method: 'POST', body: form});
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || 'Tải lên thất bại');
    refreshDocs();
  } catch (x) { fail(x.message); }
  $('#uploadBtn').disabled = false;
};
const pane = $('#docsPane');
// Narrow screens: the library is an overlay. Wide screens: it collapses to give the chat the full width.
const narrow = matchMedia('(max-width:900px)');
const setLibOff = on => { $('#app').classList.toggle('lib-off', on); $('#docsBtn').setAttribute('aria-expanded', String(!on)); save('lib.off', on); };
setLibOff(load('lib.off', false));
$('#docsBtn').onclick = () => narrow.matches ? (pane.classList.add('open'), $('#docsClose').focus()) : setLibOff(!$('#app').classList.contains('lib-off'));
$('#docsClose').onclick = () => { if (narrow.matches) pane.classList.remove('open'); else setLibOff(true); $('#docsBtn').focus(); };

// Chat view
function renderEmpty() {
  $('#dock').hidden = true;
  $('#msgs').innerHTML = `<div class="empty"><div class="hero">
      <button type="button" class="robot" id="heroBot" data-state="idle" aria-label="Chào robot trợ lý">${ROBOT}</button>
      <div class="bubble" role="status" aria-live="polite"><b>Em là trợ lý tra cứu</b><span id="bubbleText">${esc(QUIPS[0])}</span></div></div>
    <div class="chips">${EXAMPLES.map(x => `<button type="button" data-ex="${esc(x)}">${esc(x)}</button>`).join('')}</div></div>`;
  $('#dockBot').innerHTML = ROBOT;
  setRobot('hello', 2200);
}
$('#msgs').addEventListener('click', e => {
  const example = e.target.closest('[data-ex]');
  if (example) { $('#q').value = example.dataset.ex; $('#q').focus(); return; }
  const cite = e.target.closest('[data-src]');
  if (cite) openSource(cite.dataset.src);
});
document.addEventListener('click', e => {
  if (!e.target.closest('#heroBot') || busy) return;
  quip = (quip + 1) % QUIPS.length;
  $('#bubbleText').textContent = QUIPS[quip];
  setRobot('hello', 2200);
});

// Escape first; [Sx] becomes a button only when the id is a real source, so model-invented ids stay plain text.
function renderAnswer(text, sources) {
  const html = esc(text.replace(/<[^\W\d_][^<>\n]{0,38}>/g, '')).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\[(S\d+)\]/g, (m, id) => sources[id] ? `<button type="button" class="cite" data-src="${id}">${id}</button>` : m);
  const out = []; let list = [];
  const flush = () => { if (list.length) out.push('<ul>' + list.map(x => `<li>${x}</li>`).join('') + '</ul>'); list = []; };
  for (const line of html.split('\n')) {
    const item = line.match(/^\s*(?:[-*]|\d+\.)\s+(.*)/);
    if (item) { list.push(item[1]); continue; }
    flush();
    if (line.trim()) out.push(`<p>${line}</p>`);
  }
  flush();
  return out.join('');
}

function addMessage(role, idx) {
  const node = el('div', {class: 'msg ' + (role === 'user' ? 'user' : 'bot'), 'data-idx': idx});
  node.innerHTML = `<div class="who">${role === 'user' ? 'Bạn' : 'Trợ lý'}</div><div class="body"></div><div class="vers"></div><div class="srcs"></div><div class="usage"></div>`;
  $('#msgs').appendChild(node);
  return node;
}
// The answer arrives whole, after the server has checked it; this only reveals it progressively.
let skipTyping = false;
async function typeOut(body, text, sources) {
  for (let shown = 0; shown < text.length && !skipTyping; shown += Math.max(3, Math.ceil((text.length - shown) / 40))) {
    body.innerHTML = renderAnswer(text.slice(0, shown), sources); scrollDown();
    await new Promise(r => setTimeout(r, 18));
  }
  body.innerHTML = renderAnswer(text, sources); scrollDown();
}
const nf = new Intl.NumberFormat('vi-VN');
function showUsage(node, u) {
  if (u?.inputTokens == null && u?.outputTokens == null) return;
  node.querySelector('.usage').textContent = `Token: ${nf.format(u.inputTokens ?? 0)} vào · ${nf.format(u.outputTokens ?? 0)} ra`;
}
const scrollDown = () => { const t = $('#thread'); t.scrollTop = t.scrollHeight; };

function sourceButtons(sources) {
  if (!sources.length) return 'Không tìm thấy đoạn nguồn phù hợp.';
  return 'Nguồn: ' + sources.map(s => `<button type="button" data-src="${s.id}">${s.id} · ${esc(s.docNo ? 'Số ' + s.docNo : s.fileName)}, tr. ${pageRange(s)}</button>`).join('');
}

// Documents that amend one another: newest first, so the reader sees the current text and what it replaced.
function versionBoxes(groups) {
  return groups.map(g => `<div class="vgroup"><b>Những văn bản liên quan</b><ul>${g.map(v =>
    `<li><span class="badge ${v.latest ? 'ready' : 'processing'}">${v.latest ? 'Mới nhất' : 'Trước đó'}</span> `
    + `<button type="button" data-src="${esc(v.id)}">${esc(v.docNo ? 'Số ' + v.docNo : v.id)}${v.issued ? ' · ' + esc(v.issued) : ''}</button></li>`).join('')}</ul></div>`).join('');
}

function warning(data) {
  return data.placeholder ? 'Câu trả lời chưa hoàn chỉnh (còn chữ mẫu). Hãy hỏi lại hoặc đối chiếu văn bản gốc.'
    : data.uncited ? 'Câu trả lời chưa có trích dẫn nguồn. Đừng dùng khi chưa đối chiếu văn bản gốc.'
    : `Số chưa thấy trong nguồn: ${data.unverified.join(', ')}. Đối chiếu văn bản gốc trước khi dùng.`;
}

async function* sseEvents(response) {
  const reader = response.body.getReader(), decoder = new TextDecoder();
  let buffer = '';
  for (;;) {
    const {value, done} = await reader.read();
    if (done) return;
    buffer += decoder.decode(value, {stream: true});
    let end;
    while ((end = buffer.indexOf('\n\n')) >= 0) {
      const block = buffer.slice(0, end); buffer = buffer.slice(end + 2);
      yield [(block.match(/^event: (.*)$/m) || [])[1], JSON.parse((block.match(/^data: (.*)$/m) || [, '{}'])[1])];
    }
  }
}

async function ask(question) {
  busy = true; $('#send').disabled = true; $('#stop').hidden = false;
  if (!history.length) { $('#msgs').innerHTML = ''; $('#dock').hidden = false; }
  setRobot('think');
  const idx = history.length;
  addMessage('user', idx).querySelector('.body').textContent = question;
  const botEl = addMessage('bot', idx + 1), body = botEl.querySelector('.body');
  body.innerHTML = '<span class="status">Em đang suy nghĩ<span class="dots"></span></span>'; scrollDown();
  const sources = messageSources[idx + 1] = {};
  let text = '', usage = null, failed = false, aborted = false;
  skipTyping = false;
  ctrl = new AbortController();
  try {
    const r = await api('/api/chat', {method: 'POST', signal: ctrl.signal, headers: {'content-type': 'application/json'},
      body: JSON.stringify({messages: [...history, {role: 'user', content: question}], provider: settings.provider, model: settings.model,
        max_output_tokens: settings.max_output_tokens, style: settings.style, temperature: settings.temperature, document_ids: selectedIds()})});
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || 'Yêu cầu bị từ chối');
    for await (const [event, data] of sseEvents(r)) {
      if (event === 'sources') { data.sources.forEach(s => { sources[s.id] = s; }); botEl.querySelector('.srcs').innerHTML = sourceButtons(data.sources); botEl.querySelector('.vers').innerHTML = versionBoxes(data.versions || []); }
      else if (event === 'status') body.innerHTML = `<span class="status">${esc(data.text)}<span class="dots"></span></span>`;
      else if (event === 'mode') botEl.dataset.mode = data.mode;
      else if (event === 'verify') botEl.querySelector('.srcs').insertAdjacentHTML('beforebegin', errorBox(warning(data), 'warn'));
      else if (event === 'delta') { if (!text) { setRobot('talk'); botEl.classList.add('typing'); } text += data.text; }
      else if (event === 'done') usage = data.usage;
      else if (event === 'error') { failed = true; setRobot('oops', 4000); body.insertAdjacentHTML('beforeend', errorBox(data.message)); }
      scrollDown();
    }
  } catch (x) {
    if (x.name === 'AbortError') { aborted = true; body.insertAdjacentHTML('beforeend', '<div class="status">(Đã dừng)</div>'); setRobot('idle'); }
    else { failed = true; setRobot('oops', 4000); body.insertAdjacentHTML('beforeend', errorBox(x.message)); }
  }
  if (text && !failed) await typeOut(body, text, sources);
  botEl.classList.remove('typing'); showUsage(botEl, usage);
  if (!text && !failed && !body.querySelector('.status:not(.dots)')) body.innerHTML = '<span class="status">Không có nội dung trả lời.</span>';
  else if (!text && body.querySelector('.dots')) body.querySelector('.status').remove();
  if (!failed && !aborted && text) setRobot('happy', 2600); else if (!failed) setRobot('idle');
  history.push({role: 'user', content: question}, {role: 'assistant', content: text || '(không có câu trả lời)'});
  busy = false; ctrl = null; $('#send').disabled = false; $('#stop').hidden = true; $('#q').focus();
}
$('#ask').addEventListener('submit', e => {
  e.preventDefault();
  const q = $('#q').value.trim();
  if (!q || busy) return;
  if (docs?.some(d => d.status === 'ready') && !selectedIds().length) { showCount('Chọn ít nhất một tài liệu để hỏi.'); pane.classList.add('open'); return; }
  $('#q').value = ''; $('#q').style.height = 'auto'; ask(q);
});
$('#q').addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); $('#ask').requestSubmit(); } });
$('#q').addEventListener('input', e => {
  if (!busy) setRobot(e.target.value ? 'typing' : 'idle', 1800);
  e.target.style.height = 'auto'; e.target.style.height = Math.min(e.target.scrollHeight, 160) + 'px';
});
$('#stop').onclick = () => { skipTyping = true; if (ctrl) ctrl.abort(); };

// Source popup: page image beside the OCR text of that page, with the cited passage highlighted.
const norm = t => t.toLowerCase().replace(/[|*#\s]+/g, ' ').trim();
function renderChunk(text, mark = () => false) {  // escapes, then turns pipe-tables into real tables
  const out = []; let rows = [];
  const flush = () => {
    if (rows.length) out.push('<div class="tw"><table>' + rows.map((r, i) => `<tr${r.hl ? ' class="hl"' : ''}>` + r.cells.map(c => `<${i ? 'td' : 'th'}>${esc(c)}</${i ? 'td' : 'th'}>`).join('') + '</tr>').join('') + '</table></div>');
    rows = [];
  };
  for (const line of text.split('\n')) {
    const t = line.trim();
    if (t.startsWith('|')) { if (!/^\|[\s\-:|]+\|?$/.test(t)) rows.push({cells: t.replace(/^\||\|$/g, '').split('|').map(c => c.trim()), hl: mark(t)}); }
    else { flush(); if (t) out.push(`<p${mark(t) ? ' class="hl"' : ''}>${esc(line)}</p>`); }
  }
  flush();
  return out.join('');
}
let srcSeq = 0;
const blobToDataUrl = blob => new Promise((ok, no) => { const r = new FileReader(); r.onload = () => ok(r.result); r.onerror = no; r.readAsDataURL(blob); });
function openSource(id) {
  sourceOpener = document.activeElement;
  const s = (messageSources[sourceOpener.closest('.msg')?.dataset.idx] || {})[id];
  if (!s) return;
  openDialog(s, `${s.id} · ${s.docNo ? 'Số ' + s.docNo : ''}${s.issued ? ' · ngày ' + s.issued : ''}`);
}
// Library: the whole document, page by page, without a highlighted passage.
function openDocument(d) {
  if (!d) return;
  sourceOpener = document.activeElement;
  openDialog({documentId: d.id, fileName: d.title || d.name, pageStart: 1, pageEnd: Math.max(1, d.pages || 1), excerpt: ''},
    [d.doc_no ? 'Số ' + d.doc_no : '', d.issued ? 'ngày ' + d.issued : '', d.name].filter(Boolean).join(' · '));
}
function openDialog(s, meta) {
  $('#srcTitle').textContent = s.fileName;
  $('#srcMeta').textContent = meta;
  $('#source').showModal(); $('#srcClose').focus();
  showPage(s, s.pageStart);
}
async function showPage(s, n) {
  const seq = ++srcSeq, base = `/api/documents/${encodeURIComponent(s.documentId)}/page/${n}`;
  $('#srcPage').textContent = !s.excerpt ? `Trang ${n}/${s.pageEnd}` : `Trang ${n}${s.pageEnd !== s.pageStart ? ` (nguồn: ${pageRange(s)})` : ''}`;
  $('#srcPrev').disabled = n <= s.pageStart; $('#srcNext').disabled = n >= s.pageEnd;
  $('#srcPrev').onclick = () => showPage(s, n - 1); $('#srcNext').onclick = () => showPage(s, n + 1);
  $('#srcText').innerHTML = '<span class="status">Đang tải…</span>'; $('#srcWrap').hidden = true;
  const [text, img] = await Promise.allSettled([
    getJson(base),
    api(base + '/image').then(r => r.ok ? r.blob().then(blobToDataUrl) : Promise.reject(new Error('no image'))),
  ]);
  if (seq !== srcSeq) return;  // the user moved on to another page or closed the popup
  const page = text.status === 'fulfilled' ? text.value.text : null;
  const hay = norm(s.excerpt), cited = line => { const t = norm(line); return t.length >= 6 && hay.includes(t); };
  const blocks = text.status === 'fulfilled' ? text.value.blocks : null;  // MinerU boxes, normalized 0-1
  $('#srcBoxes').innerHTML = (blocks || []).filter(b => b.content && b.content.split('\n').some(cited))
    .map(b => `<i style="left:${b.bbox[0] * 100}%;top:${b.bbox[1] * 100}%;width:${(b.bbox[2] - b.bbox[0]) * 100}%;height:${(b.bbox[3] - b.bbox[1]) * 100}%"></i>`).join('');
  $('#srcText').innerHTML = page ? renderChunk(page, cited)
    : errorBox('Không có văn bản OCR của trang này. Hiển thị đoạn được trích:') + renderChunk(s.excerpt);
  $('#srcText').querySelector('.hl')?.scrollIntoView({block: 'center'});
  if (img.status === 'fulfilled') { $('#srcImg').src = img.value; $('#srcWrap').hidden = false; }
}
function closeSource() { srcSeq++; $('#source').close(); $('#srcImg').removeAttribute('src'); }
$('#srcClose').onclick = closeSource;
$('#source').addEventListener('keydown', e => {  // ← → turn pages
  if (e.target.closest('.excerpt, .pgimg') || e.target === $('#source')) { if (e.key === 'ArrowLeft') $('#srcPrev').click(); if (e.key === 'ArrowRight') $('#srcNext').click(); }
});
$('#source').addEventListener('close', () => { if (sourceOpener) sourceOpener.focus(); });
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && !$('#settings').open && $('#source').open === false && pane.classList.contains('open')) $('#docsClose').click();
});

// Login
function showLogin() {
  $('#loginErr').hidden = true;
  if (!$('#login').open) $('#login').showModal();
  $('#loginPw').focus();
}
document.addEventListener('auth-required', showLogin);
$('#login').addEventListener('cancel', e => e.preventDefault());  // no way past the gate with Escape
$('#loginForm').addEventListener('submit', async e => {
  e.preventDefault();
  const err = $('#loginErr'); err.hidden = true;
  try {
    const r = await api('/api/login', {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({password: $('#loginPw').value})});
    if (!r.ok) throw new Error(r.status === 401 ? 'Sai mật khẩu.' : r.status === 429 ? 'Thử quá nhiều lần, đợi một phút.' : 'Đăng nhập thất bại.');
    token.set((await r.json()).token);
    $('#loginPw').value = ''; $('#login').close();
    start();
  } catch (x) { err.textContent = x.message; err.hidden = false; }
});

// Start
async function start() {
  try { cfg = await getJson('/api/config'); }
  catch (x) { if (!(x instanceof AuthError)) $('#msgs').innerHTML = errorBox(x.message); return; }
  settings = {provider: cfg.default_provider, model: cfg.providers[cfg.default_provider].models[0],
    max_output_tokens: 1200, style: 'friendly', temperature: 0.2, fontScale: 1.125, ...load('settings', {})};
  applyFont(settings.fontScale);
  if (!cfg.providers[settings.provider]) Object.assign(settings, {provider: cfg.default_provider, model: cfg.providers[cfg.default_provider].models[0]});
  renderEmpty(); refreshDocs();
}

async function init() {
  trackPointer();
  let branding;
  try { branding = await getJson('/api/branding'); }
  catch (x) { $('#msgs').innerHTML = errorBox(x.message); return; }
  applyBranding(branding);
  if (branding.authRequired && !token.get()) { showLogin(); return; }
  start();
}
init();
