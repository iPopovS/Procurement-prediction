// Global search: debounced, respects the active filters, keyboard navigable.
import { api } from './api.js';
import { filterParams, on } from './state.js';
import { esc, money, num, debounce } from './format.js';
import { t, regionName, onLanguageChange } from './i18n.js';

export function initSearch({ onPick }) {
  const input = document.getElementById('search');
  const box = document.getElementById('search-results');
  let items = []; let active = -1; let seq = 0;
  let lastTotal = 0; let loading = false;

  const hide = () => { box.classList.add('hidden'); input.setAttribute('aria-expanded', 'false'); active = -1; };
  const show = () => { box.classList.remove('hidden'); input.setAttribute('aria-expanded', 'true'); };

  const render = (q, total, loading) => {
    if (loading && !items.length) { box.innerHTML = `<div class="sr-empty">${t('Searching…')}</div>`; return show(); }
    if (!items.length) { box.innerHTML = `<div class="sr-empty">${esc(t('No tenders match “{q}”. Check the spelling or clear the filters.', { q }))}</div>`; return show(); }
    box.innerHTML = items.map((r, i) => `
      <button class="sr-item" role="option" data-i="${i}" aria-selected="${i === active}">
        <span class="sr-title">${esc(r.title) || `<span class="muted">${t('No title')}</span>`}</span>
        <span class="sr-price num">${esc(money(r.max_price))}</span>
        <span class="sr-meta">${esc(r.purchase_number)} \u00b7 ${esc(t(r.type_label || ''))} \u00b7 ${esc(regionName(r.region_code, r.region_name)) || t('No region')}${r.has_location ? '' : ` \u00b7 ${t('not on map')}`}</span>
      </button>`).join('') + `<div class="sr-foot">${total > items.length ? t('Showing {n} of {total} matches. Keep typing to narrow down.', { n: num(items.length), total: num(total) }) : t('Matches: {n}', { n: num(total) })}</div>`;
    show();
  };

  const run = debounce(async () => {
    const q = input.value.trim();
    if (q.length < 2) { hide(); return; }
    const my = ++seq;
    items = []; active = -1;   // never leave results of the previous query selectable
    loading = true;
    render(q, 0, true);
    try {
      const r = await api('/api/tenders', { params: { ...filterParams(), q, limit: 8 } });
      if (my !== seq) return;
      items = r.items; active = -1;
      lastTotal = r.total; loading = false;
      render(q, r.total, false);
    } catch (e) {
      if (my !== seq) return;
      items = [];
      loading = false;
      box.innerHTML = `<div class="sr-empty">${esc(e.message)}</div>`; show();
    }
  }, 200);

  const pick = (i) => { const r = items[i]; if (!r) return; hide(); input.blur(); onPick(r); };

  input.addEventListener('input', run);
  input.addEventListener('focus', () => { if (input.value.trim().length >= 2 && items.length) show(); });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { hide(); return; }
    if (box.classList.contains('hidden') || !items.length) return;
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      active = (active + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
      box.querySelectorAll('.sr-item').forEach((b, i) => { b.setAttribute('aria-selected', i === active); if (i === active) b.scrollIntoView({ block: 'nearest' }); });
    } else if (e.key === 'Enter') { e.preventDefault(); pick(active >= 0 ? active : 0); }
  });
  box.addEventListener('mousedown', (e) => { const b = e.target.closest('.sr-item'); if (b) { e.preventDefault(); pick(+b.dataset.i); } });
  document.addEventListener('click', (e) => { if (!e.target.closest('#search-wrap')) hide(); });
  on('filters-changed', () => { if (input.value.trim().length >= 2) run(); });
  onLanguageChange(() => { if (!box.classList.contains('hidden')) render(input.value.trim(), lastTotal, loading); });
}
