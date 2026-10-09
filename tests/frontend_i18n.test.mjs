// Run with: node --test tests/frontend_i18n.test.mjs (no npm dependencies).
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync, readdirSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

const storage = new Map();
globalThis.localStorage = {
  getItem: (key) => storage.get(key) ?? null,
  setItem: (key, value) => storage.set(key, value),
};

class Element {
  constructor(attrs = {}) {
    this.attrs = { ...attrs }; this.dataset = {}; this.listeners = {}; this.style = {};
    this.textContent = ''; this.innerHTML = ''; this.value = ''; this.checked = false;
    this.isConnected = true; this.scrollTop = 0;
    const classes = new Set();
    this.classList = {
      add: (name) => classes.add(name), remove: (name) => classes.delete(name),
      contains: (name) => classes.has(name),
      toggle: (name, force) => { if (force ?? !classes.has(name)) classes.add(name); else classes.delete(name); },
    };
  }
  getAttribute(name) { return this.attrs[name]; }
  setAttribute(name, value) { this.attrs[name] = value; }
  removeAttribute(name) { delete this.attrs[name]; }
  addEventListener(name, fn) { this.listeners[name] = fn; }
  querySelectorAll() { return []; }
  querySelector() { return new Element(); }
  focus() { document.activeElement = this; }
  setSelectionRange() {}
}
const elements = new Map();
const marked = [];
globalThis.document = {
  documentElement: { lang: '' }, activeElement: null,
  getElementById: (id) => {
    if (!elements.has(id)) elements.set(id, new Element());
    return elements.get(id);
  },
  querySelectorAll: (selector) => {
    const attr = /^\[([^\]]+)\]$/.exec(selector)?.[1];
    return attr ? marked.filter((el) => Object.hasOwn(el.attrs, attr)) : [];
  },
  addEventListener() {}, removeEventListener() {},
};

const i18n = await import('../app/static/js/i18n.js');
const format = await import('../app/static/js/format.js');
const { state, LABELS, COLORS } = await import('../app/static/js/state.js');
const { api, ApiError } = await import('../app/static/js/api.js');

test('Russian is the default, regardless of browser locale', () => {
  assert.equal(i18n.getLanguage(), 'ru');
  assert.equal(i18n.getLocale(), 'ru-RU');
  assert.equal(i18n.t('Upload tenders'), 'Загрузить закупки');
});

test('switch translates marked text/attributes and saves preference, not source data', () => {
  const title = new Element({ 'data-i18n': 'Tender Price Predictor' });
  title.dataset.i18n = 'Tender Price Predictor';
  const input = new Element({ 'data-i18n-placeholder': 'Search tenders', 'data-i18n-aria-label': 'Search tenders' });
  input.value = 'Исходный запрос';
  const ru = new Element({ 'data-language': 'ru' }); ru.dataset.language = 'ru';
  const en = new Element({ 'data-language': 'en' }); en.dataset.language = 'en';
  marked.push(title, input, ru, en);
  i18n.initLanguage();
  assert.equal(document.documentElement.lang, 'ru');
  assert.equal(title.textContent, 'Прогноз цены закупки');
  assert.equal(input.attrs.placeholder, 'Поиск закупок');
  en.listeners.click();
  assert.equal(document.documentElement.lang, 'en');
  assert.equal(title.textContent, 'Tender Price Predictor');
  assert.equal(en.attrs['aria-pressed'], 'true');
  assert.equal(input.value, 'Исходный запрос');
  assert.equal(storage.get('tender-predictor-language'), 'en');
  ru.listeners.click();
});

