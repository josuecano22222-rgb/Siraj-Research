// Dependency-free guard for geographic DocType Action localization.
const assert = require('assert');
const fs = require('fs');

const source = fs.readFileSync('siraj_research/public/js/geography-action-i18n.js', 'utf8');
const bundle = fs.readFileSync('siraj_research/public/js/siraj.bundle.js', 'utf8');
const translations = fs.readFileSync('siraj_research/translations/ar.csv', 'utf8');

assert(source.includes("const GROUP = 'Geography'"));
assert(source.includes("const ACTION = 'Open geographic explorer'"));
assert(source.includes('action.textContent = __(ACTION)'));
assert(source.includes('replaceButtonText('));
for (const doctype of ['Person', 'Institution', 'Place', 'Siraj Event']) {
  assert(source.includes(`'${doctype}'`), `${doctype} action menu must be localized`);
}
assert(bundle.includes("import './geography-action-i18n.js'"));
assert(translations.includes('Geography,الجغرافيا'));
assert(translations.includes('Open geographic explorer,افتح المستكشف الجغرافي'));

console.log('Geographic action group and item are translated for every owning DocType.');
