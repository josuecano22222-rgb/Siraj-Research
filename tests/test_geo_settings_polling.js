// Unit test for C-04 (HD-2): geo_settings.js polling of bootstrap_running / bootstrap_last_status.
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const jsPath = path.join(__dirname, '..', 'siraj_research', 'public', 'js', 'geo_settings.js');
const source = fs.readFileSync(jsPath, 'utf8');

let handlers = null;
const scheduledTimers = [];
const clearedTimers = [];
const alerts = [];
const indicators = [];
const xcalls = [];

function makeWrapper() {
	const state = { visible: true, classes: new Set(), attrs: {} };
	return {
		state,
		toggle(v) { state.visible = !!v; return this; },
		toggleClass(cls, on) { if (on) state.classes.add(cls); else state.classes.delete(cls); return this; },
		attr(k, v) { state.attrs[k] = v; return this; },
	};
}

const sandbox = {
	__: (s) => s,
	setTimeout: (fn, ms) => {
		const id = scheduledTimers.length + 1;
		scheduledTimers.push({ id, fn, ms });
		return id;
	},
	clearTimeout: (id) => { clearedTimers.push(id); },
	frappe: {
		ui: {
			form: {
				on(doctype, obj) {
					if (doctype === 'Geo Settings') handlers = obj;
				},
			},
		},
		confirm: (_msg, yes) => yes(),
		show_alert: (a) => alerts.push(a),
		msgprint: (m) => alerts.push(m),
		xcall: (method, args) => {
			xcalls.push({ method, args });
			if (method === 'siraj_research.offline_bootstrap.run_online_setup') {
				return Promise.resolve({ queued: true, job_id: 'siraj_offline_bootstrap', max_zoom: 11 });
			}
			return Promise.resolve({});
		},
		db: {
			get_doc: null,
		},
	},
};

vm.runInNewContext(source, sandbox, { filename: 'geo_settings.js' });
assert(handlers && typeof handlers.refresh === 'function', 'Geo Settings form handlers registered');

(async () => {
	const pollSnapshots = [
		{ bootstrap_running: 1, bootstrap_last_status: 'running', bootstrap_stop_requested: 0 },
		{ bootstrap_running: 0, bootstrap_last_status: 'complete', bootstrap_stop_requested: 0 },
	];
	let pollIdx = 0;
	sandbox.frappe.db.get_doc = async () => pollSnapshots[Math.min(pollIdx++, pollSnapshots.length - 1)];

	const frm = {
		doc: {
			active_boundary_dataset: 'ISO-TEST-BND',
			online_setup_enabled: 1,
			bootstrap_running: 0,
			bootstrap_last_status: '',
			bootstrap_stop_requested: 0,
		},
		fields_dict: {
			stop_bootstrap: { $wrapper: makeWrapper() },
			run_online_setup: { $wrapper: makeWrapper() },
			online_setup_enabled: { $wrapper: makeWrapper() },
		},
		page: {
			set_indicator(label, color) { indicators.push({ label, color }); },
		},
		save: () => Promise.resolve(),
		reload_doc() {
			const snap = pollSnapshots[Math.min(pollIdx, pollSnapshots.length - 1)];
			Object.assign(this.doc, snap);
			handlers.refresh(this);
			return Promise.resolve();
		},
		set_value(k, v) { this.doc[k] = v; },
		refresh_fields() {},
		trigger(ev) { if (handlers[ev]) handlers[ev](this); },
	};

	// Trigger Run Online Setup -> queues background job and starts polling.
	handlers.run_online_setup(frm);
	await new Promise((r) => setImmediate(r));
	await new Promise((r) => setImmediate(r));

	assert.strictEqual(xcalls[0].method, 'siraj_research.offline_bootstrap.run_online_setup');
	assert(scheduledTimers.length >= 1, 'polling timer scheduled after queueing run_online_setup');

	// Tick 1: still running (bootstrap_running = 1, bootstrap_last_status = 'running') -> schedules next poll.
	const firstTimer = scheduledTimers[scheduledTimers.length - 1];
	await firstTimer.fn();
	assert.strictEqual(frm.doc.bootstrap_running, 1);
	assert.strictEqual(frm.doc.bootstrap_last_status, 'running');
	assert.strictEqual(
		frm.fields_dict.stop_bootstrap.$wrapper.state.visible,
		true,
		'stop_bootstrap button is visible while bootstrap_running is truthy'
	);
	const countAfterFirstTick = scheduledTimers.length;
	assert(countAfterFirstTick >= 2, 'second poll scheduled while bootstrap_running == 1');

	// Tick 2: finished (bootstrap_running = 0, bootstrap_last_status = 'complete') -> stops polling.
	const secondTimer = scheduledTimers[scheduledTimers.length - 1];
	await secondTimer.fn();
	assert.strictEqual(frm.doc.bootstrap_running, 0);
	assert.strictEqual(frm.doc.bootstrap_last_status, 'complete');
	assert.strictEqual(
		scheduledTimers.length,
		countAfterFirstTick,
		'polling stops once bootstrap_running becomes 0'
	);
	assert(
		indicators.some((i) => i.label === 'complete' && i.color === 'green'),
		'indicator reflects final bootstrap_last_status'
	);

	console.log('geo_settings.js polling: queued start, running poll, stop button visibility, and terminal completion verified.');
})().catch((err) => {
	console.error(err);
	process.exit(1);
});
