import { $, el, esc, load, save } from './util.js';
import { AuthError, api, getJson, token, url } from './api.js';
import { QUIPS, ROBOT, setRobot, trackPointer } from './robot.js';

const EXAMPLES = ['Văn bản 1866 thay thế văn bản nào?', 'Cho vay ngắn hạn mua máy móc thiết bị tối đa bao nhiêu % giá trị hàng hóa?',
  'Lãi suất cho vay người dưới 35 tuổi mua nhà ở xã hội là bao nhiêu?'];
const DOC_STATUS = {ready: 'Sẵn sàng', processing: 'Đang xử lý', failed: 'Lỗi'};
const DOC_STAGE = {queued: 'chờ', extract: 'đọc/OCR', chunk: 'chia đoạn', embed: 'lập chỉ mục', done: ''};

let cfg, settings, ctrl = null, busy = false, quip = 0, pollTimer = null, sourceOpener = null;
const history = [];
const messageSources = {};  // message index -> {S1: source}
const root = document.documentElement;
const pageRange = s => `${s.pageStart}${s.pageEnd !== s.pageStart ? '-' + s.pageEnd : ''}`;
const errorBox = (text, cls = '') => `<div class="errbox ${cls}" role="alert">${esc(text)}</div>`;

// ---- branding: identity comes from the server (.env), never from this file ----
function applyBranding({orgName, author, logos}) {
  document.title = orgName ? `Tra cứu văn bản ${orgName}` : 'Tra cứu văn bản';
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

// ---- theme ----
function applyTheme(theme) { if (theme) root.dataset.theme = theme; }
applyTheme(load('theme', null));
$('#themeBtn').onclick = () => {
  const dark = root.dataset.theme ? root.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
  const next = dark ? 'light' : 'dark';
  applyTheme(next); save('theme', next);
};

// ---- settings ----
function fillModels() {
  $('#sModel').innerHTML = cfg.providers[$('#sProvider').value].models.map(m => `<option>${esc(m)}</option>`).join('');
}
function fillSettings() {
  $('#sProvider').innerHTML = Object.entries(cfg.providers).map(([k, v]) => `<option value="${esc(k)}">${esc(v.label)}</option>`).join('');
  $('#sProvider').value = settings.provider; fillModels();
  $('#sModel').value = settings.model; $('#sTokens').value = settings.max_output_tokens; $('#sTokens').max = cfg.max_output_tokens_cap;
  $('#sStyle').value = settings.style; $('#sTemp').value = settings.temperature;
}
$('#sProvider').onchange = fillModels;
$('#settingsBtn').onclick = () => { fillSettings(); $('#settings').showModal(); };
$('#settingsForm').addEventListener('submit', e => {
  if (e.submitter?.value !== 'ok') return;
  settings = {provider: $('#sProvider').value, model: $('#sModel').value,
    max_output_tokens: Math.min(cfg.max_output_tokens_cap, Math.max(100, +$('#sTokens').value || 1200)),
    style: $('#sStyle').value, temperature: Math.min(1, Math.max(0, +$('#sTemp').value || 0))};
  save('settings', settings);
});

// ---- documents ----
async function refreshDocs() {
  let docs;
  try { docs = await getJson('/api/documents'); }
  catch (x) {
    if (x instanceof AuthError) return; $('#docs').innerHTML = '<li class="doc"><span class="status err">Không tải được danh sách tài liệu.</span></li>'; return; }
  $('#docs').innerHTML = docs.length ? docs.map(d => `<li class="doc">
      <div class="t">${esc(d.title || d.name)}</div>
      <div class="m">${esc(d.doc_no ? 'Số ' + d.doc_no : d.name)}${d.issued ? ' · ' + esc(d.issued) : ''}${d.pages ? ' · ' + d.pages + ' trang' : ''}
        <span class="badge ${esc(d.status)}">${DOC_STATUS[d.status] || esc(d.status)}${d.status === 'processing' && DOC_STAGE[d.stage] ? ' (' + DOC_STAGE[d.stage] + ')' : ''}</span></div>
      ${d.error ? `<div class="m err">${esc(d.error)}</div>` : ''}</li>`).join('')
    : '<li class="doc"><span class="status">Chưa có tài liệu. Tải một tệp lên để bắt đầu.</span></li>';
  clearTimeout(pollTimer);
  if (docs.some(d => d.status === 'processing')) pollTimer = setTimeout(refreshDocs, 3000);
}
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
$('#docsBtn').onclick = () => { pane.classList.add('open'); $('#docsClose').focus(); };
$('#docsClose').onclick = () => { pane.classList.remove('open'); $('#docsBtn').focus(); };

// ---- chat view ----
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
  const html = esc(text).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
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
  node.innerHTML = `<div class="who">${role === 'user' ? 'Bạn' : 'Trợ lý'}</div><div class="body"></div><div class="vers"></div><div class="srcs"></div>`;
  $('#msgs').appendChild(node);
  return node;
}
const scrollDown = () => { const t = $('#thread'); t.scrollTop = t.scrollHeight; };

