/* Runtime guard for the universal Location section.
 *
 * The shipped DocTypes are normalised in their JSON metadata, but Custom
 * Fields and site-specific DocTypes can scatter the same fieldnames again.
 * This module performs a defensive, idempotent DOM relocation on form
 * refresh: every SIRAJ coordinate/map/hierarchy control is gathered into one
 * section labelled "Location" before the map modules mount.
 *
 * It never removes or edits field values and it never touches unrelated
 * controls. If the JSON layout is already correct, it does nothing.
 */
(() => {
	'use strict';

	const FIELDS = [
		'latitude', 'longitude', 'geo_point',
		'country', 'governorate', 'district',
		'municipality', 'village', 'community',
		'place_name', 'location',
	];
	const SECTION_LABEL = 'Location';
	const t = s => (typeof __ === 'function' ? __(s) : s);

	function controlsFor(frm) {
		const found = [];
		for (const name of FIELDS) {
			const control = frm.fields_dict && frm.fields_dict[name];
			if (!control || !control.$wrapper || !control.$wrapper.length) continue;
			const $section = control.$wrapper.closest('.form-section');
			if (!$section.length) continue;
			found.push({ name, control, $section });
		}
		return found;
	}

	function sectionLabel($section) {
		return ($section.find('.section-head').first().text() || '').trim();
	}

	function findSection($scope, $reference) {
		let $found = $();
		$scope.find('.form-section').each((_i, element) => {
			const $candidate = $(element);
			if (sectionLabel($candidate) === t(SECTION_LABEL)) {
				$found = $found.add($candidate);
			}
		});
		return $found.first();
	}

	function makeSection($before) {
		const $section = $(
			'<div class="form-section siraj-location-section" data-siraj-location-section="1">'
			+ '<div class="section-head"><span class="section-title"></span></div>'
			+ '<div class="section-body"><div class="row"></div></div>'
			+ '</div>'
		);
		$section.find('.section-title').text(t(SECTION_LABEL));
		$before.before($section);
		return $section;
	}

	function relocate(frm) {
		try {
			const found = controlsFor(frm);
			if (!found.length) return;
			const $scope = found[0].$section.closest('.form-layout, .std-form-layout, .form-page');
			if (!$scope.length) return;
			let $section = findSection($scope, found[0].$section);
			if (!$section.length) $section = makeSection(found[0].$section);

			const alreadyGrouped = found.every(item => item.$section[0] === $section[0]);
			if (alreadyGrouped && sectionLabel($section) === t(SECTION_LABEL)) {
				$section.attr('data-siraj-location-arranged', '1');
				return;
			}

			const $row = $section.find('.section-body .row').first();
			for (const item of found) {
				const $control = item.control.$wrapper.closest('.frappe-control').addBack().last();
				$row.append($control);
			}
			$section.attr('data-siraj-location-arranged', '1');
		} catch (err) {
			// Layout hardening must never prevent a form from loading.
			try { console.warn('[SIRAJ] Location section guard failed:', err && err.message); } catch (_) {}
		}
	}

	window.SirajLocationLayout = { FIELDS, SECTION_LABEL, relocate };

	$(document).on('form-refresh.sirajLocation', (_event, frm) => {
		if (frm && frm.doctype) relocate(frm);
	});
})();
