// Right-hand drawer: location selector (several records at one point) and record details.
import { api } from './api.js';
import { state, filterParams, emit, COLORS, LABELS } from './state.js';
import { money, pct, signedPct, dateTime, esc, orDash, DASH, debounce, toast, num } from './format.js';
import { t, regionName, translateMessage, onLanguageChange } from './i18n.js';

const el = () => document.getElementById('drawer');
const ok = (v) => v !== null && v !== undefined && v !== '';
let hooks = { onRecord: () => {}, onClose: () => {} };
let view = null; // {type:'list', loc} | {type:'record', pn, back}
let listState = null;
let seq = 0;

export function initDrawer(h) {
  hooks = { ...hooks, ...h };
  el().addEventListener('click', onClick);
  el().addEventListener('input', onInput);
  onLanguageChange(() => {
    if (!view || !isOpen()) return;
    const scroll = document.getElementById('drawer-body')?.scrollTop || 0;
    if (view.type === 'record' && view.detail) renderRecord();
    else if (view.type === 'list' && listState && !listState.loading) {
      const input = document.getElementById('pick-q');
      const draft = input?.value;
      const focused = document.activeElement === input;
      renderList();
      const replacement = document.getElementById('pick-q');
      if (draft !== undefined) replacement.value = draft;
      if (focused) replacement.focus();
    }
    const body = document.getElementById('drawer-body');
    if (body) body.scrollTop = scroll;
  });
}

export function isOpen() { return !el().classList.contains('closed'); }
export function currentPn() { return view && view.type === 'record' ? view.pn : null; }

export function close() {
  el().classList.add('closed');
  view = null;
  hooks.onClose();
}

function open() { el().classList.remove('closed'); }

// ------------------------------------------------------------------ location selector
export async function openLocation(loc) {
  const my = ++seq;
  open();
  view = { type: 'list', loc };
  listState = { items: [], total: 0, q: '', loading: true };
  el().innerHTML = `<div class="dr-head"><div class="grow"><b>${esc(regionName(loc.region) || t('Location'))}</b><div class="muted" data-i18n="Loading tenders…">${t('Loading tenders…')}</div></div>${closeBtn()}</div>`;
  try {
    const r = await fetchList(loc, '', 0);
    if (my !== seq) return;
    if (r.total === 1) { await openRecord(r.items[0].purchase_number, { back: null, fly: false }); return; }
    listState = { items: r.items, total: r.total, q: '', loading: false };
    renderList();
  } catch (e) {
    if (my !== seq) return;
    el().innerHTML = `<div class="dr-head"><div class="grow"><b>${esc(regionName(loc.region) || t('Location'))}</b></div>${closeBtn()}</div><div id="drawer-body"><div class="notice err">${esc(e.message)}</div></div>`;
  }
}

function fetchList(loc, q, offset) {
  return api('/api/tenders', { params: { ...filterParams(), q, loc_key: loc.loc_key, sort: 'price_desc', limit: 40, offset } });
}

function renderList() {
  const { loc } = view;
  const { items, total, q } = listState;
  const approx = loc.approximate ? `<span class="tag approx" title="${t('Exact coordinates are not available; the point is the centre of the region.')}">${t('Approximate location')}</span>` : '';
  const rows = items.map((r) => `
    <button class="pick" data-pn="${esc(r.purchase_number)}">
      <span class="t">${esc(r.title) || `<span class="muted">${t('No title')}</span>`}</span>
      <span class="p num">${esc(money(r.max_price))}</span>
      <span class="m"><i class="dot" style="background:${COLORS.status[r.status] || COLORS.status.pending}"></i>${esc(t(r.type_label || ''))} <span class="num">${esc(r.purchase_number)}</span></span>
    </button>`).join('');
  const empty = !items.length ? `<div class="muted" style="padding:18px 6px">${t(q ? 'No tenders at this location match your search.' : 'No tenders here.')}</div>` : '';
  const more = items.length < total ? `<div style="padding:12px 6px"><button class="btn small" data-act="more">${t('Show more ({n} left)', { n: num(total - items.length) })}</button></div>` : '';
  el().innerHTML = `
    <div class="dr-head"><div class="grow"><b>${esc(t('{n} tenders — {region}', { n: num(total), region: regionName(loc.region) || t('this location') }))}</b><div class="tags" style="margin-top:6px">${approx}</div></div>${closeBtn()}</div>
    <div style="padding:10px 14px 0"><input id="pick-q" type="search" value="${esc(q)}" placeholder="${t('Search within these tenders')}" aria-label="${t('Search within these tenders')}" style="width:100%;height:34px;padding:0 10px;border:1px solid var(--rule);border-radius:8px"></div>
    <div id="drawer-body" style="padding-top:6px"><div class="pick-list">${rows}</div>${empty}${more}</div>`;
  const inp = document.getElementById('pick-q');
  if (listState.focusQ) { inp.focus(); inp.setSelectionRange(q.length, q.length); }
}