function sourceButtons(sources) {
  if (!sources.length) return 'Không tìm thấy đoạn nguồn phù hợp.';
  return 'Nguồn: ' + sources.map(s => `<button type="button" data-src="${s.id}">${s.id} · ${esc(s.docNo ? 'Số ' + s.docNo : s.fileName)}, tr. ${pageRange(s)}</button>`).join('');
}

// Documents that amend one another: newest first, so the reader sees the current text and what it replaced.
function versionBoxes(groups) {
  return groups.map(g => `<div class="vgroup"><b>Có nhiều phiên bản liên quan, ưu tiên văn bản mới nhất</b><ul>${g.map(v =>
    `<li><span class="badge ${v.latest ? 'ready' : 'processing'}">${v.latest ? 'Mới nhất' : 'Trước đó'}</span> `
    + `<button type="button" data-src="${esc(v.id)}">${esc(v.docNo ? 'Số ' + v.docNo : v.id)}${v.issued ? ' · ' + esc(v.issued) : ''}</button></li>`).join('')}</ul></div>`).join('');
}

function warning(data) {
  return data.uncited ? 'Câu trả lời chưa có trích dẫn nguồn. Đừng dùng khi chưa đối chiếu văn bản gốc.'
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
  body.innerHTML = '<span class="status">Đang tìm trong tài liệu<span class="dots"></span></span>'; scrollDown();
  const sources = messageSources[idx + 1] = {};
  let text = '', failed = false, aborted = false;
  ctrl = new AbortController();
  try {
    const r = await api('/api/chat', {method: 'POST', signal: ctrl.signal, headers: {'content-type': 'application/json'},
      body: JSON.stringify({messages: [...history, {role: 'user', content: question}], provider: settings.provider, model: settings.model,
        max_output_tokens: settings.max_output_tokens, style: settings.style, temperature: settings.temperature})});
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || 'Yêu cầu bị từ chối');
    for await (const [event, data] of sseEvents(r)) {
      if (event === 'sources') { data.sources.forEach(s => { sources[s.id] = s; }); botEl.querySelector('.srcs').innerHTML = sourceButtons(data.sources); botEl.querySelector('.vers').innerHTML = versionBoxes(data.versions || []); }
      else if (event === 'mode') botEl.dataset.mode = data.mode;
      else if (event === 'verify') botEl.querySelector('.srcs').insertAdjacentHTML('beforebegin', errorBox(warning(data), 'warn'));
      else if (event === 'delta') { if (!text) setRobot('talk'); text += data.text; body.innerHTML = renderAnswer(text, sources); }
      else if (event === 'error') { failed = true; setRobot('oops', 4000); body.insertAdjacentHTML('beforeend', errorBox(data.message)); }
      scrollDown();
    }
  } catch (x) {
    if (x.name === 'AbortError') { aborted = true; body.insertAdjacentHTML('beforeend', '<div class="status">(Đã dừng)</div>'); setRobot('idle'); }
    else { failed = true; setRobot('oops', 4000); body.insertAdjacentHTML('beforeend', errorBox(x.message)); }
  }
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
  $('#q').value = ''; $('#q').style.height = 'auto'; ask(q);
});
$('#q').addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); $('#ask').requestSubmit(); } });
$('#q').addEventListener('input', e => {
  if (!busy) setRobot(e.target.value ? 'typing' : 'idle', 1800);
  e.target.style.height = 'auto'; e.target.style.height = Math.min(e.target.scrollHeight, 160) + 'px';
});
$('#stop').onclick = () => ctrl && ctrl.abort();

