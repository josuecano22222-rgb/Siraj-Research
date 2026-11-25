/* Geo Settings: online setup gate + cooperative bootstrap stop & status polling. */
(() => {
	'use strict';
	const t = s => (typeof __ === 'function' ? __(s) : s);
	const POLL_INTERVAL_MS = 2000;

	function applyControls(frm) {
		const running = !!frm.doc.bootstrap_running;
		const status = frm.doc.bootstrap_last_status || '';
		const onlineAllowed = frm.doc.online_setup_enabled !== 0;
		if (running) {
			frm.page.set_indicator(t('Bootstrap running'), 'orange');
		} else if (status) {
			frm.page.set_indicator(t(status), status === 'stopped by user' ? 'red' : 'green');
		}
		const stopButton = frm.fields_dict.stop_bootstrap;
		if (stopButton && stopButton.$wrapper) {
			stopButton.$wrapper.toggle(running && !frm.doc.bootstrap_stop_requested);
		}
		const runButton = frm.fields_dict.run_online_setup;
		if (runButton && runButton.$wrapper) {
			runButton.$wrapper.toggle(!running);
			runButton.$wrapper.toggleClass('btn-default', !onlineAllowed);
		}
		const hint = frm.fields_dict.online_setup_enabled;
		if (hint && hint.$wrapper) {
			hint.$wrapper.attr(
				'title',
				onlineAllowed
					? t('Online setup may download wheels, tiles and packages.')
					: t('Online setup disabled: preparation will use local data only.')
			);
		}
	}

	function pollBootstrapStatus(frm) {
		if (frm._siraj_bootstrap_poll) {
			clearTimeout(frm._siraj_bootstrap_poll);
			frm._siraj_bootstrap_poll = null;
		}
		frm._siraj_bootstrap_poll = setTimeout(async () => {
			frm._siraj_bootstrap_poll = null;
			try {
				const latest = await frappe.db.get_doc('Geo Settings');
				if (latest) {
					frm.doc.bootstrap_running = latest.bootstrap_running ? 1 : 0;
					frm.doc.bootstrap_last_status = latest.bootstrap_last_status || '';
					frm.doc.bootstrap_stop_requested = latest.bootstrap_stop_requested ? 1 : 0;
					frm.refresh_fields && frm.refresh_fields([
						'bootstrap_running',
						'bootstrap_last_status',
						'bootstrap_stop_requested',
					]);
					applyControls(frm);
				}
				if (frm.doc.bootstrap_running) {
					pollBootstrapStatus(frm);
				}
			} catch (_) {
				if (frm.doc.bootstrap_running) {
					pollBootstrapStatus(frm);
				}
			}
		}, POLL_INTERVAL_MS);
	}

	frappe.ui.form.on('Geo Settings', {
		refresh(frm) {
			applyControls(frm);
			if (frm.doc.bootstrap_running) {
				pollBootstrapStatus(frm);
			} else if (frm._siraj_bootstrap_poll) {
				clearTimeout(frm._siraj_bootstrap_poll);
				frm._siraj_bootstrap_poll = null;
			}
		},

		online_setup_enabled(frm) {
			frm.trigger('refresh');
			if (!frm.doc.online_setup_enabled) {
				frappe.show_alert({
					message: t('Online setup disabled — Run Online Setup will only use local data.'),
					indicator: 'orange',
				});
			}
		},

		run_online_setup(frm) {
			const onlineAllowed = frm.doc.online_setup_enabled !== 0;
			const confirmMsg = onlineAllowed
				? t('Run the full online setup now? Wheels, tiles and packages will be downloaded while the bench has internet, then the site locks offline.')
				: t('Online setup is disabled. Run a local-only preparation (no downloads)?');
			frappe.confirm(confirmMsg, () => {
				frm.save().then(() => {
					frappe.xcall('siraj_research.offline_bootstrap.run_online_setup', {
						dataset: frm.doc.active_boundary_dataset || null,
						max_zoom: 11,
					}).then(result => {
						if (result && result.error) {
							frappe.msgprint({
								title: t('Online setup'),
								message: result.message || result.error,
								indicator: 'red',
							});
							return;
						}
						frm.doc.bootstrap_running = 1;
						frm.doc.bootstrap_last_status = 'queued';
						frm.doc.bootstrap_stop_requested = 0;
						applyControls(frm);
						frappe.show_alert({
							message: result && result.online_setup_enabled === false
								? t('Local-only preparation queued (online setup disabled).')
								: t('Online setup queued — polling bootstrap_last_status.'),
							indicator: result && result.online_setup_enabled === false ? 'orange' : 'blue',
						});
						pollBootstrapStatus(frm);
					}).catch(err => frappe.msgprint({
						title: t('Online setup failed'),
						message: err && err.message ? err.message : String(err),
						indicator: 'red',
					}));
				});
			});
		},

		stop_bootstrap(frm) {
			frappe.confirm(
				t('Stop the running offline bootstrap at the next safe point? Downloaded tiles already cached will be kept.'),
				() => {
					frappe.xcall('siraj_research.offline_bootstrap.request_stop')
						.then(() => {
							frappe.show_alert({
								message: t('Stop requested. The bootstrap will pause after the current tile batch.'),
								indicator: 'orange',
							});
							frm.reload_doc();
						})
						.catch(err => frappe.msgprint({
							title: t('Could not stop bootstrap'),
							message: err && err.message ? err.message : String(err),
							indicator: 'red',
						}));
				}
			);
		},
	});
})();
