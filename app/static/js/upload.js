// Upload dialog: paste numbers or load a file, optional immediate prediction, per-item report.
import { api } from './api.js';
import { esc, money, pct, num, toast } from './format.js';
import { t, translateDOM, translateMessage, onLanguageChange } from './i18n.js';

const CHUNK_NUMBERS = 25;
const CHUNK_RECORDS = 5;

function tokens(text) {
  return [...new Set(text.split(/[\s,;]+/).map((t) => t.trim()).filter(Boolean))];
}

async function readFile(file) {
  const text = await file.text();
  if (/\.json$/i.test(file.name) || /^\s*[\[{]/.test(text)) {
    let doc;
    try { doc = JSON.parse(text); } catch (e) { throw new Error(t('{file} is not valid JSON.', { file: file.name })); }
    if (doc && !Array.isArray(doc) && (doc.purchase_numbers || doc.records)) return { numbers: (doc.purchase_numbers || []).map(String), records: doc.records || [] };
    const arr = Array.isArray(doc) ? doc : [doc];
    return { numbers: arr.filter((x) => typeof x === 'string' || typeof x === 'number').map(String), records: arr.filter((x) => x && typeof x === 'object') };
  }
  const first = text.split(/\r?\n/, 1)[0].toLowerCase();
  const sep = (first.match(/;/g) || []).length > (first.match(/,/g) || []).length ? ';' : ',';
  const head = first.split(sep).map((h) => h.trim().replace(/^"|"$/g, ''));
  const col = head.indexOf('purchase_number');
  if (col >= 0) {
    const numbers = text.split(/\r?\n/).slice(1).map((l) => (l.split(sep)[col] || '').trim().replace(/^"|"$/g, '')).filter(Boolean);
    return { numbers, records: [] };
  }
  return { numbers: text.match(/\d{8,25}/g) || [], records: [] };
}

export function openUpload({ onDone }) {
  const root = document.getElementById('modal-root');
  let records = [];
  let running = false;
  let report = null; let fileInfo = null; let progress = null;
  root.innerHTML = `
    <div id="modal-back"><div id="modal" role="dialog" aria-modal="true" aria-labelledby="up-title">
      <header><h2 id="up-title" data-i18n="Upload tenders"></h2><button class="icon-btn" id="up-close" data-i18n-aria-label="Close">\u00d7</button></header>
      <div class="mbody">
        <label for="up-text" class="muted" data-i18n="Paste purchase numbers, separated by spaces, commas or new lines."></label>
        <textarea id="up-text" placeholder="0320300101526000015" spellcheck="false"></textarea>
        <div class="drop" id="up-drop"><span data-i18n="or drop a CSV, TXT or JSON file here"></span><input type="file" id="up-file" accept=".csv,.txt,.json" data-i18n-aria-label="Choose a file"></div>
        <div id="up-file-info" class="muted" style="margin-top:6px"></div>
        <div class="checks">
          <label class="opt"><input type="checkbox" id="up-predict" checked><span data-i18n="Predict prices immediately"></span></label>
          <label class="opt"><input type="checkbox" id="up-winner" checked><span data-i18n="Look up winner prices (display only, one extra request per tender)"></span></label>
          <label class="opt"><input type="checkbox" id="up-skip"><span data-i18n="Skip purchase numbers that are already stored"></span></label>
        </div>
        <div style="display:flex;gap:10px;align-items:center"><button class="btn primary" id="up-go" data-i18n="Upload"></button><span id="up-count" class="muted"></span></div>
        <div id="up-progress" class="hidden"><div class="progress"><i></i></div><div class="muted" id="up-ptext"></div></div>
        <div id="up-report"></div>
      </div></div></div>`;
  const $ = (id) => document.getElementById(id);
  const modal = $('modal');
  const visible = () => modal.isConnected;
  translateDOM(root);
  const count = () => { const n = tokens($('up-text').value).length + records.length; $('up-count').textContent = n ? t('Items ready: {n}', { n: num(n) }) : ''; return n; };
  const renderFileInfo = () => {
    if (fileInfo) $('up-file-info').textContent = t('{file}: loaded purchase numbers: {numbers}; full records: {records}.', { file: fileInfo.name, numbers: num(fileInfo.numbers), records: num(fileInfo.records) });
  };
  const renderProgress = () => {
    if (progress) $('up-ptext').textContent = running
      ? t('Processed {done} of {total}', { done: num(progress.done), total: num(progress.total) })
      : t('Finished: {n} items processed.', { n: num(progress.total) });
  };
  const unsubscribe = onLanguageChange(() => {
    if (!visible()) return;
    count(); renderFileInfo(); renderProgress();
    if (report) renderReport(report.results, report.opts);
  });
  const close = () => { if (running && !confirm(t('An upload is still running. Close anyway? It will continue in the background.'))) return; unsubscribe(); root.innerHTML = ''; document.removeEventListener('keydown', esc_); };
  const esc_ = (e) => { if (e.key === 'Escape') close(); };
  document.addEventListener('keydown', esc_);
  $('up-close').onclick = close;
  $('modal-back').addEventListener('mousedown', (e) => { if (e.target.id === 'modal-back') close(); });
  $('up-text').addEventListener('input', count);
  $('up-text').focus();

  async function loadFile(file) {
    try {
      const r = await readFile(file);
      if (!visible()) return;
      records = r.records;
      if (r.numbers.length) { const cur = tokens($('up-text').value); $('up-text').value = [...new Set([...cur, ...r.numbers])].join('\n'); }
      fileInfo = { name: file.name, numbers: r.numbers.length, records: r.records.length };
      renderFileInfo();
      count();
    } catch (e) { if (visible()) $('up-file-info').textContent = e.message; }
  }
  $('up-file').addEventListener('change', (e) => { if (e.target.files[0]) loadFile(e.target.files[0]); });
  const drop = $('up-drop');
  ['dragenter', 'dragover'].forEach((n) => drop.addEventListener(n, (e) => { e.preventDefault(); drop.classList.add('over'); }));
  ['dragleave', 'drop'].forEach((n) => drop.addEventListener(n, (e) => { e.preventDefault(); drop.classList.remove('over'); }));
  drop.addEventListener('drop', (e) => { if (e.dataTransfer.files[0]) loadFile(e.dataTransfer.files[0]); });

  $('up-go').onclick = async () => {
    const numbers = tokens($('up-text').value);
    if (!numbers.length && !records.length) { toast(t('Add at least one purchase number first.')); return; }
    const opts = { predict: $('up-predict').checked, fetch_winner: $('up-winner').checked, skip_existing: $('up-skip').checked };
    running = true; report = null; $('up-go').disabled = true; $('up-report').innerHTML = '';
    $('up-progress').classList.remove('hidden');
    const batches = [];
    for (let i = 0; i < numbers.length; i += CHUNK_NUMBERS) batches.push({ purchase_numbers: numbers.slice(i, i + CHUNK_NUMBERS) });
    for (let i = 0; i < records.length; i += CHUNK_RECORDS) batches.push({ records: records.slice(i, i + CHUNK_RECORDS) });
    const total = numbers.length + records.length;
    progress = { done: 0, total }; renderProgress();
    const results = []; let done = 0;
    for (const b of batches) {
      const size = (b.purchase_numbers || b.records).length;
      try {
        const r = await api('/api/tenders', { method: 'POST', body: { ...b, ...opts } });
        results.push(...r.results);
      } catch (e) {
        const ids = b.purchase_numbers || b.records.map((x) => x.purchase_number || t('(record)'));
        results.push(...ids.map((id) => ({ purchase_number: String(id), status: 'failed', error: e.rawMessage || e.message })));
      }
      done += size;
      progress.done = done;
      if (visible()) {
        $('up-progress').querySelector('i').style.width = `${(done / total) * 100}%`;
        renderProgress();
      }
    }
    running = false;
    report = { results, opts };
    if (visible()) { $('up-go').disabled = false; renderProgress(); renderReport(results, opts); }
    onDone();
  };

  function renderReport(results, opts) {
    const failedOnly = $('up-failed-only')?.checked || false;
    const c = (f) => results.filter(f).length;
    const stored = c((r) => r.status === 'created' || r.status === 'updated');
    const failed = c((r) => r.status === 'failed');
    const win = c((r) => r.winner_price !== null && r.winner_price !== undefined);
    const pred = c((r) => r.prediction && r.prediction.status === 'ok');
    const pfail = c((r) => r.prediction && r.prediction.status === 'failed');
    const chips = [
      `<span class="chip"><b>${num(stored)}</b> ${t('stored')}</span>`,
      c((r) => r.status === 'skipped') ? `<span class="chip"><b>${num(c((r) => r.status === 'skipped'))}</b> ${t('skipped')}</span>` : '',
      `<span class="chip"><b>${num(failed)}</b> ${t('failed')}</span>`,
      opts.fetch_winner ? `<span class="chip"><b>${num(win)}</b> ${t('with winner price')}</span>` : '',
      opts.predict ? `<span class="chip"><b>${num(pred)}</b> ${t('predicted')}</span>` : '',
      pfail ? `<span class="chip"><b>${num(pfail)}</b> ${t('not predictable')}</span>` : '',
    ].join('');
    const label = { created: t('Added'), updated: t('Updated'), skipped: t('Skipped'), failed: t('Failed') };
    const row = (r) => {
      let predCell = '\u2014';
      if (r.prediction) predCell = r.prediction.status === 'ok'
        ? `<span class="num">${esc(money(r.prediction.predicted_price))}</span> <span class="muted">(${esc(pct(r.prediction.expected_discount_pct))} ${t('below max')})</span>`
        : `<span class="muted">${esc(translateMessage(r.prediction.reason))}</span>`;
      const note = r.error || r.note || (r.winner_price == null && r.winner_note ? r.winner_note : '');
      return `<tr data-s="${r.status}"><td class="num">${esc(r.purchase_number)}</td><td><span class="st ${r.status}">${label[r.status] || esc(r.status)}</span></td>
        <td class="num">${r.winner_price != null ? esc(money(r.winner_price)) : '\u2014'}</td><td>${predCell}</td><td class="muted">${esc(translateMessage(note)) || '\u2014'}</td></tr>`;
    };
    $('up-report').innerHTML = `<h3 style="margin:16px 0 4px;font-size:14px">${t('Result')}</h3><div class="summary-grid">${chips}</div>
      ${failed ? `<label class="opt" style="width:max-content"><input type="checkbox" id="up-failed-only"><span>${t('Show only failed items')}</span></label>` : ''}
      <div style="max-height:300px;overflow:auto"><table class="report"><thead><tr><th>${t('Purchase number')}</th><th>${t('Result')}</th><th>${t('Winner price')}</th><th>${t('Prediction')}</th><th>${t('Note')}</th></tr></thead><tbody>${results.map(row).join('')}</tbody></table></div>`;
    const cb = $('up-failed-only');
    if (cb) {
      cb.onchange = () => $('up-report').querySelectorAll('tbody tr').forEach((tr) => tr.classList.toggle('hidden', cb.checked && tr.dataset.s !== 'failed'));
      cb.checked = failedOnly; cb.onchange();
    }
  }
}