const searchInList = debounce(async (q) => {
  if (!view || view.type !== 'list') return;
  const my = ++seq;
  try {
    const r = await fetchList(view.loc, q, 0);
    if (my !== seq) return;
    listState = { items: r.items, total: r.total, q, loading: false, focusQ: true };
    renderList();
  } catch (e) { toast(e.message); }
}, 250);

// ------------------------------------------------------------------ record details
export async function openRecord(pn, { back = undefined, fly = true } = {}) {
  const my = ++seq;
  open();
  const prevBack = back !== undefined ? back : (view && view.type === 'list' ? view.loc : (view && view.type === 'record' ? view.back : null));
  view = { type: 'record', pn, back: prevBack };
  el().innerHTML = `<div class="dr-head"><div class="grow"><span class="pn-btn" aria-busy="true">${esc(pn)}</span></div>${closeBtn()}</div><div id="drawer-body"><div class="muted"><span class="spinner"></span> <span data-i18n="Loading…">${t('Loading…')}</span></div></div>`;
  try {
    const d = await api(`/api/tenders/${encodeURIComponent(pn)}`);
    if (my !== seq) return;
    view.detail = d;
    renderRecord();
    hooks.onRecord(d, { fly });
  } catch (e) {
    if (my !== seq) return;
    el().innerHTML = `<div class="dr-head"><div class="grow"><span class="pn-btn">${esc(pn)}</span></div>${closeBtn()}</div><div id="drawer-body"><div class="notice err">${esc(e.message)}</div></div>`;
  }
}

function closeBtn() {
  return `<button class="icon-btn" data-act="close" data-i18n-aria-label="Close panel" aria-label="${t('Close panel')}"><svg width="16" height="16" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" fill="none"><path d="M6 6l12 12M18 6L6 18"/></svg></button>`;
}

function statusTag(d) {
  const map = { winner: [LABELS.status.winner, COLORS.status.winner], predicted: [LABELS.status.predicted, COLORS.status.predicted], pending: [LABELS.status.pending, COLORS.status.pending] };
  const [t, c] = map[d.status] || map.pending;
  return `<span class="tag"><i class="dot" style="background:${c}"></i>${t}</span>`;
}

function codeList(arr) {
  if (!arr || !arr.length) return DASH;
  return `${arr.length}<div class="codes">${arr.map((c) => `<code>${esc(c)}</code>`).join('')}</div>`;
}

// ---- the price ladder: 0 ... max price, with predicted (above) and winner (below) markers
function ladder(d) {
  const max = d.max_price;
  const pr = d.prediction.available ? d.prediction.predicted_price : null;
  const win = d.winner.price;
  if (!ok(max)) return `<div class="ladder"><div class="ladder-sub">${t('The maximum price is not available for this tender.')}</div></div>`;
  const x = (v) => Math.max(0, Math.min(100, (v / max) * 100));
  const align = (p) => (p < 20 ? 'l' : p > 80 ? 'r' : '');
  let big; let sub;
  if (pr !== null) {
    const disc = d.prediction.expected_discount_pct;
    big = money(pr);
    sub = esc(t('Predicted price, {discount} below the max price of {max}', { discount: pct(disc), max: money(max) }));
  } else if (win !== null) {
    big = money(win);
    sub = esc(t('Winner price, {discount} below the max price of {max}', { discount: pct((1 - win / max) * 100), max: money(max) }));
  } else {
    big = money(max);
    sub = t('Max price. No prediction has been generated yet.');
  }
  const ticks = [];
  if (pr !== null) { const p = x(pr); ticks.push(`<div class="tick up pred ${align(p)}" style="left:${p}%"><span>${t('Predicted')} ${esc(money(pr))}</span></div>`); }
  if (win !== null) { const p = x(win); ticks.push(`<div class="tick down win ${align(p)}" style="left:${p}%"><span>${t('Winner')} ${esc(money(win))}</span></div>`); }
  const fill = pr !== null ? `<div class="ladder-fill" style="width:${x(pr)}%"></div>` : '';
  return `
    <div class="ladder">
      <div class="ladder-head"><div class="ladder-big num">${esc(big)}</div></div>
      <div class="ladder-sub">${sub}</div>
      <div class="ladder-axis${win === null ? ' short' : ''}" role="img" aria-label="${t('Price scale from zero to the maximum price')}">
        <div class="ladder-track">${fill}</div>${ticks.join('')}
      </div>
      <div class="ladder-ends"><span>0</span><span>${t('Max price')} ${esc(money(max))}</span></div>
    </div>`;
}

