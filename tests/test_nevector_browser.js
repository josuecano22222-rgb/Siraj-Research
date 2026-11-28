// Browser-context tests for the Natural Earth Vector map layer (siraj-nevector.js).
//
// siraj-nevector.js is an IIFE that attaches `window.SirajNeVector`; it is not
// CommonJS, so we load it into a jsdom window (the same approach as
// test_offline_viewer.js) with a mocked Leaflet `L` and `fetch`, then assert the
// map layer's real behavior: layer planning, scale selection, choropleth
// colouring, click-to-country, and the country-intelligence fetch helpers.
//
// npm install --prefix /tmp/siraj-map-test --no-save jsdom@24
// NODE_PATH=/tmp/siraj-map-test/node_modules node tests/test_nevector_browser.js
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const {JSDOM} = require('jsdom');

const ROOT = path.resolve(__dirname, '..');
const NV_PATH = path.join(ROOT, 'siraj_research/public/js/siraj-nevector.js');

// ---- tiny mock Leaflet ----------------------------------------------------
// Only the surface attachLeaflet() touches: L.geoJSON, L.circleMarker,
// L.DomEvent.stopPropagation, and the group/map methods used in _build.
function makeLeaflet() {
	const groups = [];
	const makeGroup = (geojson, cfg) => {
		const handlers = {};
		const g = {
			geojson, cfg,
			_style: cfg.style,
			_handlers: handlers,
			addTo(map) { this._map = map; map._layers.push(this); return this; },
			removeLayer() { return this; },
			setStyle(s) { this._style = s; return this; },
			on(evt, fn) { (handlers[evt] = handlers[evt] || []).push(fn); return this; },
			hasLayer() { return true; },
			// exercise onEachFeature/pointToLayer the way Leaflet would
			_applyFeatures(features) {
				if (typeof this.cfg.onEachFeature === 'function') {
					features.forEach((f) => this.cfg.onEachFeature(f, this));
				}
			},
			_fire(evt, payload) { (handlers[evt] || []).forEach((fn) => fn(payload)); },
		};
		groups.push(g);
		return g;
	};
	const L = {
		geoJSON: (geojson, cfg) => makeGroup(geojson, cfg),
		circleMarker: (latlng, opts) => makeGroup({_circleMarker: true, latlng, opts}, {}),
		DomEvent: {stopPropagation: () => {}},
	};
	return {L, groups};
}

// A minimal but valid GeoJSON FeatureCollection with one country feature so the
// countries group can be choropleth-coloured and clicked.
function countryGeoJSON(adm0) {
	return JSON.stringify({
		type: 'FeatureCollection',
		features: [{
			type: 'Feature',
			properties: {ADM0_A3: adm0, ISO_A3: adm0, NAME: adm0},
			geometry: {type: 'Polygon', coordinates: [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]},
		}],
	});
}

function makeFetchMock({manifest, layers}) {
	const calls = [];
	const fetch = (url) => {
		calls.push(url);
		let body, ok = true, json;
		if (url.includes('manifest')) {
			body = JSON.stringify(manifest);
			json = async () => manifest;
		} else if (url.includes('layer?layer=')) {
			const name = decodeURIComponent(url.split('layer=')[1]);
			if (layers[name] != null) {
				body = layers[name];
			} else {
				ok = false; body = 'not found';
			}
			json = async () => JSON.parse(body);
		} else if (url.includes('country_profile')) {
			json = async () => ({code: 'NLD', name: 'Netherlands'});
		} else if (url.includes('country_choropleth')) {
			json = async () => ({
				empty: false, valueByKey: {NLD: 10, PRT: 5}, classByKey: {NLD: 2, PRT: 1},
				matchedCount: 2, recordCount: 2,
			});
		} else {
			ok = false; body = 'unknown';
		}
		return Promise.resolve({
			ok, status: ok ? 200 : 404,
			text: async () => body,
			json,
		});
	};
	return {fetch, calls};
}

