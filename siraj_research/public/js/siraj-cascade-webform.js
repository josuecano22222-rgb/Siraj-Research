/* Cascading administrative links on Frappe **Web Forms**.
 *
 * Desk forms get this behaviour from siraj-cascade.js. Web Forms use a
 * different object (frappe.web_form, a FieldGroup), so this small adapter
 * applies the same contract:
 *
 *   - each child Link only offers records under the selected ancestors;
 *   - changing a level clears every descendant value;
 *   - levels marked inactive in the country's configuration are hidden and
 *     cleared, so a skipped level cannot hold data.
 *
 * The server (geo_lineage.validate_hierarchy_document) remains authoritative;
 * this file only improves data entry. It makes no external requests: level
 * metadata comes from the site's own whitelisted API.
 *
 * Enable it with hooks.web_include_js (already configured). No per-form code
 * is required; forms that do not contain these fields are untouched.
 */
(function () {
	"use strict";

	var FIELDS = ["country", "governorate", "district", "municipality", "village", "community"];
	var PARENT = {
		governorate: "country",
		district: "governorate",
		municipality: "district",
		village: "municipality",
		community: "village",
	};
	var configCache = {};

	function form() {
		return window.frappe && window.frappe.web_form;
	}

	function value(frm, field) {
		try {
			return frm.get_value ? frm.get_value(field) : (frm.doc || {})[field];
		} catch (e) {
			return null;
		}
	}

	function setValue(frm, field, val) {
		try {
			if (frm.set_value) frm.set_value(field, val);
		} catch (e) {
			/* read-only or absent field */
		}
	}

	function fieldObj(frm, field) {
		return (frm.fields_dict && frm.fields_dict[field]) || null;
	}

	function filtersFor(frm, field) {
		var out = {};
		FIELDS.forEach(function (f) {
			if (f === field) return;
			if (FIELDS.indexOf(f) > FIELDS.indexOf(field)) return;
			var v = value(frm, f);
			if (v) out[f] = v;
		});
		return out;
	}

	function setQuery(frm, field, filters) {
		var getter = function () {
			return { filters: filters };
		};
		try {
			if (typeof frm.set_query === "function") {
				frm.set_query(field, getter);
				return;
			}
			var f = fieldObj(frm, field);
			if (f && f.df) {
				f.df.get_query = getter;
				if (f.refresh) f.refresh();
			}
		} catch (e) {
			/* control not rendered yet */
		}
	}

	function apply(frm) {
		FIELDS.forEach(function (field) {
			if (!fieldObj(frm, field)) return;
			setQuery(frm, field, filtersFor(frm, field));
		});
	}

	function clearBelow(frm, field) {
		var start = FIELDS.indexOf(field);
		for (var i = start + 1; i < FIELDS.length; i += 1) {
			var child = FIELDS[i];
			if (!fieldObj(frm, child)) continue;
			if (value(frm, child)) setValue(frm, child, "");
		}
	}

	function hideInactive(frm, country) {
		if (!country) return;
		var apply_ = function (payload) {
			var levels = (payload && payload.levels) || [];
			levels.forEach(function (row) {
				var f = fieldObj(frm, row.field);
				if (!f) return;
				try {
					frm.set_df_property(row.field, "hidden", row.is_active ? 0 : 1);
					frm.set_df_property(row.field, "reqd", 0);
					if (!row.is_active) setValue(frm, row.field, "");
				} catch (e) {
					/* older web form builds lack set_df_property */
				}
			});
		};
		if (configCache[country]) {
			apply_(configCache[country]);
			return;
		}
		window.frappe.call({
			method: "siraj_research.geo_levels.get_level_config",
			args: { country: country },
			callback: function (r) {
				if (!r || !r.message) return;
				configCache[country] = r.message;
				apply_(r.message);
			},
		});
	}

	function attach() {
		var frm = form();
		if (!frm || !frm.fields_dict) return;
		var present = FIELDS.some(function (f) {
			return !!fieldObj(frm, f);
		});
		if (!present) return;
		apply(frm);
		FIELDS.forEach(function (field) {
			if (!fieldObj(frm, field)) return;
			frm.on(field, function () {
				clearBelow(frm, field);
				apply(frm);
				if (field === "country") hideInactive(frm, value(frm, "country"));
			});
		});
		var country = value(frm, "country");
		if (country) hideInactive(frm, country);
	}

	if (window.frappe && window.frappe.web_form) {
		attach();
	} else if (window.frappe && window.frappe.ready) {
		window.frappe.ready(function () {
			// Web Form bootstraps after DOM ready; wait one tick for fields_dict.
			window.setTimeout(attach, 0);
		});
	}
	window.SirajWebFormCascade = { attach: attach, apply: apply };
})();
