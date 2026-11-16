/* Structure deck for the Frappe explorer. Layouts share the same counted tree. */
(function () {
	'use strict';
	const NS = 'http://www.w3.org/2000/svg';
	const W = 1000, H = 640;
	const DOCTYPE_BY_SOURCE = {
		people:'Person', institutions:'Institution', places:'Place', events:'Research Event',
		relationships:'Relationship', sources:'Source', units:'Military Unit',
		regions:'Command Region', 'regions-units':'Command Region', 'units-ops':'Operational Deployment', forces:'Military Unit',
	};
	function colorFor(node, source) {
		if (window.sirajColours) {
			if (node.data && node.data.doctype && window.sirajColours[node.data.doctype]) return window.sirajColours[node.data.doctype];
			const guess = DOCTYPE_BY_SOURCE[source];
			if (guess && window.sirajColours[guess]) return window.sirajColours[guess];
		}
		// Fallback palette.
		const palette = ['#2f6f4f','#1f5d8b','#8a5a1f','#7b3f8f','#a15143','#597d80','#987e31','#59638d'];
		const roots = (node.ancestors().slice(-1)[0] || {}).children || [];
		return palette[Math.max(0, roots.indexOf(node)) % palette.length];
	}
	function glyphFor(node, size) {
		const dt = (node.data && node.data.doctype) || DOCTYPE_BY_SOURCE[node.data && node.data.source] || 'Source';
		return (window.sirajIcons && window.sirajIcons.svg(dt, {size: size || 10})) || '';
	}

	class StructureDeck {
		constructor(explorer, canvas, aside, data) {
			this.explorer = explorer;
			explorer.structureDeck = this;
			this.canvas = canvas;
			this.aside = aside;
			this.data = data;
			this.mode = 'treemap';
			this.root = { label: data.label || __(data.doctype), count: data.count, group_count: data.group_count, children: data.children };
			this.focus = this.root;
			this.path = [this.root];
			this.expanded = new Set([this.root]);
			this.selected = null;
			this.tableVisible = false;
			this.legendVisible = true;
			this.maxDepth = 3;
			// Large registries start with record leaves hidden to avoid constructing an
			// enormous SVG. They remain available when the user enables Records.
			this.showRecords = data.count <= 3000;
			this.renderId = explorer.renderId;
			this.build();
		}
		button(label, fn, parent) {
			return this.explorer.button(label, fn).appendTo(parent);
		}
		build() {
			this.canvas.empty().removeClass('sx-tree').addClass('sx-structure-deck');
			this.bar = $('<div class="sd-bar"></div>').appendTo(this.canvas);
			this.tabs = $('<div class="sd-tabs" role="tablist"></div>').appendTo(this.bar);
			const modes = [['treemap', __('Treemap')], ['rings', __('Rings')], ['flow', __('Flow')], ['matrix', __('Matrix')], ['discs', __('Discs')], ['tree', __('Tree')]];
			this.tabButtons = modes.map(([key, label], i) => {
				const b = this.button((i + 1) + '  ' + label, () => { this.mode = key; this.render(); }, this.tabs);
				b.attr({ role: 'tab', 'data-mode': key });
				return b;
			});
			const depth = $('<select class="form-control input-sm sd-depth" aria-label="Structure depth"></select>').appendTo(this.bar);
			[1, 2, 3].forEach(n => $('<option></option>').val(n).text(__('Depth {0}', [n])).appendTo(depth));
			depth.val(this.maxDepth).on('change', () => { this.maxDepth = Number(depth.val()); this.render(); });
			const recordToggle = $('<label class="sd-check"></label>').appendTo(this.bar);
			this.recordInput = $('<input type="checkbox">').prop('checked', this.showRecords).on('change', e => { this.showRecords = e.target.checked; this.render(); }).appendTo(recordToggle);
			recordToggle.append(document.createTextNode(__('Records')));
			const find = $('<input type="search" class="form-control input-sm sd-find">').attr({'aria-label': __('Find in structure'), placeholder: __('Find in structure')}).appendTo(this.bar);
			find.on('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); this.find(find.val()); } });
			this.button(__('Find'), () => this.find(find.val()), this.bar);
			this.button(__('Legend'), () => { this.legendVisible = !this.legendVisible; this.legend.toggle(this.legendVisible); }, this.bar);
			this.button(__('Table'), () => { this.tableVisible = !this.tableVisible; this.renderTable(); }, this.bar).attr('aria-label', __('Show or hide data table'));
			this.button(__('Zoom in'), () => { if (this.svgRoot) this.svgRoot.call(this.zoom.scaleBy, 1.25); }, this.bar);
			this.button(__('Zoom out'), () => { if (this.svgRoot) this.svgRoot.call(this.zoom.scaleBy, 0.8); }, this.bar);
			this.button(__('Fit'), () => { if (this.svgRoot) this.svgRoot.call(this.zoom.transform, d3.zoomIdentity); }, this.bar);
			this.button(__('Export SVG'), () => this.exportSvg(), this.bar);
			this.button(__('Export CSV'), () => this.exportCsv(), this.bar);
			this.crumbs = $('<nav class="sd-crumbs" aria-label="Structure path"></nav>').appendTo(this.canvas);
			this.stage = $('<div class="sd-stage" tabindex="0"></div>').appendTo(this.canvas);
			this.legend = $('<div class="sd-legend" aria-label="Legend"></div>').appendTo(this.canvas);
			this.footer = $('<div class="sd-footer" role="status"></div>').appendTo(this.canvas);
			this.table = $('<div class="sd-table"></div>').appendTo(this.canvas);
			this.canvas.off('keydown.structureDeck').on('keydown.structureDeck', e => {
				if (/^(INPUT|SELECT|TEXTAREA)$/.test(e.target.tagName) || e.target.isContentEditable) return;
				const mode = Number(e.key);
				if (mode >= 1 && mode <= 6 && String(mode) === e.key) { e.preventDefault(); this.tabButtons[mode - 1].trigger('click'); }
				if (e.key === 'Escape' && this.path.length > 1) { e.preventDefault(); this.path.pop(); this.focus = this.path[this.path.length - 1]; this.render(); }
			});
			this.render();
		}
		children(data) {
			const depth = this.depths ? this.depths.get(data) || 0 : 0;
			return (data.children || []).filter(child => {
				const record = child.record || child.folded_records;
				return record ? this.showRecords : depth < this.maxDepth;
			});
		}
		hierarchy() {
			return d3.hierarchy(this.focus, d => this.children(d))
				.sum(d => Math.max(0, d.count - this.children(d).reduce((sum, child) => sum + child.count, 0)))
				.sort((a, b) => b.value - a.value);
		}
		color(node) { return colorFor(node, this.data.source); }
		glyph(node, size) { return glyphFor(node, size); }
		svg(height = H, width = W) {
			const svg = document.createElementNS(NS, 'svg');
			svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
			svg.setAttribute('role', 'group');
			svg.setAttribute('direction', 'ltr');
			svg.setAttribute('aria-label', __('Structure diagram'));
			svg.style.minWidth = width > W ? width + 'px' : '';
			svg.style.minHeight = height > H ? height + 'px' : '';
			this.stage.append(svg);
			this.svgRoot = d3.select(svg);
			const world = this.svgRoot.append('g');
			this.zoom = d3.zoom().scaleExtent([0.25, 8]).on('zoom', event => world.attr('transform', event.transform));
			this.svgRoot.call(this.zoom).on('dblclick.zoom', null);
			return world;
		}
		mark(selection, node) {
			selection.attr('tabindex', 0).attr('role', 'button')
				.attr('aria-label', node.data.label + ': ' + node.data.count)
				.on('click', event => { event.stopPropagation(); this.select(node.data); })
				.on('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); this.select(node.data); } });
			selection.append('title').text(node.data.label + ' — ' + node.data.count + (node.data.folded_groups ? ' (' + node.data.folded_groups + ' ' + __('groups') + ')' : ''));
			return selection;
		}
		label(svg, x, y, text, opts = {}) {
			return svg.append('text').attr('x', x).attr('y', y).attr('text-anchor', opts.anchor || 'start')
				.attr('class', 'sd-label ' + (opts.className || '')).text(text);
		}
		short(text, n) { text = String(text); return text.length > n ? text.slice(0, Math.max(0, n - 1)) + '…' : text; }
		select(data) {
			this.selected = data;
			this.explorer.showDetails(data.label, [[__('Records'), data.count], [__('Groups'), data.group_count],
				[__('Folded groups'), data.folded_groups], [__('Folded records'), data.folded_records], [__('Grouping'), data.field ? __(data.field) : '']], (data.record || data.target) ? {doctype: data.target_doctype || this.data.doctype, name: data.name} : null);
			if (data.record || data.target) {
				const selection = data;
				frappe.call({method: 'siraj_research.visualization.record_detail', args: {doctype: data.target_doctype || this.data.doctype, name: data.name}}).then(result => {
					if (this.selected !== selection || this.renderId !== this.explorer.renderId || this.explorer.structureDeck !== this || !result.message) return;
					const record = result.message;
					this.explorer.showDetails(record.label, [[__('Type'), __(record.doctype)], [__('ID'), record.name], ...Object.entries(record.details || {}).map(([label, value]) => [__(label), value])], record);
					this.addExplore(selection);
				}).catch(() => { if (this.selected === selection && this.renderId === this.explorer.renderId && this.explorer.structureDeck === this) $('<p class="sx-warning"></p>').text(__('Unable to load record details.')).appendTo(this.aside); });
			}
			this.addExplore(data);
		}
		addExplore(data) {
			if (data !== this.focus && (data.children || []).length) {
				this.button(__('Explore group'), () => { this.path.push(data); this.focus = data; this.expanded.add(data); this.render(); }, this.aside).addClass('sd-explore');
			}
		}
		render() {
			this.tabButtons.forEach(b => b.toggleClass('active', b.attr('data-mode') === this.mode).attr('aria-selected', b.attr('data-mode') === this.mode ? 'true' : 'false'));
			this.crumbs.empty();
			this.path.forEach((node, i) => {
				if (i) $('<span aria-hidden="true">›</span>').appendTo(this.crumbs);
				this.button(node.label, () => { this.path = this.path.slice(0, i + 1); this.focus = node; this.render(); }, this.crumbs).addClass('sd-crumb');
			});
			this.stage.empty();
			this.svgRoot = null;
			this.legend.empty().toggle(this.legendVisible);
			this.depths = new WeakMap();
			const stack = [[this.focus, 0]];
			while (stack.length) {
				const [node, depth] = stack.pop();
				this.depths.set(node, depth);
				if (depth <= this.maxDepth) (node.children || []).forEach(child => stack.push([child, depth + 1]));
			}
			this.select(this.focus);
			this.footer.text(__('Counts include only records you can read. Folded branches retain their record and group counts.') + (this.showRecords ? '' : ' ' + __('Record leaves are hidden; enable Records to show them.')));
			if (!this.focus.count) this.stage.text(__('No records to display.'));
			else {
				const root = this.hierarchy();
				(root.children || []).forEach(n => {
					const button = this.button(n.data.label + ' · ' + n.data.count, () => this.select(n.data), this.legend).addClass('sd-legend-item');
					$('<span class="sd-swatch siraj-swatch"></span>').css('background-color', this.color(n)).html(this.glyph(n, 10)).prependTo(button);
				});
				if (this.mode === 'treemap') this.treemap(root);
				else if (this.mode === 'rings') this.rings(root);
				else if (this.mode === 'flow') this.flow(root);
				else if (this.mode === 'matrix') this.matrix(root);
				else if (this.mode === 'discs') this.discs(root);
				else this.tree(root);
			}
			this.renderTable();
		}
		treemap(root) {
			d3.treemap().size([W, H]).paddingOuter(3).paddingTop(n => n.depth && n.children ? 20 : 2).paddingInner(2)(root);
			const svg = this.svg();
			root.descendants().slice(1).forEach(n => {
				const w = n.x1 - n.x0, h = n.y1 - n.y0;
				const g = svg.append('g');
				this.mark(g.append('rect').attr('x', n.x0).attr('y', n.y0).attr('width', Math.max(0, w)).attr('height', Math.max(0, h))
					.attr('fill', this.color(n)).attr('fill-opacity', n.children ? 0.35 : 0.75).attr('stroke', '#fff').attr('stroke-width', 1).attr('class', 'sd-mark'), n);
				if (w > 48 && h > 18) this.label(g, n.x0 + 5, n.y0 + 14, this.short(n.data.label, Math.max(4, Math.floor(w / 7))) + (w > 100 ? ' · ' + n.data.count : ''));
			});
		}
		rings(root) {
			const radius = 235;
			d3.partition().size([2 * Math.PI, radius * radius])(root);
			const svg = this.svg(), g = svg.append('g').attr('transform', `translate(${W / 2},${H / 2})`);
			const arc = d3.arc().startAngle(n => n.x0).endAngle(n => n.x1).innerRadius(n => Math.sqrt(n.y0)).outerRadius(n => Math.max(Math.sqrt(n.y0), Math.sqrt(n.y1) - 1));
			root.descendants().slice(1).forEach(n => {
				this.mark(g.append('path').attr('d', arc(n)).attr('fill', this.color(n)).attr('fill-opacity', n.depth === 1 ? 0.9 : 0.5 + n.depth * 0.08).attr('stroke', '#fff').attr('stroke-width', 1).attr('class', 'sd-mark'), n);
			});
			(root.children || []).slice(0, 12).forEach(n => {
				const a = (n.x0 + n.x1) / 2, x = Math.sin(a), y = -Math.cos(a);
				g.append('line').attr('x1', x * (radius + 2)).attr('y1', y * (radius + 2)).attr('x2', x * (radius + 12)).attr('y2', y * (radius + 12)).attr('stroke', this.color(n));
				this.label(g, x * (radius + 15) + (x < 0 ? -4 : 4), y * (radius + 15) + 4, this.short(n.data.label, 18) + ' · ' + n.data.count, {anchor: x < 0 ? 'end' : 'start'});
			});
			this.label(g, 0, -3, this.short(root.data.label, 24), {anchor: 'middle'});
			this.label(g, 0, 16, root.data.count + ' ' + __('records'), {anchor: 'middle'});
		}
		flow(root) {
			const list = root.descendants().filter(n => n.depth <= 2);
			if (list.length < 2) { this.stage.text(__('No subgroups to display.')); return; }
			const nodes = list.map((n, id) => ({id, original: n}));
			const ids = new Map(list.map((n, i) => [n, i]));
			const links = list.slice(1).map(n => ({source: ids.get(n.parent), target: ids.get(n), value: n.data.count, original: n}));
			const height = Math.max(H, (root.children || []).reduce((n, child) => n + Math.max(1, (child.children || []).length), 0) * 9 + 40);
			const graph = d3.sankey().nodeId(d => d.id).nodeWidth(14).nodePadding(4).nodeSort(null).extent([[15, 15], [W - 170, height - 15]])({nodes, links});
			const svg = this.svg(height);
			graph.links.forEach(link => {
				const mark = svg.append('path').attr('d', d3.sankeyLinkHorizontal()(link)).attr('fill', 'none').attr('stroke', this.color(link.original)).attr('stroke-opacity', 0.28).attr('stroke-width', Math.max(1, link.width));
				this.mark(mark.attr('class', 'sd-mark'), link.original);
			});
			graph.nodes.forEach(n => {
				this.mark(svg.append('rect').attr('x', n.x0).attr('y', n.y0).attr('width', n.x1 - n.x0).attr('height', Math.max(1, n.y1 - n.y0)).attr('fill', this.color(n.original)).attr('class', 'sd-mark'), n.original);
				if (n.y1 - n.y0 >= 10) this.label(svg, n.x1 + 4, (n.y0 + n.y1) / 2 + 4, this.short(n.original.data.label, 20) + ' · ' + n.original.data.count);
			});
			this.footer.append(document.createTextNode(' ' + __('Flow shows two grouping levels; explore a group to see deeper levels.')));
		}
		matrix(root) {
			const rows = root.children || [];
			if (!rows.length) { this.stage.text(__('No subgroups to display.')); return; }
			// Folded tails from different parents are not the same category.
			const cols = new Map();
			rows.forEach((row, ri) => (row.children || []).forEach(c => {
				const key = (c.data.folded_groups || c.data.folded_records) ? 'fold:' + ri : (c.data.target || c.data.record) ? JSON.stringify(['record', c.data.target_doctype || this.data.doctype, c.data.name]) : JSON.stringify([c.data.field, Object.prototype.hasOwnProperty.call(c.data, 'key') ? c.data.key : c.data.label]);
				if (!cols.has(key)) cols.set(key, { key, label: c.data.label, index: cols.size });
				c.matrixColumn = cols.get(key).index;
			}));
			if (!cols.size) { this.stage.text(__('Explore a different group to see a matrix.')); return; }
			const cell = 44, left = 170, top = 150;
			const width = Math.max(W, left + cols.size * cell + 40), height = Math.max(H, top + rows.length * 30 + 30);
			const svg = this.svg(height, width);
			[...cols.values()].forEach(c => svg.append('text').attr('class', 'sd-label').attr('transform', `translate(${left + c.index * cell + 22},${top - 8}) rotate(-90)`).text(this.short(c.label, 20)));
			const max = d3.max(rows.flatMap(r => (r.children || []).map(c => c.data.count))) || 1;
			rows.forEach((row, ri) => {
				this.label(svg, left - 8, top + ri * 30 + 19, this.short(row.data.label, 23), {anchor: 'end'});
				(row.children || []).forEach(n => {
					const x = left + n.matrixColumn * cell, y = top + ri * 30;
					this.mark(svg.append('rect').attr('x', x + 1).attr('y', y + 1).attr('width', cell - 2).attr('height', 28).attr('fill', this.color(row)).attr('fill-opacity', 0.2 + 0.75 * n.data.count / max).attr('class', 'sd-mark'), n);
					this.label(svg, x + cell / 2, y + 19, n.data.count, {anchor: 'middle'});
				});
			});
			this.footer.append(document.createTextNode(' ' + __('Matrix shows two grouping levels; explore a group to see deeper levels.')));
		}
		discs(root) {
			d3.pack().size([W, H]).padding(3)(root);
			const svg = this.svg();
			root.descendants().slice(1).forEach(n => {
				this.mark(svg.append('circle').attr('cx', n.x).attr('cy', n.y).attr('r', Math.max(0, n.r)).attr('fill', this.color(n)).attr('fill-opacity', n.children ? 0.23 : 0.6).attr('stroke', this.color(n)).attr('class', 'sd-mark'), n);
				if (n.r > 32) this.label(svg, n.x, n.y + (n.children ? -n.r + 17 : 4), this.short(n.data.label, Math.max(4, Math.floor(n.r / 4))) + ' · ' + n.data.count, {anchor: 'middle'});
			});
		}
		tree(root) {
			const visible = d3.hierarchy(this.focus, d => this.expanded.has(d) ? this.children(d) : null);
			const layout = d3.tree().nodeSize([32, 230])(visible);
			const all = layout.descendants(), min = d3.min(all, n => n.x), max = d3.max(all, n => n.x);
			const height = Math.max(H, max - min + 80), width = Math.max(W, (d3.max(all, n => n.depth) + 1) * 230 + 30);
			const svg = this.svg(height, width), g = svg.append('g').attr('transform', `translate(20,${30 - min})`);
			g.selectAll('path').data(layout.links()).enter().append('path').attr('d', link => { const x1 = link.source.y + 195, x2 = link.target.y, mid = (x1 + x2) / 2; return `M${x1},${link.source.x}C${mid},${link.source.x} ${mid},${link.target.x} ${x2},${link.target.x}`; }).attr('fill', 'none').attr('stroke', '#b7c6c3');
			all.forEach(n => {
				const item = g.append('g').attr('transform', `translate(${n.y},${n.x - 12})`);
				this.mark(item.append('rect').attr('width', 195).attr('height', 24).attr('rx', 4).attr('fill', n.depth ? this.color(n) : '#243c39').attr('fill-opacity', 0.18).attr('stroke', '#71918a').attr('class', 'sd-mark'), n);
				const kids = this.children(n.data).length;
				const hidden = (n.data.children || []).length && (!kids || !this.expanded.has(n.data));
				this.label(item, 6, 16, this.short(n.data.label, 20) + ' · ' + n.data.count + (hidden ? '  ▸ ' + (n.data.group_count || n.data.record_count || kids) : ''));
				if (kids) {
					const toggle = item.append('text').attr('x', 177).attr('y', 16).attr('class', 'sd-toggle').attr('tabindex', 0).attr('role', 'button').attr('aria-label', this.expanded.has(n.data) ? __('Collapse branch') : __('Expand branch')).text(this.expanded.has(n.data) ? '−' : '+');
					const change = event => { event.stopPropagation(); if (this.expanded.has(n.data)) this.expanded.delete(n.data); else this.expanded.add(n.data); this.render(); };
					toggle.on('click', change).on('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); change(event); } });
				}
			});
		}
		find(value) {
			const term = String(value || '').trim().toLocaleLowerCase();
			if (!term) return;
			const stack = [{node: this.root, parents: []}];
			while (stack.length) {
				const {node, parents} = stack.pop();
				if (node !== this.root && String(node.label).toLocaleLowerCase().includes(term)) {
					this.path = parents; this.focus = parents[parents.length - 1];
					if (node.record || node.folded_records) { this.showRecords = true; this.recordInput.prop('checked', true); }
					this.render(); this.select(node); return;
				}
				const children = node.children || [];
				for (let i = children.length - 1; i >= 0; i--) stack.push({node: children[i], parents: [...parents, node]});
			}
			this.footer.text(__('No matching group or record in the loaded structure.'));
		}
		download(name, content, type) {
			const url = URL.createObjectURL(new Blob([content], {type}));
			const link = document.createElement('a'); link.href = url; link.download = name; link.click();
			setTimeout(() => URL.revokeObjectURL(url), 1000);
		}
		exportSvg() {
			const svg = this.stage.find('svg')[0];
			if (svg) this.download('siraj-structure.svg', new XMLSerializer().serializeToString(svg), 'image/svg+xml');
		}
		exportCsv() {
			// Prefix spreadsheet formula characters; quote all cells including labels.
			const csv = value => {
				let s = String(value == null ? '' : value);
				if (/^[\s]*[=+@-]/.test(s)) s = "'" + s;
				return '"' + s.replace(/"/g, '""') + '"';
			};
			const lines = [[__('Group'), __('Records'), __('Groups'), __('Folded groups'), __('Folded records')]];
			const walk = (node, path) => {
				const fullPath = [...path, node.label];
				lines.push([fullPath.join(' / '), node.count, node.group_count || 0, node.folded_groups || 0, node.folded_records || 0]);
				this.children(node).forEach(child => walk(child, fullPath));
			};
			walk(this.focus, []);
			this.download('siraj-structure.csv', '\ufeff' + lines.map(row => row.map(csv).join(',')).join('\r\n'), 'text/csv;charset=utf-8');
		}
		renderTable() {
			this.table.empty().prop('hidden', !this.tableVisible);
			if (!this.tableVisible) return;
			const table = $('<table class="table table-bordered table-sm"></table>').appendTo(this.table);
			const head = $('<thead><tr></tr></thead>').appendTo(table).find('tr');
			[__('Group'), __('Records'), __('Groups'), __('Folded groups')].forEach(label => $('<th scope="col"></th>').text(label).appendTo(head));
			const body = $('<tbody></tbody>').appendTo(table);
			const walk = (node, depth) => {
				const row = $('<tr></tr>').appendTo(body);
				const cell = $('<td></td>').css('padding-inline-start', (depth * 18 + 8) + 'px').appendTo(row);
				this.button(node.label, () => this.select(node), cell).addClass('sd-table-link');
				[node.count, node.group_count || 0, node.folded_groups || 0].forEach(value => $('<td></td>').text(value).appendTo(row));
				this.children(node).forEach(child => walk(child, depth + 1));
			};
			walk(this.focus, 0);
		}
	}
	window.SirajStructureDeck = StructureDeck;
})();
