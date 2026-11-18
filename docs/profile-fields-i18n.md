# Profile fields & tables: presentation and i18n

The Explorer's **Fields** tab used to be a direct dump of a DocType's field
order. It mixed English labels with server-translated values, lost the
`Tab Break` boundary, and rendered child tables as `[object Object]`. The
profile presentation engine replaces that with a declared, testable layout and
one translation boundary.

## Architecture

```
DocType meta / document
        │
        ▼
api.entity_profile / api.relationship_profile   (permission-filtered payload)
        │
        ▼
profile_presentation.organise_profile           (pure Python, no Frappe import)
        │   semantic groups · stable ids · typed values · source strings
        ▼
public/js/siraj-profile-fields.js               (window.SirajProfileFields)
        │   __() once, in the UI language · RTL-aware · sortable tables
        ▼
sx-panel Fields tab / Relationship Evidence tab
```

### 1. Server: keep the source, do not pre-translate

`_fmt_value` no longer calls `frappe._()` on `Select` options or on `Check`
fields. A profile field now carries:

| key | meaning |
|---|---|
| `label` / `label_source` | raw DocField label (the `__()` key) |
| `value` | raw recorded value (boolean stays boolean, links stay objects) |
| `value_source` | safe textual form of the value (`never [object Object]`) |
| `value_kind` | `link`, `attach`, `enum`, `boolean`, `date`, `number`, `url`, `json`, `text` |
| `translatable_value` | only controlled vocabulary may go through `__()` |
| `i18n_key` | stable source string for translation harvesting |
| `group` / `section.id` | semantic group, independent of DocType field order |

`Tab Break` starts a new source section; `Table` fields are excluded from the
scalar list and collected into `children` with an explicit `column_order`
(taken from the child DocType). The old leak of `Completeness (%)` into
`External identifiers` and the `[object Object]` cells are both gone.

### 2. Semantic organisation

`profile_presentation.SECTION_BLUEPRINTS` declares the canonical order:

```
identity → life → origin → classification → service → public →
relationship → endpoints → location → timing → provenance →
evidence → identifiers → quality → other
```

Matching is deterministic: exact source-heading alias, then explicit
fieldname membership, then keyword fallback. A field is always moved to its
own blueprint group even when its DocType placed it under another heading.
Child tables carry a `section` id (`social_accounts → public`,
`evidence → evidence`, `external_identifiers → identifiers`, …) so the client
interleaves them directly after their group. A group with only a table still
gets a section header.

### 3. Client: one translation boundary

`SirajProfileFields.mountFields()` accepts the profile and renders:

* a **Translated / Source text / Both languages** segmented control. The
  choice is persisted per user in `localStorage` and does not refetch data;
* a live **filter** across field labels, values and table rows;
* **typed cells**: links become buttons that fly to a mapped pin or open the
  form, URLs become safe anchors, enums/booleans go through `__()`, nested
  objects become key/value chips;
* `dir="auto"` on every value (Arabic data stays RTL inside an English UI);
* demo markers `[DEMO]` as a small translated badge, with the raw value kept
  in `data-source-value` and in `title`;
* sortable, column-union tables with translated headers and a truncation note;
* `data-i18n-source` / `data-i18n-key` on all generated labels so a crawler
  (or translator using the browser) can harvest exactly the strings in use.

`mountTables()` renders only selected child tables; the Relationship panel
uses it for its Evidence tab. Both controllers expose `setMode`, `applyFilter`,
`render`, `getData` and `destroy`.

The client also normalises older (v1) payloads with `normaliseProfile()`, so a
stale cached response cannot reintroduce the old layout.

### 4. Translation catalogue

New UI strings were added to `siraj_research/translations/ar.csv` (Excel/CSV
format: `source,translation`). Runtime translation uses Frappe's `window.__()`
with a safe identity fallback in tests and offline contexts. Data values that
are not controlled vocabulary (names, notes, URLs) are deliberately **not**
passed to `__()`.

To add a string:

1. use `__(source)` client-side (or emit it as a source string from
   `profile_presentation.py`);
2. add `source,Arabic translation` to `translations/ar.csv`;
3. keep `data-i18n-source` intact — the source/translation toggle depends on it.

## Tests

* `tests/test_profile_presentation.py` — pure Python: ordering, Tab Break
  leak, table extraction, column unions, i18n metadata, catalogue contents.
* `tests/test_profile_fields.js` — jsdom: bilingual toggling, demo badges,
  RTL, URL sanitising, table sorting/filtering, `sectionFactory` integration
  and v1 fallback. Run with `node tests/test_profile_fields.js` (also included
  in `npm run test:js`).
* `tests/test_explorer_sections.js` — full Explorer smoke test with mocked
  Frappe/Leaflet/vis: verifies the *other* tabs keep the same conventions —
  translated workflow states and relationship types in both headers and
  Overview, translated outbound DocField labels in Connections, controlled
  Location values with their source underneath, direction-aware activity
  rows, safe attachment URLs, and the Relationship Endpoints tab.

### Other sections at a glance

| Section | Organisation / i18n behaviour |
|---|---|
| Overview | Stable `meta` / `network` / `actions` sections; workflow state goes through `__()`; values are `dir=auto`. |
| Connections | Relationship type is translated (source kept in `title`), outbound field labels use `__()`, linked titles stay archive data; empty tabs no longer show a `0` badge. |
| Location | `precision` and `method` are rendered as controlled vocabulary: translated value with the recorded option beneath, matching the Fields tab. |
| Activity | Attachment URLs are validated before becoming anchors; comments and versions are `dir=auto`; unsafe URLs remain plain text. |
| Relationship panel | Edge heading and status chips translate; the Fields tab is engine-mounted; Evidence uses table-only mode; Endpoints retains translated role labels. |