function predictionBlock(d) {
  const p = d.prediction;
  if (!p.available) {
    const err = p.error ? `<div class="notice err"><b>${t('Prediction unavailable.')}</b> ${esc(translateMessage(p.error))}</div>` : '';
    return `<div class="box">${err}
      <div style="margin-top:${err ? 10 : 0}px"><button class="btn primary" data-act="predict" id="btn-predict">${t(p.error ? 'Try again' : 'Generate price prediction')}</button></div>
      <div class="muted" style="margin-top:8px;font-size:12.5px">${t('Uses only what was known when the notice was published.')}</div></div>`;
  }
  const lowPct = p.p_low * 100; const partPct = p.p_partial * 100; const noPct = p.p_nodrop * 100;
  const sc = [
    [t('Very low price (under 1% of max, usually per-unit pricing)'), lowPct, '#3a7ca5'],
    [t('Partial price drop'), partPct, COLORS.status.predicted],
    [t('No drop (ends at the max price)'), noPct, COLORS.status.pending],
  ];
  const err = d.prediction_error;
  const errLine = err
    ? `<div class="notice" style="background:var(--paper);color:var(--ink)">${t('Compared with the winner price, the prediction was')} <b class="${err.abs > 0 ? 'err-pos' : 'err-neg'}">${t(err.abs > 0 ? 'too high' : 'too low')}: ${esc(money(Math.abs(err.abs)))}</b> (${esc(signedPct(err.pct_of_winner))} ${t('of the winner price')}, ${esc(pct(Math.abs(err.pct_of_max_price)))} ${t('of the max price')}).</div>`
    : '';
  const h = p.history || {};
  const typical = p.typical_error_ratio;
  const warn = (p.warnings || []).length ? `<div class="notice"><b>${t('Take with care')}</b><ul>${p.warnings.map((w) => `<li>${esc(translateMessage(w))}</li>`).join('')}</ul></div>` : '';
  const likelyMap = { very_low: t('a very low final price'), partial_drop: t('a partial price drop'), no_drop: t('no price drop') };
  return `
    <div class="sect"><h3>${t('How the model sees it')}</h3>
      <div>${t('Most likely outcome')}: <b>${esc(likelyMap[p.most_likely_outcome] || DASH)}</b>.</div>
      <div class="stack" role="img" aria-label="${t('Outcome probabilities')}">${sc.map(([, v, c]) => `<i style="width:${v}%;background:${c}"></i>`).join('')}</div>
      <div class="stack-legend">${sc.map(([t, v, c]) => `<div><i class="dot" style="background:${c}"></i><span>${esc(t)}</span><span class="pct num">${esc(pct(v, 0))}</span></div>`).join('')}</div>
      <dl class="kv" style="margin-top:12px">
        <dt>${t('For totals')}</dt><dd><b class="num">${esc(money(p.predicted_price_for_sums))}</b><span class="sub">${t('Mean estimate. Use this, not the figure above, when adding up many tenders.')}</span></dd>
        <dt>${t('Typical error')}</dt><dd>${esc(t('About {pct} of the max price ({price}) per tender, on average.', { pct: pct(typical * 100, 0), price: money(typical * d.max_price) }))}<span class="sub">${t('Reference value from the model documentation, not a confidence interval.')}</span></dd>
        <dt>${t('History used')}</dt><dd>${esc(t('{n} earlier finished purchases by this organizer. Of those, {g2} share the purchase type and product group (first 2 characters of the code) and {g5} the narrower group (first 5 characters).', { n: num(h.organizer_n), g2: num(h.group2_n), g5: num(h.group5_n) }))}</dd>
      </dl>
      ${errLine}${warn}
      <div style="margin-top:10px"><button class="btn small" data-act="predict" id="btn-predict">${t('Regenerate prediction')}</button></div>
    </div>`;
}

