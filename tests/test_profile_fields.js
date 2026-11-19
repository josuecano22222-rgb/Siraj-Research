// Run with node. jsdom checks of the bilingual field/table presentation engine.
// `npm run test:js` includes this file.
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');
const jquery = require('jquery');

const root = path.resolve(__dirname, '..') + '/';
const dom = new JSDOM('<!doctype html><html lang="en"><body><div id="host"></div></body></html>', {
	url: 'http://site.test/app/siraj-explorer',
});
const w = dom.window;
const $ = jquery(w);
w.$ = $;
const dictionary = {
	'Display name': 'الاسم المعروض',
	'Birth': 'الميلاد',
	'Life & dates': 'الحياة والتواريخ',
	'Date of birth precision': 'دقة تاريخ الميلاد',
	'year': 'عام',
	'Public activity': 'النشاط العام',
	'Official accounts': 'الحسابات الرسمية',
	'Platform': 'المنصة',
	'Support': 'الدعم',
	'supports': 'يدعم',
	'Copied': 'تم النسخ',
	'Copy value': 'نسخ القيمة',
	'Demo data': 'بيانات تجريبية',
	'Sort by {0}': 'ترتيب حسب {0}',
	'Filter fields and tables': 'تصفية الحقول والجداول',
};
w.__ = (text, args) => {
	let result = dictionary[text] || text;
	if (args) result = result.replace(/\{(\d+)\}/g, (match, i) => args[i] == null ? match : String(args[i]));
	return result;
};
global.window = w;
global.__ = w.__;
const fields = require(root + 'siraj_research/public/js/siraj-profile-fields.js');

const text = (node) => $(node).text().replace(/\s+/g, ' ').trim();
const section = (id) => w.document.querySelector('[data-sx-section="' + id + '"]');
const row = (fieldname) => w.document.querySelector('[data-sx-fieldname="' + fieldname + '"]');

function field(fieldname, label, value, extra = {}) {
	return Object.assign({
		fieldname,
		label,
		label_source: label,
		i18n_key: label,
		fieldtype: 'Data',
		value,
		value_source: typeof value === 'object' ? JSON.stringify(value) : String(value),
		value_kind: 'text',
		translatable_value: false,
		group: '',
	}, extra);
}

function profile() {
	const link = {type: 'link', doctype: 'Person Status', name: 'active', title: 'Active'};
	return {
		presentation: {version: 2, language: 'en', rtl: false},
		sections: [
			{
				id: 'identity',
				heading: 'Identity',
				heading_source: 'Identity',
				fields: [
					field('display_name', 'Display name', 'Gen. Ari Saeed (DEMO) [DEMO]',
						{value_source: 'Gen. Ari Saeed (DEMO) [DEMO]', value_demo: true}),
					field('name_ar', 'Name (Arabic)', 'اللواء آري سعيد', {value_rtl: true}),
					field('person_status', 'Current status', link,
						{value_kind: 'link', value_source: 'Active', fieldtype: 'Link'}),
				],
			},
			{
				id: 'life',
				heading: 'Life & dates',
				heading_source: 'Life & dates', source_headings: ['Birth'],
				fields: [
					field('birth_date_precision', 'Date of birth precision', 'year',
						{value_kind: 'enum', value_source: 'year', fieldtype: 'Select', translatable_value: true}),
					field('birth_date', 'Date of birth (comparable)', '1969-01-01',
						{value_kind: 'date', fieldtype: 'Date'}),
				],
			},
			{
				id: 'public',
				heading: 'Public activity',
				heading_source: 'Public activity',
				fields: [field('website', 'Official website', 'https://example.org/a?b=1&c=2',
					{value_kind: 'url'})],
			},
			{
				id: 'quality',
				heading: 'Quality',
				heading_source: 'Quality',
				fields: [field('completeness_score', 'Completeness (%)', 0, {value_kind: 'number'})],
			},
		],
		children: {
			social_accounts: {
				id: 'social_accounts', fieldname: 'social_accounts',
				label: 'Official accounts', label_source: 'Official accounts',
				section: 'public', total: 2, truncated: false,
				columns: [
					{fieldname: 'platform', label: 'Platform', label_source: 'Platform'},
					{fieldname: 'url', label: 'URL', label_source: 'URL'},
				],
				rows: [
					{
						platform: field('platform', 'Platform', {type: 'link', doctype: 'Social Platform', name: 'telegram', title: 'Telegram'},
							{value_kind: 'link', value_source: 'Telegram'}),
						url: field('url', 'URL', 'https://t.me/zeta', {value_kind: 'url', value_source: 'https://t.me/zeta'}),
					},
					{
						platform: field('platform', 'Platform', {type: 'link', doctype: 'Social Platform', name: 'x', title: 'X'},
							{value_kind: 'link', value_source: 'X'}),
						url: field('url', 'URL', 'https://t.me/alpha', {value_kind: 'url', value_source: 'https://t.me/alpha'}),
					},
				],
			},
			evidence: {
				id: 'evidence', fieldname: 'evidence',
				label: 'Evidence', label_source: 'Evidence',
				section: 'evidence', total: 1, truncated: false,
				columns: [{fieldname: 'support_type', label: 'Support', label_source: 'Support'}],
				rows: [{
					support_type: field('support_type', 'Support', 'supports',
						{value_kind: 'enum', value_source: 'supports', translatable_value: true}),
				}],
			},
		},
	};
}

