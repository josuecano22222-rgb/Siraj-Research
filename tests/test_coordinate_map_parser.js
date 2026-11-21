// Dependency-free test of the actual Desk picker parsing function. Not a browser test.
const assert=require('assert'), fs=require('fs'), vm=require('vm');
const source=fs.readFileSync('siraj_research/public/js/coordinate_map.js','utf8');
// Slice must start at the const declarations above parseCoordinate — the
// function body references EASTERN_DIGITS/PERSIAN_DIGITS from that scope.
const start=source.indexOf('\tconst EASTERN_DIGITS'), end=source.indexOf('\n\tfunction decimalText(',start);
assert(start>=0 && end>start);
const context={}; vm.runInNewContext(source.slice(start,end)+'\nthis.parseCoordinate = parseCoordinate;',context);
const parse=context.parseCoordinate;
assert.equal(parse(1e-7,90),1e-7); assert.equal(parse('1e-7',90),null);
assert.equal(parse('٣٣٫٢٥',90),33.25); assert.equal(parse('۴۴٫۵',180),44.5);
assert.equal(parse('90.'+'0'.repeat(50),90),90);
assert.equal(parse('90.'+'0'.repeat(50)+'1',90),null);
assert.equal(parse('-180',180),-180); assert.equal(parse('180.00001',180),null);
assert.equal(parse(true,90),null); assert.equal(parse(null,90),null); assert.equal(parse('bad',90),null);
console.log('Coordinate picker parsing: synthetic exact bounds, legacy numbers and multilingual text passed (Node only).');
