/* SIRAJ offline reverse-geocoder Web Worker.
 *
 * Loaded once by siraj-geo.js on map mount. Receives a spatial package
 * (polygons + gazetteer points) from the main thread, builds an in-memory
 * R-tree over polygon bounding boxes, and answers point-to-admin-chain
 * queries in <5 ms. No network, no DOM access — runs off the main thread
 * so UI stays responsive while the user drags the pin.
 *
 * Message protocol (main → worker):
 *   { type: 'load',   package: {...} }      one-time; builds index
 *   { type: 'query',  id:<num>, lat, lon }  resolve one point
 *   { type: 'clear' }                        drop index (for reload)
 *
 * Worker → main:
 *   { type: 'ready' }                         index built
 *   { type: 'result', id, result }            query response
 */
(function () {
	'use strict';

	let polys = [];       // [{id, level, pcode, parent, name_en, name_ar, rings, bbox}]
	let tree = null;      // R-tree node
	let places = [];      // [{lat,lon,...}]
	let pcodeIndex = {};  // pcode → poly record
	let byId = [];

	// ---- Minimal R-tree (static bulk-loaded; ~O(log N) query). -----------
	// We don't need insert/delete (the package is immutable until reload),
	// so a simple sort-tile-recursive bulk load is sufficient and tiny.
	function RTree(items, nodeCap) {
		this.nodeCap = nodeCap || 9;
		this.root = _bulkLoad(items, this.nodeCap);
	}
	function _bounds(rec) { return rec.bbox; }
	function _aabb(a, b) {
		return [Math.min(a[0],b[0]), Math.min(a[1],b[1]),
		        Math.max(a[2],b[2]), Math.max(a[3],b[3])];
	}
	function _intersects(a, b) {
		return a[0] <= b[2] && a[2] >= b[0] && a[1] <= b[3] && a[3] >= b[1];
	}
	function _bulkLoad(items, cap) {
		if (items.length <= cap) return { leaf: true, items: items.slice(), bbox: items.reduce((b,r)=>_aabb(b,_bounds(r)), _bounds(items[0])) };
		// Sort-tile-recursive: tile in one dimension, split into slices of `cap` children.
		items = items.slice().sort((a,b) => a.bbox[0]-b.bbox[0] || a.bbox[1]-b.bbox[1]);
		const sliceSize = Math.ceil(Math.ceil(items.length / cap));
		const children = [];
		for (let i = 0; i < items.length; i += sliceSize) {
			const slice = items.slice(i, i + sliceSize);
			children.push(_bulkLoad(slice, cap));
		}
		return { leaf: false, children: children, bbox: children.reduce((b,c)=>_aabb(b,c.bbox), children[0].bbox) };
	}
	function _search(node, q, out) {
		if (!_intersects(node.bbox, q)) return;
		if (node.leaf) {
			for (let i = 0; i < node.items.length; i++)
				if (_intersects(node.items[i].bbox, q)) out.push(node.items[i]);
		} else {
			for (let i = 0; i < node.children.length; i++)
				_search(node.children[i], q, out);
		}
	}
	RTree.prototype.query = function (bbox) {
		const out = [];
		if (this.root) _search(this.root, bbox, out);
		return out;
	};

	// ---- Geometry helpers ----------------------------------------------
	function ringBBox(rings) {
		let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
		for (let p = 0; p < rings.length; p++) {
			const poly = rings[p];
			for (let r = 0; r < poly.length; r++) {
				const ring = poly[r];
				for (let i = 0; i < ring.length; i++) {
					const x = ring[i][0], y = ring[i][1];
					if (x < minX) minX = x; if (y < minY) minY = y;
					if (x > maxX) maxX = x; if (y > maxY) maxY = y;
				}
			}
		}
		return [minX, minY, maxX, maxY];
	}

	// Ray-casting point-in-polygon (Jordan curve theorem). `ring` is a
	// closed [ [x,y], ... ] array.
	function pointInRing(ring, x, y) {
		let inside = false;
		for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
			const xi = ring[i][0], yi = ring[i][1];
			const xj = ring[j][0], yj = ring[j][1];
			const intersect = ((yi > y) !== (yj > y)) &&
			                  (x < (xj - xi) * (y - yi) / ((yj - yi) || 1e-12) + xi);
			if (intersect) inside = !inside;
		}
		return inside;
	}
	// MultiPolygon: OR of polygons; first ring is exterior, rest are holes
	// (holes subtract).
	function pointInMulti(rings, x, y) {
		for (let p = 0; p < rings.length; p++) {
			const poly = rings[p];
			if (!poly.length) continue;
			if (!pointInRing(poly[0], x, y)) continue;
			let inHole = false;
			for (let r = 1; r < poly.length; r++) {
				if (pointInRing(poly[r], x, y)) { inHole = true; break; }
			}
			if (!inHole) return true;
		}
		return false;
	}

	// ---- Haversine for nearest-place gazetteer -------------------------
	function hav_m(lat1, lon1, lat2, lon2) {
		const R = 6371000, p1 = lat1*Math.PI/180, p2 = lat2*Math.PI/180;
		const dp = (lat2-lat1)*Math.PI/180, dl = (lon2-lon1)*Math.PI/180;
		const a = Math.sin(dp/2)**2 + Math.cos(p1)*Math.cos(p2)*Math.sin(dl/2)**2;
		return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
	}

	// ---- Message handler -----------------------------------------------
	self.onmessage = function (e) {
		const msg = e.data || {};
		if (msg.type === 'clear') { polys = []; places = []; tree = null; pcodeIndex = {}; byId = []; return; }
		if (msg.type === 'load') {
			try {
				const pkg = msg.package || {};
				polys = [];
				pcodeIndex = {};
				byId = [];
				const rawPolys = pkg.polygons || [];
				for (let i = 0; i < rawPolys.length; i++) {
					const row = rawPolys[i];
					const rec = {
						id: i, level: row[0]|0, pcode: row[1]||'',
						parent: row[2]||'', name_en: row[3]||'', name_ar: row[4]||'',
						rings: row[5], bbox: ringBBox(row[5]||[]), linked_name: row[6]||'',
					};
					polys.push(rec);
					byId.push(rec);
					if (rec.pcode) pcodeIndex[rec.pcode] = rec;
				}
				tree = polys.length ? new RTree(polys, 9) : null;
				places = (pkg.places || []).map(r => ({
					lat:r[0], lon:r[1], pcode:r[2]||'', name_en:r[3]||'',
					fcode:r[4]||'', a1:r[5]||'', a2:r[6]||'',
				}));
				self.postMessage({ type: 'ready', count: polys.length, places: places.length, version: pkg.version|0 });
			} catch (err) {
				self.postMessage({ type: 'error', message: String(err && err.message || err) });
			}
			return;
		}
		if (msg.type === 'query') {
			const id = msg.id, lat = +msg.lat, lon = +msg.lon;
			const res = { lat:lat, lon:lon, on_land:false, admin_chain:{},
			              ambiguous:false, candidates:[], nearest_place:null,
			              warnings:[], source:'offline-worker' };
			if (!isFinite(lat) || !isFinite(lon) || Math.abs(lat)>90 || Math.abs(lon)>180) {
				res.warnings.push('bad_coords');
				self.postMessage({ type:'result', id:id, result:res });
				return;
			}
			if (!tree) {
				res.warnings.push('no_index');
				self.postMessage({ type:'result', id:id, result:res });
				return;
			}
			// Query bbox: a small window around (lon,lat). We use a ~2 km
			// square (~0.02 deg) — fast; real containment filters below.
			const D = 0.02;
			const hits = tree.query([lon-D, lat-D, lon+D, lat+D]);
			let containing = [];
			for (let i = 0; i < hits.length; i++) {
				if (pointInMulti(hits[i].rings, lon, lat)) containing.push(hits[i]);
			}
			// Expand search if no hits — rare at polygon edges where the
			// 2 km window missed a polygon (shouldn't happen with country
			// polys, but defensive).
			if (!containing.length) {
				const big = tree.query([lon-1, lat-1, lon+1, lat+1]);
				let bestD = Infinity;
				for (let i = 0; i < big.length; i++) {
					if (pointInMulti(big[i].rings, lon, lat)) { containing.push(big[i]); continue; }
				}
				// (distance computation skipped — we just need on_land flag)
				res.nearest_boundary_m = containing.length ? 0 : null;
			}
			if (!containing.length) {
				self.postMessage({ type:'result', id:id, result:res });
				return;
			}
			res.on_land = true;
			// Pick smallest (by bbox area) polygon per level — same heuristic
			// the server uses.
			const best = {};
			const bestArea = {};
			for (let i = 0; i < containing.length; i++) {
				const rec = containing[i];
				const a = (rec.bbox[2]-rec.bbox[0])*(rec.bbox[3]-rec.bbox[1]);
				if (!(rec.level in best) || a < bestArea[rec.level]) {
					best[rec.level] = rec;
					bestArea[rec.level] = a;
				}
			}
			// Ambiguity: same level has ≥2 containing polygons.
			const lvlCounts = {};
			for (let i = 0; i < containing.length; i++) lvlCounts[containing[i].level] = (lvlCounts[containing[i].level]||0)+1;
			for (const k in lvlCounts) if (lvlCounts[k] > 1) res.ambiguous = true;
			// Build chain from finest level up via parent pcode.
			const LEVELS = [
				[0,'country'],[1,'governorate'],[2,'district'],
				[3,'municipality'],[4,'village'],[5,'community'],
			];
			const finest = Math.max.apply(null, Object.keys(best).map(Number));
			let cur = best[finest] || null;
			for (let li = 0; li < LEVELS.length; li++) {
				const [lvl, key] = LEVELS[li];
				if (!cur) break;
				if (cur.level === lvl) {
					res.admin_chain[key] = { pcode: cur.pcode, name_en: cur.name_en,
					                         name_ar: cur.name_ar, linked_name: cur.linked_name || '' };
					cur = cur.parent ? pcodeIndex[cur.parent] : null;
				} else if (cur.level > lvl) {
					cur = cur.parent ? pcodeIndex[cur.parent] : null;
				}
			}
			// Nearest gazetteer place within 5 km.
			let nearest = null, nearestD = 5000;
			for (let i = 0; i < places.length; i++) {
				const p = places[i];
				if (Math.abs(p.lat - lat) > 0.05 || Math.abs(p.lon - lon) > 0.05) continue;
				const d = hav_m(lat, lon, p.lat, p.lon);
				if (d < nearestD) { nearestD = d; nearest = p; }
			}
			if (nearest) res.nearest_place = { name_en: nearest.name_en, pcode: nearest.pcode,
			                                feature_code: nearest.fcode, distance_m: Math.round(nearestD),
			                                admin1_pcode: nearest.a1, admin2_pcode: nearest.a2 };
			self.postMessage({ type:'result', id:id, result:res });
			return;
		}
	};
})();
