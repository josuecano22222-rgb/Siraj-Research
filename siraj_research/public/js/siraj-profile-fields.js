/*
 * SIRAJ profile presentation engine — fields & child tables.
 *
 * Renders the read-only profile payloads produced by api.entity_profile and
 * api.relationship_profile. Design goals:
 *
 *  1. Source strings and source values are NEVER lost. Every translatable
 *     piece of text carries its source in data attributes so the
 *     panel can switch language without another request and so translators
 *     can harvest strings from a rendered page.
 *  2. Values are typed. Links are buttons, URLs are anchors, booleans/enums
 *     go through __(), nested objects become readable key/value chips. No
 *     "[object Object]" ever reaches the DOM.
 *  3. RTL text uses dir=auto; the surrounding UI stays in the UI language.
 *  4. Child tables are independent, sortable, filterable components placed
 *     next to the section they belong to (accounts after Public activity,
 *     evidence after Provenance, and so on).
 *
 * The module is UMD so it can be unit-tested with jsdom/Node and is also
 * available as window.SirajProfileFields in the Frappe desk bundle.
 */
(function (root, factory) {
	const api = factory(root);
	if (typeof module === "object" && module.exports) module.exports = api;
	if (root) root.SirajProfileFields = api;
})(typeof window !== "undefined" ? window : globalThis, function (browserRoot) {
	const root = (browserRoot && browserRoot.window) || browserRoot || {};
	const $ = root.$ || root.jQuery;
	const CARET_SVG =
		'<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" ' +
		'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 6 6 6-6 6"/></svg>';
	const MODE_KEY = "siraj.profile.fields.mode.v1";

	// Mirrors profile_presentation.SECTION_BLUEPRINTS for payloads produced by
	// an older server. The server is authoritative whenever it sends v2 data.
	const GROUP_ORDER = [
		"identity", "life", "origin", "classification", "service", "public",
		"relationship", "endpoints", "location", "timing", "provenance",
		"evidence", "identifiers", "quality", "other",
	];
	const GROUP_TITLES = {
		identity: "Identity",
		life: "Life & dates",
		origin: "Origin",
		classification: "Classification",
		service: "Military service",
		public: "Public activity",
		relationship: "Relationship details",
		endpoints: "Endpoints",
		location: "Location",
		timing: "Timing",
		provenance: "Provenance & state",
		evidence: "Evidence",
		identifiers: "External identifiers",
		quality: "Quality",
		other: "Other fields",
	};
	const FIELD_GROUP = {
		naming_series: "identity", display_name: "identity", name_ar: "identity",
		name_en: "identity", name_original: "identity", name_transliteration: "identity",
		birth_date_as_stated: "life", birth_date: "life", birth_date_precision: "life",
		death_date_as_stated: "life", death_date: "life", death_date_precision: "life",
		nationality: "origin", birthplace: "origin", country: "origin",
		person_category: "classification", person_status: "classification",
		category: "classification", classification: "classification",
		current_position_as_stated: "classification", declared_affiliation: "classification",
		rank_title: "service", rank: "service", branch: "service",
		commission_date: "service", service_status: "service", military_biography: "service",
		relationship_type: "relationship", direction: "relationship", is_current: "relationship",
		description: "relationship", subject_type: "endpoints", object_type: "endpoints",
		subject: "endpoints", object: "endpoints",
		latitude: "location", longitude: "location", geo_precision: "location",
		geocoding_method: "location", geo_uncertainty_m: "location", geometry_source: "location",
		start_date_as_stated: "timing", start_date: "timing", end_date_as_stated: "timing",
		end_date: "timing", last_review_date: "timing",
		primary_source: "provenance", documentation_level: "provenance",
		authentication_level: "provenance", workflow_state: "provenance",
		researcher_notes: "provenance", status: "provenance",
		completeness_score: "quality", quality_score: "quality",
	};
	const CHILD_GROUP = {
		social_accounts: "public", leadership_assessments: "service",
		specializations: "classification", admin_boundary_geom: "location",
		evidence: "evidence", external_identifiers: "identifiers",
		unit_armament_holding: "service",
	};
	const DEMO_RE = /\[DEMO\]/gi;
	const URL_RE = /^(https?:|mailto:|tel:)/i;
	const RTL_LANGS = ["ar", "fa", "he", "ur"];

	function asJq(node) {
		if (!node) return $();
		return node.jquery ? node : $(node);
	}

	function interpolate(text, args) {
		const out = String(text == null ? "" : text);
		if (!args || !args.length) return out;
		return out.replace(/\{(\d+)\}/g, (match, index) =>
			args[index] == null ? match : String(args[index]),
		);
	}

	function translate(source, args) {
		const text = String(source == null ? "" : source);
		const fn = typeof root.__ === "function" ? root.__ : null;
		if (!fn) return interpolate(text, args);
		try {
			const result = fn(text, args);
			return result == null || result === "" ? interpolate(text, args) : String(result);
		} catch (error) {
			return interpolate(text, args);
		}
	}

	function languageOf(profile) {
		const explicit = profile && profile.presentation && profile.presentation.language;
		const frappeLang = root.frappe && root.frappe.boot && root.frappe.boot.lang;
		const htmlLang = root.document && root.document.documentElement
			? root.document.documentElement.lang || "" : "";
		return String(explicit || frappeLang || htmlLang || "en").split("-")[0].toLowerCase();
	}

	function currentMode() {
		try {
			const value = root.localStorage && root.localStorage.getItem(MODE_KEY);
			return value === "source" || value === "both" || value === "translated" ? value : "translated";
		} catch (error) {
			return "translated";
		}
	}

	function saveMode(mode) {
		try {
			if (root.localStorage) root.localStorage.setItem(MODE_KEY, mode);
		} catch (error) {
			/* private browsing: mode simply does not persist */
		}
	}

	function splitDemo(text) {
		const source = String(text == null ? "" : text);
		const demo = /\[DEMO\]/i.test(source);
		return { text: source.replace(DEMO_RE, "").replace(/\s{2,}/g, " ").trim(), demo: demo };
	}

	function safeUrl(value) {
		const text = String(value || "").trim();
		if (!URL_RE.test(text)) return null;
		try {
			const base = root.location && root.location.href ? root.location.href : "https://siraj.local/";
			const url = new URL(text, base);
			return /^(https?:|mailto:|tel:)$/.test(url.protocol) ? url.href : null;
		} catch (error) {
			return null;
		}
	}

	function inferKind(value) {
		if (value && typeof value === "object") {
			if (value.type === "link") return "link";
			if (value.type === "attach") return "attach";
			return "json";
		}
		if (typeof value === "boolean") return "boolean";
		if (typeof value === "number") return "number";
		return "text";
	}

	function normaliseField(field, sourceHeading) {
		const item = field && typeof field === "object" ? Object.assign({}, field) : { value: field };
		const value = item.value;
		const kind = item.value_kind || inferKind(value);
		const sourceValue =
			item.value_source != null
				? String(item.value_source)
				: value && typeof value === "object" && value.type === "link"
					? String(value.title || value.name || "")
					: value && typeof value === "object" && value.type === "attach"
						? String(value.url || "")
						: value == null ? "" : String(value);
		return Object.assign(
			{
				fieldname: item.fieldname || "",
				label: item.label || item.fieldname || "",
				label_source: item.label_source || item.label || item.fieldname || "",
				i18n_key: item.i18n_key || item.label || item.fieldname || "",
				fieldtype: item.fieldtype || "Data",
				source_heading: item.source_heading || sourceHeading || "",
				value: value,
				value_source: sourceValue,
				value_kind: kind,
				translatable_value: kind === "enum" && !!sourceValue,
				value_demo: splitDemo(sourceValue).demo,
				group: item.group || "",
			},
			item,
		);
	}

	/* Defensive client-side normalisation for older profile payloads. */
	function normaliseProfile(profile) {
		const data = profile || {};
		const buckets = {};
		const groups = [];
		(data.sections || []).forEach((section) => {
			const heading = section.heading || section.label || "";
			const fields = section.fields || [];
			fields.forEach((field) => {
				const normalised = normaliseField(field, heading);
				const group = normalised.group || FIELD_GROUP[normalised.fieldname] || "other";
				buckets[group] = buckets[group] || [];
				if (!buckets[group].some((existing) => existing.fieldname === normalised.fieldname)) {
					buckets[group].push(normalised);
				}
			});
		});
		GROUP_ORDER.forEach((id) => {
			const fields = buckets[id] || [];
			if (!fields.length) return;
			groups.push({
				id: id,
				heading: GROUP_TITLES[id],
				heading_source: GROUP_TITLES[id],
				i18n_key: GROUP_TITLES[id],
				fields: fields,
			});
		});
		const children = {};
		Object.keys(data.children || {}).forEach((fieldname) => {
			const table = data.children[fieldname] || {};
			const rows = table.rows || [];
			const keys = [];
			(table.column_order || []).concat(rows.reduce((all, row) => all.concat(Object.keys(row)), []))
				.forEach((key) => { if (key && keys.indexOf(key) === -1) keys.push(key); });
			const columns = keys.map((key) => {
				const first = rows.map((row) => row[key]).find((cell) => cell != null) || {};
				return {
					fieldname: key,
					label: first.label || key,
					label_source: first.label || key,
					i18n_key: first.label || key,
				};
			});
			children[fieldname] = {
				id: fieldname,
				fieldname: fieldname,
				label: table.label || fieldname,
				label_source: table.label || fieldname,
				i18n_key: table.label || fieldname,
				section: CHILD_GROUP[fieldname] || "other",
				total: table.total == null ? rows.length : table.total,
				truncated: !!table.truncated,
				columns: columns,
				rows: rows.map((row) => {
					const out = {};
					Object.keys(row).forEach((key) => { out[key] = normaliseField(row[key]); });
					return out;
				}),
			};
		});
		return { sections: groups, children: children, presentation: data.presentation || {} };
	}

	function isV2(profile) {
		return !!(
			profile && profile.presentation && profile.presentation.version >= 2 &&
			Array.isArray(profile.sections) && profile.sections.some((section) => section.id)
		);
	}

	function localisedText(source, translated, mode) {
		if (mode === "source") return { primary: source, secondary: "" };
		if (mode === "both") {
			return translated && translated !== source
				? { primary: translated, secondary: source }
				: { primary: source, secondary: "" };
		}
		return { primary: translated || source, secondary: "" };
	}

	/** Build a translated label node that keeps the source string in the DOM. */
	function labelNode(source, options) {
		const opts = options || {};
		const mode = opts.mode || "translated";
		const translated = opts.translated || translate(source);
		const text = localisedText(source, translated, mode);
		const span = $('<span class="sx-i18n-label"></span>')
			.attr({ "data-i18n-source": source, "data-i18n-key": opts.i18nKey || source, dir: "auto" })
			.text(text.primary);
		if (text.secondary) {
			span.append($('<small class="sx-i18n-source"></small>').text(text.secondary));
		}
		return span;
	}

	function demoBadge(show, source) {
		if (!show) return $();
		return $('<span class="sx-demo-badge"></span>')
			.text("DEMO")
			.attr("title", translate("Demo data") + (source ? " · " + source : ""));
	}

	function valueNode(field, options) {
		const opts = options || {};
		const mode = opts.mode || "translated";
		const kind = field.value_kind || inferKind(field.value);
		const source = String(field.value_source == null ? field.value : field.value_source);
		const parts = splitDemo(source);
		const text = parts.text;
		const holder = $('<span class="sx-profile-value" dir="auto"></span>');
		let content;

		if (kind === "link" && field.value && typeof field.value === "object") {
			const link = field.value;
			const label = String(link.title || link.name || text);
			content = $('<button type="button" class="btn btn-link btn-xs sx-profile-link"></button>')
				.text(splitDemo(label).text)
				.attr("title", label + " · " + (link.doctype || ""))
				.on("click", (event) => {
					event.preventDefault();
					if (typeof opts.onOpenLink === "function") opts.onOpenLink(link, field);
					else if (root.frappe && root.frappe.set_route) root.frappe.set_route("Form", link.doctype, link.name);
				});
		} else if (kind === "attach") {
			const url = field.value && field.value.url;
			content = safeUrl(url)
				? $("<a></a>").attr({ href: safeUrl(url), target: "_blank", rel: "noopener noreferrer" }).text(text || url)
				: $("<span></span>").text(text);
		} else if (kind === "url") {
			// Some imported records carry a markdown link skeleton ("[https://…")
			// instead of a bare URL. Strip only that leading bracket for the
			// anchor; the untouched value stays in data-source-value.
			const urlText = text.replace(/^\[/, "").trim();
			const url = safeUrl(urlText);
			content = url
				? $("<a></a>").attr({ href: url, target: "_blank", rel: "noopener noreferrer" }).text(urlText)
				: $("<span></span>").text(text);
		} else if (kind === "boolean") {
			const raw = field.value ? "Yes" : "No";
			const shown = localisedText(raw, translate(raw), mode);
			content = $("<span></span>").text(shown.primary);
			if (shown.secondary) content.append($('<small class="sx-i18n-source"></small>').text(shown.secondary));
		} else if (kind === "enum" && text) {
			const shown = localisedText(text, translate(text), mode);
			content = $("<span></span>").text(shown.primary);
			if (shown.secondary) content.append($('<small class="sx-i18n-source"></small>').text(shown.secondary));
		} else if (kind === "json" && field.value && typeof field.value === "object") {
			content = $('<span class="sx-profile-json"></span>');
			const values = Array.isArray(field.value) ? field.value : [field.value];
			values.forEach((entry) => {
				if (!entry || typeof entry !== "object") {
					content.append($("<span></span>").text(String(entry)));
					return;
				}
				Object.keys(entry).forEach((key) => {
					const value = entry[key];
					content.append(
						$('<span class="sx-profile-json-pair"></span>')
							.append($("<b></b>").text(key + ": "))
							.append($("<span></span>").text(displayValue(value))),
					);
				});
			});
		} else {
			content = $("<span></span>").text(text);
		}

		holder.append(content);
		holder.append(demoBadge(parts.demo || field.value_demo, text));
		holder.attr("data-source-value", source);
		holder.attr("data-value-kind", kind);
		if (opts.rtlLanguages && RTL_LANGS.indexOf(languageOf(opts.profile)) !== -1) {
			holder.addClass("is-rtl");
		}
		return holder;
	}

	function displayValue(value) {
		if (value == null) return "";
		if (typeof value === "string") return value;
		if (typeof value === "object") {
			try { return JSON.stringify(value); } catch (error) { return String(value); }
		}
		return String(value);
	}

	function fieldSection(container, options) {
		const opts = options || {};
		const section = $('<details class="sx-section" data-sx-section="fields:' + (opts.id || "other") + '"></details>');
		const summary = $("<summary></summary>").appendTo(section);
		summary.append($('<span class="sx-section-caret">' + CARET_SVG + "</span>"));
		summary.append($('<span class="sx-section-label"></span>').append(labelNode(opts.heading, opts)));
		if (opts.count != null) {
			summary.append($('<span class="sx-section-count"></span>').text(String(opts.count)));
		}
		const body = $('<div class="sx-section-body"></div>').appendTo(section);
		summary.on("click", (event) => {
			event.preventDefault();
			const opening = !section.attr("open");
			if (opening) section.attr("open", "open");
			else section.removeAttr("open");
			if (opts.onToggle) opts.onToggle(opts.id, opening);
		});
		if (opts.open !== false) section.attr("open", "open");
		container.append(section);
		return body;
	}

	function renderFields(body, fields, options) {
		const opts = options || {};
		const dl = $('<dl class="sx-profile-fields"></dl>').appendTo(body);
		fields.forEach((field) => {
			const row = $('<div class="sx-profile-row"></div>')
				.attr({
					"data-sx-fieldname": field.fieldname || "",
					"data-sx-filter": (field.label_source || field.label || "") + " " +
						(field.value_source || "") + " " + (field.source_heading || ""),
				})
				.appendTo(dl);
			const label = String(field.label_source || field.label || field.fieldname || "");
			const labelParts = splitDemo(label);
			const dt = $("<dt></dt>").appendTo(row);
			dt.append(labelNode(labelParts.text, Object.assign({}, opts, {
				translated: opts.mode === "source" ? labelParts.text : translate(labelParts.text),
				i18nKey: field.i18n_key || labelParts.text,
			})));
			dt.append(demoBadge(labelParts.demo || field.label_demo, labelParts.text));
			if (field.derived) {
				// Derived confidence (no recorded authentication level) —
				// distinguish it from the recorded value at a glance.
				dt.append(
					$('<span class="sx-derived-badge"></span>')
						.text(translate("(derived)"))
						.attr("title", translate("Computed from evidence rows — the record stores no recorded confidence."))
				);
			}
			const dd = $("<dd></dd>").appendTo(row);
			dd.append(valueNode(field, opts));
			const copy = $('<button type="button" class="sx-profile-copy" aria-label="' + translate("Copy value") + '"></button>')
				.text("⧉")
				.attr("title", translate("Copy value"))
				.on("click", (event) => {
					event.preventDefault();
					const raw = field.value_source || displayValue(field.value);
					if (root.navigator && root.navigator.clipboard && root.navigator.clipboard.writeText) {
						const copied = root.navigator.clipboard.writeText(raw);
						if (copied && typeof copied.catch === "function") copied.catch(() => {});
					}
					const button = $(event.currentTarget);
					button.addClass("is-copied").attr("title", translate("Copied"));
					setTimeout(() => button.removeClass("is-copied").attr("title", translate("Copy value")), 1200);
				})
				.appendTo(dd);
		});
	}

	function renderTable(container, table, options) {
		const opts = options || {};
		const rows = table.rows || [];
		const columns = table.columns || [];
		const wrap = $('<div class="sx-table-wrap sx-profile-table-wrap"></div>')
			.attr("data-sx-table", table.fieldname || table.id || "")
			.appendTo(container);
		if (!rows.length) {
			wrap.addClass("is-empty").text(translate("No rows recorded"));
			return wrap;
		}
		const htmlTable = $('<table class="table table-condensed sx-profile-table"></table>').appendTo(wrap);
		const thead = $("<thead></thead>").appendTo(htmlTable);
		const headRow = $("<tr></tr>").appendTo(thead);
		columns.forEach((column) => {
			const th = $("<th></th>").attr({ "data-column": column.fieldname, scope: "col" }).appendTo(headRow);
			th.append(
				$('<button type="button" class="sx-profile-sort"></button>')
					.attr({ "data-sort-key": column.fieldname, "aria-label": translate("Sort by {0}", [column.label_source]) })
					.append(labelNode(column.label_source || column.label, opts))
					.append($('<span class="sx-profile-sort-arrow"></span>').text("↕"))
					.on("click", (event) => {
						event.preventDefault();
						const button = $(event.currentTarget);
						const index = columns.indexOf(column);
						const ascending = button.attr("aria-sort") !== "ascending";
						htmlTable.find("th").removeAttr("aria-sort").find(".sx-profile-sort-arrow").text("↕");
						th.attr("aria-sort", ascending ? "ascending" : "descending");
						button.find(".sx-profile-sort-arrow").text(ascending ? "↑" : "↓");
						const body = htmlTable.find("tbody");
						const cellText = (row) => {
							try {
								return JSON.parse($(row).attr("data-sort-values"))[index] || "";
							} catch (error) {
								return "";
							}
						};
						const ordered = body.find("tr").get().sort((a, b) => {
							const result = cellText(a).localeCompare(cellText(b), languageOf(opts.profile) || undefined, {
								numeric: true, sensitivity: "base",
							});
							return ascending ? result : -result;
						});
						ordered.forEach((row) => body.append(row));
					}),
			);
		});
		const tbody = $("<tbody></tbody>").appendTo(htmlTable);
		rows.forEach((row) => {
			const tr = $("<tr></tr>").appendTo(tbody);
			const searchable = [];
			const sortable = [];
			columns.forEach((column) => {
				const cell = row[column.fieldname];
				const field = cell || { value: "", value_kind: "text", value_source: "", label: column.label };
				const td = $("<td></td>").attr({ "data-column": column.fieldname }).appendTo(tr);
				td.append(valueNode(field, opts));
				searchable.push(String(field.value_source || displayValue(field.value) || ""));
				sortable.push(String(field.value_source || displayValue(field.value) || ""));
			});
			tr.attr({
				"data-sx-filter": searchable.join(" "),
				"data-sort-values": JSON.stringify(sortable),
			});
		});
		if (table.truncated && table.total) {
			$('<div class="sx-profile-table-note"></div>')
				.text(translate("Showing {0} of {1}", [rows.length, table.total]))
				.appendTo(wrap);
		}
		return wrap;
	}

	function createController(options) {
		const opts = Object.assign({ mode: currentMode(), stateKey: "", openSections: {} }, options);
		const data = isV2(opts.profile) ? opts.profile : normaliseProfile(opts.profile);
		const host = asJq(opts.container);
		const sections = data.sections || [];
		const children = data.children || {};
		let mode = opts.mode;
		let filter = "";

		host.empty();
		if (!opts.compactToolbar) {
			const tools = $('<div class="sx-profile-tools"></div>').appendTo(host);
			const search = $('<input type="search" class="form-control input-sm sx-profile-filter"></input>')
				.attr({ placeholder: translate("Filter fields and tables"), "aria-label": translate("Filter fields and tables") })
				.appendTo(tools);
			const modes = $('<div class="sx-profile-modes" role="group"></div>')
				.attr("aria-label", translate("Display language"))
				.appendTo(tools);
			[["translated", "Translated"], ["source", "Source text"], ["both", "Both languages"]].forEach(
				([key, label]) => {
					$('<button type="button" class="btn btn-xs btn-default"></button>')
						.text(translate(label))
						.attr({ "data-mode": key, "aria-pressed": key === mode ? "true" : "false" })
						.toggleClass("btn-primary", key === mode)
						.toggleClass("btn-default", key !== mode)
						.on("click", () => setMode(key))
						.appendTo(modes);
				},
			);
			let timer = null;
			search.on("input.sxProfile", () => {
				const value = search.val() || "";
				if (timer) clearTimeout(timer);
				timer = setTimeout(() => applyFilter(value), 100);
			});
		}

		function tableSection(sectionHost, table) {
			const title = table.label_source || table.label || table.fieldname || "";
			const key = "ctbl_" + (table.fieldname || table.id);
			let body;
			if (opts.sectionFactory) {
				const element = opts.sectionFactory("fields", key, labelNode(title, { mode: mode }), table.total);
				sectionHost.append(element);
				body = element.find(".sx-section-body");
			} else {
				body = fieldSection(sectionHost, {
					id: key,
					heading: title,
					count: table.total,
					mode: mode,
					profile: data,
					open: opts.openSections[key] !== false,
					onToggle: (sectionKey, open) => { opts.openSections[sectionKey] = open; },
				});
			}
			renderTable(body, table, Object.assign({}, opts, { profile: data, mode: mode }));
		}

		function visibleRows(scope) {
			return scope.find(".sx-profile-row, .sx-profile-table-wrap tbody tr").filter(function () {
				return $(this).css("display") !== "none";
			}).length;
		}

		function render() {
			host.children(".sx-profile-section-host").remove();
			const sectionHost = $('<div class="sx-profile-section-host"></div>').appendTo(host);
			const tableNames = opts.tables || Object.keys(children);
			if (!opts.onlyTables) {
				sections.forEach((section) => {
					const key = "fld_" + (section.id || section.heading_source || section.heading);
					const count = (section.fields || []).length;
					let body;
					if (opts.sectionFactory) {
						const element = opts.sectionFactory(
							"fields", key,
							labelNode(section.heading_source || section.heading, { mode: mode }), count,
						);
						sectionHost.append(element);
						body = element.find(".sx-section-body");
					} else {
					body = fieldSection(sectionHost, {
						id: key,
						heading: section.heading_source || section.heading,
						count: count,
						mode: mode,
						profile: data,
						open: opts.openSections[key] !== false,
						onToggle: (sectionKey, open) => { opts.openSections[sectionKey] = open; },
					});
					}
					if (section.help) {
						// Section-level help (e.g. the Quality scoring weights).
						body.append(
							$('<div class="sx-section-help"></div>').append(
								labelNode(section.help, { mode: mode })
							)
						);
					}
					renderFields(body, section.fields || [], Object.assign({}, opts, { profile: data, mode: mode }));
					tableNames
						.filter((name) => children[name] && (children[name].section || "other") === section.id)
						.forEach((name) => tableSection(sectionHost, children[name]));
				});
			}
			// Tables with no matching field group still deserve a home.
			tableNames.forEach((name) => {
				const table = children[name];
				if (!table) return;
				const group = table.section || "other";
				if (opts.onlyTables || !sections.some((section) => section.id === group)) {
					tableSection(sectionHost, table);
				}
			});
			if (!sections.length && !tableNames.some((name) => children[name])) {
				$('<div class="sx-empty"></div>').text(translate("No field data available.")).appendTo(sectionHost);
			}
			applyFilter(filter);
			if (typeof opts.onCount === "function") {
				opts.onCount(sections.reduce((sum, section) => sum + (section.fields || []).length, 0));
			}
		}

		function setMode(next) {
			mode = next;
			saveMode(mode);
			host.find(".sx-profile-modes button").each(function () {
				const active = $(this).attr("data-mode") === mode;
				$(this).toggleClass("btn-primary", active).toggleClass("btn-default", !active)
					.attr("aria-pressed", active ? "true" : "false");
			});
			const scroll = host[0] && host[0].parentElement ? host[0].parentElement.scrollTop : 0;
			render();
			if (host[0] && host[0].parentElement) host[0].parentElement.scrollTop = scroll;
		}

		function applyFilter(term) {
			filter = String(term || "").trim().toLowerCase();
			host.find("[data-sx-filter]").each(function () {
				const node = $(this);
				const haystack = node.attr("data-sx-filter") || "";
				node.toggle(!filter || haystack.toLowerCase().indexOf(filter) !== -1);
			});
			host.find(".sx-section").each(function () {
				const section = $(this);
				const hasMatch = section.find("[data-sx-filter]").filter(function () {
					return $(this).css("display") !== "none";
				}).length > 0;
				section.toggle(!filter || hasMatch || section.find(".sx-section-body .sx-empty").length > 0);
			});
			let empty = host.find(".sx-profile-no-match");
			if (!empty.length) {
				empty = $('<div class="sx-empty sx-profile-no-match"></div>')
					.text(translate("No matching fields")).appendTo(host);
			}
			empty.toggle(!!filter && visibleRows(host) === 0);
		}

		render();
		return {
			render,
			setMode,
			applyFilter,
			getMode: () => mode,
			getData: () => data,
			destroy: () => host.off(".sxProfile"),
		};
	}

	function mountFields(options) {
		return createController(options);
	}

	function mountTables(options) {
		const opts = Object.assign({}, options, { compactToolbar: true, onlyTables: true });
		return createController(opts);
	}

	return {
		mountFields,
		mountTables,
		renderTable,
		labelNode,
		valueNode,
		translate,
		interpolate,
		normaliseProfile,
		splitDemo,
		safeUrl,
		GROUP_TITLES,
		VERSION: "1.0.0",
	};
});
