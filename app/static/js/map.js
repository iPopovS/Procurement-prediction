// Map view: MapLibre GL (no Leaflet). Points arrive pre-aggregated per location from the server;
// MapLibre clusters nearby locations and sums the per-category counts (clusterProperties).
// Markers are HTML donuts so no glyph/font server is needed (works offline).
import { COLORS, LABELS, state, filterParams } from './state.js';
import { api } from './api.js';
import { money, compact, esc, num } from './format.js';
import { t, regionName, onLanguageChange } from './i18n.js';

const maplibregl = window.maplibregl;
const EMPTY = { type: 'FeatureCollection', features: [] };
const KEYS = ['winner', 'predicted', 'pending', 'ef', 'ezk', 'ezt'];
const CLUSTER_MAX_ZOOM = 7; // above this zoom every location is its own marker
const DRAWER_W = 440;

export class MapView {
  constructor({ container, tiles, onLocation }) {
    this.tiles = tiles || {};
    this.onLocation = onLocation;
    this.markers = new Map(); // id -> {marker, props}
    this.ready = false;
    this.pendingData = null;
    this.selectedLoc = null;
    this.firstFit = true;
    this.leafCache = new Map();
    this.sampleCache = new Map();
    this.tip = null;
    this.tipToken = 0;

    this.map = new maplibregl.Map({
      container,
      style: { version: 8, sources: {}, layers: [{ id: 'ground', type: 'background', paint: { 'background-color': '#dce4ec' } }] },
      center: [90, 62], zoom: 2.2, minZoom: 1, maxZoom: 14,
      renderWorldCopies: false, dragRotate: false, pitchWithRotate: false, attributionControl: false,
      locale: {
        'Map.Title': t('Map'), 'Marker.Title': t('Map marker'), 'Popup.Close': t('Close popup'),
        'NavigationControl.ZoomIn': t('Zoom in'), 'NavigationControl.ZoomOut': t('Zoom out'),
        'AttributionControl.ToggleAttribution': t('Toggle attribution'),
      },
    });
    this.map.touchZoomRotate.disableRotation();
    this.map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-left');
    this.map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-left');
    this.map.on('load', () => this.#setup());
    const refresh = () => this.#scheduleMarkers();
    this.map.on('moveend', refresh);
    this.map.on('idle', refresh);
    this.map.on('sourcedata', (e) => { if (e.sourceId === 'tenders' && e.isSourceLoaded) refresh(); });
    const localizeControls = () => {
      const root = document.getElementById(container);
      for (const [selector, key] of [
        ['.maplibregl-ctrl-zoom-in', 'Zoom in'], ['.maplibregl-ctrl-zoom-out', 'Zoom out'],
        ['.maplibregl-ctrl-attrib-button', 'Toggle attribution'],
      ]) {
        root.querySelectorAll(selector).forEach((el) => { el.title = t(key); el.setAttribute('aria-label', t(key)); });
      }
      root.querySelector('canvas')?.setAttribute('aria-label', t('Map'));
    };
    this.map.on('load', localizeControls);
    onLanguageChange(() => { localizeControls(); this.setColorMode(); });
  }

  #setup() {
    const m = this.map;
    const t = this.tiles;
    m.addSource('countries', { type: 'geojson', data: '/static/data/countries.geojson' });
    m.addSource('regions', { type: 'geojson', data: '/static/data/regions.geojson' });
    // Land fill sits UNDER the raster tiles: with tiles it is hidden, and if the tile server is
    // unreachable (restricted network) the map still shows land and borders.
    m.addLayer({ id: 'countries-fill', type: 'fill', source: 'countries', paint: { 'fill-color': '#f6f8fa' } });
    if (t.url) {
      m.addSource('basemap', { type: 'raster', tiles: [t.url], tileSize: 256, maxzoom: t.max_zoom || 18, attribution: t.attribution || '' });
      m.addLayer({ id: 'basemap', type: 'raster', source: 'basemap' });
    }
    m.addLayer({ id: 'regions-line', type: 'line', source: 'regions', paint: { 'line-color': '#7d8ba0', 'line-width': 0.7, 'line-opacity': 0.8 } });
    m.addLayer({ id: 'countries-line', type: 'line', source: 'countries', paint: { 'line-color': '#4d5b70', 'line-width': 1.1 } });

    const sum = (k) => ['+', ['get', k]];
    m.addSource('tenders', {
      type: 'geojson', data: EMPTY, cluster: true, clusterRadius: 48, clusterMaxZoom: CLUSTER_MAX_ZOOM,
      clusterProperties: Object.fromEntries(['n', ...KEYS].map((k) => [k, sum(k)])),
    });
    // invisible anchor layer: makes the source load tiles so querySourceFeatures() works
    m.addLayer({ id: 'tenders-anchor', type: 'circle', source: 'tenders', paint: { 'circle-radius': 2, 'circle-opacity': 0 } });
    this.ready = true;
    if (this.pendingData) this.setData(this.pendingData);
  }