// ---- source panel ----
function renderChunk(text) {  // escapes, then turns pipe-tables into real tables
  const out = []; let rows = [];
  const flush = () => {
    if (rows.length) out.push('<div class="tw"><table>' + rows.map((r, i) => '<tr>' + r.map(c => `<${i ? 'td' : 'th'}>${esc(c)}</${i ? 'td' : 'th'}>`).join('') + '</tr>').join('') + '</table></div>');
    rows = [];
  };
  for (const line of text.split('\n')) {
    const t = line.trim();
    if (t.startsWith('|')) { if (!/^\|[\s\-:|]+\|?$/.test(t)) rows.push(t.replace(/^\||\|$/g, '').split('|').map(c => c.trim())); }
    else { flush(); if (t) out.push(`<p>${esc(line)}</p>`); }
  }
  flush();
  return out.join('');
}
function openSource(id) {
  sourceOpener = document.activeElement;
  const s = (messageSources[sourceOpener.closest('.msg')?.dataset.idx] || {})[id];
  if (!s) return;
  $('#srcTitle').textContent = s.fileName;
  $('#srcMeta').textContent = `${s.id} · ${s.docNo ? 'Số ' + s.docNo : ''}${s.issued ? ' · ngày ' + s.issued : ''} · trang ${pageRange(s)}`;
  $('#srcExcerpt').innerHTML = renderChunk(s.excerpt);
  const isPdf = /\.pdf$/i.test(s.fileName);
  $('#srcFrame').hidden = !isPdf;
  $('#srcFrame').src = 'about:blank';
  $('#source').hidden = false; $('#app').classList.add('with-source'); $('#srcClose').focus();
  if (isPdf) showPdf(s);
}
// The iframe cannot send an Authorization header, so it loads a short-lived signed link.
async function showPdf(s) {
  try {
    const {url: link} = await getJson(`/api/documents/${encodeURIComponent(s.documentId)}/link`);
    $('#srcFrame').src = `${url(link)}#page=${s.pageStart}`;
  } catch { $('#srcExcerpt').insertAdjacentHTML('afterbegin', errorBox('Không mở được văn bản gốc.')); }
}
function closeSource() {
  $('#source').hidden = true; $('#app').classList.remove('with-source'); $('#srcFrame').src = 'about:blank';
  if (sourceOpener) sourceOpener.focus();
}
$('#srcClose').onclick = closeSource;
document.addEventListener('keydown', e => {
  if (e.key !== 'Escape' || $('#settings').open) return;
  if (!$('#source').hidden) closeSource(); else if (pane.classList.contains('open')) $('#docsClose').click();
});

// ---- login ----
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

// ---- start ----
async function start() {
  try { cfg = await getJson('/api/config'); }
  catch (x) { if (!(x instanceof AuthError)) $('#msgs').innerHTML = errorBox(x.message); return; }
  settings = {provider: cfg.default_provider, model: cfg.providers[cfg.default_provider].models[0],
    max_output_tokens: 1200, style: 'concise', temperature: 0.2, ...load('settings', {})};
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
