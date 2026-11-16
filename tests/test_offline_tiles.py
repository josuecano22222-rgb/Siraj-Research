"""Actual SQLite MBTiles unit tests, not a Frappe/server integration test."""
from pathlib import Path
import sqlite3
import tempfile
import unittest

from siraj_research.utils import offline_tiles as tiles

PNG = b'\x89PNG\r\n\x1a\n' + b'test image bytes'


def create_pack(path, fmt='png', rows=None):
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE metadata (name TEXT, value TEXT)')
        db.executemany('INSERT INTO metadata VALUES (?, ?)', [('format', fmt), ('name', 'Test'), ('attribution', 'Example attribution')])
        db.execute('CREATE TABLE tiles (zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER, tile_data BLOB)')
        db.executemany('INSERT INTO tiles VALUES (?, ?, ?, ?)', rows or [(0, 0, 0, PNG), (1, 0, 1, PNG), (1, 1, 0, PNG)])


class OfflineTileTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.pack = self.root / 'map.mbtiles'
        create_pack(self.pack)

    def test_xyz_to_tms_and_missing_tiles(self):
        self.assertEqual(tiles.read_tile(self.pack, 1, 0, 0), (PNG, 'image/png'))
        self.assertIsNone(tiles.read_tile(self.pack, 1, 0, 1))
        self.assertEqual(tiles.read_tile(self.pack, 1, 1, 1), (PNG, 'image/png'))
        for args in [(-1, 0, 0), (1, -1, 0), (1, 2, 0), (23, 0, 0), (1, 0, True), ('1', 0, 0)]:
            with self.subTest(args=args), self.assertRaises(tiles.TilePackError): tiles.read_tile(self.pack, *args)

    def test_area_export_round_trip_and_no_overwrite(self):
        dest = self.root / 'subset.mbtiles'
        result = tiles.export_area(self.pack, dest, (-180, -85, 180, 85), 0, 1)
        self.assertEqual(result, {'tiles': 3, 'possible_tiles': 5, 'tile_bytes': 3 * len(PNG)})
        self.assertEqual(tiles.read_tile(dest, 1, 1, 1), (PNG, 'image/png'))
        with sqlite3.connect(dest) as db:
            self.assertEqual(db.execute("SELECT value FROM metadata WHERE name='attribution'").fetchone()[0], 'Example attribution')
        before = dest.read_bytes()
        with self.assertRaises(FileExistsError): tiles.export_area(self.pack, dest, (-180, -85, 180, 85), 0, 1)
        self.assertEqual(dest.read_bytes(), before)

    def test_dateline_does_not_double_count_world_tile(self):
        ranges, count = tiles.tile_ranges((170, -10, -170, 10), 0, 1)
        self.assertEqual(count, 5)
        self.assertEqual(ranges[0], (0, 0, 0, 0, 0))
        self.assertEqual(ranges[1], (1, 0, 1, 0, 1))
        dest = self.root / 'dateline.mbtiles'
        tiles.export_area(self.pack, dest, (170, -10, -170, 10), 0, 1)
        with sqlite3.connect(dest) as db:
            metadata = dict(db.execute('SELECT name, value FROM metadata'))
        self.assertEqual(metadata['bounds'], '-180,-10,180,10')
        self.assertEqual(metadata['siraj_requested_bounds'], '170,-10,-170,10')

    def test_limits_invalid_data_and_cleanup(self):
        dest = self.root / 'failed.mbtiles'
        with self.assertRaisesRegex(tiles.TilePackError, 'tile limit'):
            tiles.export_area(self.pack, dest, (-180, -85, 180, 85), 0, 5, max_tiles=10)
        self.assertFalse(dest.exists())
        with self.assertRaisesRegex(tiles.TilePackError, 'size or tile limit'):
            tiles.export_area(self.pack, dest, (-180, -85, 180, 85), 0, 0, max_tile_bytes=2)
        self.assertFalse(dest.exists())
        with self.assertRaises(tiles.TilePackError): tiles.tile_ranges((0, -90, 10, 10), 0, 1)
        with self.assertRaises(tiles.TilePackError): tiles.tile_ranges((0, 1, 0, 2), 0, 1)
        with self.assertRaises(tiles.TilePackError): tiles.tile_ranges((0, 1, 2, 3), 0, 1, max_tiles=100000)
        with sqlite3.connect(self.pack) as db:
            db.execute('UPDATE tiles SET tile_data=? WHERE zoom_level=0', (b'<svg>not an image</svg>',))
        with self.assertRaisesRegex(tiles.TilePackError, 'declared raster format'):
            tiles.export_area(self.pack, dest, (-180, -85, 180, 85), 0, 0)
        self.assertFalse(dest.exists())

    def test_duplicate_coordinates_are_not_silently_accepted(self):
        with sqlite3.connect(self.pack) as db:
            db.execute('INSERT INTO tiles VALUES (?, ?, ?, ?)', (0, 0, 0, PNG))
        with self.assertRaisesRegex(tiles.TilePackError, 'Duplicate'):
            tiles.read_tile(self.pack, 0, 0, 0)
        dest = self.root / 'duplicate.mbtiles'
        with self.assertRaises(tiles.TilePackError):
            tiles.export_area(self.pack, dest, (-180, -85, 180, 85), 0, 0)
        self.assertFalse(dest.exists())

    def test_vector_and_xyz_scheme_are_refused(self):
        with sqlite3.connect(self.pack) as db: db.execute("UPDATE metadata SET value='pbf' WHERE name='format'")
        with self.assertRaisesRegex(tiles.TilePackError, 'raster'): tiles.read_tile(self.pack, 0, 0, 0)
        with sqlite3.connect(self.pack) as db:
            db.execute("UPDATE metadata SET value='png' WHERE name='format'")
            db.execute("INSERT INTO metadata VALUES ('scheme', 'xyz')")
        with self.assertRaisesRegex(tiles.TilePackError, 'TMS'): tiles.read_tile(self.pack, 0, 0, 0)


if __name__ == '__main__': unittest.main()
