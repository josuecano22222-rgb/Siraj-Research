// Run with node; verifies the locally packaged offline basemap can be decoded.
const assert = require('assert');
const topojson = require('../siraj_research/public/vendor/topojson/topojson-client.min.js');
const world = require('../siraj_research/public/vendor/world-atlas/countries-110m.json');
const vis = require('../siraj_research/public/vendor/vis-network/vis-network.min.js');
const countries = topojson.feature(world, world.objects.countries);
assert.strictEqual(countries.type, 'FeatureCollection');
assert(countries.features.length > 100, 'offline map must contain country geometry');
assert.strictEqual(typeof vis.Network, 'function');
assert.strictEqual(typeof vis.DataSet, 'function');
console.log(`Offline map decoded: ${countries.features.length} country features; network exports available.`);
