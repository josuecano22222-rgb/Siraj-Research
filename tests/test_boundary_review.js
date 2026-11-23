// Dependency-free tests for the quiet administrative-boundary review fingerprint.
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const source = fs.readFileSync('siraj_research/public/js/coordinate_map.js', 'utf8');
const applyStart = source.indexOf('\tfunction applyAdminChain');
const dialogStart = source.indexOf('\n\tfunction showDiffDialog', applyStart);
assert(applyStart >= 0 && dialogStart > applyStart, 'review workflow must remain extractable');
const automaticPath = source.slice(applyStart, dialogStart);
assert(!automaticPath.includes('showDiffDialog('), 'resolver must never open the conflict dialog automatically');
assert(automaticPath.includes('installBoundaryReviewButton(frm)'), 'resolver must expose a quiet review button');

const start = source.indexOf('\tfunction normalizedBoundaryValue');
const end = source.indexOf('\n\tfunction removeBoundaryReviewButton', start);
assert(start >= 0 && end > start, 'boundary review helpers must remain extractable');

const context = {};
vm.runInNewContext(
  source.slice(start, end)
    + '\nthis.normalize = normalizedBoundaryValue;'
    + '\nthis.fingerprint = boundaryReviewFingerprint;',
  context,
);

const normalize = context.normalize;
const fingerprint = context.fingerprint;
const cfg = {lat_field: 'latitude', lon_field: 'longitude'};
const form = (lat, lon) => ({doc: {latitude: lat, longitude: lon}});
const diffs = [{fieldname: 'country', current: ' Palestine ', proposed: 'PS'}];

assert.equal(normalize(null), '');
assert.equal(normalize('  RFH  '), 'RFH');

const first = fingerprint(form('31.2500', '34.2500'), cfg, diffs, {dataset: 'boundaries-v1'});
const same = fingerprint(
  form(' 31.2500 ', '34.2500'),
  cfg,
  [{fieldname: 'country', current: 'Palestine', proposed: 'PS'}],
  {dataset: 'boundaries-v1'},
);
assert.equal(first, same, 'whitespace-only differences must not reopen the review');

const moved = fingerprint(form('31.2600', '34.2500'), cfg, diffs, {dataset: 'boundaries-v1'});
assert.notEqual(first, moved, 'changed coordinates must create a new review');

const redetected = fingerprint(
  form('31.2500', '34.2500'),
  cfg,
  [{fieldname: 'country', current: 'Palestine', proposed: 'PSE'}],
  {dataset: 'boundaries-v2'},
);
assert.notEqual(first, redetected, 'changed detected values must create a new review');

console.log('Boundary review: resolver stays silent and exposes meaningful changes for on-demand review.');
