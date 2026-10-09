// Shared UI state + a tiny event bus.
import { t } from './i18n.js';
export const bus = new EventTarget();
export const emit = (name, detail) => bus.dispatchEvent(new CustomEvent(name, { detail }));
export const on = (name, fn) => bus.addEventListener(name, (e) => fn(e.detail));

export const EMPTY_FILTERS = () => ({
  q: '', status: '', purchase_type: [], region: [], responsible: '', responsible_label: '',
  published_from: '', published_to: '', price_min: '', price_max: '', has_location: '',
});

export const state = {
  filters: EMPTY_FILTERS(),
  colorMode: 'status', // 'status' | 'type'
  facets: null,
  config: null,
};

// Query params understood by /api/tenders, /api/summary and /api/map/points
export function filterParams(extra = {}) {
  const f = state.filters;
  return {
    status: f.status, purchase_type: f.purchase_type, region: f.region, responsible: f.responsible,
    published_from: f.published_from, published_to: f.published_to, price_min: f.price_min, price_max: f.price_max,
    has_location: f.has_location, ...extra,
  };
}

export function setFilters(patch) {
  Object.assign(state.filters, patch);
  emit('filters-changed');
}
export function resetFilters() {
  state.filters = EMPTY_FILTERS();
  emit('filters-changed');
  emit('filters-reset');
}

export const COLORS = {
  status: { winner: '#1c8a58', predicted: '#e0950a', pending: '#8592a6' },
  type: { ezk: '#7b4fd0', ef: '#2467d8', ezt: '#d4502f' },
};
export const LABELS = {
  get status() { return { winner: t('Winner price known'), predicted: t('Predicted, no winner yet'), pending: t('Not predicted yet') }; },
  get type() { return { ezk: t('EZK'), ef: t('EF'), ezt: t('EZT') }; },
};
export const TYPE_KEY = { epNotificationEZK2020: 'ezk', epNotificationEF2020: 'ef', epNotificationEZT2020: 'ezt' };
