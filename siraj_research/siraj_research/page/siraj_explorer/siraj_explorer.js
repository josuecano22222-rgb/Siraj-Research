frappe.pages['siraj-explorer'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __('SIRAJ Explorer'), single_column: true });
	new SirajExplorer(page);
};

class SirajExplorer {
	constructor(page) {
		this.page = page;
		this.root = $('<div class="siraj-explorer"></div>').appendTo(page.main);
		this.kind = 'geography';
		this.map = null;
		this.network = null;
		this.colors = { 'Person': '#3577c0', 'Institution': '#8262b0', 'Place': '#188c7e', 'Event': '#d08733', 'Source': '#aa6b85', 'Military Unit': '#c3564b', 'Operational Deployment': '#867e45' };
		this.render();
	}

	escape(value) { return $('<div>').text(value == null ? '' : String(value)).html(); }
	id(node) { return JSON.stringify([node.doctype, node.name]); }
	t(label) { return this.escape(__(label)); }
	button(text, handler, primary = false) {
		const b = $('<button type="button" class="btn btn-sm"></button>').addClass(primary ? 'btn-primary' : 'btn-default').text(text);
		b.on('click', handler);
		return b;
	}
	async render() {
		if (this.map) { this.map.remove(); this.map = null; }
		if (this.network) { this.network.destroy(); this.network = null; }
		const renderId = this.renderId = (this.renderId || 0) + 1;
		this.root.empty();
		const tabs = $('<div class="sx-tabs"></div>').appendTo(this.root);
		[['geography', __('Geographic map')], ['relationships', __('Relationship map')], ['structures', __('Structures')]].forEach(([key, title]) => {
			this.button(title, () => { this.kind = key; this.render(); }).toggleClass('active', this.kind === key).appendTo(tabs);
		});
		this.tools = $('<div class="sx-tools"></div>').appendTo(this.root);
		this.note = $('<div class="sx-note" role="status"></div>').text(__('Loading…')).appendTo(this.root);
		this.legend = $('<div class="sx-legend"></div>').appendTo(this.root);
		const layout = $('<div class="sx-layout"></div>').appendTo(this.root);
		this.canvas = $('<div class="sx-canvas"></div>').appendTo(layout);
		this.aside = $('<aside class="sx-aside"></aside>').appendTo(layout);
		try {
			if (this.kind === 'structures') {
				await this.structures(renderId);
			} else if (this.kind === 'geography') {
				// A failing data endpoint must not prevent the local base map loading.
				let data;
				try {
					const res = await frappe.call({ method: 'siraj_research.visualization.geographic_data' });
					data = res.message;
				} catch (error) {
					console.error(error);
					data = { points: [], truncated: [], unavailable: true };
				}
				if (renderId === this.renderId) await this.geography(data, renderId);
			} else {
				const res = await frappe.call({ method: 'siraj_research.visualization.relationship_data' });
				if (renderId === this.renderId) await this.relationships(res.message, renderId);
			}
		} catch (error) {
			if (renderId !== this.renderId) return;
			this.note.text(__('Unable to load the explorer. Check permissions and try again.')).addClass('sx-warning');
			console.error(error);
		}
	}
	warning(data) {
		if (data.truncated && (Array.isArray(data.truncated) ? data.truncated.length : data.truncated)) {
			return __('Results are limited to {0} visible records per type; the view is incomplete.', [data.limit]);
		}
		return '';
	}
	showDetails(title, rows, target) {
		this.aside.empty();
		$('<h4></h4>').text(title).appendTo(this.aside);
		const dl = $('<dl></dl>').appendTo(this.aside);
		rows.forEach(([label, value]) => {
			if (value === null || value === undefined || value === '') return;
			$('<dt></dt>').text(label).appendTo(dl);
			$('<dd></dd>').text(value).appendTo(dl);
		});
		if (target) this.button(__('Open record'), () => frappe.set_route('Form', target.doctype, target.name), true).addClass('sx-open').appendTo(this.aside);
	}
	showLegend(types, icons = null) {
		types.forEach(type => {
			const item = $('<span class="sx-legend-item"></span>').appendTo(this.legend);
			if (icons && icons[type]) {
				// SVG fragments are fixed application constants, never record data.
				$('<span class="sx-map-pin sx-legend-pin"><svg viewBox="0 0 24 24" aria-hidden="true">' + icons[type] + '</svg></span>').css('background', this.colors[type]).appendTo(item);
			} else $('<i class="sx-pin-key"></i>').css('background', this.colors[type]).appendTo(item);
			item.append(document.createTextNode(__(type)));
		});
	}
	filterControls(types, onChange) {
		const search = $('<input class="form-control input-sm" type="search">').attr('placeholder', __('Search records')).appendTo(this.tools);
		const select = $('<select class="form-control input-sm"></select>').appendTo(this.tools);
		$('<option value=""></option>').text(__('All types')).appendTo(select);
		types.forEach(type => $('<option></option>').val(type).text(__(type)).appendTo(select));
		search.on('input', () => onChange(search.val(), select.val()));
		select.on('change', () => onChange(search.val(), select.val()));
	}
	async geography(data, renderId) {
		await frappe.require([
			'/assets/siraj_research/vendor/leaflet/leaflet.css',
			'/assets/siraj_research/vendor/leaflet/leaflet.js',
			'/assets/siraj_research/vendor/leaflet-markercluster/leaflet.markercluster.js',
			'/assets/siraj_research/vendor/topojson/topojson-client.min.js',
			'/assets/siraj_research/css/siraj_explorer.css'
		]);
		if (renderId !== this.renderId) return;
		const map = this.map = L.map(this.canvas[0], { worldCopyJump: true, preferCanvas: true, minZoom: 2, maxZoom: 19 }).setView([33.3152, 44.3661], 4);
		L.control.scale({ imperial: false }).addTo(map);
		// All basemap geometry is served by this site; no external request is
		// made until the user explicitly selects OpenStreetMap.
		let offlineLayer = null, onlineLayer = null, selectedCircle = null;
		const mapStatus = $('<div class="sx-map-status" role="status"></div>').appendTo(this.root);
		try {
			const response = await fetch('/assets/siraj_research/vendor/world-atlas/countries-110m.json');
			if (!response.ok) throw new Error('Offline basemap HTTP ' + response.status);
			const world = await response.json();
			if (renderId !== this.renderId) return;
			offlineLayer = L.geoJSON(topojson.feature(world, world.objects.countries), {
				interactive: false, style: { color: '#a4b4a8', weight: 0.7, fillColor: '#e8e4cf', fillOpacity: 1 }
			}).addTo(map);
			map.attributionControl.addAttribution('Natural Earth / world-atlas');
			mapStatus.text(__('Offline basemap: Natural Earth, low detail.'));
		} catch (error) {
			console.error(error);
			if (renderId !== this.renderId) return;
			mapStatus.text(__('Local basemap could not be loaded. You can still use the markers or enable online tiles.')).addClass('sx-warning');
		}
		const icons = {
			'Person': '<circle cx="12" cy="8" r="3"/><path d="M5 19c0-4 3-6 7-6s7 2 7 6"/>',
			'Institution': '<path d="M3 9h18L12 3 3 9Zm2 1v8m5-8v8m4-8v8m5-8v8M3 20h18"/>',
			'Place': '<path d="M12 21s-6-6-6-11a6 6 0 0 1 12 0c0 5-6 11-6 11Z"/><circle cx="12" cy="10" r="2"/>',
			'Event': '<path d="M12 2l2.5 6 6.5.5-5 4 1.5 6.5-5.5-3.5L6.5 19 8 12.5l-5-4L9.5 8Z"/>',
			'Military Unit': '<path d="M12 2 20 5v6c0 5-3 8-8 11-5-3-8-6-8-11V5Z"/><path d="M12 7v10M7 12h10"/>',
			'Operational Deployment': '<circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="2"/><path d="M12 2v3m0 14v3M2 12h3m14 0h3"/>'
		};
		const types = [...new Set(data.points.map(p => p.doctype))];
		this.showLegend(types, icons);
		let clustered = true, currentPoints = [], searchTerm = '', selectedType = '';
		let markers = L.markerClusterGroup({
			maxClusterRadius: 45, showCoverageOnHover: false, spiderfyOnMaxZoom: true,
			iconCreateFunction: cluster => L.divIcon({ className: 'sx-cluster', html: '<span>' + cluster.getChildCount() + '</span>', iconSize: [40, 40] })
		}).addTo(map);
		const pointIcon = p => L.divIcon({
			className: 'sx-pin-wrapper', iconSize: [36, 36], iconAnchor: [18, 18],
			html: '<span class="sx-map-pin" style="background:' + this.colors[p.doctype] + '"><svg viewBox="0 0 24 24" aria-hidden="true">' + icons[p.doctype] + '</svg></span>'
		});
		const draw = () => {
			if (selectedCircle) { map.removeLayer(selectedCircle); selectedCircle = null; }
			markers.clearLayers();
			const term = searchTerm.toLocaleLowerCase();
			currentPoints = data.points.filter(p => (!selectedType || p.doctype === selectedType) && (p.label + ' ' + p.name).toLocaleLowerCase().includes(term));
			currentPoints.forEach(p => {
				const marker = L.marker([Number(p.latitude), Number(p.longitude)], { icon: pointIcon(p), title: p.label, keyboard: true });
				marker.bindTooltip(this.escape(p.label));
				marker.on('click', () => {
					if (selectedCircle) map.removeLayer(selectedCircle);
					const radius = Number(p.geo_uncertainty_m);
					if (Number.isFinite(radius) && radius > 0 && radius <= 1000000) selectedCircle = L.circle([p.latitude, p.longitude], { radius, color: this.colors[p.doctype], fillOpacity: 0.1, interactive: false }).addTo(map);
					this.showDetails(p.label, [[__('Type'), __(p.doctype)], [__('ID'), p.name], [__('Latitude'), p.latitude], [__('Longitude'), p.longitude], [__('Coordinate precision'), p.geo_precision], [__('How the point was obtained'), p.geocoding_method], [__('Uncertainty radius (m)'), p.geo_uncertainty_m], [__('Point source'), p.geometry_source]], p);
				});
				markers.addLayer(marker);
			});
			const text = data.unavailable ? __('Record data could not be loaded. The local basemap may still be available.') : __('Showing {0} record-owned points. Unset and ambiguous 0,0 coordinates are excluded.', [currentPoints.length]) + ' ' + this.warning(data);
			this.note.toggleClass('sx-warning', !!data.unavailable).text(text);
		};
		this.filterControls(types, (search, type) => { searchTerm = search; selectedType = type; draw(); });
		this.button(__('Fit points'), () => { if (currentPoints.length) map.fitBounds(L.latLngBounds(currentPoints.map(p => [Number(p.latitude), Number(p.longitude)])).pad(0.15), { maxZoom: 12 }); }).appendTo(this.tools);
		const clusterButton = this.button(__('Clusters: on'), () => {
			clustered = !clustered;
			map.removeLayer(markers);
			markers = clustered ? L.markerClusterGroup({ maxClusterRadius: 45, showCoverageOnHover: false, spiderfyOnMaxZoom: true, iconCreateFunction: cluster => L.divIcon({ className: 'sx-cluster', html: '<span>' + cluster.getChildCount() + '</span>', iconSize: [40, 40] }) }) : L.featureGroup();
			markers.addTo(map); clusterButton.text(clustered ? __('Clusters: on') : __('Clusters: off')); draw();
		}).appendTo(this.tools);
		const base = $('<select class="form-control input-sm" aria-label="Basemap"></select>').appendTo(this.tools);
		$('<option value="local"></option>').text(__('Offline basemap')).appendTo(base);
		$('<option value="online"></option>').text(__('Online: OpenStreetMap')).appendTo(base);
		base.on('change', () => {
			if (onlineLayer) { map.removeLayer(onlineLayer); onlineLayer = null; }
			if (base.val() === 'online') {
				if (offlineLayer) map.removeLayer(offlineLayer);
				onlineLayer = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' }).addTo(map);
				onlineLayer.on('tileerror', () => mapStatus.text(__('Some online tiles failed to load. Choose the offline basemap to continue.')).addClass('sx-warning'));
				mapStatus.text(__('Online tiles disclose your IP address and viewed area to OpenStreetMap.')).removeClass('sx-warning');
			} else {
				if (offlineLayer) offlineLayer.addTo(map).bringToBack();
				mapStatus.text(offlineLayer ? __('Offline basemap: Natural Earth, low detail.') : __('Local basemap could not be loaded. You can still use the markers or enable online tiles.')).toggleClass('sx-warning', !offlineLayer);
			}
		});
		this.button(__('Export visible points'), () => {
			const geojson = { type: 'FeatureCollection', features: currentPoints.map(p => ({ type: 'Feature', geometry: { type: 'Point', coordinates: [Number(p.longitude), Number(p.latitude)] }, properties: { doctype: p.doctype, name: p.name, label: p.label, precision: p.geo_precision, method: p.geocoding_method, uncertainty_m: p.geo_uncertainty_m, source: p.geometry_source } })) };
			const url = URL.createObjectURL(new Blob([JSON.stringify(geojson)], { type: 'application/geo+json' }));
			const a = document.createElement('a'); a.href = url; a.download = 'siraj-visible-points.geojson'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
		}).appendTo(this.tools);
		let measuring = false, measurePoints = [], measureLine = null;
		const measureStatus = $('<div class="sx-map-status" role="status"></div>').appendTo(this.root);
		const measureButton = this.button(__('Measure distance'), () => {
			measuring = !measuring; measurePoints = [];
			if (measureLine) { map.removeLayer(measureLine); measureLine = null; }
			measureStatus.text(measuring ? __('Click two points on the map to measure distance.') : '');
			measureButton.text(measuring ? __('Clear measurement') : __('Measure distance'));
		}).appendTo(this.tools);
		map.on('click', event => {
			if (!measuring) return;
			if (measurePoints.length === 2) { measurePoints = []; if (measureLine) map.removeLayer(measureLine); }
			measurePoints.push(event.latlng);
			if (measurePoints.length === 2) {
				measureLine = L.polyline(measurePoints, { color: '#1a6670', weight: 3, dashArray: '6 5', interactive: false }).addTo(map);
				const distance = map.distance(measurePoints[0], measurePoints[1]);
				measureStatus.text(__('Distance: {0} km', [(distance / 1000).toFixed(2)]));
			}
		});
		this.showDetails(__('Geographic map'), [[__('About this view'), __('Select a marker to inspect its record. Clusters show the number of nearby points. Online tiles are optional.')]]);
		draw();
		if (currentPoints.length) map.fitBounds(L.latLngBounds(currentPoints.map(p => [Number(p.latitude), Number(p.longitude)])).pad(0.15), { maxZoom: 12 });
	}

