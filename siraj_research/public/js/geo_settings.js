/* Geo Settings: cooperative stop control for the offline bootstrap. */
(() => {
	'use strict';
	const t = s => (typeof __ === 'function' ? __(s) : s);

	frappe.ui.form.on('Geo Settings', {
		refresh(frm) {
			const running = !!frm.doc.bootstrap_running;
			const status = frm.doc.bootstrap_last_status || '';
			if (running) {
				frm.page.set_indicator(t('Bootstrap running'), 'orange');
			} else if (status) {
				frm.page.set_indicator(t(status), status === 'stopped by user' ? 'red' : 'green');
			}
			const button = frm.fields_dict.stop_bootstrap;
			if (button && button.$wrapper) {
				button.$wrapper.toggle(!running && !frm.doc.bootstrap_stop_requested);
			}
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
