// Node tests for the advanced map search widget's pure helpers.
// Precision contract: coordinate strings must survive verbatim — never
// through Number()/toFixed() — and grouping must preserve server order.
const assert = require('assert');
const search = require('../siraj_research/public/js/siraj-map-search.js');

// ---------- buildParams ----------
assert.deepStrictEqual(search.buildParams({ query: '  Gaza  ' }), {
  query: 'Gaza', scope: 'all', limit: 8,
});
assert.deepStrictEqual(
  search.buildParams({ query: 'x', scope: 'regions', levels: '1,2', types: 'Person,Place', limit: 12 }),
  { query: 'x', scope: 'regions', levels: '1,2', types: 'Person,Place', limit: 12 },
);
assert.strictEqual(search.buildParams({}).query, '');

// ---------- shouldSearch ----------
assert.strictEqual(search.shouldSearch('غ'), false);        // 1 char
assert.strictEqual(search.shouldSearch(' Gaza '), true);
assert.strictEqual(search.shouldSearch('31.5, 34.47'), true);

// ---------- coordinateDisplay: exactness ----------
const exact = search.coordinateDisplay({
  format: 'decimal', lat: '31.5900000000000001', lon: '34.47', input: '31.5900000000000001, 34.47',
});
assert.strictEqual(exact.primary, '31.5900000000000001, 34.47'); // verbatim, no float
assert.strictEqual(exact.fraction, null);

const dms = search.coordinateDisplay({
  format: 'dms', lat: '31.59013888888888888888888889', lon: '34.47025555555555555555555556',
  lat_fraction: '227449/7200', lon_fraction: '615713/17775',
  input: '31°35\'24.5"N 34°28\'11.92"E',
});
assert.strictEqual(exact.lat, undefined); // sanity: display objects are copies
assert.ok(dms.primary.startsWith('31.59013888888888888888888889'));
assert.strictEqual(dms.fraction, '227449/7200  ·  615713/17775');

const err = search.coordinateDisplay({ error: 'out_of_range', input: '100.2, 34.47',
  suggestion: { lat: '34.47', lon: '100.2' } });
assert.strictEqual(err.error, 'out_of_range');
assert.strictEqual(err.suggestion.text, '34.47, 100.2');

assert.strictEqual(search.coordinateDisplay(null), null);

// ---------- coordinateErrorText ----------
assert.ok(search.coordinateErrorText('out_of_range').includes('-90'));
assert.ok(search.coordinateErrorText('conflicting_hemisphere').includes('hemisphere'));
assert.ok(search.coordinateErrorText('unknown-code').length > 0);
// Translator is honoured (no global __ required in Node).
assert.strictEqual(
  search.coordinateErrorText('out_of_range', (s) => 'T:' + s).slice(0, 2),
  'T:',
);

// ---------- groupResults: order + empties ----------
const resp = {
  query: 'gaza',
  coordinate: null,
  regions: [{ name_en: 'Gaza' }],
  places: [{ name_en: 'Gaza City' }],
  records: [{ label: 'Person in Gaza' }],
};
assert.deepStrictEqual(
  search.groupResults(resp).map((g) => g.key),
  ['regions', 'places', 'records'],
);
const withCoord = Object.assign({}, resp, { coordinate: { format: 'decimal', lat: '1', lon: '2' } });
assert.deepStrictEqual(search.groupResults(withCoord).map((g) => g.key),
  ['coordinate', 'regions', 'places', 'records']);
assert.deepStrictEqual(search.groupResults({}), []);
assert.deepStrictEqual(search.groupResults(null), []);

// ---------- titles ----------
assert.strictEqual(search.regionTitle({ name_en: 'Gaza', name_ar: 'غزة' }), 'Gaza');
assert.strictEqual(search.regionTitle({ name_ar: 'غزة' }), 'غزة');
assert.strictEqual(search.placeTitle({ pcode: 'PS-GZ' }), 'PS-GZ');
assert.strictEqual(search.recordTitle({ label: 'Ahmad' }), 'Ahmad');
assert.strictEqual(search.recordTitle({ name: 'PER-0001' }), 'PER-0001');

// ---------- groupLabel via translator ----------
assert.strictEqual(search.groupLabel('regions', (s) => s), 'Regions');
assert.strictEqual(search.groupLabel('nope', (s) => s), 'nope');


