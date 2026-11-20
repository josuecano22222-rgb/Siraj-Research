# 3. Demo data

The demo dataset exists to prove the model end to end: a person is linked to a
military unit, the unit is deployed to a place, the place sits inside a
governorate, the governorate has a level label, and every claim carries
evidence and a source. It is **fiction**, clearly tagged, and never installed
automatically.

## 3.1 What gets created

Source: `siraj_research/setup/demo_data.py` (1 571 lines). Every top-level record
carries the `[DEMO]` tag **appended** to its display field, e.g.
`Baghdad [DEMO]`, `Iraqi Ground Forces [DEMO]`; teardown matches on that tag.

| Group | Count | Coverage highlights |
|---|---|---|
| Places | 50+ | Iraq country, 10+ cities, military bases, mosques/shrines, universities, archaeological sites, government buildings; each with coordinates, precision, method, uncertainty radius and workflow state |
| Sources | 14 | encyclopedia, report, book, archive document, website, press release, interview, newspaper, journal article, thesis, map, photograph, database — across every reliability tier |
| Institutions | 12 | ministry, military college, university, research centre, archive, museum, association, media, international body |
| Persons | 22 | officer chain from Chief of Staff to battalion, retired officer, deceased historical figure, academics, archivists, journalists, historians; careers across postings |
| Command regions | 6 | Places of type `command_region` spanning Iraq |
| Division-level units | 4 | ISF and KRG |
| Unit classifications | 3 | Mechanized Infantry, Armored, Special Operations |
| Armaments | 10 | Weapons, Vehicles, Artillery, Aircraft, Communications |
| Military units | 14 | group nodes + leaf brigades/battalions; statuses Active, Training, Standby, Reserve, Reorganizing, Stand-down, Mobilized, Disbanded, Attached |
| Deployments | 8 | Active, Completed, Suspended, Planned, including historical/ISIS-era |
| Training exercises | 5 | Exercise, Course, Certification, Drill, Joint Exercise; all assessment tiers |
| Missions | 4 | Ongoing, Executed, Cancelled, Planned |
| Research events | 18 | birth, death, founding, merger, closure, conference, appointment, publication, migration, dispute, celebration, destruction, reform, other |
| Relationships | 70+ | 20+ relationship types and every subject/object endpoint combination |
| Child rows | many | Leadership Quality Assessments, Social Accounts, External Identifiers, Evidence on every record; workflow states across Draft → Published → Disputed → Archived |

The demo deliberately includes **incomplete records** (missing coordinates,
`(0, 0)`, a single zero coordinate, an uncertainty radius, dates with
year-only precision) so that list views, maps and the resolver's edge-case
handling can be exercised without inventing test scripts.

## 3.2 Prerequisites

1. The app is installed and migrated (chapter 1).
2. Core data exists — the demo looks up `Place Type`, `Source Type`, `Country`
   `Iraq`, `Military Branch`, etc. If a lookup is missing the helper returns
   `None` and the affected record is skipped with a printed warning rather than
   crashing halfway.

```bash
bench --site research.local geo seed-core --country IQ
```

3. **Use a non-production site.** These are real documents: they appear in
   lists, counts, searches, exports and dashboards, and normal hooks run. There
   is no demo-only database.

## 3.3 Seed

```bash
cd ~/frappe-bench

# Full demo + Geographic Administration rows
bench --site research.local geo seed-demo

# Demo only, no GA back-fill
bench --site research.local execute siraj_research.setup.demo_data.seed_demo_data

# GA rows only (e.g. after importing real boundaries)
bench --site research.local geo seed-demo --skip-demo --limit 5000
```

`geo seed-demo` prints its own summary and then the JSON result:

```text
SIRAJ extensive DEMO data seeded:
  places                    52
  sources                   14
  institutions              12
  persons                   22
  command_region_places      6
  division_units             4
  unit_classifications       3
  armaments                 10
  military_units            14
  deployments                8
  training_exercises         5
  missions                   4
  research_events           18
  relationships             74
  social_platforms           4
  external_id_schemes        3
  tag              [DEMO]
```

Counts come from the run, not from constants; the list above is the shape to
expect, not an assertion. The command is **idempotent**: `_add()` checks for an
existing record before inserting, so a second run only fills gaps.

