# Country → Community cascading in Desk forms

Every form that exposes the location hierarchy (Person, Institution, Place,
Research Event, Siraj Event, Military Unit, Operational Deployment, Explorer,
and the hierarchy DocTypes themselves) now supports two directions of
selection:

- **Downward:** select **Country**, then the **Governorate** dropdown contains
  only governorates of that country. The same restriction continues for
  District → Municipality → Village → Community. The next-level choices are
  also shown as small buttons inside the **Location** section, so the user can
  see the available values without guessing.
- **Global until narrowed:** with **no parent selected**, a level's dropdown
  and the status chips list **every** place at that level across all countries.
  As soon as a parent is chosen the list snaps to that parent's children only.
- **Upward:** select a lower level first (for example a Community or a
  province). The form reads that record's own Link fields and fills Country,
  Governorate, District, Municipality and Village automatically — empty
  higher fields are written immediately; human-entered conflicts open the
  Keep/Replace dialog.

Empty levels stay empty. The system never invents a hierarchy row or writes a
raw code/label into a Link field.

## Where the data comes from

1. **Local bench (authoritative):** `siraj_research.geo_cascade.cascade`
   reads the same hierarchy DocTypes the Link fields point at. It creates
   nothing and makes no external request. This is normal Desk operation.
2. **Same-origin offline package (fallback):** if the local API cannot be
   reached, `siraj-cascade-core.js` builds an index from
   `/assets/siraj_research/data/geo-package.json` (format 2 adds the Country
   code to each polygon row). No OSM, Esri, Nominatim or GeoNames host is
   contacted.

## Human values are protected

When an automatically implied ancestor differs from a value already on the
form, a **Keep existing / Replace higher levels** dialog is shown. Empty
fields are filled either way. Changing or clearing a parent clears only the
now-invalid descendant fields, with no silent rewrite of unrelated data.

All hierarchy controls, map controls and the cascade status remain together
in one **Location** section (enforced by `siraj-location-layout.js`).

## Re-export after upgrading

Because the package format changed to 2, re-export the static asset once:

```bash
cd ~/frappe-bench
bench --site frappe.com execute siraj_research.api.geo_package.export_offline_package
```

The browser will then load the new `OSM-IL-PS:2.2` etag on reload.
