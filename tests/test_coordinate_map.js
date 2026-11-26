// Coordinate map unit tests — run with:
//   NODE_PATH=/tmp/siraj-map-test/node_modules node tests/test_coordinate_map.js
//
// These exercise the mock DOM / mock Leaflet surface, not a real browser
// (TESTED (mock)). They assert the Slice-A UI: declarative per-Doctype
// field config, hashed-bundle build attribute, uncertainty circle,
// teardrop pins tip-anchored, dirty-state set_value calls, swapped
// lat/lon & null-island warnings, read-only rendering, permission
// removal, "use linked place" action + ghost marker, correct linked-
// place field per DocType.
const assert = require('assert');
const fs = require('fs');
const {JSDOM} = require('jsdom');

const dom = new JSDOM('<html><body><main id="form"></main></body></html>', {runScripts:'dangerously', url:'http://example.test/app'});
const w = dom.window;
w.Map = global.Map; w.Set = global.Set; w.WeakMap = global.WeakMap; w.Promise = global.Promise;
w.requestAnimationFrame = f => setTimeout(f, 0);
w.cancelAnimationFrame = id => clearTimeout(id);
w.ResizeObserver = class { observe(){} disconnect(){} };
w.crypto = { subtle: {}, getRandomValues: a => a };
w.TextEncoder = TextEncoder; w.TextDecoder = TextDecoder;
w.requestIdleCallback = fn => setTimeout(fn, 0);
global.window = w; global.document = w.document; global.navigator = w.navigator;

const $ = require('jquery');
w.$ = $; w.jQuery = $; w.__ = s => s;

// ---- Mock Leaflet ----
let network = 0, maps = [], tileCalls = [];
class LLayer {
  constructor(){ this._map = null; }
  addTo(m){ this._map = m; m.layers.push(this); return this; }
  remove(){ if (this._map) this._map.layers = this._map.layers.filter(x => x !== this); }
  bringToFront(){ return this; }
  on(){ return this; }
  off(){ return this; }
  bindTooltip(){ return this; }
  setLatLng(){ return this; }
  setIcon(){ return this; }
  fire(){ return this; }
}
class Marker extends LLayer {
  constructor(p,o){ super(); this.point=p; this.options=o||{}; this._dragging=false; this._listeners={}; }
  on(ev,fn){ (this._listeners[ev]=this._listeners[ev]||[]).push(fn); return this; }
  setLatLng(p){ this.point = p; return this; }
  setIcon(i){ this.options.icon = i; return this; }
  dragend(){ (this._listeners.dragend||[]).forEach(f=>f()); }
}
class Circle extends LLayer { constructor(p,o){ super(); this.point=p; this.options=o||{}; } }
class LControl {
  constructor(opts){ this.options = Object.assign({position:'topright'}, opts||{}); this._groups=[]; this._current=null; }
  addTo(m){ this._map=m; return this; }
  group(label){ const g={label, items:[], add(i){this.items.push(i); return this;}, separator(){ return this; }}; this._groups.push(g); this._current=g; return g; }
  add(i){ if(this._current) this._current.add(i); return this; }
  separator(){ if(this._current) this._current.separator(); return this; }
  getContainer(){ return this._container || (this._container = document.createElement('div')); }
}
LControl.extend = function(proto){
  const Cls = function(opts){ if(this.initialize) this.initialize(opts); };
  Cls.prototype = Object.create(LControl.prototype);
  Cls.prototype.constructor = Cls;
  Object.assign(Cls.prototype, proto || {});
  return Cls;
};
class LeafletMap {
  constructor(){ this.events = {}; this.layers = []; this.zoom = 4; this.views = []; maps.push(this); this._ctl={}; }
  setView(p,z){ if(z!=null) this.zoom=z; this.views.push(p); return this; }
  getZoom(){ return this.zoom; }
  setZoom(z){ this.zoom=z; return this; }
  setMinZoom(){ return this; }
  on(n,h){ this.events[n]=h; return this; }
  removeLayer(l){ this.layers = this.layers.filter(x => x !== l); return this; }
  addLayer(l){ this.layers.push(l); l._map=this; return this; }
  invalidateSize(){ this._invalidated = (this._invalidated||0)+1; }
  remove(){ this.removed=true; }
  fitBounds(){ return this; }
  panTo(p){ this.views.push(p); return this; }
  locate(){} stopLocate(){}
}
w.L = {
  map: () => new LeafletMap(),
  marker: (p,o) => new Marker(p,o),
  circle: (p,o) => new Circle(p,o),
  circleMarker: (p,o) => new Circle(p,o),
  geoJSON: () => new LLayer(),
  tileLayer: (url, opt) => { network++; tileCalls.push({url,opt}); return new LLayer(); },
  divIcon: opt => ({ options: opt, className: opt && opt.className }),
  Icon: { Default: { mergeOptions(){}, prototype: {} } },
  control: { scale: () => new LControl(), sirajToolbar: () => new LControl() },
  FeatureGroup: { mergeOptions(){} },
  layerGroup: () => new LLayer(),
  markerClusterGroup: () => ({ addTo(){return this;}, addLayer(){return this;}, clearLayers(){return this;} }),
  DomEvent: { on(){}, off(){}, disableClickPropagation(){}, disableScrollPropagation(){}, stopPropagation(){}, preventDefault(){} },
  DomUtil: {
    create(tag, cls, parent){ const el = document.createElement(tag); if(cls) el.className = cls; if(parent) parent.appendChild(el); return el; },
    get(){ return document.createElement('div'); },
    addClass(){}, removeClass(){}, hasClass(){ return false; },
  },
  Util: { setOptions(obj, opt){ obj.options = Object.assign({}, obj.options||{}, opt||{}); return obj.options; }, extend(a,b){ return Object.assign(a,b); } },
  Control: LControl,
  CRS: {},
};
w.topojson = { feature: () => ({type:'FeatureCollection', features:[]}) };
w.fetch = async () => ({ ok: true, json: async () => ({ objects: { countries: {} } }) });
w.console = { info(){}, warn(){}, error(){} };
w.performance = { getEntriesByType: () => [] };

