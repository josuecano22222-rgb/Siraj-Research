"""Offline ZIP builder tests with real SQLite and ZIP files, no Frappe."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from zipfile import ZipFile

from siraj_research.utils.offline_tiles import TilePackError
from siraj_research.utils.offline_viewer import create_package
from test_offline_tiles import create_pack, PNG


class OfflineViewerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'source.mbtiles'
        self.output = self.root / 'offline.zip'
        create_pack(self.source)

    def package(self, bounds=(-180, -85, 180, 85), **kwargs):
        return create_package(self.source, self.output, bounds, 0, 1, **kwargs)

    def test_package_contains_only_local_assets_and_xyz_tiles(self):
        summary = self.package(redistribution_allowed=True)
        self.assertEqual(summary['tiles'], 3)
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o600)
        with ZipFile(self.output) as z:
            names = set(z.namelist())
            self.assertTrue({'index.html', 'viewer.js', 'leaflet/leaflet.js', 'leaflet/leaflet.css',
                             'leaflet/LICENSE', 'tiles/0/0/0.png', 'tiles/1/0/0.png', 'tiles/1/1/1.png'} <= names)
            self.assertEqual(z.read('tiles/1/0/0.png'), PNG)
            config = json.loads(z.read('config.js').decode().removeprefix('window.SIRAJ_OFFLINE_MAP = ').strip().removesuffix(';'))
            self.assertEqual(config['center'], [0, 0])
            self.assertEqual(config['bounds'], [-180, -85, 180, 85])
            self.assertEqual(config['attribution'], 'Example attribution')
            self.assertNotIn('https://', z.read('viewer.js').decode())

    def test_rights_limits_cleanup_and_no_overwrite(self):
        with self.assertRaises(TilePackError): self.package()
        self.assertFalse(self.output.exists())
        with self.assertRaises(TilePackError): self.package((0, 1, 0, 2), redistribution_allowed=True)
        self.assertFalse(self.output.exists())
        with self.assertRaisesRegex(TilePackError, 'No tiles'):
            create_package(self.source, self.output, (10, 1, 11, 2), 5, 5, redistribution_allowed=True)
        self.assertFalse(self.output.exists())
        self.output.write_bytes(b'existing')
        with self.assertRaises(FileExistsError): self.package(redistribution_allowed=True)
        self.assertEqual(self.output.read_bytes(), b'existing')

    def test_attribution_is_data_not_inline_html(self):
        with sqlite3.connect(self.source) as db:
            db.execute("UPDATE metadata SET value=? WHERE name='attribution'", ('</script><script>alert(1)</script>',))
        self.package((170, -10, -170, 10), redistribution_allowed=True)
        with ZipFile(self.output) as z:
            self.assertIn('attribution.textContent = c.attribution', z.read('viewer.js').decode())
            config = json.loads(z.read('config.js').decode().removeprefix('window.SIRAJ_OFFLINE_MAP = ').strip().removesuffix(';'))
            self.assertEqual(config['center'][1], -180)

if __name__ == '__main__':
    unittest.main()
