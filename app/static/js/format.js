// Formatting helpers. Every missing value renders as an em dash - never null/NaN/undefined.
import { getLocale, onLanguageChange } from './i18n.js';
export const DASH = '\u2014';

let moneyFmt, moneyFmt2, numFmt, compactFmt, dateFmt, dayFmt;
function initFormats() {
  const locale = getLocale();
  moneyFmt = new Intl.NumberFormat(locale, { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 });
  moneyFmt2 = new Intl.NumberFormat(locale, { style: 'currency', currency: 'RUB', maximumFractionDigits: 2 });
  numFmt = new Intl.NumberFormat(locale);
  compactFmt = new Intl.NumberFormat(locale, { notation: 'compact', maximumFractionDigits: 1 });
  dateFmt = new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short', timeZone: 'UTC' });
  dayFmt = new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeZone: 'UTC' });
}
initFormats();
onLanguageChange(initFormats);

const ok = (v) => v !== null && v !== undefined && v !== '' && !(typeof v === 'number' && !Number.isFinite(v));

export function money(v, { cents = false } = {}) {
  if (!ok(v)) return DASH;
  return (cents || Math.abs(v) < 1000 && !Number.isInteger(v) ? moneyFmt2 : moneyFmt).format(v);
}
export const num = (v) => (ok(v) ? numFmt.format(v) : DASH);
export const compact = (v) => (ok(v) ? compactFmt.format(v) : DASH);

export function pct(v, digits = 1) {
  if (!ok(v)) return DASH;
  return `${new Intl.NumberFormat(getLocale(), { maximumFractionDigits: digits }).format(+v)}%`;
}
export function signedPct(v, digits = 1) {
  if (!ok(v)) return DASH;
  return `${v > 0 ? '+' : v < 0 ? '\u2212' : ''}${pct(Math.abs(v), digits)}`;
}

// The API returns naive UTC timestamps (e.g. 2026-01-30T00:03:03.391000).
export function parseUTC(iso) {
  if (!ok(iso)) return null;
  const s = /([zZ]|[+-]\d\d:?\d\d)$/.test(iso) ? iso : `${iso}Z`;
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? null : d;
}
export function dateTime(iso) {
  const d = parseUTC(iso);
  return d ? `${dateFmt.format(d)} UTC` : DASH;
}
export function day(iso) {
  const d = parseUTC(iso);
  return d ? dayFmt.format(d) : DASH;
}

export function esc(v) {
  if (!ok(v)) return '';
  return String(v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
export const orDash = (v) => (ok(v) ? esc(v) : DASH);

export function debounce(fn, ms) {
  let t;
  const d = (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
  d.cancel = () => clearTimeout(t);
  return d;
}

export function toast(msg, ms = 3200) {
  document.getElementById('toast')?.remove();
  const el = document.createElement('div');
  el.id = 'toast';
  el.setAttribute('role', 'status');
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), ms);
}
