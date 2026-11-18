"""Administrator-only, offline raster viewer package builder (no web endpoint).

Only trusted, checkpointed raster MBTiles may be used. License permission for
redistribution to disconnected devices must be obtained before running this.
"""

import argparse
import json
import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from siraj_research.utils.offline_tiles import TilePackError, _metadata, _open_readonly, export_area

ASSETS = Path(__file__).resolve().parents[1] / "public"


def create_package(source, destination, bounds, minzoom, maxzoom, *, redistribution_allowed=False):
	"""Write a new ZIP, bounded by export_area's tile and payload limits.

	This is a local administrative operation, not an authorization boundary.
	Output and temporary files contain licensed imagery and need private storage.
	"""
	if redistribution_allowed is not True:
		raise TilePackError("Confirm the license allows redistribution to offline devices")
	destination = Path(destination)
	# Exclusive creation avoids overwriting files, including symlinks.
	fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
	try:
		with os.fdopen(fd, "wb") as result, tempfile.TemporaryDirectory(prefix="siraj-map-") as temporary:
			subset = Path(temporary) / "subset.mbtiles"
			summary = export_area(source, subset, bounds, minzoom, maxzoom)
			if not summary["tiles"]:
				raise TilePackError("No tiles are available in the selected area")
			with closing(_open_readonly(subset)) as db, ZipFile(result, "w", allowZip64=True) as archive:
				meta, fmt = _metadata(db)
				extension = "jpg" if fmt in ("jpg", "jpeg") else fmt
				west, south, east, north = bounds
				span = east - west if east > west else (east - west) % 360
				center_lon = ((west + span / 2 + 180) % 360) - 180
				config = {
					"minzoom": minzoom,
					"maxzoom": maxzoom,
					"center": [(south + north) / 2, center_lon],
					"extension": extension,
					"bounds": list(bounds),
					"attribution": meta.get("attribution", ""),
				}
				# JSON in a separate script, not an inline HTML context.
				archive.writestr(
					"config.js",
					"window.SIRAJ_OFFLINE_MAP = " + json.dumps(config, ensure_ascii=True) + ";\n",
					compress_type=ZIP_DEFLATED,
				)
				for name in ("index.html", "viewer.js", "records.js", "snapshot_verify.js"):
					archive.write(ASSETS / "offline_map" / name, name, compress_type=ZIP_DEFLATED)
				for name in ("leaflet.js", "leaflet.css", "LICENSE"):
					archive.write(
						ASSETS / "vendor" / "leaflet" / name, "leaflet/" + name, compress_type=ZIP_DEFLATED
					)
				for image in (ASSETS / "vendor" / "leaflet" / "images").iterdir():
					if image.is_file():
						archive.write(image, "leaflet/images/" + image.name, compress_type=ZIP_STORED)
				for z, x, row, data in db.execute(
					"SELECT zoom_level, tile_column, tile_row, tile_data FROM tiles"
				):
					y = (1 << z) - 1 - row
					archive.writestr(f"tiles/{z}/{x}/{y}.{extension}", data, compress_type=ZIP_STORED)
		return summary
	except BaseException:
		destination.unlink(missing_ok=True)
		raise


def main():
	parser = argparse.ArgumentParser(
		description="Build a private, bounded offline basemap ZIP from licensed raster MBTiles."
	)
	parser.add_argument("source", help="trusted, checkpointed MBTiles file")
	parser.add_argument("destination", help="new private ZIP path; will not overwrite")
	parser.add_argument(
		"--bounds", required=True, nargs=4, type=float, metavar=("WEST", "SOUTH", "EAST", "NORTH")
	)
	parser.add_argument("--minzoom", required=True, type=int)
	parser.add_argument("--maxzoom", required=True, type=int)
	parser.add_argument("--confirm-redistribution-rights", required=True, action="store_true")
	args = parser.parse_args()
	try:
		summary = create_package(
			args.source,
			args.destination,
			args.bounds,
			args.minzoom,
			args.maxzoom,
			redistribution_allowed=args.confirm_redistribution_rights,
		)
	except (TilePackError, OSError, sqlite3.Error) as exc:
		parser.exit(1, f"Package not created: {exc}\n")
	print(
		f"Created {args.destination}: {summary['tiles']} tiles, {summary['tile_bytes']} tile bytes; "
		f"{summary['possible_tiles']} tiles in requested area."
	)


if __name__ == "__main__":
	main()
