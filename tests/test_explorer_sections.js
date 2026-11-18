// Integration check for the remaining Explorer panel tabs (overview, fields,
// evidence, endpoints) with the presentation engine wired in. Run with node.
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');
const jquery = require('jquery');

const root = path.resolve(__dirname, '..') + '/';
const dom = new JSDOM('<!doctype html><html lang="en"><body><div id="host"></div></body></html>', {
	url: 'http://site.test/app/siraj-explorer',
	runScripts: 'dangerously',
});
const w = dom.window;
const $ = jquery(w);
w.$ = $;
w.requestAnimationFrame = (fn) => setTimeout(fn, 0);
w.fetch = async () => ({ok: false, json: async () => ({})});
w.console = {error: (...a) => console.log('PAGEERR', ...a), warn: () => {}, info: () => {}};

const dictionary = {
	'Relationship map': 'خريطة العلاقات',
	'Details': 'التفاصيل',
	'Evidence': 'الأدلة',
	'Endpoints': 'الأطراف',
	'Overview': 'نظرة عامة',
	'Relationship details': 'تفاصيل العلاقة',
	'Relationship type': 'نوع العلاقة',
	'Status': 'الحالة',
	'Verified': 'موثّق',
	'Member': 'عضو',
	'Support': 'الدعم',
	'supports': 'يدعم',
	'Subject': 'الفاعل',
	'Object': 'المفعول به',
	'Fields': 'الحقول',
	'Connections': 'الصلات',
	'Location': 'الموقع',
	'Activity': 'النشاط',
	'Precision': 'الدقة',
	'Method': 'الطريقة',
	'centroid': 'مركز',
	'map_pick': 'تحديد على الخريطة',
	'Nationality': 'الجنسية',
	'Relationships': 'العلاقات',
};
w.__ = (text, args) => {
	let result = dictionary[text] || text;
	if (args) result = result.replace(/\{(\d+)\}/g, (match, i) => args[i] == null ? match : String(args[i]));
	return result;
};

class Layer {
	constructor() { this.items = []; this.events = {}; this.options = {}; }
	addTo() { return this; }
	addLayer(x) { this.items.push(x); return this; }
	clearLayers() { this.items = []; }
	on(n, fn) { this.events[n] = fn; return this; }
	bindTooltip() { return this; }
	bringToBack() { return this; }
	getChildCount() { return 1; }
	eachLayer(fn) { this.items.forEach(fn); }
	getLayers() { return this.items; }
}
class FakeMap {
	constructor() { this.items = []; this.events = {}; this.attributionControl = {addAttribution() {}}; }
	setView() { return this; }
	getZoom() { return 4; }
	setZoom() { return this; }
	setMinZoom() { return this; }
	setMaxZoom() { return this; }
	getSize() { return {x: 600, y: 400}; }
	getCenter() { return [0, 0]; }
	getBounds() { return {isValid: () => false}; }
	addLayer(x) { this.items.push(x); return this; }
	removeLayer() {}
	remove() {}
	panTo() {}
	panInside() {}
	flyTo() {}
	invalidateSize() {}
	on(n, fn) { this.events[n] = fn; return this; }
	fitBounds() {}
	distance() { return 1000; }
}
w.L = {
	map: () => new FakeMap(),
	control: {
		scale: () => new Layer(), zoom: () => new Layer(), attribution: () => new Layer(),
		sirajToolbar: () => ({
			_buttons: new global.Map(), addTo() { return this; }, status() {},
			group() { return {add() { return this; }}; }, separator() {}, setActive() {}, toggle() { return true; }, _closeAll() {},
			find() { return $(); },
		}),
	},
	geoJSON: () => new Layer(),
	markerClusterGroup: () => new Layer(),
	featureGroup: () => new Layer(),
	marker: () => new Layer(),
	circle: () => new Layer(),
	polyline: () => new Layer(),
	polygon: () => new Layer(),
	tileLayer: () => new Layer(),
	divIcon: (x) => x,
	DomEvent: {on() {}, off() {}},
	latLngBounds: () => ({pad() { return this; }}),
};
class DataSet {
	constructor() { this.items = new Map(); }
	add(xs) { (Array.isArray(xs) ? xs : [xs]).forEach((x) => this.items.set(x.id, x)); }
	get(id) { return this.items.get(id); }
	clear() { this.items.clear(); }
}
let lastNetwork;
class Network {
	constructor(el, data) { this.events = {}; this.data = data; lastNetwork = this; }
	on(name, fn) { this.events[name] = fn; }
	selectNodes() {}
	focus() {}
	setOptions() {}
	fit() {}
	stabilize() {}
	destroy() {}
}
w.vis = {DataSet, Network};
class RelLayer {
	constructor() { this.layer = new Layer(); this.events = {}; }
	on() { return this; }
	setEdges() {}
	registerType() {}
	redraw() {}
}
class MeasureTool {
	activate() {}
	deactivate() {}
	clear() {}
}
w.SirajMapKit = {RelLayer, MeasureTool};
w.SirajMapAdvanced = {attach: () => null};
w.sirajIcons = {pin: () => '', svg: () => '', types: {}};
w.SirajBasemap = {attach: () => ({
	setOfflineLayer() {}, setStandardLayer() {}, toolbarGroup() { return {add() { return this; }}; },
})};

