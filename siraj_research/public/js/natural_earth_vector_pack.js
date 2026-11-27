/* Natural Earth Vector Pack form controller — provisioning admin UI.
 *
 * Adds provisioning controls to the Natural Earth Vector Pack form:
 *   - Refresh status: re-reads the pack manifest and shows statistics.
 *   - Provision pack: runs provisioning (git clone from the canonical
 *     mirror, or copy from a local mirror directory) and compiles the
 *     offline ZIP archive.
 *   - Fill layer list: populates the optional explicit layer JSON with the
 *     full catalog for the selected scales (left empty = full catalog).
 *
 * All network calls go through frappe.call to the DocType controller and the
 * /api/method/siraj_research.api.natural_earth_vector.* endpoints.
 */
frappe.ui.form.on('Natural Earth Vector Pack', {
	refresh(frm) {
		if (frm.is_new()) return;
		const is_admin = frappe.user_roles.includes('SIRAJ Administrator') ||
			frappe.user_roles.includes('System Manager');
		if (!is_admin) return;

		frm.add_custom_button(__('Refresh status'), () => {
			frappe.call({
				method: 'siraj_research.natural_earth_vector_pack.natural_earth_vector_pack.refresh_status',
				args: { docname: frm.doc.name },
				callback(r) {
					const d = r.message || {};
					frm.reload_doc();
					frappe.msgprint(
						`<p>${__('Status')}: <b>${d.status}</b></p>` +
						`<p>${__('Packed files')}: <b>${d.file_count || 0}</b></p>` +
						`<p>${__('Available scales')}: <b>${(d.available_scales || []).join(', ') || '—'}</b></p>` +
						`<p>${__('Offline ZIP')}: <b>${d.zip_ready ? __('ready') : __('not built')}</b></p>`,
						__('Natural Earth Vector Pack'),
					);
				},
			});
		});

		frm.add_custom_button(__('Provision pack'), () => {
			const scales = [];
			if (frm.doc.scale_110m) scales.push('1:110m');
			if (frm.doc.scale_50m) scales.push('1:50m');
			if (frm.doc.scale_10m) scales.push('1:10m (≈1.1 GB)');
			if (!scales.length) {
				frappe.msgprint(__('Select at least one scale tier.'), __('Nothing to provision'));
				return;
			}
			const big = frm.doc.scale_10m && !frm.doc.scale_110m && !frm.doc.scale_50m;
			const msg = `${__('Provision the Natural Earth Vector pack')}?\n` +
				`${__('Source')}: ${frm.doc.source}\n${__('Scales')}: ${scales.join(', ')}` +
				(big ? `\n\n${__('The 1:10m tier is ~1.1 GB and will take several minutes.')}` : '');
			frappe.confirm(msg, () => {
				frappe.call({
					method: 'siraj_research.natural_earth_vector_pack.natural_earth_vector_pack.run_provision',
					args: { docname: frm.doc.name },
					callback(r) {
						const d = r.message || {};
						if (!d || !d.ok) {
							frappe.msgprint(__('Provisioning failed. See the Message field.'),
								__('Natural Earth Vector Pack'), true);
							frm.reload_doc();
							return;
						}
						frappe.msgprint(
							`<p>${__('Status')}: <b>${d.status}</b></p>` +
							`<p>${__('Packed files')}: <b>${d.file_count}</b></p>` +
							`<p>${__('Offline ZIP')}: <b>${d.zip ? __('built') : __('not built')}</b></p>`,
							__('Provisioning complete'),
						);
						frm.reload_doc();
					},
				});
			}, __('Provision Natural Earth Vector pack'));
		});

		frm.add_custom_button(__('Fill full layer list'), () => {
			frappe.call({
				method: 'siraj_research.natural_earth_vector_pack.natural_earth_vector_pack.get_catalog_layers',
				callback(r) {
					const layers = (r.message || []).map(l => l.name);
					frm.set_value('layers_json', JSON.stringify(layers, null, 2));
					frm.reload_doc();
					frappe.msgprint(__('Full catalog layer list filled (optional — empty means full catalog).'));
				},
			});
		});
	},
});
