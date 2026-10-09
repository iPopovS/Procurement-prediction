// Filter rail, generated from /api/filters (i.e. from the stored data).
import { api } from './api.js';
import { state, setFilters, resetFilters, on, COLORS, TYPE_KEY } from './state.js';
import { esc, num, money, debounce } from './format.js';
import { t, regionName, onLanguageChange } from './i18n.js';

const $ = (id) => document.getElementById(id);

export async function initFilters() {
  await refreshFacets();
  $('f-from').addEventListener('change', (e) => setFilters({ published_from: e.target.value }));
  $('f-to').addEventListener('change', (e) => setFilters({ published_to: e.target.value }));
  const price = debounce(() => setFilters({ price_min: $('f-pmin').value, price_max: $('f-pmax').value }), 400);
  $('f-pmin').addEventListener('input', price);
  $('f-pmax').addEventListener('input', price);
  $('f-loc').addEventListener('change', (e) => setFilters({ has_location: e.target.value }));
  $('btn-reset').addEventListener('click', () => resetFilters());
  $('f-region-q').addEventListener('input', (e) => {
    const q = e.target.value.trim().toLowerCase();
    for (const row of $('region-list').querySelectorAll('[data-name]')) row.classList.toggle('hidden', !!q && !row.dataset.name.includes(q));
  });
  initOrganizer();
  on('filters-reset', syncControls);
  onLanguageChange(() => {
    const prices = [$('f-pmin').value, $('f-pmax').value];
    if (state.facets) renderFacets(state.facets);
    // A price input may still be waiting for the debounce callback.
    [$('f-pmin').value, $('f-pmax').value] = prices;
  });
}

export async function refreshFacets() {
  const f = await api('/api/filters');
  state.facets = f;
  renderFacets(f);
}

function renderFacets(f) {
  renderStatus(f); renderTypes(f); renderRegions(f);
  const pr = f.price_range;
  $('price-hint').textContent = pr && pr.min !== null ? t('Data range: {min} to {max}', { min: money(pr.min), max: money(pr.max) }) : '';
  if (f.published_range && f.published_range.min) {
    $('f-from').min = $('f-to').min = f.published_range.min.slice(0, 10);
    $('f-from').max = $('f-to').max = f.published_range.max.slice(0, 10);
  }
  syncControls();
}

function radio(name, value, label, count, checked) {
  return `<label class="opt"><input type="radio" name="${name}" value="${esc(value)}" ${checked ? 'checked' : ''}><span>${esc(label)}</span><span class="cnt num">${esc(count === null ? '' : num(count))}</span></label>`;
}

function renderStatus(f) {
  const box = $('f-status');
  box.innerHTML = radio('status', '', t('All tenders'), f.total, !state.filters.status)
    + f.status.map((s) => radio('status', s.value, t(s.label), s.count, state.filters.status === s.value)).join('');
  box.onchange = (e) => setFilters({ status: e.target.value });
}

function renderTypes(f) {
  const box = $('f-type');
  box.innerHTML = f.purchase_type.map((item) => `<label class="opt" title="${esc(item.value)}"><input type="checkbox" value="${esc(item.value)}" ${state.filters.purchase_type.includes(item.value) ? 'checked' : ''}>
    <i class="dot" style="background:${COLORS.type[TYPE_KEY[item.value]] || '#8592a6'}"></i><span>${esc(t(item.label))}</span><span class="cnt num">${esc(num(item.count))}</span></label>`).join('')
    || `<div class="muted">${t('No data yet.')}</div>`;
  box.onchange = () => setFilters({ purchase_type: [...box.querySelectorAll('input:checked')].map((i) => i.value) });
}

function renderRegions(f) {
  const box = $('region-list');
  box.innerHTML = f.region.map((r) => `<label class="opt" data-name="${esc(regionName(r.value, r.label).toLowerCase())}"><input type="checkbox" value="${esc(r.value)}" ${state.filters.region.includes(r.value) ? 'checked' : ''}><span>${esc(regionName(r.value, r.label))}</span><span class="cnt num">${esc(num(r.count))}</span></label>`).join('')
    || `<div class="muted" style="padding:6px">${t('No data yet.')}</div>`;
  if (f.region_unknown_count) box.insertAdjacentHTML('beforeend', `<div class="muted" style="padding:6px;font-size:12px">${t('Tenders without a region: {n}', { n: num(f.region_unknown_count) })}</div>`);
  const q = $('f-region-q').value.trim().toLowerCase();
  for (const row of box.querySelectorAll('[data-name]')) row.classList.toggle('hidden', !!q && !row.dataset.name.includes(q));
  box.onchange = () => setFilters({ region: [...box.querySelectorAll('input:checked')].map((i) => i.value) });
}