// ---- Mock Frappe ----
const modelCache = {};
w.frappe = {
  call: async () => ({ message: [] }),
  require: async () => {},
  boot: { siraj_record_meta: { build: 'test-build', coordinate_docs: {} } },
  ui: { form: { on(doctype, evts){ registrations[doctype] = Object.assign(registrations[doctype]||{}, evts); } } },
  get_route: () => [],
  get_doc: (dt, name) => modelCache[dt + '::' + name] || null,
};
const registrations = {};

w.SirajMapKit = {
  MeasureTool: class {
    constructor(map, opts){ this.map=map; this._opts=opts||{}; this._active=false; }
    activate(mode){ this._active=true; this._mode=mode; }
    deactivate(){ this._active=false; }
    isActive(){ return !!this._active; }
    clear(){ this._active=false; if(this._opts.onStatus) this._opts.onStatus('cleared'); return this; }
  },
};
w.L.control.sirajToolbar = () => new LControl();

// Load source in bundle order.
w.eval(fs.readFileSync('siraj_research/public/js/siraj-record-meta.js','utf8'));
w.eval(fs.readFileSync('siraj_research/public/js/siraj-map/siraj-map.js','utf8'));
w.eval(fs.readFileSync('siraj_research/public/js/siraj-map/siraj-graph.js','utf8'));
w.eval(fs.readFileSync('siraj_research/public/js/siraj-map/siraj-filters.js','utf8'));
w.eval(fs.readFileSync('siraj_research/public/js/siraj-map-kit.js','utf8'));
// Provide stubs siraj-map-toolbar.js expects that aren't in jsdom.
w.localStorage = { getItem(){return null;}, setItem(){}, removeItem(){} };
w.eval(fs.readFileSync('siraj_research/public/js/siraj-map-toolbar.js','utf8'));
// After the real toolbar registered L.Control.SirajToolbar, replace the
// factory with our mock control so tests don't build real DOM.
w.L.control.sirajToolbar = () => new LControl();
w.eval(fs.readFileSync('siraj_research/public/js/siraj-list-icons.js','utf8'));
w.eval(fs.readFileSync('siraj_research/public/js/siraj-compat.js','utf8'));
w.eval(fs.readFileSync('siraj_research/public/js/coordinate_map.js','utf8'));
w.eval(fs.readFileSync('siraj_research/public/js/siraj-icons.js','utf8'));