	async relationships(data, renderId) {
		await frappe.require(['/assets/siraj_research/vendor/vis-network/vis-network.min.js', '/assets/siraj_research/css/siraj_explorer.css']);
		if (renderId !== this.renderId) return;
		this.canvas.addClass('sx-graph');
		const types = [...new Set(data.nodes.map(n => n.doctype))];
		this.showLegend(types);
		const all = new Map(data.nodes.map(n => [this.id(n), n]));
		const edgeLookup = new Map(data.edges.map(e => [e.name, e]));
		const nodeSet = new vis.DataSet();
		const edgeSet = new vis.DataSet();
		let currentEdges = [], history = [], currentId = null, centerId = null;
		let searchTerm = '', selectedType = '';
		let centerButton, resetButton;
		this.network = new vis.Network(this.canvas[0], { nodes: nodeSet, edges: edgeSet }, {
			interaction: { hover: true, navigationButtons: true, keyboard: true },
			physics: { stabilization: { iterations: 100 }, barnesHut: { gravitationalConstant: -5000, springLength: 150 } },
			nodes: { shape: 'dot', size: 13, font: { size: 13 }, borderWidth: 2 },
			edges: { color: { color: '#9aa9b1', highlight: '#267b77' }, smooth: { type: 'dynamic' }, font: { size: 11, align: 'middle' } }
		});
		const showNode = (id, remember = true) => {
			const node = all.get(id);
			if (!node || !nodeSet.get(id)) return;
			if (remember && currentId && currentId !== id) history.push(currentId);
			currentId = id;
			if (centerButton) centerButton.prop('disabled', false);
			this.network.selectNodes([id]);
			this.network.focus(id, { scale: 1, animation: { duration: 400 } });
			this.showDetails(node.label, [[__('Type'), __(node.doctype)], [__('ID'), node.name]], node);
			const connected = currentEdges.filter(e => JSON.stringify(e.source) === id || JSON.stringify(e.target) === id);
			$('<h5 class="sx-neighbors-heading"></h5>').text(__('Connections ({0})', [connected.length])).appendTo(this.aside);
			if (!connected.length) $('<p class="sx-muted"></p>').text(__('No visible connections in this view.')).appendTo(this.aside);
			connected.forEach(edge => {
				const sourceId = JSON.stringify(edge.source), targetId = JSON.stringify(edge.target);
				const neighbor = all.get(sourceId === id ? targetId : sourceId);
				if (!neighbor) return;
				const row = $('<div class="sx-neighbor"></div>').appendTo(this.aside);
				$('<small></small>').text(edge.type || __('Relationship')).appendTo(row);
				this.button(neighbor.label, () => showNode(this.id(neighbor))).addClass('sx-neighbor-link').appendTo(row);
			});
		};
		const showEdge = edge => {
			if (!edge) return;
			currentId = null;
			if (centerButton) centerButton.prop('disabled', true);
			this.showDetails(edge.type || __('Relationship'), [[__('ID'), edge.name], [__('Direction'), edge.direction], [__('Description'), edge.description], [__('Record status'), edge.state]], { doctype: 'Relationship', name: edge.name });
			[edge.source, edge.target].forEach((key, index) => {
				const id = JSON.stringify(key), node = all.get(id);
				if (!node) return;
				const row = $('<div class="sx-neighbor"></div>').appendTo(this.aside);
				$('<small></small>').text(index === 0 ? __('Subject') : __('Object')).appendTo(row);
				this.button(node.label, () => showNode(id)).addClass('sx-neighbor-link').appendTo(row);
			});
		};
		const update = () => {
			const term = searchTerm.toLocaleLowerCase();
			let nodes = data.nodes.filter(n => (!selectedType || n.doctype === selectedType) && (n.label + ' ' + n.name).toLocaleLowerCase().includes(term));
			let ids = new Set(nodes.map(n => this.id(n)));
			if (centerId && ids.has(centerId)) {
				const neighborhood = new Set([centerId]);
				data.edges.forEach(e => {
					const source = JSON.stringify(e.source), target = JSON.stringify(e.target);
					if (source === centerId && ids.has(target)) neighborhood.add(target);
					if (target === centerId && ids.has(source)) neighborhood.add(source);
				});
				nodes = nodes.filter(n => neighborhood.has(this.id(n)));
				ids = neighborhood;
			} else { centerId = null; }
			currentEdges = data.edges.filter(e => ids.has(JSON.stringify(e.source)) && ids.has(JSON.stringify(e.target)));
			edgeSet.clear(); nodeSet.clear(); history = []; currentId = null;
			if (centerButton) centerButton.prop('disabled', true);
			if (resetButton) resetButton.prop('disabled', !centerId);
			const large = nodes.length > 500;
			this.network.setOptions({ physics: { enabled: !large } });
			const columns = Math.ceil(Math.sqrt(nodes.length || 1));
			nodeSet.add(nodes.map((n, i) => ({ id: this.id(n), label: n.label, color: this.colors[n.doctype],
				...(large ? { x: (i % columns) * 180, y: Math.floor(i / columns) * 110 } : {}) })));
			edgeSet.add(currentEdges.map(e => ({ id: e.name, from: JSON.stringify(e.source), to: JSON.stringify(e.target), label: e.type, arrows: /^(directed|one.way)$/i.test(e.direction) ? 'to' : '' })));
			this.note.text(__('Showing {0} records and {1} relationships. Only visible records and links are included.', [nodes.length, currentEdges.length]) + ' ' + this.warning(data));
			this.showDetails(__('Relationship map'), [[__('About this view'), __('Select a record or a connection to inspect it. Drag nodes to rearrange the network.')]]);
		};
		this.network.on('selectNode', event => showNode(event.nodes[0]));
		this.network.on('selectEdge', event => showEdge(edgeLookup.get(event.edges[0])));
		this.filterControls(types, (search, type) => { searchTerm = search; selectedType = type; centerId = null; update(); });
		centerButton = this.button(__('Center on selected record'), () => {
			if (!currentId) return;
			centerId = currentId;
			update();
			showNode(centerId, false);
		}).prop('disabled', true).appendTo(this.tools);
		resetButton = this.button(__('Show all records'), () => { centerId = null; update(); }).prop('disabled', true).appendTo(this.tools);
		this.button(__('Back'), () => { while (history.length) { const id = history.pop(); if (nodeSet.get(id)) { showNode(id, false); break; } } }).appendTo(this.tools);
		this.button(__('Fit network'), () => this.network.fit({ animation: true })).appendTo(this.tools);
		this.button(__('Stabilize layout'), () => this.network.stabilize()).appendTo(this.tools);
		update();
	}

