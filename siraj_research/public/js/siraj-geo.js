/* SIRAJ offline reverse-geocoding client.
 *
 * Responsibilities
 *   1. On page load, check the server's current spatial-package version
 *      (via geo_package.current, honouring ETag). If the cached version in
 *      IndexedDB matches the server ETag, use the cached copy; otherwise
 *      fetch the package, store it in IndexedDB, and load it into the
 *      Web Worker.
 *   2. Maintain one long-lived Web Worker (siraj-geo-worker.js) that
 *      holds the polygon R-tree and gazetteer points.
 *   3. Expose window.SirajGeo.resolve(lat, lon) → Promise<result>, which:
 *        - tries the SERVER first (fast network, authoritative, has full
 *          STRtree on shapely);
 *        - on any error / timeout (150 ms) / offline, falls back to the
 *          WORKER (returns the offline result immediately);
 *        - marks result.source = 'server' | 'offline-worker' so callers
 *          can show a subtle "offline" indicator if needed.
 *   4. Expose window.SirajGeo.status() → { online, offline_ready, version,
 *      polyCount, placeCount } for diagnostics in the map status bar.
 *
 * IndexedDB schema (database: 'siraj-geo', version 1):
 *   store 'package': key = 'current', value = { version, etag, payload }
 *   store 'tiles':   key = '<layer>/<z>/<x>/<y>', value = { data, ctype, savedAt }
 *     (reserved for future offline tile caching; not used yet)
 */