function form(doctype, type='Float', extraDoc, opts) {
  opts = opts || {};
  const cfg = (w.sirajCoordinateDocs || w.SIRAJ_COORDINATE_DOCS_ACTIVE)[doctype] || { lat_field:'latitude', lon_field:'longitude' };
  const container = $('<div><div class="form-section"><div class="section-body"></div></div></div>').appendTo('#form');
  const latWrapper = $('<div class="frappe-control"><input></div>').appendTo(container.find('.section-body'));
  const lonWrapper = $('<div class="frappe-control"><input></div>').appendTo(container.find('.section-body'));
  const latField = 'lat_status' in opts ? 'Read' : 'Write';
  const lonField = 'lon_status' in opts ? 'Read' : 'Write';
  const lat = { df: { fieldtype: type, fieldname: cfg.lat_field }, $wrapper: latWrapper, $input: latWrapper.find('input'), status: opts.lat_status||'Write', get_status(){ return this.status; } };
  const lon = { df: { fieldtype: type, fieldname: cfg.lon_field }, $wrapper: lonWrapper, $input: lonWrapper.find('input'), status: opts.lon_status||'Write', get_status(){ return this.status; } };
  const fields_dict = { [cfg.lat_field]: lat, [cfg.lon_field]: lon };
  if (cfg.uncertainty_field) fields_dict[cfg.uncertainty_field] = { df:{fieldtype:'Float'}, get_status(){return 'Write';} };
  fields_dict.geocoding_method = { df:{fieldtype:'Select'}, get_status(){return 'Write';} };
  fields_dict.geometry_source = { df:{fieldtype:'Data'}, get_status(){return 'Write';} };
  if (cfg.linked_place_field) {
    fields_dict[cfg.linked_place_field] = { df:{fieldtype:'Link',options:'Place'}, get_status(){return 'Write';} };
  }
  const doc = Object.assign({ doctype: doctype, [cfg.lat_field]:'', [cfg.lon_field]:'', geo_uncertainty_m: 0, geocoding_method:'', geometry_source:'' }, extraDoc || {});
  if (cfg.linked_place_field && doc[cfg.linked_place_field]) {
    // Simulate linked place doc in model cache
    const placeName = doc[cfg.linked_place_field];
    if (extraDoc && extraDoc._place) {
      modelCache['Place::' + placeName] = extraDoc._place;
    }
  }
  const frm = {
    doctype, docname: (extraDoc && extraDoc.name) || 'test-' + doctype.replace(/\s/g,''), doc, fields_dict, calls: [],
    async set_value(values) {
      this.calls.push(values);
      Object.keys(values).forEach(k => { this.doc[k] = values[k]; });
      if (lat.$input && cfg.lat_field in values) lat.$input.val(values[cfg.lat_field]);
      if (lon.$input && cfg.lon_field in values) lon.$input.val(values[cfg.lon_field]);
    },
  };
  return { frm, lat, lon, container, cfg };
}
const wait = (ms=60) => new Promise(r => setTimeout(r, ms));

