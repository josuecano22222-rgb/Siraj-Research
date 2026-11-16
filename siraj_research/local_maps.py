"""Authenticated, site-local raster map packs; never fetch external tiles.

Only administrator-provisioned, trusted, indexed MBTiles are supported. Packs
are shared with users who may read Place records and must be licensed for this
use. No upload or remote-fetch endpoint is provided.
"""
from contextlib import closing
from functools import lru_cache
import json
from pathlib import Path
import re
import sqlite3

import frappe
from frappe.rate_limiter import rate_limit
from werkzeug.wrappers import Response

from siraj_research.utils.offline_tiles import TilePackError, _metadata, _open_readonly, read_tile

PACKS = {"standard": "standard.mbtiles", "aerial": "aerial.mbtiles"}
_COORD = re.compile(r"^[0-9]{1,10}$")


def _authorize():
    if frappe.session.user == "Guest" or not frappe.has_permission("Place", "read"):
        frappe.throw("Not permitted to access local map packs", frappe.PermissionError)


def _path(kind):
    if not isinstance(kind, str) or kind not in PACKS:
        raise TilePackError("Unknown map pack")
    private = Path(frappe.get_site_path("private")).resolve()
    root = private / "siraj_maps"
    if root.is_symlink() or not root.is_dir():
        return None
    path = root / PACKS[kind]
    if path.is_symlink() or not path.is_file():
        return None
    if path.resolve().parent != root.resolve() or root.resolve().parent != private:
        raise TilePackError("Invalid map pack location")
    return path


def _inspect(path):
    """Reject complex/unindexed databases before serving a tile."""
    stat = path.stat()
    return _inspect_cached(str(path), stat.st_ino, stat.st_size, stat.st_mtime_ns)


@lru_cache(maxsize=64)
def _inspect_cached(path, inode, size, mtime):
    try:
        with closing(_open_readonly(path)) as db:
            meta, fmt = _metadata(db)
            table = db.execute("SELECT type FROM sqlite_master WHERE name=?", ("tiles",)).fetchone()
            if not table or table[0] != "table":
                raise TilePackError("Tile pack must contain a tiles table")
            columns = {row[1] for row in db.execute("PRAGMA table_info(tiles)")}
            if not {"zoom_level", "tile_column", "tile_row", "tile_data"}.issubset(columns):
                raise TilePackError("Tile pack has an invalid tiles table")
            valid_index = False
            for index in db.execute("SELECT name, \"unique\", partial FROM pragma_index_list(?)", ("tiles",)):
                name, unique, partial = index
                names = [row[0] for row in db.execute("SELECT name FROM pragma_index_info(?) ORDER BY seqno", (name,))]
                if unique and not partial and names == ["zoom_level", "tile_column", "tile_row"]:
                    valid_index = True
                    break
            if not valid_index:
                raise TilePackError("Tile pack needs a unique zoom/column/row index")
            def zoom(field, default):
                value = meta.get(field, str(default))
                if not re.fullmatch(r"[0-9]{1,2}", value):
                    raise TilePackError("Invalid pack zoom metadata")
                result = int(value)
                if result > 22:
                    raise TilePackError("Invalid pack zoom metadata")
                return result
            actual_low, actual_high = db.execute("SELECT MIN(zoom_level), MAX(zoom_level) FROM tiles").fetchone()
            if (type(actual_low) is not int or type(actual_high) is not int or
                    not 0 <= actual_low <= actual_high <= 22):
                raise TilePackError("Tile pack is empty or has invalid zooms")
            low, high = zoom("minzoom", actual_low), zoom("maxzoom", actual_high)
            if low > actual_low or high < actual_high or low > high:
                raise TilePackError("Pack zoom metadata excludes tiles")
            return {"name": meta.get("name", ""), "attribution": meta.get("attribution", ""),
                    "format": fmt, "minzoom": low, "maxzoom": high}
    except sqlite3.Error as exc:
        raise TilePackError("Invalid tile pack") from exc


def _coord(value):
    if not isinstance(value, str) or not _COORD.fullmatch(value):
        raise TilePackError("Invalid tile coordinates")
    return int(value)


@frappe.whitelist(methods=["GET"])
@rate_limit(limit=120, seconds=60)
def available_packs():
    """Report available trusted basemaps without returning server paths."""
    _authorize()
    result = []
    for kind in PACKS:
        try:
            path = _path(kind)
            if path:
                # This opt-in is a licensing decision, not additional access control:
                # tile readers can already save individual tiles.
                enabled = frappe.conf.get("siraj_offline_map_downloads", [])
                allowed = isinstance(enabled, list) and kind in enabled
                result.append({"kind": kind, **_inspect(path), "download_allowed": allowed})
        except (TilePackError, OSError):
            # A broken pack must not prevent other packs from being used.
            result.append({"kind": kind, "unavailable": True})
    return Response(json.dumps({"message": result}), content_type="application/json", headers={
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
    })


@frappe.whitelist(methods=["GET"])
@rate_limit(limit=1200, seconds=60)
def tile(kind, z, x, y):
    """Serve a single XYZ tile from the selected site's private pack."""
    _authorize()
    try:
        z, x, y = _coord(z), _coord(x), _coord(y)
        path = _path(kind)
        if not path:
            return Response(status=404, headers={"Cache-Control": "private, no-store"})
        _inspect(path)
        result = read_tile(path, z, x, y)
        if result is None:
            return Response(status=404, headers={"Cache-Control": "private, no-store"})
        data, content_type = result
        return Response(data, content_type=content_type, headers={
            "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
        })
    except (TilePackError, OSError):
        frappe.throw("Invalid or unavailable local map tile", frappe.ValidationError)