function winnerBlock(d) {
  const w = d.winner;
  if (w.price === null || w.price === undefined) {
    return `<div class="muted" style="margin-top:14px;font-size:12.5px">${t('No winner price on record.')} <button class="btn ghost small" data-act="winner">${t('Check the protocols again')}</button></div>`;
  }
  const disc = d.max_price ? (1 - w.price / d.max_price) * 100 : null;
  const src = w.source === 'uploaded' ? t('provided with the uploaded record') : w.published_at ? t('taken from the protocol published {date}', { date: dateTime(w.published_at) }) : t('taken from the protocols');
  return `<div class="sect"><h3>${t('Winner price')}</h3>
    <div><b class="num" style="font-size:18px">${esc(money(w.price, { cents: true }))}</b> <span class="muted">${esc(pct(disc))} ${t('below the max price')}</span></div>
    <div class="muted" style="font-size:12.5px">${esc(src)}.${w.note ? ` ${esc(translateMessage(w.note))}.` : ''} ${t('Shown for reference only; the model never sees it.')}</div></div>`;
}

function renderRecord() {
  const d = view.detail;
  const ex = d.extras || {};
  const gp = d.gosplan || {};
  const raw = d.raw || {};
  const back = view.back
    ? `<button class="btn ghost small" data-act="back" style="margin:0 0 6px -8px">\u2039 ${esc(t('All {n} tenders — {region}', { n: num(view.back.n), region: regionName(view.back.region) || t('this location') }))}</button>`
    : '';
  const locTag = d.has_location
    ? (d.approximate_location ? `<span class="tag approx" title="${t('Exact coordinates are not available; the point is the centre of the region.')}">${t('Approximate location')}</span>` : `<span class="tag">${t('Exact location')}</span>`)
    : `<span class="tag">${t('No map location')}</span>`;
  const places = (ex.delivery_places_text || []).map((t) => `<span class="sub">${esc(t)}</span>`).join('');
  const guarantee = ok(d.contract_guarantee_part)
    ? `${esc(pct(d.contract_guarantee_part))}${ok(d.max_price) ? `<span class="sub">${t('about')} ${esc(money(d.max_price * d.contract_guarantee_part / 100))}</span>` : ''}`
    : (ok(gp.contract_guarantee_amount) ? esc(money(gp.contract_guarantee_amount)) : DASH);
  const title = d.title
    ? `<h2 class="d-title">${esc(d.title)}</h2>${d.title_source === 'notice_document' ? `<div class="muted" style="font-size:12px;margin:-4px 0 6px">${t('Title taken from the notice document.')}</div>` : ''}`
    : `<h2 class="d-title empty">${t('No title available')}</h2>`;
  el().innerHTML = `
    <div class="dr-head"><div class="grow">${back}
      <button class="pn-btn" data-act="download" title="${t('Download the GosPlan JSON for this purchase')}" aria-label="${esc(t('Download GosPlan data for purchase {pn}', { pn: d.purchase_number }))}">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4v11m0 0l-4-4m4 4l4-4M5 20h14"/></svg>${esc(d.purchase_number)}</button>
    </div>${closeBtn()}</div>
    <div id="drawer-body">
      ${title}
      <div class="tags">${statusTag(d)}<span class="tag" title="${esc(d.purchase_type)}"><i class="dot" style="background:${COLORS.type[{ epNotificationEZK2020: 'ezk', epNotificationEF2020: 'ef', epNotificationEZT2020: 'ezt' }[d.purchase_type]] || '#8592a6'}"></i>${orDash(t(d.type_label || ''))}</span>${locTag}</div>
      <div class="sect"><h3>${t('Price')}</h3>${ladder(d)}</div>
      ${predictionBlock(d)}
      ${winnerBlock(d)}
      <div class="sect"><h3>${t('Details')}</h3>
        <dl class="kv">
          <dt>${t('Organizer')}</dt><dd>${orDash(d.responsible_name)}${d.responsible ? `<span class="sub">ID ${esc(d.responsible)}</span>` : ''}${ex.responsible_address ? `<span class="sub">${esc(ex.responsible_address)}</span>` : ''}</dd>
          <dt>${t('Purchase type')}</dt><dd>${orDash(t(d.type_label || ''))}<span class="sub">${esc(d.purchase_type)}</span>${ex.placing_way ? `<span class="sub">${esc(ex.placing_way)}</span>` : ''}</dd>
          <dt>${t('Location')}</dt><dd>${orDash(regionName(d.region_code, d.region_name))}${places}</dd>
          <dt>${t('Published')}</dt><dd>${esc(dateTime(d.published_at))}</dd>
          <dt>${t('Bids due')}</dt><dd>${esc(dateTime(d.collecting_finished_at))}</dd>
          <dt>${t('Max price')}</dt><dd><b class="num">${esc(money(d.max_price, { cents: true }))}</b></dd>
          <dt>${t('Contract guarantee')}</dt><dd>${guarantee}</dd>
          <dt>${t('KTRU codes')}</dt><dd>${codeList(raw.ktru)}</dd>
          <dt>${t('OKPD2 codes')}</dt><dd>${codeList(raw.okpd2)}</dd>
          <dt>${t('Positions')}</dt><dd>${esc(num(raw.position_numbers_cnt))}</dd>
          <dt>${t('Plan numbers')}</dt><dd>${(gp.plan_numbers || []).length ? gp.plan_numbers.map(esc).join(', ') : DASH}</dd>
          <dt>${t('IKZ')}</dt><dd>${(gp.ikzs || []).length ? gp.ikzs.map(esc).join(', ') : DASH}</dd>
          <dt>${t('Trading platform')}</dt><dd>${orDash(ex.etp)}</dd>
          <dt>${t('Official notice')}</dt><dd>${/^https?:\/\//i.test(ex.notice_url || '') ? `<a href="${esc(ex.notice_url)}" target="_blank" rel="noopener noreferrer">${t('Open on zakupki.gov.ru')}</a>` : DASH}</dd>
          <dt>${t('Updated at source')}</dt><dd>${esc(dateTime(gp.updated_at || gp.doc_updated_at))}</dd>
          <dt>${t('Stored in this app')}</dt><dd>${esc(dateTime(d.updated_at))}</dd>
        </dl>
      </div>
    </div>`;
  if (view.busy) {
    el().querySelectorAll('[data-act="predict"], [data-act="winner"]').forEach((btn) => { btn.disabled = true; });
    if (view.busy === 'predict') {
      const btn = document.getElementById('btn-predict');
      if (btn) btn.innerHTML = `<span class="spinner"></span> ${t('Generating…')}`;
    }
  }
}