  // ---------- data ----------
  setData(fc) {
    if (!this.ready) { this.pendingData = fc; return; }
    this.pendingData = null;
    this.lastFc = fc;
    this.leafCache.clear();
    this.sampleCache.clear();
    this.#clearMarkers();
    this.map.getSource('tenders').setData(fc);
    if (this.firstFit && fc.features.length) {
      this.firstFit = false;
      this.fitToData(fc);
    }
  }

  fitToData(fc) {
    const feats = (fc || this.lastFc || EMPTY).features;
    if (!feats.length) return;
    const b = new maplibregl.LngLatBounds();
    feats.forEach((f) => b.extend(f.geometry.coordinates));
    this.map.fitBounds(b, { padding: { top: 70, bottom: 70, left: 70, right: window.innerWidth > 900 ? DRAWER_W + 40 : 70 }, maxZoom: 6, duration: 600 });
  }

  setColorMode() {
    this.#clearMarkers();
    this.#scheduleMarkers();
  }

  setBorders(visible) {
    if (!this.ready) return;
    for (const id of ['regions-line', 'countries-line']) this.map.setLayoutProperty(id, 'visibility', visible ? 'visible' : 'none');
  }

  setSelectedLoc(key) {
    this.selectedLoc = key;
    for (const { el, props } of this.markers.values()) el.classList.toggle('selected', !props.cluster && props.loc_key === key);
  }

  flyToPoint(lon, lat) {
    const padRight = window.innerWidth > 900 ? DRAWER_W : 0;
    this.map.flyTo({ center: [lon, lat], zoom: Math.max(this.map.getZoom(), CLUSTER_MAX_ZOOM + 1.3), padding: { right: padRight, top: 0, bottom: 0, left: 0 }, speed: 1.4 });
  }