function mount(options = {}) {
	w.localStorage.clear();
	$('#host').empty();
	return fields.mountFields(Object.assign({container: $('#host'), profile: profile()}, options));
}

// 1. Grouping, typed values, translation and demo markers.
let controller = mount();
assert(text(section('fields:fld_identity')).includes('Identity'));
assert(section('fields:fld_life').querySelector('[data-i18n-source="Life & dates"]'), 'Life group present');
assert(text(row('display_name')).includes('الاسم المعروض'), 'labels use the translation catalogue');
assert(text(row('display_name')).includes('DEMO'), 'demo marker becomes a badge');
assert(!text(row('display_name')).includes('[DEMO]'), 'raw marker is not shown inline');
assert(text(row('birth_date_precision')).includes('عام'), 'enum value is translated');
assert(text(row('name_ar')).includes('اللواء آري سعيد'));
assert(row('name_ar').querySelector('[dir="auto"]'), 'user data is auto-directional');
assert.strictEqual(row('person_status').querySelector('button.sx-profile-link').textContent, 'Active');
assert.strictEqual($('#host a[href*="example.org"]').length, 1, 'URL values are anchors');
assert(!w.document.body.textContent.includes('[object Object]'), 'no stringified objects');
assert.strictEqual(controller.getData().children.social_accounts.rows.length, 2);

// Child tables are interleaved after their semantic section, with translated headers.
assert(section('fields:ctbl_social_accounts'), 'accounts table mounted');
const publicIndex = $('#host > .sx-profile-section-host > .sx-section').toArray()
	.findIndex((node) => node.getAttribute('data-sx-section') === 'fields:fld_public');
const tableIndex = $('#host > .sx-profile-section-host > .sx-section').toArray()
	.findIndex((node) => node.getAttribute('data-sx-section') === 'fields:ctbl_social_accounts');
assert.strictEqual(tableIndex, publicIndex + 1, 'table sits next to its field group');
assert(text(section('fields:ctbl_social_accounts')).includes('المنصة'));
assert.strictEqual($('[data-sx-table="social_accounts"] tbody tr').length, 2);

// 2. Mode switch without re-fetching: translated / source / both.
controller.setMode('source');
assert(text(row('birth_date_precision')).includes('year'));
assert(!text(row('birth_date_precision')).includes('عام'));
controller.setMode('both');
assert(text(row('birth_date_precision')).includes('عام'));
assert(text(row('birth_date_precision')).includes('year'));
assert.strictEqual(controller.getMode(), 'both');
assert.strictEqual(w.localStorage.getItem('siraj.profile.fields.mode.v1'), 'both');
controller.destroy();

