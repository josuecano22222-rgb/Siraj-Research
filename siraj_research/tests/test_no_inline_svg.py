"""Static grep to ensure no inline <svg> appears outside the icon registries.

Run: python siraj_research/tests/test_no_inline_svg.py
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
PUBLIC_JS = ROOT / "siraj_research" / "public" / "js"
PAGES = ROOT / "siraj_research" / "siraj_research" / "page"

# The only files allowed to contain <svg ...> (they build the SVG strings).
ALLOWED = {
    PUBLIC_JS / "siraj-record-meta.js",  # builds pin/swatch SVGs from registry
    PUBLIC_JS / "siraj-map-kit.js",       # no-op today but builds helpOverlay HTML
    ROOT / "siraj_research" / "public" / "js" / "siraj-icons.js",  # legacy facade
    ROOT / "siraj_research" / "templates" / "pages" / "icon_sheet.html",  # dev page
}

SVG_TAG = re.compile(r"<svg\b", re.I)

EXEMPT_DIR_PARTS = {"vendor", "node_modules", "__pycache__"}


def iter_js():
    for base in (PUBLIC_JS, PAGES):
        for p in base.rglob("*.js"):
            if any(part in EXEMPT_DIR_PARTS for part in p.parts):
                continue
            yield p


def test():
    bad = []
    for p in iter_js():
        if p in ALLOWED:
            continue
        src = p.read_text(errors="ignore")
        # Skip files in siraj-map/siraj-graph.js and siraj-filters.js (pure logic, no SVG).
        for i, line in enumerate(src.splitlines(), 1):
            # Allow SVG templates that are used ONLY to build data: URIs for
            # marker images (e.g. vis.Network circularImage). The pattern is a
            # template literal starting with `<svg ...` on the same line that
            # also contains `encodeURIComponent(svg)` usage in the file.
            if SVG_TAG.search(line):
                # Detect data-URI builder: line uses backticks and is used in encodeURIComponent.
                is_data_uri = ('encodeURIComponent' in src) and ('data:image/svg+xml' in src)
                # Only exempt if this exact line is inside a const svg = `` block that feeds a data URI.
                if '`<' in line and '/>' in line and 'xmlns="http://www.w3.org/2000/svg"' in line and is_data_uri:
                    continue
                bad.append((p, i, line.strip()[:120]))
    if bad:
        for p, i, line in bad:
            print(f"FAIL inline <svg>: {p.relative_to(ROOT)}:{i}: {line}")
        sys.exit(1)
    print(f"PASS no inline <svg> outside registries ({sum(1 for _ in iter_js())} JS files scanned)")


if __name__ == "__main__":
    test()