test('preference survives a fresh module load; invalid and blocked storage default to Russian', async () => {
  storage.set('tender-predictor-language', 'en');
  const saved = await import('../app/static/js/i18n.js?saved');
  assert.equal(saved.getLanguage(), 'en');
  storage.set('tender-predictor-language', 'fr');
  const invalid = await import('../app/static/js/i18n.js?invalid');
  assert.equal(invalid.getLanguage(), 'ru');
  const original = globalThis.localStorage;
  globalThis.localStorage = { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('blocked'); } };
  try {
    const blocked = await import('../app/static/js/i18n.js?blocked');
    assert.equal(blocked.getLanguage(), 'ru');
    assert.doesNotThrow(() => blocked.setLanguage('en'));
  } finally { globalThis.localStorage = original; }
});

test('invalid languages are ignored; listeners fire once and can unsubscribe', () => {
  let count = 0;
  const stop = i18n.onLanguageChange(() => count++);
  i18n.setLanguage('de'); i18n.setLanguage('ru');
  assert.equal(count, 0);
  i18n.setLanguage('en');
  assert.equal(count, 1);
  stop(); i18n.setLanguage('ru');
  assert.equal(count, 1);
});

test('numbers, currency, percentages and UTC dates follow the selected language', () => {
  i18n.setLanguage('ru');
  assert.equal(format.num(12345), new Intl.NumberFormat('ru-RU').format(12345));
  assert.equal(format.money(12345), new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 }).format(12345));
  assert.equal(format.pct(12.5), '12,5%');
  assert.equal(format.signedPct(-12.5), '−12,5%');
  const iso = '2026-01-30T00:03:03.391000';
  assert.equal(format.parseUTC(iso).toISOString(), '2026-01-30T00:03:03.391Z');
  assert.match(format.dateTime(iso), /UTC$/);
  assert.match(format.day(iso), /янв/);
  i18n.setLanguage('en');
  assert.equal(format.num(12345), '12,345');
  assert.equal(format.pct(12.5), '12.5%');
  assert.match(format.day(iso), /Jan/);
  for (const missing of [null, undefined, '', NaN, Infinity]) {
    assert.equal(format.money(missing), '—'); assert.equal(format.num(missing), '—');
  }
  assert.equal(format.dateTime('not-a-date'), '—');
  i18n.setLanguage('ru');
});

test('all bundled regions localize by code or stored English name, including unknown codes', () => {
  const regions = JSON.parse(readFileSync(new URL('../app/data/regions.json', import.meta.url), 'utf8'));
  i18n.setRegions(regions);
  for (const [code, region] of Object.entries(regions)) {
    assert.equal(i18n.regionName(code), region.name_ru);
    assert.equal(i18n.regionName(region.name_en), region.name_ru);
  }
  assert.equal(i18n.regionName('90', 'Region 90'), 'Регион 90');
  assert.equal(i18n.regionName('Region 90'), 'Регион 90');
  assert.equal(i18n.regionName(null, 'Custom source name'), 'Custom source name');
  i18n.setLanguage('en');
  assert.equal(i18n.regionName('25'), 'Primorsky Krai');
  i18n.setLanguage('ru');
});

test('service errors, saved prediction warnings and nested winner notes are translated', () => {
  assert.equal(i18n.translateMessage('GosPlan is unavailable (HTTP 503)'), 'ГосПлан недоступен (HTTP 503)');
  assert.match(i18n.translateMessage('Purchase type epNotificationEOK2020 is not supported by the model (supported: EF, EZK, EZT).'), /не поддерживается/);
  assert.match(i18n.translateMessage("The model's history ends on 2026-06-02; this tender was published later, so recent organizer behavior is not reflected."), /История модели заканчивается 2026-06-02/);
  assert.match(i18n.translateMessage('winner lookup failed: GosPlan did not answer in time'), /не удалось получить цену победителя: ГосПлан не ответил вовремя/);
  assert.match(i18n.translateMessage('epProtocolEF2020Final: winner price 500.00 exceeds max price 100.00; protocol has no applications'), /превышает начальную цену/);
  assert.equal(i18n.translateMessage('Custom diagnostic: E123'), 'Custom diagnostic: E123');
  i18n.setLanguage('en');
  assert.equal(i18n.translateMessage('GosPlan did not answer in time'), 'GosPlan did not answer in time');
  i18n.setLanguage('ru');
});