const nodes = [
	{doctype: 'Person', name: 'P1', label: 'Ada', latitude: 10, longitude: 20},
	{doctype: 'Institution', name: 'I1', label: 'Institute', latitude: 11, longitude: 21},
];
const edge = {
	name: 'R1', type: 'Member', direction: 'Directed', is_current: 1,
	source: ['Person', 'P1'], target: ['Institution', 'I1'], evidence_count: 1,
};
const profile = {
	presentation: {version: 2, language: 'en'},
	header: {status: 'Verified', direction: 'Directed', is_current: true, modified: '2026-01-01', owner: 'admin'},
	sections: [{
		id: 'relationship', heading: 'Relationship details', heading_source: 'Relationship details',
		fields: [{
			fieldname: 'relationship_type', label: 'Relationship type', label_source: 'Relationship type',
			i18n_key: 'Relationship type', fieldtype: 'Select', value: 'Member', value_source: 'Member',
			value_kind: 'enum', translatable_value: true,
		}],
	}],
	children: {
		evidence: {
			id: 'evidence', fieldname: 'evidence', label: 'Evidence', label_source: 'Evidence',
			section: 'evidence', total: 1,
			columns: [{fieldname: 'support_type', label: 'Support', label_source: 'Support'}],
			rows: [{support_type: {
				fieldname: 'support_type', label: 'Support', label_source: 'Support',
				value: 'supports', value_source: 'supports', value_kind: 'enum', translatable_value: true,
			}}],
		},
	},
	endpoints: {
		subject: {doctype: 'Person', name: 'P1', title: 'Ada', readable: true},
		object: {doctype: 'Institution', name: 'I1', title: 'Institute', readable: true},
	},
	counters: {evidence: 1, external_identifiers: 0},
	permissions: {can_write: true, can_create: true},
};
w.frappe = {
	pages: {'siraj-explorer': {}},
	ui: {make_app_page: () => ({main: $('#host')})},
	require: async () => {},
	set_route() {},
	show_alert() {},
	call: async ({method, args = {}}) => {
		if (method.endsWith('geographic_data')) return {message: {points: nodes, edges: [], truncated: []}};
		if (method.endsWith('relationship_data')) return {message: {nodes, edges: [edge], truncated: []}};
		if (method.endsWith('get_relationship_profile')) return {message: profile};
		if (method.endsWith('get_entity_network')) return {message: {nodes: [], edges: [], unmapped: [], truncated: false, types: {}}};
		if (method.endsWith('get_entity_profile')) return {message: {
			presentation: {version: 2, language: 'en'},
			header: {status: 'Verified', modified: '2026-01-01', owner: 'admin'},
			sections: [{
				id: 'identity', heading: 'Identity', heading_source: 'Identity',
				fields: [{fieldname: 'display_name', label: 'Display name', label_source: 'Display name',
					fieldtype: 'Data', value: 'Ada', value_source: 'Ada', value_kind: 'text'}],
			}],
			children: {},
			connections: {
				relationships: [{counterpart_title: 'Institute', counterpart_doctype: 'Institution',
					counterpart_name: 'I1', relationship_type: 'Member', direction_relative: 'outbound'}],
				outbound_links: [{field: 'nationality', label: 'Nationality', doctype: 'Country',
					name: 'IQ', title: 'Iraq', restricted: false}],
				inbound_links: [],
			},
			location: {latitude: 10, longitude: 20, precision: 'centroid', method: 'map_pick'},
			activity: {attachments: [
				{file_name: 'safe.txt', file_url: 'https://example.org/safe.txt'},
				{file_name: 'unsafe.txt', file_url: 'javascript:alert(1)'},
			], comments: [], versions: []},
			permissions: {can_write: true, can_create: true},
			network_summary: {relationship_count: 1, outbound_count: 1, inbound_count: 0},
		}};
		return {message: {}};
	},
};

