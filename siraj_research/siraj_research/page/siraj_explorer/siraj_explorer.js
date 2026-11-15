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
			} else {
				const method = this.kind === 'geography' ? 'geographic_data' : 'relationship_data';
				const res = await frappe.call({ method: 'siraj_research.visualization.' + method });
				if (renderId !== this.renderId) return;
				if (this.kind === 'geography') await this.geography(res.message, renderId);
				else await this.relationships(res.message, renderId);
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
	showLegend(types) {
		types.forEach(type => {
			const item = $('<span></span>').appendTo(this.legend);
			$('<i class="sx-pin-key"></i>').css('background', this.colors[type]).appendTo(item);
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
		await frappe.require(['/assets/siraj_research/vendor/leaflet/leaflet.css', '/assets/siraj_research/vendor/leaflet/leaflet.js', '/assets/siraj_research/css/siraj_explorer.css']);
		if (renderId !== this.renderId) return;
		this.map = L.map(this.canvas[0], { worldCopyJump: true }).setView([30, 20], 2);
		let markers = L.featureGroup().addTo(this.map);
		let tileLayer = null;
		const types = [...new Set(data.points.map(p => p.doctype))];
		this.showLegend(types);
		const update = (search = '', type = '') => {
			markers.clearLayers();
			const term = search.toLocaleLowerCase();
			const points = data.points.filter(p => (!type || p.doctype === type) && (p.label + ' ' + p.name).toLocaleLowerCase().includes(term));
			points.forEach(p => {
				const marker = L.circleMarker([Number(p.latitude), Number(p.longitude)], { radius: 8, color: '#fff', weight: 2, fillColor: this.colors[p.doctype], fillOpacity: 0.9 });
				marker.bindTooltip(this.escape(p.label));
				marker.on('click', () => this.showDetails(p.label, [[__('Type'), __(p.doctype)], [__('ID'), p.name], [__('Latitude'), p.latitude], [__('Longitude'), p.longitude], [__('Coordinate precision'), p.geo_precision], [__('How the point was obtained'), p.geocoding_method], [__('Uncertainty radius (m)'), p.geo_uncertainty_m], [__('Point source'), p.geometry_source]], p));
				marker.addTo(markers);
			});
			this.note.text(__('Showing {0} record-owned points. Unset and ambiguous 0,0 coordinates are excluded.', [points.length]) + ' ' + this.warning(data));
		};
		this.filterControls(types, update);
		this.button(__('Fit points'), () => { if (markers.getLayers().length) this.map.fitBounds(markers.getBounds().pad(0.15), { maxZoom: 12 }); }).appendTo(this.tools);
		this.button(__('Toggle OpenStreetMap tiles'), () => {
			if (tileLayer) { this.map.removeLayer(tileLayer); tileLayer = null; }
			else {
				tileLayer = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' }).addTo(this.map);
			}
		}).appendTo(this.tools);
		this.showDetails(__('Geographic map'), [[__('About this view'), __('Select a marker to inspect its record. Tiles are optional; enabling them sends map requests to OpenStreetMap.')]]);
		update();
		if (markers.getLayers().length) this.map.fitBounds(markers.getBounds().pad(0.15), { maxZoom: 12 });
	}
	async relationships(data, renderId) {
		await frappe.require(['/assets/siraj_research/vendor/vis-network/vis-network.min.js', '/assets/siraj_research/css/siraj_explorer.css']);
		if (renderId !== this.renderId) return;
		this.canvas.addClass('sx-graph');
		const types = [...new Set(data.nodes.map(n => n.doctype))];
		this.showLegend(types);
		const all = new Map(data.nodes.map(n => [this.id(n), n]));
		const nodeSet = new vis.DataSet();
		const edgeSet = new vis.DataSet();
		this.network = new vis.Network(this.canvas[0], { nodes: nodeSet, edges: edgeSet }, {
			interaction: { hover: true, navigationButtons: true, keyboard: true },
			physics: { stabilization: { iterations: 100 }, barnesHut: { gravitationalConstant: -5000, springLength: 150 } },
			nodes: { shape: 'dot', size: 13, font: { size: 13 }, borderWidth: 2 },
			edges: { color: { color: '#9aa9b1', highlight: '#267b77' }, smooth: { type: 'dynamic' }, font: { size: 11, align: 'middle' } }
		});
		const update = (search = '', type = '') => {
			const term = search.toLocaleLowerCase();
			const nodes = data.nodes.filter(n => (!type || n.doctype === type) && (n.label + ' ' + n.name).toLocaleLowerCase().includes(term));
			const ids = new Set(nodes.map(n => this.id(n)));
			const edges = data.edges.filter(e => ids.has(JSON.stringify(e.source)) && ids.has(JSON.stringify(e.target)));
			edgeSet.clear(); nodeSet.clear();
			// Force simulation on thousands of nodes can freeze the Desk. Use a
			// deterministic, draggable grid for large results instead.
			const large = nodes.length > 500;
			this.network.setOptions({ physics: { enabled: !large } });
			const columns = Math.ceil(Math.sqrt(nodes.length || 1));
			nodeSet.add(nodes.map((n, i) => ({ id: this.id(n), label: n.label, color: this.colors[n.doctype],
				...(large ? { x: (i % columns) * 180, y: Math.floor(i / columns) * 110 } : {}) })));
			edgeSet.add(edges.map(e => ({ id: e.name, from: JSON.stringify(e.source), to: JSON.stringify(e.target), label: e.type, arrows: /^(directed|one.way)$/i.test(e.direction) ? 'to' : '' })));
			this.note.text(__('Showing {0} records and {1} relationships. Only visible records and links are included.', [nodes.length, edges.length]) + ' ' + this.warning(data));
		};
		this.network.on('selectNode', event => {
			const n = all.get(event.nodes[0]);
			if (n) this.showDetails(n.label, [[__('Type'), __(n.doctype)], [__('ID'), n.name]], n);
		});
		this.network.on('selectEdge', event => {
			const e = data.edges.find(edge => edge.name === event.edges[0]);
			if (e) this.showDetails(e.type || __('Relationship'), [[__('ID'), e.name], [__('Subject'), (all.get(JSON.stringify(e.source)) || {}).label], [__('Object'), (all.get(JSON.stringify(e.target)) || {}).label], [__('Direction'), e.direction], [__('Description'), e.description], [__('Record status'), e.state]], { doctype: 'Relationship', name: e.name });
		});
		this.filterControls(types, update);
		this.button(__('Fit network'), () => this.network.fit({ animation: true })).appendTo(this.tools);
		this.button(__('Stabilize layout'), () => this.network.stabilize()).appendTo(this.tools);
		this.showDetails(__('Relationship map'), [[__('About this view'), __('Select a record or a connection to inspect it. Drag nodes to rearrange the network.')]]);
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
		let request = 0;
		const load = async () => {
			const current = ++request;
			try {
				const result = await frappe.call({ method: 'siraj_research.visualization.structure_data', args: { source: select.val() } });
				if (renderId !== this.renderId || current !== request) return;
				const data = result.message;
				this.note.text(__('Counting {0} visible records.', [data.count]) + ' ' + this.warning(data));
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
						$('<span class="sx-count"></span>').text(group.count).appendTo(summary);
						if (group.children.length) appendGroups(details, group.children);
					});
					appendGroups(this.canvas, data.children);
				}
			} catch (error) {
				if (renderId !== this.renderId || current !== request) return;
				this.canvas.empty(); this.aside.empty(); this.note.text(__('Unable to load this structure. Check permissions.')).addClass('sx-warning');
			}
		};
		select.on('change', load); mode.on('change', load);
		await load();
	}
}
