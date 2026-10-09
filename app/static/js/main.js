import { api } from './api.js';
import { state, filterParams, on, emit, resetFilters, COLORS, LABELS } from './state.js';
import { MapView } from './map.js';
import { initDrawer, openLocation, openRecord } from './details.js';
import { initFilters, refreshFacets, renderCounters, hasActiveFilters } from './filters.js';
import { initSearch } from './search.js';
import { openUpload } from './upload.js';
import { esc, num, debounce, toast } from './format.js';
import { t, initLanguage, onLanguageChange, setRegions, translateMessage } from './i18n.js';

const $ = (id) => document.getElementById(id);
let map; let reqSeq = 0; let lastSummary = null; let borders = true;
let legendCollapsed = window.matchMedia('(max-width: 700px)').matches;
let lastModel = null;
initLanguage();
onLanguageChange(() => {
  if (map) renderLegend();
  if (lastSummary) {
    renderCounters(lastSummary, hasActiveFilters());
    renderEmpty(lastSummary, map.lastFc);
  }
  renderModel();
});

// ---------------------------------------------------------------- legend
function renderLegend() {
  const mode = state.colorMode;
  const keys = mode === 'status' ? ['winner', 'predicted', 'pending'] : ['ezk', 'ef', 'ezt'];
  const s = lastSummary || {};
  const counts = mode === 'status' ? { winner: s.winner, predicted: s.predicted, pending: s.pending } : null;
  $('legend').classList.toggle('collapsed', legendCollapsed);
  $('legend').innerHTML = `
    <div class="legend-head">
      <button type="button" class="legend-toggle" aria-expanded="${!legendCollapsed}" aria-controls="legend-body">${t('Legend and layers')} ${legendCollapsed ? '\u25B8' : '\u25BE'}</button>
      <button type="button" class="icon-btn legend-close" aria-label="${t('Hide legend')}" title="${t('Hide legend')}">\u00d7</button>
    </div>
    <div class="lg-body" id="legend-body" ${legendCollapsed ? 'hidden' : ''}>
    <h4>${t('Colour by')}</h4>
    <div class="mode-switch" role="group" aria-label="${t('Colour markers by')}">
      <button type="button" data-mode="status" aria-pressed="${mode === 'status'}">${t('Status')}</button>
      <button type="button" data-mode="type" aria-pressed="${mode === 'type'}">${t('Purchase type')}</button>
    </div>
    ${keys.map((k) => `<div class="legend-row"><i class="dot" style="background:${COLORS[mode][k]}"></i><span>${esc(LABELS[mode][k])}</span>${counts && counts[k] !== undefined ? `<span class="muted num" style="margin-left:auto">${esc(num(counts[k]))}</span>` : ''}</div>`).join('')}
    <div class="legend-size"><span>${t('Size = number of tenders')}</span>
      <i style="width:14px;height:14px"></i><i style="width:24px;height:24px"></i><i style="width:36px;height:36px"></i></div>
    <label class="toggle"><input type="checkbox" id="tg-borders" ${borders ? 'checked' : ''}> ${t('Country and region borders')}</label>
    <button class="btn small" id="btn-fit" type="button" style="margin-top:8px">${t('Fit map to tenders')}</button></div>`;
  const setCollapsed = (collapsed) => {
    legendCollapsed = collapsed;
    renderLegend();
    $('legend').querySelector('.legend-toggle').focus();
  };
  $('legend').querySelector('.legend-toggle').addEventListener('click', () => setCollapsed(!legendCollapsed));
  $('legend').querySelector('.legend-close').addEventListener('click', () => setCollapsed(true));
  $('legend').querySelectorAll('[data-mode]').forEach((b) => b.addEventListener('click', () => {
    state.colorMode = b.dataset.mode; map.setColorMode(); renderLegend();
  }));
  $('tg-borders').addEventListener('change', (e) => { borders = e.target.checked; map.setBorders(borders); });
  $('btn-fit').addEventListener('click', () => map.fitToData());
}