// ------------------------------------------------------------------ events
async function onClick(e) {
  const pick = e.target.closest('[data-pn]');
  if (pick) { openRecord(pick.dataset.pn, { back: view && view.type === 'list' ? view.loc : null, fly: false }); return; }
  const btn = e.target.closest('[data-act]');
  if (!btn) return;
  const act = btn.dataset.act;
  if (act === 'close') close();
  else if (act === 'back' && view && view.back) openLocation(view.back);
  else if (act === 'more') loadMore(btn);
  else if (act === 'download') download(btn);
  else if (act === 'predict') predict(btn);
  else if (act === 'winner') refreshWinner(btn);
}

function onInput(e) {
  if (e.target.id === 'pick-q') searchInList(e.target.value.trim());
}

async function loadMore(btn) {
  btn.disabled = true;
  try {
    const r = await fetchList(view.loc, listState.q, listState.items.length);
    listState.items = listState.items.concat(r.items);
    listState.total = r.total;
    listState.focusQ = false;
    renderList();
  } catch (err) { toast(err.message); btn.disabled = false; }
}

async function download(btn) {
  const pn = view.pn;
  btn.setAttribute('aria-busy', 'true');
  try {
    const res = await fetch(`/api/tenders/${encodeURIComponent(pn)}/download`);
    if (!res.ok) {
      let msg = t('GosPlan could not deliver this purchase (HTTP {status}).', { status: res.status });
      try { msg = translateMessage((await res.json()).detail) || msg; } catch { /* keep default */ }
      throw new Error(msg);
    }
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement('a');
    a.href = url; a.download = `${pn}.json`;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  } catch (err) { toast(err.message, 5000); } finally { btn.removeAttribute('aria-busy'); }
}

async function predict(btn) {
  const current = view;
  const pn = current.pn;
  current.busy = 'predict';
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span> ${t('Generating…')}`;
  try {
    current.detail = await api(`/api/tenders/${encodeURIComponent(pn)}/predict`, { method: 'POST' });
    current.busy = null;
    if (view === current) renderRecord();
    emit('data-changed');
  } catch (err) {
    current.busy = null;
    current.detail.prediction = { ...current.detail.prediction, available: false, error: err.rawMessage || err.message };
    if (view === current) renderRecord();
  }
}

async function refreshWinner(btn) {
  const current = view;
  const pn = current.pn;
  current.busy = 'winner';
  btn.disabled = true;
  try {
    const had = current.detail.winner.price;
    current.detail = await api(`/api/tenders/${encodeURIComponent(pn)}/winner`, { method: 'POST' });
    current.busy = null;
    if (view === current) renderRecord();
    if (current.detail.winner.price !== had) emit('data-changed');
    else toast(t('No winner price has been published yet.'));
  } catch (err) { current.busy = null; toast(err.message); if (view === current) renderRecord(); }
}