w.eval(fs.readFileSync(root + 'siraj_research/public/js/siraj-map/siraj-filters.js', 'utf8'));
w.eval(fs.readFileSync(root + 'siraj_research/public/js/siraj-profile-fields.js', 'utf8'));
w.eval(fs.readFileSync(root + 'siraj_research/siraj_research/page/siraj_explorer/siraj_explorer.js', 'utf8'));
const wait = () => new Promise((resolve) => setTimeout(resolve, 40));
const tab = (label) => $('.sx-panel-tabs button').filter((i, node) => $(node).text().indexOf(label) !== -1).first();

(async () => {
	w.frappe.pages['siraj-explorer'].on_page_load(w.document.getElementById('host'));
	await wait();
	$('button').filter((i, node) => $(node).text() === 'خريطة العلاقات').trigger('click');
	await wait();
	lastNetwork.events.selectNode({nodes: [JSON.stringify(['Person', 'P1'])]});
	await wait();
	assert($('.sx-edge-link').length, 'edge link rendered in the relationship panel');
	$('.sx-edge-link').first().trigger('click');
	await wait();

	// Edge header + Overview: relationship type and workflow state are translated.
	assert.strictEqual($('.sx-panel-head h4').text(), 'عضو', 'relationship type translated in heading');
	assert.strictEqual($('.sx-panel-head h4').attr('title'), 'Member', 'source value kept in title');
	const overview = $('[data-tab-pane="overview"]');
	assert(overview.text().includes('موثّق'), 'workflow state translated');
	assert(overview.find('dd[dir="auto"]').length > 0, 'meta values are direction-aware');

	// Fields tab is mounted by the presentation engine.
	tab('التفاصيل').trigger('click');
	await wait();
	const fields = $('[data-tab-pane="fields"]');
	assert(fields.find('.sx-profile-fields').length, 'engine mounted the relationship fields tab');
	assert(fields.text().includes('نوع العلاقة'), 'field label translated via __()');
	assert(fields.text().includes('عضو'), 'enum value translated');
	if (fields.text().includes('[object Object]')) console.log('FIELDS HTML:', fields.html().slice(0, 1200));
	assert(!fields.text().includes('[object Object]'), 'no stringified objects in fields tab');

	// Evidence tab uses the table-only mode.
	tab('الأدلة').trigger('click');
	await wait();
	const evidence = $('[data-tab-pane="evidence"]');
	assert(evidence.find('[data-sx-table="evidence"]').length, 'evidence table mounted');
	assert(evidence.find('th').text().includes('الدعم'), 'table header translated');
	assert(evidence.text().includes('يدعم'), 'enum cell translated');

	// Endpoints tab remains intact and labels are translated.
	tab('الأطراف').trigger('click');
	await wait();
	const endpoints = $('[data-tab-pane="endpoints"]');
	assert(endpoints.text().includes('الفاعل') && endpoints.text().includes('المفعول به'));
	assert(endpoints.text().includes('Ada') && endpoints.text().includes('Institute'));

	// Entity panel: the same conventions apply to the remaining tabs.
	$('button').filter((i, node) => $(node).text() === 'Geographic map').trigger('click');
	await new Promise((resolve) => setTimeout(resolve, 3000));
	$('.sx-record-item').first().trigger('click');
	await wait();
	assert($('[data-tab-pane]').length, 'entity detail panel opened');
	assert($('[data-tab-pane="overview"]').text().includes('موثّق'), 'entity status translated');
	tab('الصلات').trigger('click');
	await wait();
	const connections = $('[data-tab-pane="connections"]');
	assert(connections.text().includes('عضو'), 'relationship type translated in connections');
	assert(connections.text().includes('الجنسية'), 'outbound DocField label translated');
	tab('الموقع').trigger('click');
	await wait();
	const location = $('[data-tab-pane="location"]');
	assert(location.text().includes('مركز') && location.text().includes('تحديد على الخريطة'), 'controlled location values translated');
	assert(location.find('.sx-i18n-source').length >= 2, 'source options retained under translations');
	tab('النشاط').trigger('click');
	await wait();
	const activity = $('[data-tab-pane="activity"]');
	assert.strictEqual(activity.find('a[href^="javascript:"]').length, 0, 'unsafe attachment URL is not linked');
	assert.strictEqual(activity.find('a[href="https://example.org/safe.txt"]').length, 1, 'safe attachment URL is linked');
	assert(activity.text().includes('unsafe.txt'), 'unsafe attachment remains visible as text');

	console.log('Explorer sections: relationship + entity tabs verified with translations and safe links');
})().catch((error) => {
	console.error(error);
	process.exitCode = 1;
});