// ---------- v2.0.0: bbox params, cascade payload, coordinate chains ----------
// String bounds pass through verbatim (leaflet float bounds are String()'d
// by the caller — viewport params, never stored coordinates).
const bboxParams = search.buildBboxParams(
  { min_lat: '31.590000000000001', min_lon: '34.47', max_lat: '31.6', max_lon: '34.5' },
  { types: 'Person', limit: 25 },
);
assert.strictEqual(bboxParams.min_lat, '31.590000000000001'); // verbatim
assert.strictEqual(bboxParams.min_lon, '34.47');
assert.strictEqual(bboxParams.max_lat, '31.6');
assert.strictEqual(bboxParams.max_lon, '34.5');
assert.strictEqual(bboxParams.types, 'Person');
assert.strictEqual(bboxParams.limit, 25);

const cascadeSelected = [
  { level: 0, name_en: 'Palestine, State of', name_ar: 'فلسطين', pcode: 'PS' },
  { level: 1, name_en: 'Gaza Strip', name_ar: 'قطاع غزة', pcode: 'PS-GZ' },
];
const cascadeRow = {
  level: 2, level_name: 'District', name_en: 'Gaza', name_ar: 'غزة',
  pcode: 'PS-GZ-GZ', centroid: ['31.522678211310364', '34.467321788689634'],
  bbox: ['31.4', '34.3', '31.6', '34.6'],
};
const payload = search.cascadePayload(cascadeSelected, cascadeRow);
assert.strictEqual(payload.kind, 'region');
assert.strictEqual(payload.level, 2);
assert.strictEqual(payload.source, 'registry');
assert.deepStrictEqual(payload.bbox, ['31.4', '34.3', '31.6', '34.6']);
assert.deepStrictEqual(payload.centroid, ['31.522678211310364', '34.467321788689634']);
assert.strictEqual(payload.chain.length, 2);
assert.strictEqual(payload.chain[1].pcode, 'PS-GZ');

const chains = search.coordinateChains({
  format: 'decimal', lat: '31.5', lon: '34.47',
  admin_chain: [
    { level: 0, level_name: 'Country', name_en: 'Palestine, State of' },
    { level: 1, level_name: 'Governorate', name_en: 'Gaza Strip' },
  ],
  missing_levels: ['district', 'municipality', 'village', 'community'],
  nearby: [{ name: 'Gaza', distance: '146.1', distance_m: 146.1 }],
  on_land: true,
});
assert.strictEqual(chains.chain.length, 2);
assert.strictEqual(chains.chain[0].label, 'Country: Palestine, State of');
assert.deepStrictEqual(chains.missing, ['district', 'municipality', 'village', 'community']);
assert.strictEqual(chains.nearby[0].distance, '146.1');
assert.strictEqual(chains.on_land, true);
assert.strictEqual(search.coordinateChains(null), null);
assert.strictEqual(search.coordinateChains({ error: 'out_of_range' }), null);

console.log('Map search widget helpers: params, exact coordinate display, grouping, bbox, cascade and chains passed (Node only).');

// ---------- GEO_TYPES contract (server: visualization.py) ----------
assert.deepStrictEqual(
  search.RECORD_TYPES.map((pair) => pair[0]),
  ['', 'Person', 'Institution', 'Place', 'Research Event', 'Military Unit', 'Operational Deployment'],
);

// ---------- mount() ordering: creation must precede append (TDZ guard) ----------
// A const used before its declaration is a ReferenceError that killed the
// whole explorer geography view on the desk; lock the source order.
const widgetSrc = require('fs').readFileSync(
  require('path').join(__dirname, '..', 'siraj_research', 'public', 'js', 'siraj-map-search.js'),
  'utf8',
);
const order = (needle) => {
  const at = widgetSrc.indexOf(needle);
  assert.ok(at >= 0, 'missing in widget source: ' + needle);
  return at;
};
assert.ok(order('const bboxBtn') < order('row.appendChild(bboxBtn)'),
  'bboxBtn must be created before row.appendChild(bboxBtn)');
assert.ok(order('const cascade') < order('wrap.appendChild(cascade)'),
  'cascade must be created before wrap.appendChild(cascade)');
assert.ok(order('const applyScopeChrome') < order('applyScopeChrome();'),
  'applyScopeChrome must be defined before it is invoked');
