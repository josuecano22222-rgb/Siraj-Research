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

console.log('Map search widget helpers: params, exact coordinate display, grouping and labels passed (Node only).');
