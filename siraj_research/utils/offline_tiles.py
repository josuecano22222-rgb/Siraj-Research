"""Bounded local raster MBTiles operations; no network and no web endpoints.

This low-level library is not a pack installer, authorization layer, or a safe
interface for arbitrary user-supplied files. Only use administrator-reviewed,
trusted MBTiles with appropriate redistribution rights. Integration must add
site isolation, permissions, cache policy, lifecycle and operational limits.
"""

from __future__ import annotations

import math
import os
import sqlite3
from contextlib import closing
from pathlib import Path

MAX_ZOOM = 22
MAX_MERCATOR_LATITUDE = 85.0511287798066
MAX_TILE_BYTES = 4 * 1024 * 1024
MAX_TILES_PER_EXPORT = 25_000
MAX_EXPORT_BYTES = 200 * 1024 * 1024
_FORMATS = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}


class TilePackError(ValueError):
	pass


def _open_readonly(path):
	# The pack must not be changed while in use; immutable mode deliberately
	# ignores a live WAL. Imported packs must be checkpointed before use.
	resolved = Path(path).resolve(strict=True)
	if not resolved.is_file():
		raise TilePackError("Tile pack is not a regular file")
	db = sqlite3.connect(resolved.as_uri() + "?mode=ro&immutable=1", uri=True)
	if hasattr(db, "setlimit"):
		db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, MAX_TILE_BYTES + 65_536)
	db.execute("PRAGMA query_only=ON")
	db.execute("PRAGMA trusted_schema=OFF")
	return db


def _metadata(db):
	try:
		rows = db.execute("SELECT name, value FROM metadata LIMIT 101")
	except sqlite3.Error as exc:
		raise TilePackError("Invalid MBTiles metadata") from exc
	metadata = {}
	for index, (key, value) in enumerate(rows):
		if index >= 100:
			raise TilePackError("Too many metadata entries")
		if not isinstance(key, str) or not isinstance(value, str) or len(key) > 128 or len(value) > 4096:
			raise TilePackError("Invalid MBTiles metadata value")
		if key in metadata:
			raise TilePackError("Duplicate metadata key")
		metadata[key] = value
	fmt = metadata.get("format", "").lower()
	if fmt not in _FORMATS:
		raise TilePackError("Only PNG, JPEG and WebP raster MBTiles are supported")
	if metadata.get("scheme", "tms").lower() != "tms":
		raise TilePackError("Only TMS-row MBTiles are supported")
	return metadata, fmt


def _tile_data(value, fmt):
	if not isinstance(value, bytes) or not value or len(value) > MAX_TILE_BYTES:
		raise TilePackError("Invalid or oversized tile")
	valid = (
		(fmt == "png" and value.startswith(b"\x89PNG\r\n\x1a\n"))
		or (fmt in ("jpg", "jpeg") and value.startswith(b"\xff\xd8\xff"))
		or (fmt == "webp" and len(value) >= 12 and value.startswith(b"RIFF") and value[8:12] == b"WEBP")
	)
	if not valid:
		raise TilePackError("Tile does not match declared raster format")
	return value


def _xyz(z, x, y):
	# Strict integer checks avoid coercing arbitrary request strings or bools.
	if any(type(n) is not int for n in (z, x, y)) or not 0 <= z <= MAX_ZOOM:
		raise TilePackError("Invalid tile coordinates")
	width = 1 << z
	if not (0 <= x < width and 0 <= y < width):
		raise TilePackError("Tile coordinates outside zoom level")
	return width - 1 - y


def read_tile(path, z, x, y):
	"""Return (raster bytes, MIME) or None; XYZ input uses MBTiles TMS rows."""
	row = _xyz(z, x, y)
	try:
		with closing(_open_readonly(path)) as db:
			_meta, fmt = _metadata(db)
			results = db.execute(
				"SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=? LIMIT 2",
				(z, x, row),
			).fetchall()
			if len(results) > 1:
				raise TilePackError("Duplicate tile coordinates")
			return (_tile_data(results[0][0], fmt), _FORMATS[fmt]) if results else None
	except sqlite3.Error as exc:
		raise TilePackError("Invalid or unreadable MBTiles pack") from exc


def _x_ranges(west, east, n):
	segments = [(west, east)] if west < east else [(west, 180.0), (-180.0, east)]
	out = []
	for left, right in segments:
		if left >= right:
			continue
		x0 = max(0, min(n - 1, math.floor((left + 180) / 360 * n)))
		x1 = max(0, min(n - 1, math.ceil((right + 180) / 360 * n) - 1))
		if x0 <= x1:
			out.append((x0, x1))
	# At low zoom dateline halves may occupy the same tile. Merge intervals.
	merged = []
	for a, b in sorted(out):
		if merged and a <= merged[-1][1] + 1:
			merged[-1] = (merged[-1][0], max(merged[-1][1], b))
		else:
			merged.append((a, b))
	return merged


