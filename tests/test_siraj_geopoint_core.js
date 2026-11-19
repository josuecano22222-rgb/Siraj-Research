// Pure conversion tests for the native Geolocation ("map") field bridge.
const assert = require('assert');
const core = require('../siraj_research/public/js/siraj-geopoint-core.js');

const fc = core.featureCollection('٣٣٫٢٥', '۴۴٫۵');
assert.deepStrictEqual(fc.features[0].geometry, {
  type: 'Point',
  coordinates: [44.5, 33.25],
});
assert.deepStrictEqual(core.firstPoint(JSON.stringify(fc)), { lat: 33.25, lon: 44.5, properties: { source: 'siraj_map_pick' } });
assert.strictEqual(core.latitude('90.0000000000001'), null);
assert.strictEqual(core.longitude('180.1'), null);
assert.strictEqual(core.parse('1e-7', 90), null);
assert.strictEqual(core.isZero(0, 0), true);
assert.strictEqual(core.isZero(0, 0.000001), false);
assert.strictEqual(core.encode(91, 0), null);
assert.strictEqual(core.firstPoint('not json'), null);
assert.strictEqual(core.firstPoint(JSON.stringify({
  type: 'FeatureCollection',
  features: [{ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: [181, 0] } }],
})), null);

const origin = core.featureCollection(0, 0, { source: 'siraj_map_pick' });
assert.deepStrictEqual(core.firstPoint(origin), {
  lat: 0, lon: 0, properties: { source: 'siraj_map_pick' },
});

console.log('Geolocation field bridge: point conversion, digit normalisation and bounds passed (Node only).');
