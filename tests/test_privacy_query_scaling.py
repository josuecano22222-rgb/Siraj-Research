"""Synthetic query-shape regression, not performance or database measurements."""

import unittest

import test_reports


class PrivacyQueryScalingTests(unittest.TestCase):
	def run_report(self, count, unique, excluded=()):
		case = test_reports.ReportTest()
		case.setUp()
		f = case.frappe
		f.rows = {
			"Person": [{"name": f"p{i}"} for i in range(unique)],
			"Place": [{"name": "place"}],
			"Relationship": [
				{
					"name": f"r{i:05}",
					"subject_type": "Person",
					"subject": f"p{i % unique}",
					"object_type": "Place",
					"object": "place",
				}
				for i in range(count)
			],
		}
		original = f.get_list
		counts = {"relationship_pages": 0, "person_links": 0, "place_links": 0}

		def monitored(dt, **kwargs):
			if dt == "Relationship":
				counts["relationship_pages"] += 1
			elif dt == "Person" and "name" in kwargs.get("filters", {}):
				counts["person_links"] += 1
			elif dt == "Place" and "name" in kwargs.get("filters", {}):
				counts["place_links"] += 1
			rows = original(dt, **kwargs)
			return [row for row in rows if (dt, row["name"]) not in excluded]

		f.get_list = monitored
		_, rows = case.report("entity_relationship_graph").execute()
		return counts, rows

	def test_repeated_endpoints_are_cached_per_report_execution(self):
		for count in (1, 10, 1000):
			with self.subTest(edges=count):
				counts, rows = self.run_report(count, 1)
				self.assertEqual(len(rows), count)
				self.assertEqual((counts["person_links"], counts["place_links"]), (1, 1))
				self.assertEqual(counts["relationship_pages"], count // 200 + 1)

	def test_distinct_endpoints_require_distinct_checks(self):
		counts, rows = self.run_report(500, 500)
		self.assertEqual(len(rows), 500)
		self.assertEqual((counts["person_links"], counts["place_links"]), (500, 1))
		self.assertEqual(counts["relationship_pages"], 3)

	def test_list_hidden_endpoint_is_never_exposed_even_if_doc_allows(self):
		counts, rows = self.run_report(30, 3, excluded={("Person", "p1")})
		self.assertEqual(len(rows), 20)
		self.assertTrue(all(row["subject"] != "p1" for row in rows))
		self.assertEqual(counts["person_links"], 3)


if __name__ == "__main__":
	unittest.main()