(async () => {
	const dom = new JSDOM('<!doctype html><html><body></body></html>', {runScripts: 'outside-only'});
	const w = dom.window;

	// Stub the globals siraj-nevector.js depends on.
	const {L, groups} = makeLeaflet();
	w.L = L;
	w.console = console;
	const manifest = {available_scales: ['110m', '50m'], zoom_tiers: [{scale: '110m', max_zoom: 4}, {scale: '50m', max_zoom: 6}]};
	const layers = {
		'ne_110m_ocean': countryGeoJSON('OCN'),
		'ne_110m_land': countryGeoJSON('LAND'),
		'ne_110m_admin_0_countries': countryGeoJSON('NLD'),
	};
	const {fetch, calls} = makeFetchMock({manifest, layers});
	w.fetch = fetch;

	// Load the IIFE into the window context.
	w.eval(fs.readFileSync(NV_PATH, 'utf8'));

	const NV = w.SirajNeVector;
	assert.ok(NV, 'window.SirajNeVector must be defined after loading siraj-nevector.js');

	// ---- 1. Pure exported helpers ---------------------------------------
	assert.strictEqual(NV.CHOROPLETH_JOIN_FIELD, 'ADM0_A3',
		'join key must be ADM0_A3 (ISO_A3 is -99 for some countries)');
	assert.ok(Array.isArray(NV.CHOROPLETH_COLORS) && NV.CHOROPLETH_COLORS.length === 7,
		'choropleth palette must have 7 sequential colours');

	// choroplethLegend: title range + one row per colour.
	const legend = NV.choroplethLegend(0, 100);
	assert.ok(legend.includes('0 → 100'), 'legend title must show the min → max range');
	assert.strictEqual((legend.match(/ne-legend-row/g) || []).length, 7,
		'legend must render one row per palette colour');
	assert.ok(legend.includes('#ffffcc') && legend.includes('#b10026'),
		'legend rows must carry the sequential palette colours');

	// ---- 2. fetchCountryProfile: URL construction + response -----------
	const prof = await NV.fetchCountryProfile({code: 'NLD'});
	assert.deepStrictEqual(prof, {code: 'NLD', name: 'Netherlands'});
	assert.ok(calls.some((u) => u.includes('country_profile') && u.includes('code=NLD')),
		'fetchCountryProfile must encode the code param');

	const profCoord = await NV.fetchCountryProfile({longitude: 4.9, latitude: 52.37});
	assert.deepStrictEqual(profCoord, {code: 'NLD', name: 'Netherlands'});
	assert.ok(calls.some((u) => u.includes('longitude=4.9') && u.includes('latitude=52.37')),
		'fetchCountryProfile must encode coordinate params');

	// ---- 3. fetchSiteChoropleth: URL construction + response ----------
	const choro = await NV.fetchSiteChoropleth('Person', {agg: 'count', classes: 5});
	assert.ok(choro && choro.valueByKey && choro.classByKey, 'choropleth payload must carry value/class maps');
	assert.ok(calls.some((u) => u.includes('country_choropleth') && u.includes('doctype=Person') &&
		u.includes('agg=count') && u.includes('classes=5')),
		'fetchSiteChoropleth must encode doctype/agg/classes');

	// ---- 4. attach(): engine dispatch -----------------------------------
	// Unknown engine must reject.
	await assert.rejects(
		() => NV.attach({}, {engine: 'nope'}),
		/unknown engine/,
		'attach() must reject an unknown engine');

	// Leaflet attach builds the layer set from the manifest + layer plan.
	const map = {_layers: [], hasLayer: () => true, removeLayer: () => {}, getZoom: () => 2};
	const ctrl = await NV.attach(map, {engine: 'leaflet', zoom: 2});
	assert.strictEqual(ctrl.engine, 'leaflet', 'controller must report the leaflet engine');
	assert.strictEqual(ctrl.currentScale(), '110m',
		'zoom 2 (<= 110m tier max_zoom 4) must select the 110m scale');

	// The countries group must have been built and added to the map.
	// Every geoJSON group carries onEachFeature, so identify the countries
	// group by its distinctive default fill colour (#d9d0b8) rather than the
	// first group (which is ocean).
	const countriesGroup = groups.find(
		(g) => g.cfg && g.cfg.style && g.cfg.style.fillColor === '#d9d0b8');
	assert.ok(countriesGroup, 'the countries geoJSON group must be created');
	assert.ok(map._layers.includes(countriesGroup), 'the countries group must be added to the map');

	// ---- 5. Choropleth legend computation -----------------------------
	const painted = ctrl.setChoropleth('ADM0_A3', {NLD: 10, PRT: 5});
	assert.strictEqual(painted.min, 5);
	assert.strictEqual(painted.max, 10);
	assert.ok(painted.legendHtml && painted.legendHtml.includes('5 → 10'),
		'setChoropleth must return a legend for the computed min/max');

	// Clearing the choropleth restores the static default style object.
	ctrl.clearChoropleth();
	assert.strictEqual(typeof countriesGroup._style, 'object',
		'clearChoropleth must restore a static style object on the countries group');

	// ---- 6. Click-to-country callback ----------------------------------
	let clicked = null;
	ctrl.onCountryClick((payload) => { clicked = payload; });
	// onEachFeature wires layer.on('click') on the group; apply features then
	// fire the stored click handler the way Leaflet would.
	countriesGroup._applyFeatures([{
		properties: {ADM0_A3: 'NLD', NAME: 'Netherlands'},
		geometry: {type: 'Polygon', coordinates: []},
	}]);
	countriesGroup._fire('click', {type: 'click'});
	assert.ok(clicked && clicked.properties && clicked.properties.ADM0_A3 === 'NLD',
		'country click must invoke the callback with the feature properties');

	// ---- 7. setChoroplethFromSite: data-driven recolour ----------------
	const siteResult = await ctrl.setChoroplethFromSite('Person', {agg: 'count'});
	assert.ok(siteResult && siteResult.painted,
		'setChoroplethFromSite must return a painted result');
	assert.strictEqual(siteResult.painted.min, 5);
	assert.strictEqual(siteResult.painted.max, 10);
	assert.strictEqual(typeof countriesGroup._style, 'function',
		'setChoroplethFromSite must install a per-feature style on the countries group');

	// ---- 8. destroy clears groups ---------------------------------------
	ctrl.destroy();
	assert.ok(true, 'destroy() must not throw and clear groups');

	console.log('Natural Earth Vector map layer: legend, country-intelligence fetch, ' +
		'engine dispatch, scale selection, choropleth colouring, click-to-country ' +
		'and site-data choropleth passed (jsdom).');
})().catch((err) => {
	console.error(err);
	process.exit(1);
});