(async () => {
  const fails = [];
  const check = (name, cond, detail) => { try { assert.ok(cond, detail||name); console.log('PASS', name); } catch(e){ fails.push(name+': '+e.message); console.log('FAIL', name, e.message); } };
  const checkEq = (name, a, b) => { try { assert.deepEqual(a,b); console.log('PASS', name); } catch(e){ fails.push(name+': expected '+JSON.stringify(b)+' got '+JSON.stringify(a)); console.log('FAIL', name, e.message); } };

  // ---- 1. Person mounts in frappe-control group with data-siraj-build ----
  const p = form('Person','Float');
  $(w.document).trigger('form-refresh', [p.frm]); await wait();
  check('person.map_created', maps.length >= 1, 'maps='+maps.length);
  check('person.no_online_tiles_default', network === 0, 'network='+network);
  check('person.wrapper_present', p.container.find('.siraj-coordinate-map').length === 1);
  check('person.frappe_control_row', p.container.find('.frappe-control.siraj-coord-group').length === 1);
  check('person.data_build_attr', p.container.find('.siraj-coord-group[data-siraj-build]').length === 1);
  const buildAttr = p.container.find('.siraj-coord-group').attr('data-siraj-build');
  check('person.build_matches_window', buildAttr === w.SIRAJ_BUILD, 'attr='+buildAttr+' SIRAJ_BUILD='+w.SIRAJ_BUILD);

  // ---- 2. Eastern-Arabic numerals parse & marker moves ----
  p.lat.$input.val('٣٣٫١٢٣٤٥').trigger('input');
  p.lon.$input.val('۴۴٫۲۵').trigger('input'); await wait();
  const pMarker = maps[maps.length-1].layers.find(l => l instanceof Marker);
  check('person.eastern_arabic_parsed', !!pMarker, 'marker exists after eastern-arabic input');
  checkEq('person.eastern_arabic_lat', pMarker && pMarker.point[0], 33.12345);
  checkEq('person.eastern_arabic_lon', pMarker && pMarker.point[1], 44.25);

  // ---- 3. Click sets value via frm.set_value (dirty state) ----
  const beforeCalls = p.frm.calls.length;
  const personMap = maps[maps.length-1];
  personMap.events.click({ latlng: { lat: 33.3, lng: 44.4 } }); await wait();
  check('person.click_set_value_called', p.frm.calls.length > beforeCalls, 'calls before='+beforeCalls+' after='+p.frm.calls.length);
  check('person.geocoding_method_set', p.frm.calls.some(c => c.geocoding_method === 'map_pick'), 'calls='+JSON.stringify(p.frm.calls));
  check('person.geometry_source_set', p.frm.calls.some(c => c.geometry_source === 'map_pick'));

  // ---- 4. Null-island (0,0) warning ----
  personMap.events.click({ latlng: { lat: 0, lng: 0 } }); await wait();
  check('person.zero_warning', p.container.text().indexOf('Zero pair') !== -1 || p.container.text().indexOf('legacy') !== -1);

  // ---- 5. Swapped lat/lon (lat > 90 is definitive swap signal) ----
  p.lat.$input.val('100.5').trigger('input');
  p.lon.$input.val('33.12').trigger('input'); await wait();
  check('person.swapped_warning', p.container.text().toLowerCase().indexOf('swap') !== -1,
    'status='+p.container.find('.siraj-coord-status').text());

  // Reset to valid Baghdad coords (clear the 0/0 pair left by null-island
  // test by setting both the $input and the doc, since set_value wrote 0/0).
  p.frm.doc.latitude = '33.3'; p.frm.doc.longitude = '44.4';
  p.lat.$input.val('33.3'); p.lon.$input.val('44.4');
  p.lat.$input.trigger('input'); await wait();

  // ---- 6. Out-of-range validation: lat=200 is invalid and not plausibly swapped ----
  p.lat.$input.val('200').trigger('input'); await wait();
  check('person.out_of_range', p.container.text().indexOf('valid decimal') !== -1,
    'status='+p.container.find('.siraj-coord-status').text());
  // Restore valid coords
  p.frm.doc.latitude = '33.3'; p.frm.doc.longitude = '44.4';
  p.lat.$input.val('33.3'); p.lon.$input.val('44.4');
  p.lat.$input.trigger('input'); await wait();
  check('person.readonly_ready', p.container.text().toLowerCase().indexOf('location shown') !== -1,
    'status='+p.container.find('.siraj-coord-status').text());

  // ---- 7. Read-only renders (no "Preview only") ----
  p.lat.status = 'Read'; p.lon.status = 'Read';
  const clickBefore = p.frm.calls.length;
  $(w.document).trigger('form-refresh', [p.frm]); await wait();
  check('person.readonly_renders', p.container.find('.siraj-coordinate-map').length === 1);
  // clicks should be ignored in read-only
  const roMap = maps[maps.length-1];
  roMap.events.click({ latlng: { lat: 1, lng: 2 } }); await wait();
  check('person.readonly_no_write', p.frm.calls.length === clickBefore, 'calls after read-only click='+p.frm.calls.length);
  check('person.readonly_status_text', p.container.text().toLowerCase().indexOf('read-only') !== -1,
    'text='+p.container.find('.siraj-coord-status').text());

  // ---- 8. No-permission removes the map ----
  p.lon.status = 'None';
  $(w.document).trigger('form-refresh', [p.frm]); await wait();
  check('person.no_perms_removed', p.container.find('.siraj-coordinate-map').length === 0,
    'maps left='+p.container.find('.siraj-coordinate-map').length);

  // ---- 9. Data-type fields writable on click ----
  const d = form('Custom Survey','Data');
  $(w.document).trigger('form-refresh', [d.frm]); await wait();
  maps[maps.length-1].events.click({ latlng: { lat: 12.34, lng: 56 } }); await wait();
  checkEq('data_fields_write.lat', d.frm.doc.latitude, '12.34');
  checkEq('data_fields_write.lon', d.frm.doc.longitude, '56');

  // ---- 10. geo_uncertainty_m → dashed circle ----
  const u = form('Place','Data',{ latitude:'33', longitude:'44', geo_uncertainty_m: 500 });
  $(w.document).trigger('form-refresh', [u.frm]); await wait();
  u.lat.$input.val('33').trigger('input'); u.lon.$input.val('44').trigger('input'); await wait();
  const placeMap = maps[maps.length-1];
  const circle = placeMap.layers.find(l => l instanceof Circle);
  check('place.uncertainty_circle_present', !!circle);
  checkEq('place.uncertainty_radius', circle && circle.options.radius, 500);
  checkEq('place.uncertainty_dasharray', circle && circle.options.dashArray, '4 3');

  // ---- 11. Teardrop pin with tip anchor ----
  const marker = placeMap.layers.find(l => l instanceof Marker);
  check('place.marker_present', !!marker);
  check('place.marker_teardrop_class', marker && /sx-pin-wrapper/.test(marker.options.icon.className));
  checkEq('place.marker_iconAnchor_tip', marker && marker.options.icon.options.iconAnchor, [17, 39]);
  check('place.marker_has_tip_element', marker && /siraj-pin-point/.test(marker.options.icon.options.html));

  // ---- 12. Linked-place chip for each of the six primary DocTypes ----
  const doctypeLinkField = {
    'Person':                { field: 'birthplace',   value: 'Baghdad' },
    'Institution':           { field: 'place',        value: 'Mosul University' },
    'Place':                 { field: 'parent_place', value: 'Baghdad Governorate' },
    'Siraj Event':           { field: 'place',        value: 'Taji' },
    'Military Unit':         { field: 'linked_place', value: 'Camp Victory' },
  };
  for (const [dt, info] of Object.entries(doctypeLinkField)) {
    const extras = { [info.field]: info.value };
    const f = form(dt, 'Data', extras);
    $(w.document).trigger('form-refresh', [f.frm]); await wait();
    const chipText = f.container.find('.siraj-coord-chip').text();
    check(dt+'.linked_chip_shows_name', chipText.indexOf(info.value) !== -1,
      dt+' chip='+chipText+' expected to contain '+info.value);
  }

  // ---- 13. Operational Deployment has NO linked_place field; chip absent ----
  const od = form('Operational Deployment','Data',{ latitude:'33', longitude:'44' });
  $(w.document).trigger('form-refresh', [od.frm]); await wait();
  check('od.no_linked_chip', od.container.find('.siraj-coord-chip').length === 0);

  // ---- 14. Linked place WITH cached coordinates shows "Use coordinates" button and ghost marker ----
  const person2 = form('Person','Float',{
    birthplace: 'Baghdad', latitude: '', longitude: '',
    _place: { doctype:'Place', name:'Baghdad', latitude: 33.315, longitude: 44.366 },
  });
  $(w.document).trigger('form-refresh', [person2.frm]); await wait();
  check('person.use_btn_present', person2.container.find('.siraj-coord-chip-use').length === 1,
    'found '+person2.container.find('.siraj-coord-chip-use').length+' use buttons');
  const p2map = maps[maps.length-1];
  const ghost = p2map.layers.find(l => l instanceof Marker && l.options.icon && /siraj-pin-ghost/.test(l.options.icon.options.html));
  check('person.ghost_marker_when_no_pin', !!ghost, 'ghost layers: '+p2map.layers.filter(l=>l instanceof Marker).length);

  // ---- 15. Clicking "Use coordinates" writes linked place's lat/lon with geocoding_method=inherited ----
  const callsBefore = person2.frm.calls.length;
  person2.container.find('.siraj-coord-chip-use').trigger('click'); await wait();
  check('person.use_calls_set_value', person2.frm.calls.length > callsBefore, 'calls before/after='+callsBefore+'/'+person2.frm.calls.length);
  const inheritCall = person2.frm.calls.find(c => c.geocoding_method === 'inherited');
  check('person.use_sets_inherited', !!inheritCall, 'calls='+JSON.stringify(person2.frm.calls));

  // ---- 16. Old "Enable online street map" button is gone ----
  check('no_old_enable_btn', p.container.find('button').filter((i,e) => /Enable online/.test($(e).text())).length === 0);

  // ---- Summary ----
  if (fails.length) {
    console.error('\n' + fails.length + ' FAILURES:');
    fails.forEach(f => console.error(' -', f));
    process.exitCode = 1;
  } else {
    console.log('\nCoordinate map: all assertions passed (mount, permissions, validation, uncertainty, teardrop anchor, 5 DocType linked chips + OD no-chip, ghost marker + use action, data-siraj-build attr, dirty set_value with geocoding_method/geometry_source, swapped-lat detection, zero-pair warning)');
  }
})().catch(err => { console.error(err); process.exitCode = 1; });
