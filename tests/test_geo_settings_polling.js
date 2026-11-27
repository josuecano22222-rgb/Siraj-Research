// Unit test for C-04 & G3: geo_settings.js polling lifecycle, terminal alerts, form-current guard, and stale-running handling.
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
let nowMs = 100000;

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
	Date: { now: () => nowMs },
	cur_frm: null,
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

function makeForm(overrides = {}) {
	return {
		doctype: 'Geo Settings',
		doc: {
			active_boundary_dataset: 'ISO-TEST-BND',
			online_setup_enabled: 1,
			bootstrap_running: 0,
			bootstrap_last_status: '',
			bootstrap_stop_requested: 0,
			...overrides,
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
			handlers.refresh(this);
			return Promise.resolve();
		},
		set_value(k, v) { this.doc[k] = v; },
		refresh_fields() {},
		trigger(ev) { if (handlers[ev]) handlers[ev](this); },
	};
}

(async () => {
	// 1. Happy path: queue -> running -> complete shows green completion alert and stops polling.
	const pollSnapshots = [
		{ bootstrap_running: 1, bootstrap_last_status: 'running', bootstrap_stop_requested: 0 },
		{ bootstrap_running: 0, bootstrap_last_status: 'complete', bootstrap_stop_requested: 0 },
	];
	let pollIdx = 0;
	sandbox.frappe.db.get_doc = async () => pollSnapshots[Math.min(pollIdx++, pollSnapshots.length - 1)];

	const frm = makeForm();
	sandbox.cur_frm = frm;
	handlers.run_online_setup(frm);
	await new Promise((r) => setImmediate(r));
	await new Promise((r) => setImmediate(r));

	assert.strictEqual(xcalls[0].method, 'siraj_research.offline_bootstrap.run_online_setup');
	assert(scheduledTimers.length >= 1, 'polling timer scheduled after queueing run_online_setup');

	await scheduledTimers[scheduledTimers.length - 1].fn();
	assert.strictEqual(frm.doc.bootstrap_running, 1);
	assert.strictEqual(frm.fields_dict.stop_bootstrap.$wrapper.state.visible, true);

	const alertsBeforeComplete = alerts.length;
	const timersBeforeComplete = scheduledTimers.length;
	await scheduledTimers[scheduledTimers.length - 1].fn();
	assert.strictEqual(frm.doc.bootstrap_running, 0);
	assert.strictEqual(frm.doc.bootstrap_last_status, 'complete');
	assert.strictEqual(scheduledTimers.length, timersBeforeComplete, 'polling stops once bootstrap_running becomes 0');
	const completeAlerts = alerts.slice(alertsBeforeComplete);
	assert(
		completeAlerts.some((a) => a.indicator === 'green' && /complete/i.test(a.message)),
		'completion alert shown when bootstrap finishes cleanly'
	);

	// 2. Failure transition: running -> failed shows red failure alert and red indicator.
	const frmFail = makeForm({ bootstrap_running: 1, bootstrap_last_status: 'running' });
	sandbox.cur_frm = frmFail;
	sandbox.frappe.db.get_doc = async () => ({
		bootstrap_running: 0,
		bootstrap_last_status: 'failed',
		bootstrap_stop_requested: 0,
	});
	handlers.refresh(frmFail);
	const alertsBeforeFail = alerts.length;
	await scheduledTimers[scheduledTimers.length - 1].fn();
	const failAlerts = alerts.slice(alertsBeforeFail);
	assert(
		failAlerts.some((a) => a.indicator === 'red' && /failed/i.test(a.message)),
		'failure alert shown when bootstrap terminates with failed status'
	);
	assert(
		indicators.some((i) => i.label === 'failed' && i.color === 'red'),
		'indicator is red on failed status'
	);

	// 3. Navigating away (cur_frm !== frm) stops polling without calling get_doc or scheduling another timer.
	const frmAway = makeForm({ bootstrap_running: 1, bootstrap_last_status: 'running' });
	sandbox.cur_frm = frmAway;
	let awayCalls = 0;
	sandbox.frappe.db.get_doc = async () => { awayCalls += 1; return { bootstrap_running: 1, bootstrap_last_status: 'running' }; };
	handlers.refresh(frmAway);
	const awayTimer = scheduledTimers[scheduledTimers.length - 1];
	const timersBeforeAway = scheduledTimers.length;
	sandbox.cur_frm = makeForm(); // User navigated to another form!
	await awayTimer.fn();
	assert.strictEqual(awayCalls, 0, 'poll does not fetch when form is no longer current');
	assert.strictEqual(scheduledTimers.length, timersBeforeAway, 'polling stops when form is no longer current');

	// 4. Stale running state exceeding maximum poll duration stops polling and shows a visible warning message.
	nowMs = 200000;
	const frmStale = makeForm({ bootstrap_running: 1, bootstrap_last_status: 'queued' });
	sandbox.cur_frm = frmStale;
	sandbox.frappe.db.get_doc = async () => ({
		bootstrap_running: 1,
		bootstrap_last_status: 'queued',
		bootstrap_stop_requested: 0,
	});
	handlers.refresh(frmStale);
	const staleTimer = scheduledTimers[scheduledTimers.length - 1];
	const alertsBeforeStale = alerts.length;
	// Advance clock past MAX_POLL_DURATION_MS (e.g., +2 hours).
	nowMs += 2 * 60 * 60 * 1000 + 5000;
	const timersBeforeStaleTick = scheduledTimers.length;
	await staleTimer.fn();
	assert.strictEqual(scheduledTimers.length, timersBeforeStaleTick, 'polling stops after max poll duration');
	const staleAlerts = alerts.slice(alertsBeforeStale);
	assert(
		staleAlerts.some((a) => /stale|timed out|still marked running/i.test(a.message)),
		'visible message shown when running state appears stale / exceeds max poll duration'
	);

	console.log('geo_settings.js polling: completion/failure alerts, form-current guard, and max-duration stale handling verified.');
})().catch((err) => {
	console.error(err);
	process.exit(1);
});