  // ---------- markers ----------
  #clearMarkers() {
    this.#hideTip();
    for (const { marker } of this.markers.values()) marker.remove();
    this.markers.clear();
  }

  #scheduleMarkers() {
    if (this._raf) return;
    this._raf = requestAnimationFrame(() => { this._raf = 0; this.#updateMarkers(); });
  }

  #updateMarkers() {
    if (!this.ready || !this.map.getSource('tenders')) return;
    const seen = new Set();
    for (const f of this.map.querySourceFeatures('tenders')) {
      const p = f.properties || {};
      const id = p.cluster ? `c${p.cluster_id}` : `p${p.loc_key}`;
      if (seen.has(id)) continue; // features repeat across tile borders
      seen.add(id);
      if (!this.markers.has(id)) {
        const coords = f.geometry.coordinates.slice();
        const props = { ...p, cluster: !!p.cluster };
        const el = this.#makeEl(props);
        const marker = new maplibregl.Marker({ element: el }).setLngLat(coords).addTo(this.map);
        el.addEventListener('mouseenter', () => this.#showTip(props, coords, el));
        el.addEventListener('mouseleave', () => this.#hideTip());
        el.addEventListener('click', (ev) => { ev.stopPropagation(); this.#click(props, coords); });
        el.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); this.#click(props, coords); } });
        if (!props.cluster && props.loc_key === this.selectedLoc) el.classList.add('selected');
        this.markers.set(id, { marker, el, props });
      }
    }
    for (const [id, m] of this.markers) {
      if (!seen.has(id)) { m.marker.remove(); this.markers.delete(id); }
    }
  }

  #makeEl(p) {
    const mode = state.colorMode;
    const keys = mode === 'status' ? ['winner', 'predicted', 'pending'] : ['ezk', 'ef', 'ezt'];
    const n = +p.n || 0;
    const d = n <= 1 ? 18 : Math.round(26 + 13 * Math.log10(n)); // diameter grows with the record count
    const el = document.createElement('div');
    el.className = 'mk';
    el.tabIndex = 0;
    el.setAttribute('role', 'button');
    el.setAttribute('aria-label', p.cluster ? t('{n} tenders in a group of locations', { n: num(n) }) : t('{n} tenders — {region}', { n: num(n), region: regionName(p.region) || t('this location') }));
    el.style.width = el.style.height = `${d}px`;
    const parts = keys.map((k) => [COLORS[mode][k], +p[k] || 0]).filter(([, v]) => v > 0);
    const total = parts.reduce((a, [, v]) => a + v, 0) || 1;
    if (n <= 1) {
      el.classList.add('dot');
      el.style.background = (parts[0] || [COLORS[mode][keys[2]]])[0];
    } else {
      let acc = 0;
      const stops = parts.map(([c, v]) => { const from = (acc / total) * 100; acc += v; return `${c} ${from}% ${(acc / total) * 100}%`; });
      el.style.background = parts.length === 1 ? parts[0][0] : `conic-gradient(${stops.join(',')})`;
      el.style.setProperty('--ring', `${Math.max(6, Math.round(d * 0.2))}px`);
      el.innerHTML = `<span>${esc(compact(n))}</span>`;
    }
    return el;
  }

  // ---------- interaction ----------
  async #click(p, coords) {
    this.#hideTip();
    if (p.cluster) {
      try {
        const z = await this.map.getSource('tenders').getClusterExpansionZoom(p.cluster_id);
        this.map.easeTo({ center: coords, zoom: Math.min(z + 0.3, 12) });
      } catch { this.map.easeTo({ center: coords, zoom: this.map.getZoom() + 2 }); }
      return;
    }
    this.setSelectedLoc(p.loc_key);
    this.onLocation({ loc_key: p.loc_key, region: p.region, n: +p.n, approximate: p.precision === 'region', lon: coords[0], lat: coords[1] });
  }

  #statusBar(p) {
    const mode = state.colorMode;
    const keys = mode === 'status' ? ['winner', 'predicted', 'pending'] : ['ezk', 'ef', 'ezt'];
    const n = +p.n || 1;
    const segs = keys.filter((k) => +p[k] > 0).map((k) => `<i style="flex:${(+p[k] / n) * 100};background:${COLORS[mode][k]}"></i>`).join('');
    const txt = keys.filter((k) => +p[k] > 0).map((k) => `${esc(LABELS[mode][k])}: <b>${+p[k]}</b>`).join(' &nbsp; ');
    return `<div class="bar" style="display:flex">${segs}</div><div>${txt}</div>`;
  }

  async #showTip(p, coords, el) {
    const token = ++this.tipToken;
    const n = +p.n || 0;
    let html;
    if (p.cluster) {
      html = `<div class="tip"><b>${t('{n} tenders in {locations} locations', { n: num(n), locations: num(p.point_count) })}</b>${this.#statusBar(p)}<div class="hint">${t('Loading…')}</div></div>`;
      this.#openTip(html, coords, el);
      const leaves = await this.#leaves(p.cluster_id);
      if (token !== this.tipToken) return;
      const names = leaves.map((l) => regionName(l.properties.region)).filter(Boolean);
      const more = p.point_count > names.length ? ` ${t('and {n} more', { n: num(p.point_count - names.length) })}` : '';
      html = `<div class="tip"><b>${t('{n} tenders in {locations} locations', { n: num(n), locations: num(p.point_count) })}</b>${this.#statusBar(p)}`
        + `<div class="hint">${esc(names.join(', '))}${more}<br>${t('Click to zoom in.')}</div></div>`;
      this.#openTip(html, coords, el);
      return;
    }
    const approx = p.precision === 'region' ? `<div class="hint">${t('Approximate location (region centre)')}</div>` : '';
    const head = `<b>${esc(regionName(p.region) || t('Location'))}</b> \u00b7 ${t('Tenders: {n}', { n: num(n) })}${this.#statusBar(p)}`;
    this.#openTip(`<div class="tip">${head}<div class="hint">${t('Loading…')}</div>${approx}</div>`, coords, el);
    const samples = await this.#samples(p.loc_key);
    if (token !== this.tipToken) return;
    const rows = samples.map((s) => `<li><span title="${esc(s.title || '')}">${esc(s.title || s.purchase_number)}</span><span class="num">${esc(money(s.max_price))}</span></li>`).join('');
    this.#openTip(`<div class="tip">${head}<ul>${rows}</ul>${n > samples.length ? `<div class="hint">${t('Largest {n} by max price. Click to browse all.', { n: num(samples.length) })}</div>` : ''}${approx}</div>`, coords, el);
  }

  async #samples(locKey) {
    if (!this.sampleCache.has(locKey)) {
      try {
        const r = await api('/api/tenders', { params: { ...filterParams(), loc_key: locKey, sort: 'price_desc', limit: 3 } });
        this.sampleCache.set(locKey, r.items);
      } catch { return []; }
    }
    return this.sampleCache.get(locKey);
  }

  async #leaves(id) {
    if (!this.leafCache.has(id)) {
      try { this.leafCache.set(id, await this.map.getSource('tenders').getClusterLeaves(id, 4, 0)); } catch { this.leafCache.set(id, []); }
    }
    return this.leafCache.get(id);
  }

  #openTip(html, coords, el) {
    if (!this.tip) this.tip = new maplibregl.Popup({ closeButton: false, closeOnClick: false, className: 'tip-popup', maxWidth: '320px' });
    this.tip.setLngLat(coords).setHTML(html).setOffset([0, -(el.offsetHeight / 2 + 4)]).addTo(this.map);
  }

  #hideTip() {
    this.tipToken++;
    if (this.tip) { this.tip.remove(); }
  }
}

