/* Boundary Dataset form controller — upload widget + progress bar.
 *
 * This file adds a "Start import" button to the Boundary Dataset form
 * that lets an administrator upload a .zip (shapefile), .geojson or
 * .gpkg file and watch the background job's progress. All network
 * calls go through frappe.call to /api/method/siraj_research.api.boundary_import.*.
 */
frappe.ui.form.on('Boundary Dataset', {
	refresh(frm) {
		if (frm.doc.import_status === 'Running' || frm.doc.import_status === 'Queued') {
			_pollStatus(frm);
		}
		if (frm.is_new()) return;
		if (!frappe.user_roles.includes('SIRAJ Administrator') && !frappe.user_roles.includes('System Manager')) return;

		frm.add_custom_button(__('Check dependencies'), () => {
			frappe.call({
				method: 'siraj_research.api.boundary_import.dependencies',
				callback(r) {
					const d = r.message || {};
					if (d.ok) {
						frappe.msgprint(__('pyogrio / shapely / pyproj available.'));
					} else {
						frappe.msgprint(
							`<p>${__('Geospatial libraries missing:')} <code>${(d.missing||[]).join(', ')}</code></p>`
							+ `<p>${__('Install them on the bench with:')}<br><code>./env/bin/pip install pyogrio shapely pyproj</code></p>`,
							__('Dependencies needed'),
						);
					}
				},
			});
		});

		frm.add_custom_button(__('Upload & import'), () => {
			if (frm.doc.import_status === 'Running') {
				frappe.msgprint(__('Import already running.'));
				return;
			}
			// File picker — zip/geojson/gpkg/shp.
			const input = document.createElement('input');
			input.type = 'file';
			input.accept = '.zip,.geojson,.json,.gpkg,.shp';
			input.onchange = async () => {
				const file = input.files && input.files[0];
				if (!file) return;
				const is_gazetteer = await new Promise(resolve => {
					frappe.confirm(
						__('Is this a point gazetteer (settlements / places)? Click Cancel for polygon boundaries.'),
						() => resolve(true),
						() => resolve(false),
					);
				});
				const reader = new FileReader();
				reader.onload = () => {
					const b64 = reader.result.split(',')[1];
					frappe.call({
						method: 'siraj_research.api.boundary_import.upload_file',
						args: { filename: file.name, filedata: b64 },
						callback(r1) {
							if (!r1.message) return;
							frappe.call({
								method: 'siraj_research.api.boundary_import.start_import',
								args: { dataset: frm.doc.name, file_path: r1.message.path, is_gazetteer },
								callback() {
									frm.reload_doc();
									setTimeout(() => _pollStatus(frm), 1500);
								},
							});
						},
					});
				};
				reader.readAsDataURL(file);
			};
			input.click();
		});
	},
});

function _pollStatus(frm) {
	if (frm._siraj_poll) clearTimeout(frm._siraj_poll);
	frm._siraj_poll = setTimeout(async () => {
		try {
			const r = await frappe.call({ method: 'siraj_research.api.boundary_import.status', args: { dataset: frm.doc.name } });
			const s = r.message || {};
			frm.set_value('import_status', s.import_status);
			frm.set_value('import_progress', s.import_progress);
			frm.set_value('feature_count', s.feature_count);
			frm.set_value('imported_at', s.imported_at);
			frm.set_value('import_log', s.import_log);
			frm.refresh_fields();
			if (s.import_status === 'Running' || s.import_status === 'Queued') {
				_pollStatus(frm);
			}
		} catch (_) {
			_pollStatus(frm);   // network blip: retry
		}
	}, 2000);
}