(function () {
	'use strict';
	const DB_NAME = 'siraj-geo';
	const DB_VERSION = 1;
	const WORKER_URL = '/assets/siraj_research/js/siraj-geo-worker.js';
	const SERVER_TIMEOUT_MS = 150;

	let db = null;
	let worker = null;
	let workerReady = false;
	let pending = {};     // pending query promises by id
	let nextId = 1;
	let currentPackage = null;
	let status_ = { online: true, offline_ready: false, version: 0, polyCount: 0, placeCount: 0 };
	let initPromise = null;

	function openDB() {
		if (db) return Promise.resolve(db);
		return new Promise((resolve, reject) => {
			const req = indexedDB.open(DB_NAME, DB_VERSION);
			req.onupgradeneeded = () => {
				const d = req.result;
				if (!d.objectStoreNames.contains('package')) d.createObjectStore('package');
				if (!d.objectStoreNames.contains('tiles')) d.createObjectStore('tiles');
			};
			req.onsuccess = () => { db = req.result; resolve(db); };
			req.onerror = () => reject(req.error);
		});
	}
	function dbGet(store, key) {
		return openDB().then(d => new Promise((resolve, reject) => {
			const tx = d.transaction(store, 'readonly');
			const r = tx.objectStore(store).get(key);
			r.onsuccess = () => resolve(r.result);
			r.onerror = () => reject(r.error);
		}));
	}
	function dbPut(store, key, value) {
		return openDB().then(d => new Promise((resolve, reject) => {
			const tx = d.transaction(store, 'readwrite');
			tx.objectStore(store).put(value, key);
			tx.oncomplete = () => resolve();
			tx.onerror = () => reject(tx.error);
		}));
	}

	function spawnWorker() {
		if (worker) return;
		try {
			worker = new Worker(WORKER_URL);
		} catch (e) {
			console.warn('[SIRAJ] geo worker spawn failed:', e);
			worker = null;
			return;
		}
		worker.onmessage = (ev) => {
			const m = ev.data || {};
			if (m.type === 'ready') {
				workerReady = true;
				status_.offline_ready = true;
				status_.polyCount = m.count|0;
				status_.placeCount = m.places|0;
				status_.version = m.version|0;
				console.info('[SIRAJ] offline geo index ready:', m.count, 'polygons,', m.places, 'places, version', m.version);
			} else if (m.type === 'result') {
				const p = pending[m.id];
				if (p) { delete pending[m.id]; p.resolve(m.result); }
			} else if (m.type === 'error') {
				console.warn('[SIRAJ] geo worker error:', m.message);
			}
		};
		worker.onerror = (e) => console.warn('[SIRAJ] geo worker error event:', e.message);
	}

	function loadIntoWorker(pkg) {
		if (!worker) spawnWorker();
		if (!worker) return;
		workerReady = false;
		worker.postMessage({ type: 'clear' });
		worker.postMessage({ type: 'load', package: pkg });
		currentPackage = pkg;
	}

	// Fetch package from server. The etag travels in ?version= as well as
	// If-None-Match because Frappe does not relay custom response headers;
	// the endpoint returns 304 when the cached version is unchanged.
	function fetchPackage(etag) {
		const headers = { 'Accept': 'application/json' };
		if (etag) headers['If-None-Match'] = etag;
		const query = etag ? ('?version=' + encodeURIComponent(etag)) : '';
		return fetch('/api/method/siraj_research.api.geo_package.current' + query,
			{ headers, credentials: 'same-origin' })
			.then(res => {
				if (res.status === 304) return { __notModified: true, etag };
				if (!res.ok) throw new Error('HTTP ' + res.status);
				return res.json().then(wrapped => {
					// /api/method wraps the return value in `message`.
					const body = (wrapped && wrapped.message !== undefined) ? wrapped.message : wrapped;
					return { etag: (body && body.etag) || res.headers.get('ETag') || '', body: body };
				});
			});
	}

	async function sync() {
		spawnWorker();
		try {
			const cached = await dbGet('package', 'current');
			let pkg = cached && cached.payload;
			let etag = cached && cached.etag;
			if (navigator.onLine !== false) {
				try {
					const res = await fetchPackage(etag);
					if (res.__notModified) {
						// cached copy still fresh; ensure loaded in worker
					} else if (res.body) {
						pkg = res.body;
						etag = res.etag;
						await dbPut('package', 'current', { version: pkg.version|0, etag, payload: pkg, savedAt: Date.now() });
					}
				} catch (e) {
					console.warn('[SIRAJ] geo package fetch failed, using cache:', e && e.message);
					status_.online = false;
				}
			}
			if (pkg) loadIntoWorker(pkg);
		} catch (e) {
			console.warn('[SIRAJ] geo sync failed:', e);
		}
	}

	function queryWorker(lat, lon) {
		return new Promise((resolve) => {
			if (!worker || !workerReady) return resolve(null);
			const id = nextId++;
			pending[id] = { resolve: resolve };
			worker.postMessage({ type: 'query', id: id, lat: lat, lon: lon });
			// Defensive timeout (worker should answer in <50 ms).
			setTimeout(() => { if (pending[id]) { delete pending[id]; resolve(null); } }, 500);
		});
	}

	function queryServer(lat, lon) {
		return new Promise((resolve) => {
			let done = false;
			const t = setTimeout(() => { if (!done) { done = true; resolve(null); } }, SERVER_TIMEOUT_MS);
			frappe.call({
				method: 'siraj_research.api.geo_resolve.resolve_point',
				args: { latitude: lat, longitude: lon },
				type: 'GET',
				callback: (r) => { if (done) return; done = true; clearTimeout(t); resolve(r && r.message); },
				error: () => { if (done) return; done = true; clearTimeout(t); resolve(null); },
			});
		});
	}

	async function resolve(lat, lon) {
		await initPromise;
		if (navigator.onLine === false) {
			status_.online = false;
			const r = await queryWorker(lat, lon);
			if (r) return r;
			return { lat, lon, on_land: false, admin_chain: {}, warnings: ['offline_no_index'], source: 'offline-fail' };
		}
		// Race: prefer server, fall back to worker.
		const serverPromise = queryServer(lat, lon);
		const timer = new Promise(r => setTimeout(() => r('__timeout__'), SERVER_TIMEOUT_MS));
		const first = await Promise.race([serverPromise, timer]);
		if (first && first !== '__timeout__') {
			status_.online = true;
			first.source = 'server';
			return first;
		}
		// Server timeout or error — try worker (and still wait for server
		// in the background for next call's LRU cache; but don't block).
		const workerRes = await queryWorker(lat, lon);
		if (workerRes) return workerRes;
		// Wait for server fully as a last resort.
		const serverRes = await serverPromise;
		if (serverRes) { serverRes.source = 'server'; return serverRes; }
		return { lat, lon, on_land: false, admin_chain: {}, warnings: ['unreachable'], source: 'none' };
	}

	function status() {
		return Object.assign({}, status_);
	}

	// Kick off initialization (lazy; resolve() waits on it).
	initPromise = sync();
	window.SirajGeo = { resolve, status, sync };
	// Re-sync when browser comes back online.
	if (typeof window.addEventListener === 'function') {
		window.addEventListener('online', () => { sync(); });
	}
})();