	async structures(renderId) {
		await frappe.require(['/assets/siraj_research/css/siraj_explorer.css']);
		if (renderId !== this.renderId) return;
		this.canvas.removeClass('sx-canvas').addClass('sx-tree');
		const choices = [['people', __('Person')], ['institutions', __('Institution')], ['places', __('Place')], ['events', __('Event')], ['relationships', __('Relationship')], ['sources', __('Source')], ['units', __('Military Unit')]];
		const select = $('<select class="form-control input-sm"></select>').appendTo(this.tools);
		choices.forEach(([id, title]) => $('<option></option>').val(id).text(title).appendTo(select));
		const mode = $('<select class="form-control input-sm"></select>').appendTo(this.tools);
		$('<option value="tree"></option>').text(__('Expandable tree')).appendTo(mode);
		$('<option value="bars"></option>').text(__('Distribution bars')).appendTo(mode);
		let request = 0, cachedData = null;
		const load = async () => {
			cachedData = null;
			this.canvas.empty(); this.aside.empty(); this.note.removeClass('sx-warning').text(__('Loading…'));
			const current = ++request;
			try {
				const result = await frappe.call({ method: 'siraj_research.visualization.structure_data', args: { source: select.val() } });
				if (renderId !== this.renderId || current !== request) return;
				const data = cachedData = result.message;
				draw(data);
			} catch (error) {
				if (renderId !== this.renderId || current !== request) return;
				this.canvas.empty(); this.aside.empty(); this.note.text(__('Unable to load this structure. Check permissions.')).addClass('sx-warning');
			}
		};
		const draw = data => {
			this.note.removeClass('sx-warning').text(__('Counting {0} visible records.', [data.count]) + ' ' + this.warning(data));
			this.showDetails(__('Structures'), [[__('Source'), __(data.doctype)], [__('Grouping'), data.dimensions.map(x => __(x)).join(' → ')], [__('Records'), data.count], [__('About this view'), __('Counts reflect visible records only. Expand a branch to inspect its groups.')]]);
			this.canvas.empty();
			if (!data.count) { this.canvas.text(__('No records to display.')); return; }
			if (mode.val() === 'bars') {
				data.children.forEach(group => {
					const row = $('<div class="sx-bar-row"></div>').appendTo(this.canvas);
					$('<span></span>').text(group.label).appendTo(row);
					$('<span class="sx-count"></span>').text(group.count).appendTo(row);
					$('<div class="sx-bar"></div>').css('width', (100 * group.count / data.count) + '%').appendTo(row);
				});
			} else {
				const appendGroups = (parent, groups) => groups.forEach(group => {
					const details = $('<details></details>').appendTo(parent);
					const summary = $('<summary></summary>').appendTo(details);
					$('<span></span>').text(group.label).appendTo(summary);
					if (group.group_count) $('<span class="sx-group-count"></span>').text(__('Groups: {0}', [group.group_count])).appendTo(summary);
					$('<span class="sx-count"></span>').text(group.count).appendTo(summary);
					if (group.children.length) appendGroups(details, group.children);
				});
				appendGroups(this.canvas, data.children);
			}
		};
		select.on('change', load); mode.on('change', () => { if (cachedData) draw(cachedData); });
		await load();
	}
}