function initOrganizer() {
  const inp = $('f-resp'); const list = $('resp-list');
  const run = debounce(async () => {
    const q = inp.value.trim();
    if (!q) { list.classList.add('hidden'); return; }
    try {
      const items = await api('/api/filters/responsibles', { params: { q, limit: 12 } });
      list.innerHTML = items.length
        ? items.map((i) => `<button type="button" data-v="${esc(i.value)}" data-l="${esc(i.label)}"><span style="flex:1">${esc(i.label)}<br><span class="muted" style="font-size:12px">ID ${esc(i.value)}</span></span><span class="muted num">${esc(num(i.count))}</span></button>`).join('')
        : `<div class="muted" style="padding:8px">${t('No organizer matches.')}</div>`;
      list.classList.remove('hidden');
    } catch { list.classList.add('hidden'); }
  }, 200);
  inp.addEventListener('input', run);
  onLanguageChange(() => { if (!list.classList.contains('hidden')) run(); });
  list.addEventListener('click', (e) => {
    const b = e.target.closest('button[data-v]');
    if (!b) return;
    setFilters({ responsible: b.dataset.v, responsible_label: b.dataset.l });
    inp.value = ''; list.classList.add('hidden'); syncControls();
  });
  document.addEventListener('click', (e) => { if (!e.target.closest('.ac-wrap')) list.classList.add('hidden'); });
}

// keep the controls in sync with state (after reset / facet refresh)
export function syncControls() {
  const f = state.filters;
  $('f-from').value = f.published_from; $('f-to').value = f.published_to;
  $('f-pmin').value = f.price_min; $('f-pmax').value = f.price_max;
  $('f-loc').value = f.has_location;
  document.querySelectorAll('#f-status input').forEach((i) => { i.checked = i.value === (f.status || ''); });
  document.querySelectorAll('#f-type input').forEach((i) => { i.checked = f.purchase_type.includes(i.value); });
  document.querySelectorAll('#region-list input').forEach((i) => { i.checked = f.region.includes(i.value); });
  $('resp-chip').innerHTML = f.responsible
    ? `<span class="sel-chip" title="ID ${esc(f.responsible)}"><span>${esc(f.responsible_label || f.responsible)}</span><button type="button" aria-label="${t('Remove organizer filter')}">\u00d7</button></span>` : '';
  const b = $('resp-chip').querySelector('button');
  if (b) b.onclick = () => { setFilters({ responsible: '', responsible_label: '' }); syncControls(); };
}

export function renderCounters(s, filtered) {
  const total = state.facets ? state.facets.total : s.n;
  $('counters').innerHTML = `
    <div id="count-main">${t(filtered ? 'Matching tenders: {n} of {total}' : 'Tenders: {n}', { n: `<b class="num">${esc(num(s.n))}</b>`, total: esc(num(total)) })}</div>
    <div class="count-chips">
      <span class="chip"><i style="background:${COLORS.status.winner}"></i>${esc(num(s.winner))} ${t('with winner')}</span>
      <span class="chip"><i style="background:${COLORS.status.predicted}"></i>${esc(num(s.predicted))} ${t('predicted')}</span>
      <span class="chip"><i style="background:${COLORS.status.pending}"></i>${esc(num(s.pending))} ${t('pending')}</span>
      ${s.unlocated ? `<span class="chip" title="${t('Listed and searchable, but without a map location')}">${esc(num(s.unlocated))} ${t('not on map')}</span>` : ''}
    </div>`;
}

export function hasActiveFilters() {
  const f = state.filters;
  return !!(f.status || f.purchase_type.length || f.region.length || f.responsible || f.published_from || f.published_to
    || f.price_min !== '' || f.price_max !== '' || f.has_location);
}