## 3.4 What the demo proves geographically

The demo is the fastest way to see the hierarchy contract working:

* `Place` rows carry `country` / `governorate` / `district` and a `Geographic
  Administration` link. Example: **Baghdad** at `33.3152, 44.3661` is linked to
  `Iraq → IQ-BG` (Baghdad), and its child `Ministry of Defence HQ`
  (`33.3300, 44.4000`) is linked to district **Karkh** (`IQ-BG-KR`).
* `geo_doc_events.auto_fill_hierarchy` fills only *empty* ancestors on save. It
  never overwrites an explicit choice, so an operator can correct a village
  without the hook fighting back.
* A `Military Unit` has `country`, `governorate` and linked command-region
  places; `Operational Deployment` links a unit to a place, and the deployment's
  hierarchy is derived from that place.
* `Research Event` rows use the same seven coordinate-bearing DocTypes, so the
  custom `geographic_administration` field is present on each of them after the
  v1.2 patch.

Verify the chain without opening the UI:

```python
# bench --site research.local console
import frappe
place = frappe.get_doc("Place", {"name_en": "Baghdad [DEMO]"})
print(place.country, place.governorate, place.district)
print(place.ancestry_path, "|", place.ancestry_labels)
# Iraq IQ-BG None
# Iraq/IQ-BG | Iraq › Baghdad
```

(`name_en` values follow the demo's naming: each demo name is suffixed with
`[DEMO]`, so `frappe.get_all("Place", filters={"name_en": ["like", "%Baghdad%"]})`
is the safe lookup.)

## 3.5 Verify the linked geography

```bash
# How many GA rows exist, and from which source
bench --site research.local execute frappe.client.get_count \
  --kwargs '{"doctype":"Geographic Administration"}'

bench --site research.local execute frappe.get_all \
  --kwargs '{"doctype":"Geographic Administration","fields":["code","hierarchy_level","resolution_source"],"limit_page_length":5}'
```

Expected: a row per distinct chain, `code` starting `GA:` followed by the
ancestry path, `hierarchy_level` equal to the deepest populated level, and
`resolution_source = "manual"` for demo rows.

Resolver check with the demo coordinates (needs an imported boundary dataset,
see chapter 4):

```bash
bench --site research.local geo resolve --lat 33.3152 --lon 44.3661
```

The result should name `Iraq` at level 0 and `Baghdad` at level 1; deeper levels
depend on which polygons the dataset contains. Demo *records* do not create
polygons, so a coordinates-only site answers
`{"resolved": false, "reason": "no_dataset"}` — by design.

## 3.6 Teardown

```bash
bench --site research.local execute siraj_research.setup.demo_data.teardown_demo_data
```

Teardown deletes only records whose display field contains `[DEMO]`, in
dependency order:

1. children and evidence (`Relationship`, `Person Position`, `Leadership Quality
   Assessment`, `Social Account`, `Evidence`, `External Identifier`,
   `Unit Armament Holding`),
2. operations (`Operational Deployment`, `Training Exercise`, `Mission`),
3. `Research Event`, `Military Unit`, `Armament`,
4. `Person`, `Institution`, `Source`, `Place`,
5. `Unit Classification`, plus demo-created `Social Platform` / `External ID
   Scheme` rows whose code ends in `_demo`.

It prints `Removed N DEMO records.` Records you created yourself are untouched —
unless you edited a demo record's tag, in which case it is no longer recognised
as demo data. `Geographic Administration` rows created by `seed-demo` are
**not** deleted (they may now be referenced by real records); remove them
explicitly if you want a pristine site:

```bash
bench --site research.local execute frappe.db.delete \
  --kwargs '{"doctype":"Geographic Administration","filters":{"resolution_source":"manual"}}'
```

That last command is destructive and shown only for a scratch site.

## 3.7 Demo vs. the optional synthetic fixture

`setup/test_data.py` is a **different, paused** fixture (50 DocTypes, `TEST`
markers). It is blocked by the `Event` DocType collision with Frappe's calendar
`Event` and is documented in `docs/test-data.md`. Do not run it; the demo
dataset above is the supported, integrated data set.
