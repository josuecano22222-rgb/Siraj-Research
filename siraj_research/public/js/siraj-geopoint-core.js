/* Pure GeoJSON point helpers shared by the form map bridge and its tests.
 *
 * Frappe's "Geolocation" field stores a GeoJSON FeatureCollection, while
 * SIRAJ's research fields keep exact decimal latitude/longitude text. The
 * conversion here is deliberately lossless: numbers are emitted with
 * String(number), never toFixed(), so a map pick does not silently round a
 * value that the researcher typed.
 */
((root) => {
	'use strict';

	const DIGITS = {
		'٠': '0', '١': '1', '٢': '2', '٣': '3', '٤': '4',
		'٥': '5', '٦': '6', '٧': '7', '٨': '8', '٩': '9',
		'۰': '0', '۱': '1', '۲': '2', '۳': '3', '۴': '4',
		'۵': '5', '۶': '6', '۷': '7', '۸': '8', '۹': '9',
		'٫': '.',
	};
	const DECIMAL = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/;

	function normalise(value) {
		return String(value == null ? '' : value).trim().replace(/[٠-٩۰-۹٫]/g, c => DIGITS[c] || c);
	}

	function parse(value, limit) {
		if (value === null || value === undefined || typeof value === 'boolean') return null;
		if (typeof value === 'number') {
			return Number.isFinite(value) && Math.abs(value) <= limit ? value : null;
		}
		const text = normalise(value);
		if (!DECIMAL.test(text)) return null;
		const number = Number(text);
		return Number.isFinite(number) && Math.abs(number) <= limit ? number : null;
	}

	function latitude(value) { return parse(value, 90); }
	function longitude(value) { return parse(value, 180); }

	function isZero(lat, lon) {
		return lat === 0 && lon === 0;
	}

	function point(lat, lon, properties) {
		const a = latitude(lat), b = longitude(lon);
		if (a === null || b === null) return null;
		// GeoJSON is [longitude, latitude]; SIRAJ fields are latitude first.
		return {
			type: 'Feature',
			properties: Object.assign({ source: 'siraj_map_pick' }, properties || {}),
			geometry: { type: 'Point', coordinates: [b, a] },
		};
	}

	function featureCollection(lat, lon, properties) {
		const f = point(lat, lon, properties);
		return f ? { type: 'FeatureCollection', features: [f] } : null;
	}

	function encode(lat, lon, properties) {
		const value = featureCollection(lat, lon, properties);
		return value ? JSON.stringify(value) : null;
	}

	function firstPoint(value) {
		if (!value) return null;
		let parsed = value;
		if (typeof value === 'string') {
			const text = value.trim();
			if (!text) return null;
			try { parsed = JSON.parse(text); } catch (_) { return null; }
		}
		if (!parsed || typeof parsed !== 'object') return null;
		const features = parsed.type === 'FeatureCollection' && Array.isArray(parsed.features)
			? parsed.features
			: [parsed];
		for (const feature of features) {
			const geometry = feature && feature.geometry;
			if (!geometry || geometry.type !== 'Point' || !Array.isArray(geometry.coordinates)) continue;
			const lon = longitude(geometry.coordinates[0]);
			const lat = latitude(geometry.coordinates[1]);
			if (lat === null || lon === null) continue;
			return { lat, lon, properties: (feature && feature.properties) || {} };
		}
		return null;
	}

	const api = { normalise, parse, latitude, longitude, isZero, point, featureCollection, encode, firstPoint };
	if (typeof module !== 'undefined' && module.exports) module.exports = api;
	else root.SirajGeoPointCore = api;
})(typeof window !== 'undefined' ? window : globalThis);
