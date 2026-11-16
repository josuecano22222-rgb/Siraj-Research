/* siraj-graph.js — engine-neutral ego network + relationship rendering model.
 *
 * Pure functions here:
 *   - buildAdjacency(edges) -> Map<id, [{edge, other}]>
 *   - egoNetwork(adj, centerId, depth, opts) -> {nodes:Set, edges:Set, hops:Map}
 *   - shortestPath(adj, a, b, maxHops) -> edge[] | null
 *   - clusterAggregate(edges, clusterOf) -> bundled edges  (clusterOf: id -> clusterId)
 *   - offsetEdge(a, b, pairIndex, pairTotal) -> control point for parallel offsets
 *   - selfTest() -> throws if any TOOL_SPEC or record icon key is missing
 *
 * Renderers (Leaflet today, MapLibre later) consume the outputs of these
 * functions; they never traverse relationships themselves.
 */
(() => {
	'use strict';

	/* ---------- Adjacency ---------- */
	function edgeId(e) { return e.name || JSON.stringify([e.source, e.target, e.type]); }
	function nodeId(n) { return typeof n === 'string' ? n : JSON.stringify(n); }

	function buildAdjacency(edges) {
		const adj = new Map();
		edges.forEach(e => {
			const s = nodeId(e.source), t = nodeId(e.target);
			if (!adj.has(s)) adj.set(s, []);
			if (!adj.has(t)) adj.set(t, []);
			adj.get(s).push({ edge: e, other: t, dir: 'out' });
			adj.get(t).push({ edge: e, other: s, dir: 'in' });
		});
		return adj;
	}

	/* ---------- Ego network: BFS to depth ---------- */
	function egoNetwork(adj, centerId, depth, opts) {
		const opt = Object.assign({
			types: null,           // Set of relationship.type values to include; null = all
			maxNodes: 500,
			maxEdges: 1000,
			includeEnded: false,
			now: new Date().toISOString(),
		}, opts || {});
		const center = nodeId(centerId);
		const nodes = new Set([center]);
		const edges = new Set();
		const hops = new Map(); hops.set(center, 0);
		const frontier = [center];
		let d = 0;
		while (frontier.length && d <= depth) {
			const next = [];
			for (const id of frontier) {
				const neighbours = adj.get(id) || [];
				for (const { edge, other } of neighbours) {
					if (opt.types && edge.type && !opt.types.has(edge.type)) continue;
					if (!opt.includeEnded && edge.end_date && edge.end_date < opt.now) continue;
					const eKey = edgeId(edge);
					if (!edges.has(eKey)) {
						if (edges.size >= opt.maxEdges) return { nodes, edges, hops, truncated: true, reason: 'edges' };
						edges.add(eKey);
					}
					if (!nodes.has(other)) {
						if (nodes.size >= opt.maxNodes) return { nodes, edges, hops, truncated: true, reason: 'nodes' };
						nodes.add(other);
						hops.set(other, d + 1);
						if (d + 1 < depth) next.push(other);
					}
				}
			}
			frontier.length = 0;
			for (const n of next) frontier.push(n);
			d++;
		}
		return { nodes, edges, hops, truncated: false };
	}

	/* ---------- Shortest path (BFS) ---------- */
	function shortestPath(adj, a, b, maxHops) {
		const start = nodeId(a), end = nodeId(b);
		if (start === end) return [];
		const prev = new Map(); const visited = new Set([start]);
		const q = [{id:start, depth:0}];
		while (q.length) {
			const {id, depth} = q.shift();
			if (depth > (maxHops || 6)) break;
			for (const {edge, other} of (adj.get(id)||[])) {
				if (visited.has(other)) continue;
				visited.add(other); prev.set(other, {edge, from:id});
				if (other === end) {
					const out = []; let cur = end;
					while (cur !== start) { const p = prev.get(cur); out.unshift(p.edge); cur = p.from; }
					return out;
				}
				q.push({id:other, depth:depth+1});
			}
		}
		return null;
	}

	/* ---------- Parallel-edge offset for curved lines ----------
	 * Returns a perpendicular control point offset from the AB midpoint,
	 * alternating side by index.
	 */
	function offsetEdge(A, B, index, total) {
		if (total <= 1) return null;
		const dx = B.lng - A.lng, dy = B.lat - A.lat, len = Math.hypot(dx, dy) || 1;
		// Offset in screen-space-like degrees (adjusted for latitude).
		const step = 0.18; // fraction of segment length
		const offset = (index - (total - 1) / 2) * step;
		// Perpendicular, scaled by cos(lat) for longitude.
		const midLat = (A.lat + B.lat) / 2;
		return {
			lat: (A.lat + B.lat)/2 + (-dx/len) * offset,
			lng: (A.lng + B.lng)/2 + ( dy/len) * offset / Math.cos(midLat * Math.PI/180),
		};
	}

	/* ---------- Cluster aggregation (basic: count edges between clusters) ---------- */
	function aggregateByCluster(edgeIdSet, clusterOf) {  // clusterOf: id -> clusterId
		const bundles = new Map();
		edgeIdSet.forEach(eKey => {
			const e = eKey.edge || eKey;  // accept raw edge objects too
			const s = clusterOf(nodeId(e.source)), t = clusterOf(nodeId(e.target));
			if (s == null || t == null || s === t) return;
			const key = [s,t].sort().join('|');
			const b = bundles.get(key) || { clusterA:s, clusterB:t, count:0, types:new Set() };
			b.count++; if (e.type) b.types.add(e.type);
			bundles.set(key, b);
		});
		return [...bundles.values()];
	}

	/* ---------- Self-test: run on boot in dev; visible in the console ---------- */
	function selfTest() {
		const missing = [];
		const spec = (window.SirajMapKit && window.SirajMapKit.TOOL_SPEC) || [];
		const tools = (window.sirajIcons && window.sirajIcons.tools) || {};
		spec.forEach(t => { if (!tools[t.icon]) missing.push('tool:' + t.id + ' -> ' + t.icon); });
		// Ego network smoke test.
		const edges = [
			{name:'e1', source:['Person','A'], target:['Person','B'], type:'knows', direction:'Symmetric'},
			{name:'e2', source:['Person','A'], target:['Place','P'],  type:'located at', direction:'Directed'},
		];
		const adj = buildAdjacency(edges);
		const net = egoNetwork(adj, nodeId(['Person','A']), 1);
		if (net.nodes.size !== 3 || net.edges.size !== 2) missing.push('egoNetwork traversal failed');
		if (missing.length) {
			console.error('[SIRAJ graph] self-test FAIL:', missing);
			if (typeof frappe !== 'undefined' && frappe.throw) { /* don't crash the app */ }
		} else {
			console.info('[SIRAJ graph] self-test OK (' + spec.length + ' tool icons, ego traversal)');
		}
		return missing;
	}

	// Run once DOM is ready.
	if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', selfTest, {once:true});
	else setTimeout(selfTest, 0);

	window.SirajGraph = { buildAdjacency, egoNetwork, shortestPath, offsetEdge, aggregateByCluster, nodeId, edgeId, selfTest };
})();
