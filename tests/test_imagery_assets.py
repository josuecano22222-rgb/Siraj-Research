"""Provenance regression for bundled visual bytes; not a legal rights audit."""

import hashlib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "siraj_research/public"
IMAGES = {
	"layers.png": "1dbbe9d028e292f36fcba8f8b3a28d5e8932754fc2215b9ac69e4cdecf5107c6",
	"layers-2x.png": "066daca850d8ffbef007af00b06eac0015728dee279c51f3cb6c716df7c42edf",
	"marker-icon.png": "574c3a5cca85f4114085b6841596d62f00d7c892c7b03f28cbfa301deb1dc437",
	"marker-icon-2x.png": "00179c4c1ee830d3a108412ae0d294f55776cfeb085c60129a39aa6fc4ae2528",
	"marker-shadow.png": "264f5c640339f042dd729062cfc04c17f8ea0f29882b538e3848ed8f10edb4da",
}


def sha(path):
	return hashlib.sha256(path.read_bytes()).hexdigest()


class ImageryAssetsTest(unittest.TestCase):
	def test_leaflet_images_match_recorded_package_hashes(self):
		folder = PUBLIC / "vendor/leaflet/images"
		self.assertEqual({p.name for p in folder.iterdir() if p.is_file()}, set(IMAGES))
		for name, digest in IMAGES.items():
			with self.subTest(name=name):
				self.assertEqual(sha(folder / name), digest)
		self.assertTrue((PUBLIC / "vendor/leaflet/LICENSE").is_file())

	def test_world_overview_and_notice_present(self):
		self.assertEqual(
			sha(PUBLIC / "vendor/world-atlas/countries-110m.json"),
			"2516c915867c7baf18ddec727aec46c315541a07cfb3d79a6559b05d5e94eee8",
		)
		self.assertTrue((PUBLIC / "vendor/world-atlas/LICENSE").is_file())

	def test_no_unregistered_standalone_raster_or_svg_in_app_public(self):
		extensions = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico", ".avif", ".tif", ".tiff"}
		found = {
			p.relative_to(PUBLIC).as_posix()
			for p in PUBLIC.rglob("*")
			if p.is_file() and p.suffix.lower() in extensions
		}
		expected = {"vendor/leaflet/images/" + name for name in IMAGES}
		self.assertEqual(
			found, expected, "Update the licensing register and provenance checks for new assets"
		)


if __name__ == "__main__":
	unittest.main()