// 3. Table sorting by column.
controller = mount();
const beforeSort = $('[data-sx-table="social_accounts"] tbody tr td:nth-child(2)').toArray().map(text);
assert.deepStrictEqual(beforeSort, ['https://t.me/zeta', 'https://t.me/alpha']);
$('[data-sx-table="social_accounts"] th[data-column="url"] button').trigger('click');
const afterSort = $('[data-sx-table="social_accounts"] tbody tr td:nth-child(2)').toArray().map(text);
assert.deepStrictEqual(afterSort, ['https://t.me/alpha', 'https://t.me/zeta']);
assert.strictEqual($('[data-sx-table="social_accounts"] th[data-column="url"]').attr('aria-sort'), 'ascending');

// 4. Filtering fields and tables, including the empty state.
const search = $('.sx-profile-filter');
search.val('birth').trigger('input');
const wait = () => new Promise((resolve) => setTimeout(resolve, 130));

(async () => {
	await wait();
	assert.strictEqual(row('display_name').style.display, 'none');
	assert.strictEqual(row('birth_date_precision').style.display, '');
	assert.strictEqual(section('fields:fld_identity').style.display, 'none');
	search.val('matches-nothing-at-all').trigger('input');
	await wait();
	assert(text($('.sx-profile-no-match')).includes('No matching fields'));
	search.val('').trigger('input');
	await wait();
	assert.strictEqual(row('display_name').style.display, '');

	// 5. sectionFactory (the Explorer supplies its own <details> builder).
	mount({
		sectionFactory: (tab, key, title, count) => {
			const sec = $('<details class="sx-section"></details>')
				.attr('data-sx-section', tab + ':' + key)
				.append($('<summary></summary>').append(title).append($('<span class="sx-section-count"></span>').text(String(count))));
			const body = $('<div class="sx-section-body"></div>').appendTo(sec);
			return sec;
		},
	});
	assert(text(section('fields:fld_life')).includes('الحياة والتواريخ'), 'sectionFactory title is translated');
	assert(section('fields:fld_life').querySelector('[data-i18n-source="Life & dates"]'), 'source string retained for the toggle');
	assert(row('birth_date_precision'), 'sectionFactory body receives fields');

	// 6. mountTables renders only chosen tables (Relationship Evidence tab).
	$('#host').empty();
	fields.mountTables({container: $('#host'), profile: profile(), tables: ['evidence']});
	assert.strictEqual($('[data-sx-table]').length, 1);
	assert(text($('[data-sx-table="evidence"]')).includes('يدعم'));
	assert(!section('fields:fld_identity'), 'no field sections in table-only mode');

	// 7. Older payloads are normalised on the client instead of crashing.
	$('#host').empty();
	fields.mountFields({
		container: $('#host'),
		profile: {
			sections: [{
				heading: 'Identity',
				fields: [
					{fieldname: 'display_name', label: 'Display name', value: 'Old client', fieldtype: 'Data'},
					{fieldname: 'evidence', label: 'Evidence', value: [{source: 'S1'}], fieldtype: 'Table'},
				],
			}],
			children: {},
		},
	});
	assert(!w.document.body.textContent.includes('[object Object]'));
	assert(row('display_name'), 'legacy payload still renders fields');

	// 8. Defensive helpers.
	assert.deepStrictEqual(fields.splitDemo('Name [DEMO]'), {text: 'Name', demo: true});
	assert.strictEqual(fields.safeUrl('javascript:alert(1)'), null);
	assert.strictEqual(fields.safeUrl('https://t.me/ari_demo'), 'https://t.me/ari_demo');
	assert.strictEqual(fields.interpolate('Showing {0} of {1}', [2, 9]), 'Showing 2 of 9');
	const mangled = fields.valueNode(field('u', 'URL', '[https://t.me/ari_demo',
		{value_kind: 'url', value_source: '[https://t.me/ari_demo'}), {});
	assert.strictEqual(mangled.find('a').attr('href'), 'https://t.me/ari_demo');
	const emptyWrap = fields.renderTable($('#host')[0], {fieldname: 'empty', rows: [], columns: []}, {});
	assert(text(emptyWrap).includes('No rows recorded'));

	console.log('Profile fields: i18n modes, grouping, typed values, sorting, filtering and legacy fallback passed');
})().catch((error) => {
	console.error(error);
	process.exitCode = 1;
});