test('dictionary preserves interpolation variables and covers all literal UI translation calls', () => {
  for (const [en, ru] of Object.entries(i18n.translations)) {
    const vars = (text) => [...text.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();
    assert.deepEqual(vars(ru), vars(en), en);
    assert.match(ru, /[А-Яа-яЁё₽]/, en);
  }
  const dir = new URL('../app/static/js/', import.meta.url);
  const files = readdirSync(dir).filter((name) => name.endsWith('.js') && name !== 'i18n.js');
  const html = readFileSync(new URL('../app/static/index.html', import.meta.url), 'utf8');
  const texts = files.map((name) => readFileSync(new URL(name, dir), 'utf8')).concat(html);
  for (const source of texts) {
    for (const match of source.matchAll(/\bt\(\s*(['"])(.*?)\1/g)) {
      assert.ok(Object.hasOwn(i18n.translations, match[2]), `Missing translation: ${match[2]}`);
    }
    for (const match of source.matchAll(/data-i18n(?:-placeholder|-title|-aria-label)?="([^"]+)"/g)) {
      assert.ok(Object.hasOwn(i18n.translations, match[1]), `Missing DOM translation: ${match[1]}`);
    }
  }
  assert.match(html, /<html lang="ru">/);
  assert.match(html, /data-language="ru"/); assert.match(html, /data-language="en"/);
});

test('API errors retain English originals and follow language changes', async () => {
  const error = new ApiError('GosPlan did not answer in time', 504);
  assert.equal(error.message, 'ГосПлан не ответил вовремя');
  i18n.setLanguage('en');
  assert.equal(error.message, 'GosPlan did not answer in time');
  i18n.setLanguage('ru');
  globalThis.fetch = async () => { throw new TypeError('offline'); };
  await assert.rejects(api('/api/config'), (e) => e.status === 0 && /Нет связи/.test(e.message));
  globalThis.fetch = async () => ({ ok: false, status: 503, json: async () => ({ detail: 'The model is not loaded.' }) });
  await assert.rejects(api('/api/config'), (e) => e.rawMessage === 'The model is not loaded.' && e.message === 'Модель не загружена.');
});

test('filter facets and counters re-render in Russian/English without clearing selections or draft prices', async () => {
  const filters = await import('../app/static/js/filters.js');
  const facets = {
    total: 2, status: [{ value: 'winner', label: 'Has winner price', count: 1 }],
    purchase_type: [{ value: 'epNotificationEZK2020', label: 'EZK', count: 2 }],
    region: [{ value: '25', label: 'Primorsky Krai', count: 2 }], price_range: { min: 100, max: 200 },
  };
  globalThis.fetch = async () => ({ ok: true, status: 200, json: async () => facets });
  state.filters.status = 'winner'; state.filters.region = ['25'];
  await filters.initFilters();
  assert.match(document.getElementById('f-status').innerHTML, /Есть цена победителя/);
  assert.match(document.getElementById('region-list').innerHTML, /Приморский край/);
  assert.match(document.getElementById('f-type').innerHTML, /Электронный запрос котировок/);
  document.getElementById('f-pmin').value = '123';
  i18n.setLanguage('en');
  assert.match(document.getElementById('f-status').innerHTML, /Has winner price/);
  assert.match(document.getElementById('region-list').innerHTML, /Primorsky Krai/);
  assert.equal(document.getElementById('f-pmin').value, '123');
  assert.deepEqual(state.filters.region, ['25']); assert.equal(state.filters.status, 'winner');
  i18n.setLanguage('ru');
  filters.renderCounters({ n: 1, winner: 1, predicted: 0, pending: 0, unlocated: 0, total_max_price: 100 }, true);
  assert.match(document.getElementById('counters').innerHTML, /По фильтрам/);
  assert.doesNotMatch(document.getElementById('counters').innerHTML, /Сумма начальных цен|Total max price/);
  i18n.setLanguage('en');
  filters.renderCounters({ n: 1, winner: 1, predicted: 0, pending: 0, unlocated: 0, total_max_price: 100 }, true);
  assert.doesNotMatch(document.getElementById('counters').innerHTML, /Сумма начальных цен|Total max price/);
  i18n.setLanguage('ru');
  assert.match(LABELS.status.winner, /Цена победителя/);
});

test('open tender details switch language without changing source title or region data', async () => {
  const details = await import('../app/static/js/details.js');
  const record = {
    purchase_number: '0320300101526000015', title: 'Поставка оборудования', purchase_type: 'epNotificationEZK2020',
    type_label: 'EZK', status: 'pending', region_code: '25', region_name: 'Primorsky Krai',
    has_location: true, approximate_location: true, max_price: 1000,
    prediction: { available: false, error: 'The model is not loaded.' }, winner: { price: null },
  };
  globalThis.fetch = async () => ({ ok: true, status: 200, json: async () => record });
  details.initDrawer({}); await details.openRecord(record.purchase_number, { fly: false });
  let html = document.getElementById('drawer').innerHTML;
  assert.match(html, /Рассчитать|Попробовать снова/); assert.match(html, /Приморский край/);
  assert.match(html, /Поставка оборудования/); assert.match(html, /Модель не загружена/);
  i18n.setLanguage('en');
  html = document.getElementById('drawer').innerHTML;
  assert.match(html, /Try again/); assert.match(html, /Primorsky Krai/);
  assert.match(html, /Поставка оборудования/); assert.equal(record.region_name, 'Primorsky Krai');
  details.close(); i18n.setLanguage('ru');
});

test('upload continues across a language switch and renders the final report in the current language', async () => {
  const { openUpload } = await import('../app/static/js/upload.js');
  let resolveRequest; let done = 0;
  globalThis.fetch = () => new Promise((resolve) => { resolveRequest = resolve; });
  openUpload({ onDone: () => done++ });
  document.getElementById('up-text').value = '0320300101526000015';
  document.getElementById('up-predict').checked = true;
  const upload = document.getElementById('up-go').onclick();
  assert.match(document.getElementById('up-ptext').textContent, /Обработано 0 из 1/);
  i18n.setLanguage('en');
  assert.equal(document.getElementById('up-text').value, '0320300101526000015');
  assert.equal(document.getElementById('up-go').disabled, true);
  assert.match(document.getElementById('up-ptext').textContent, /Processed 0 of 1/);
  resolveRequest({ ok: true, status: 200, json: async () => ({ results: [
    { purchase_number: '0320300101526000015', status: 'created', prediction: { status: 'failed', reason: 'The model is not loaded.' } },
  ] }) });
  await upload;
  assert.equal(done, 1); assert.equal(document.getElementById('up-go').disabled, false);
  assert.match(document.getElementById('up-report').innerHTML, /The model is not loaded/);
  i18n.setLanguage('ru');
  assert.match(document.getElementById('up-report').innerHTML, /Модель не загружена/);
  assert.match(document.getElementById('up-ptext').textContent, /Готово/);
  document.getElementById('up-close').onclick();
});

// Execute the actual UI module with browser/API dependencies stubbed and only its
// automatic boot call omitted. This exercises the legend without WebGL or Docker.
function legendHarness(mobile = false) {
  const source = readFileSync(new URL('../app/static/js/main.js', import.meta.url), 'utf8');
  const localElements = new Map();
  const legend = new Element();
  let buttons = new Map();
  let html = '';
  Object.defineProperty(legend, 'innerHTML', {
    get: () => html,
    set: (value) => { html = value; buttons = new Map(); },
  });
  legend.querySelector = (selector) => {
    if (!buttons.has(selector)) buttons.set(selector, new Element());
    return buttons.get(selector);
  };
  localElements.set('legend', legend);
  const localDocument = {
    getElementById: (id) => {
      if (!localElements.has(id)) localElements.set(id, new Element());
      return localElements.get(id);
    },
  };
  const callbacks = [];
  const context = {
    document: localDocument, window: { matchMedia: () => ({ matches: mobile }) },
    state, COLORS, LABELS, t: i18n.t, esc: format.esc, num: format.num,
    initLanguage() {}, onLanguageChange: (fn) => callbacks.push(fn),
    translateMessage: i18n.translateMessage, hasActiveFilters: () => false,
  };
  const script = source.slice(0, source.indexOf('\nboot().catch(')).replace(/^import .*;\r?\n/gm, '');
  runInNewContext(`${script}\nmap = { setColorMode() {}, setBorders() {}, fitToData() {} }; renderLegend();`, context);
  return {
    legend, render: context.renderLegend, getElement: localDocument.getElementById,
    languageChanged: () => callbacks.forEach((fn) => fn()),
  };
}

test('legend X hides contents on desktop and mobile; reopening restores controls', () => {
  for (const mobile of [false, true]) {
    const { legend, render } = legendHarness(mobile);
    if (mobile) legend.querySelector('.legend-toggle').listeners.click();
    assert.equal(legend.classList.contains('collapsed'), false);
    assert.match(legend.innerHTML, /aria-expanded="true"/);
    assert.match(legend.innerHTML, /aria-label="Скрыть легенду"/);
    legend.querySelector('.legend-close').listeners.click();
    assert.equal(legend.classList.contains('collapsed'), true);
    assert.equal(document.activeElement, legend.querySelector('.legend-toggle'));
    assert.match(legend.innerHTML, /id="legend-body" hidden/);
    assert.match(legend.innerHTML, /aria-expanded="false"/);
    render(); // summary/filter refresh must not reopen it
    assert.equal(legend.classList.contains('collapsed'), true);
    legend.querySelector('.legend-toggle').listeners.click();
    assert.equal(legend.classList.contains('collapsed'), false);
    assert.doesNotMatch(legend.innerHTML, /id="legend-body" hidden/);
    assert.match(legend.innerHTML, /id="tg-borders" checked/);
    assert.match(legend.innerHTML, /id="btn-fit"/);
  }
});

test('legend remains hidden after language switches and keeps layer settings', () => {
  const { legend, languageChanged, getElement } = legendHarness();
  document.activeElement = null;
  getElement('tg-borders').listeners.change({ target: { checked: false } });
  legend.querySelector('.legend-close').listeners.click();
  i18n.setLanguage('en'); languageChanged();
  assert.equal(legend.classList.contains('collapsed'), true);
  assert.match(legend.innerHTML, /Legend and layers/);
  legend.querySelector('.legend-toggle').listeners.click();
  assert.match(legend.innerHTML, /aria-label="Hide legend"/);
  assert.doesNotMatch(legend.innerHTML, /id="tg-borders" checked/);
  i18n.setLanguage('ru'); languageChanged();
  assert.match(legend.innerHTML, /Легенда и слои/);
});

test('legend spacing and collapsed styles apply at all screen sizes; attribution is retained', () => {
  const css = readFileSync(new URL('../app/static/css/app.css', import.meta.url), 'utf8');
  const legendRules = [...css.matchAll(/#legend\s*\{([^}]+)\}/g)].map((m) => m[1]);
  const offsets = legendRules.flatMap((rule) => [...rule.matchAll(/\bbottom:\s*(\d+)px/g)].map((m) => +m[1]));
  assert.ok(offsets.length > 0);
  assert.ok(offsets.every((px) => px >= 48), 'No mobile rule should reduce clearance above attribution');
  assert.match(css, /#legend\.collapsed \.lg-body, #legend\.collapsed \.legend-close\s*\{ display: none; \}/);
  const map = readFileSync(new URL('../app/static/js/map.js', import.meta.url), 'utf8');
  assert.match(map, /new maplibregl\.AttributionControl\(\{ compact: true \}\)/);
});