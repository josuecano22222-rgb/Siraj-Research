/* Pure JS cascade regression test — runs with plain Node, no DOM/Frappe. */
const assert = require('assert');
const core = require('../siraj_research/public/js/siraj-cascade-core.js');

const poly = (level, pcode, parent, name, linked, country) => [
  level, pcode, parent, name, '', [[[[0, 0]]]], linked, country,
];
const pkg = {
  dataset: 'OSM-IL-PS', version: 2,
  polygons: [
    poly(1, 'G1', 'IL', 'Governorate A', 'Gov A', 'IL'),
    poly(2, 'D1', 'G1', 'District A', 'Dist A', 'IL'),
    poly(3, 'M1', 'D1', 'Municipality A', 'Mun A', 'IL'),
    poly(4, 'V1', 'M1', 'Village A', 'Vil A', 'IL'),
    poly(5, 'Q1', 'V1', 'Community A', 'Com A', 'IL'),
  ],
};
const idx = core.buildIndex(pkg);

assert.deepStrictEqual(core.ancestorFilters('community', {
  country: 'IL', governorate: 'Gov A', district: 'Dist A',
  municipality: 'Mun A', village: 'Vil A',
}), {
  country: 'IL', governorate: 'Gov A', district: 'Dist A',
  municipality: 'Mun A', village: 'Vil A',
});

assert.strictEqual(core.optionsFor('governorate', { country: 'IL' }, idx).length, 1);
assert.strictEqual(core.optionsFor('district', { governorate: 'Gov A' }, idx)[0].value, 'Dist A');
// Parent unset → global list (not an empty dropdown).
assert.strictEqual(core.optionsFor('district', {}, idx).length, 1);

const chain = core.chainFromRecord('community', 'Com A', idx);
assert.strictEqual(chain.country.value, 'IL');
assert.strictEqual(chain.governorate.value, 'Gov A');
assert.strictEqual(chain.district.value, 'Dist A');
assert.strictEqual(chain.municipality.value, 'Mun A');
assert.strictEqual(chain.village.value, 'Vil A');
assert.strictEqual(chain.community.value, 'Com A');

console.log('Hierarchy cascade core: filters, options, ancestor chain and gaps passed.');

// Global search: with no parent selected every level-N row is offered.
const allGovs = core.optionsFor('governorate', {}, idx);
assert.strictEqual(allGovs.length, 1, 'global governorate list');
const allDistricts = core.optionsFor('district', {}, idx);
assert.strictEqual(allDistricts.length, 1, 'global district list');
// Parent present but unknown → still global rather than an empty dropdown.
const orphan = core.optionsFor('district', { governorate: 'MISSING' }, idx);
assert.strictEqual(orphan.length, 1, 'unknown parent falls back to global');
// Scoped list still wins once a real parent is chosen.
assert.strictEqual(core.optionsFor('district', { governorate: 'Gov A' }, idx)[0].value, 'Dist A');
// Community with only a country set: village parent missing → global villages
// (still one village in this fixture), never a dead empty list.
assert.strictEqual(core.optionsFor('community', { country: 'XX' }, idx).length, 1);
// District scoped by a real governorate is NOT global.
assert.strictEqual(core.optionsFor('district', { governorate: 'Gov A' }, idx).length, 1);
console.log('Cascade core global-until-narrowed options passed.');