def _y(latitude, n):
	return (1 - math.asinh(math.tan(math.radians(latitude))) / math.pi) / 2 * n


def tile_ranges(bounds, minzoom, maxzoom, max_tiles=MAX_TILES_PER_EXPORT):
	"""Plan bounded XYZ ranges for (west,south,east,north), including dateline."""
	if not isinstance(bounds, (tuple, list)) or len(bounds) != 4:
		raise TilePackError("Expected west, south, east, north")
	if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in bounds):
		raise TilePackError("Invalid bounds")
	west, south, east, north = bounds
	if not (
		-180 <= west <= 180
		and -180 <= east <= 180
		and west != east
		and -MAX_MERCATOR_LATITUDE <= south < north <= MAX_MERCATOR_LATITUDE
	):
		raise TilePackError("Bounds outside Web Mercator or empty")
	if (
		any(type(v) is not int for v in (minzoom, maxzoom, max_tiles))
		or not 0 <= minzoom <= maxzoom <= MAX_ZOOM
		or not 1 <= max_tiles <= MAX_TILES_PER_EXPORT
	):
		raise TilePackError("Invalid zoom or tile limit")
	result, total = [], 0
	for z in range(minzoom, maxzoom + 1):
		n = 1 << z
		y0 = max(0, min(n - 1, math.floor(_y(north, n))))
		y1 = max(0, min(n - 1, math.ceil(_y(south, n)) - 1))
		for x0, x1 in _x_ranges(west, east, n):
			if y1 < y0:
				continue
			total += (x1 - x0 + 1) * (y1 - y0 + 1)
			if total > max_tiles:
				raise TilePackError("Requested area exceeds tile limit")
			result.append((z, x0, x1, y0, y1))
	if not result:
		raise TilePackError("Empty tile selection")
	return result, total


def export_area(
	source,
	destination,
	bounds,
	minzoom,
	maxzoom,
	*,
	max_tiles=MAX_TILES_PER_EXPORT,
	max_tile_bytes=MAX_EXPORT_BYTES,
):
	"""Write a new bounded MBTiles subset; never overwrite an existing file.

	The byte limit applies to tile payloads, not SQLite file overhead. Counts
	only source tiles available within the selection. No external tiles
	are fetched. Caller is responsible for rights, private paths and access.
	"""
	if type(max_tile_bytes) is not int or not 1 <= max_tile_bytes <= MAX_EXPORT_BYTES:
		raise TilePackError("Invalid byte limit")
	ranges, requested = tile_ranges(bounds, minzoom, maxzoom, max_tiles)
	destination = Path(destination)
	created = False
	try:
		with closing(_open_readonly(source)) as src:
			meta, fmt = _metadata(src)
			fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
			created = True
			os.close(fd)
			out = sqlite3.connect(str(destination))
			try:
				out.execute("CREATE TABLE metadata (name TEXT, value TEXT)")
				out.execute(
					"CREATE TABLE tiles (zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER, tile_data BLOB)"
				)
				out.execute("CREATE UNIQUE INDEX tile_index ON tiles (zoom_level, tile_column, tile_row)")
				retained = {
					key: meta[key]
					for key in ("name", "description", "attribution", "version", "type")
					if key in meta
				}
				# Standard MBTiles bounds cannot represent a dateline-crossing
				# interval. Use a conservative global-width bounding box and
				# retain the precise requested interval separately.
				west, south, east, north = bounds
				standard_bounds = (-180, south, 180, north) if west > east else bounds
				retained.update(
					format=fmt,
					scheme="tms",
					minzoom=str(minzoom),
					maxzoom=str(maxzoom),
					bounds=",".join(str(v) for v in standard_bounds),
					siraj_requested_bounds=",".join(str(v) for v in bounds),
				)
				out.executemany("INSERT INTO metadata VALUES (?, ?)", retained.items())
				count, size = 0, 0
				for z, x0, x1, y0, y1 in ranges:
					tms0, tms1 = (1 << z) - 1 - y1, (1 << z) - 1 - y0
					cursor = src.execute(
						"SELECT tile_column, tile_row, tile_data FROM tiles WHERE zoom_level=? AND tile_column BETWEEN ? AND ? AND tile_row BETWEEN ? AND ?",
						(z, x0, x1, tms0, tms1),
					)
					for x, row, value in cursor:
						data = _tile_data(value, fmt)
						count += 1
						size += len(data)
						if count > max_tiles or size > max_tile_bytes:
							raise TilePackError("Export exceeds size or tile limit")
						out.execute("INSERT INTO tiles VALUES (?, ?, ?, ?)", (z, x, row, data))
				out.commit()
				return {"tiles": count, "possible_tiles": requested, "tile_bytes": size}
			finally:
				out.close()
	except sqlite3.Error as exc:
		if created:
			destination.unlink(missing_ok=True)
		raise TilePackError("Invalid or unreadable MBTiles pack") from exc
	except Exception:
		if created:
			destination.unlink(missing_ok=True)
		raise