// ---------------------------------------------------------------- data loading
async function reload() {
  const my = ++reqSeq;
  $('map-loading').classList.remove('hidden');
  try {
    const params = filterParams();
    const [fc, sum] = await Promise.all([api('/api/map/points', { params }), api('/api/summary', { params })]);
    if (my !== reqSeq) return; // a newer request superseded this one
    lastSummary = sum;
    map.lastFc = fc;
    map.setData(fc);
    renderCounters(sum, hasActiveFilters());
    renderLegend();
    renderEmpty(sum, fc);
  } catch (e) {
    if (my !== reqSeq) return;
    toast(e.message, 5000);
  } finally {
    if (my === reqSeq) $('map-loading').classList.add('hidden');
  }
}

function renderEmpty(sum, fc) {
  const box = $('map-empty');
  const total = state.facets ? state.facets.total : sum.n;
  let html = '';
  if (total === 0) {
    html = `<h2>${t('No tenders yet')}</h2><p>${t('Upload purchase numbers and they are fetched from GosPlan, stored and drawn on the map.')}</p><button class="btn primary" data-open-upload>${t('Upload tenders')}</button>`;
  } else if (sum.n === 0) {
    html = `<h2>${t('No tenders match these filters')}</h2><p>${t('Try removing a filter or widening the date or price range.')}</p><button class="btn" data-reset>${t('Reset all filters')}</button>`;
  } else if (!fc.features.length) {
    html = `<h2>${t('These tenders have no map location')}</h2><p>${t('They are still listed in search and can be opened from there. Locations come from the region code in the GosPlan record.')}</p>`;
  }
  box.innerHTML = html ? `<div>${html}</div>` : '';
  box.classList.toggle('hidden', !html);
}

// ---------------------------------------------------------------- model status
async function pollModel() {
  try {
    const h = await api('/api/health');
    const m = h.model;
    lastModel = m;
    renderModel();
    if (!m.ready && m.state !== 'error') setTimeout(pollModel, 4000);
  } catch { setTimeout(pollModel, 8000); }
}

function renderModel() {
  const pill = $('model-pill');
  const m = lastModel;
  if (!m) {
    pill.querySelector('span').textContent = t('Model loading');
    pill.title = t('Prediction model status');
    return;
  }
  pill.className = m.ready ? 'ready' : m.state === 'error' ? 'error' : 'loading';
  pill.querySelector('span').textContent = t(m.ready ? 'Model ready' : m.state === 'error' ? 'Model unavailable' : 'Model loading');
  pill.title = m.ready
    ? t('Model {version}; history covers purchases finished until {date}', { version: m.model_version || t('(legacy file)'), date: (m.history_until || '').slice(0, 10) })
      + ((m.library_warnings || []).length ? `. ${t('Library version warnings')}: ${m.library_warnings.map(translateMessage).join('; ')}` : '')
    : (m.error ? translateMessage(m.error) : t('The model loads in the background after start-up (about a minute).'));
}
renderModel();

// ---------------------------------------------------------------- boot
async function boot() {
  state.config = await api('/api/config');
  setRegions(state.config.regions || {});
  map = new MapView({ container: 'map', tiles: state.config.tiles, onLocation: (loc) => openLocation(loc) });
  initDrawer({
    onRecord: (d, { fly }) => {
      map.setSelectedLoc(d.loc_key || null);
      if (fly && d.has_location) map.flyToPoint(d.lon, d.lat);
    },
    onClose: () => map.setSelectedLoc(null),
  });
  initSearch({ onPick: (r) => openRecord(r.purchase_number, { back: null, fly: true }) });
  await initFilters();
  const refresh = debounce(reload, 120);
  on('filters-changed', refresh);
  on('data-changed', async () => { await refreshFacets(); reload(); });

  $('btn-upload').addEventListener('click', () => openUpload({ onDone: () => emit('data-changed') }));
  $('btn-filters').addEventListener('click', () => $('rail').classList.toggle('open'));
  $('map-empty').addEventListener('click', (e) => {
    if (e.target.closest('[data-open-upload]')) $('btn-upload').click();
    if (e.target.closest('[data-reset]')) resetFilters();
  });
  map.map.on('click', () => { $('rail').classList.remove('open'); });
  renderLegend();
  pollModel();
  reload();
}

boot().catch((e) => {
  console.error(e);
  document.getElementById('stage').insertAdjacentHTML('afterbegin', `<div class="notice err" style="position:absolute;z-index:50;margin:12px">${esc(t('The application could not start: {error}', { error: e.message }))}</div>`);
});
