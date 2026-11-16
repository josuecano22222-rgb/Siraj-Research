# Consolidated imagery and asset input needed from the owner

No site files, image URLs, supplied packs, contracts or trademark permissions have been inspected by the agent. Do not place sensitive contracts, files, personal data or large map packs in Git. For detailed sources/notices and verified package hashes see `imagery-register.md`.

| Asset or use | Input/decision needed | Current state |
| --- | --- | --- |
| Local standard raster MBTiles (`private/siraj_maps/standard.mbtiles`) | Supply a trusted pack and provider/source, version/acquisition date, coverage/zoom, checksum, attribution, commercial and offline/device redistribution rights, expiry and limits; approve distribution. | Not supplied or verified. |
| Local aerial raster MBTiles (`private/siraj_maps/aerial.mbtiles`) | Same information separately for the imagery, underlying data and tile rendering. | Not supplied or verified. |
| Record attachments and external image URLs (Person, Institution, Place, Event, Military Unit and any site customizations) | Inventory actual images and their creators/providers, consent, permitted use, public/private access, commercial/offline rights, attribution and expiry. Identify any images to remove or replace. | Site contents unknown; no agent access. |
| Inline Explorer SVG icons and any derivative designs | Establish original authorship/provenance and redistribution rights, or approve replacement with independently licensed assets. | Provenance not established. |
| App/project authorship and license | Confirm actual copyright holder/year and redistribution authority; root license text has placeholders and original reference-app rights are not established. | Blocked pending clarification. |
| Frappe app-screen logo/branding | Confirm intended use and any applicable branding/trademark permissions for the installed version. | Trademark permission not independently verified. |
| External OSM interactive layer, if enabled | Decide whether to use it and verify policy, caching, attribution, privacy and applicable data/map rights; do not bulk-download public OSM tiles. | Canonical URL/attribution implemented; complete compliance not verified. |
| Site-specific themes, logos, maps or custom visual assets not present in this checkout | Identify locations and suppliers, license/attribution and use (including offline); review rights and privacy individually. | Unknown; needs local inventory. |

Bundled Natural Earth/world-atlas and Leaflet image bytes were matched to documented upstream packages; retain the applicable notices. That evidence does not grant rights to unrelated imagery or establish all production compliance. Offline map packs contain basemap only, not Explorer records. Supplying imagery does not authorize enabling downloads or deploying it.

## Optional isolated-site aggregate inventory

The new non-whitelisted `siraj_research.setup.imagery_inventory.inspect` is an **unverified helper** that reads at most 5,000 File records and 5,000 rows per known image-URL field; it returns aggregate URL/extension/privacy counts only, never filenames, paths, record names, hosts, URL tokens or file contents. It reports truncation and missing fields. It neither checks rights nor inventories site custom fields, packs, logos, themes, other apps or embedded assets. Counts and field presence can still be sensitive.

Only after separate explicit approval, on a verified isolated copy and after reviewing custom hooks and load, run:

```bash
bench --site <isolated-site> execute siraj_research.setup.imagery_inventory.inspect --kwargs '{"confirm":"ISOLATED-TEST-APPROVED"}'
```

Replace the placeholder with the actual isolated-site name. The helper requires the Administrator session and confirmation string; that string is not authorization. It has only stub tests, is not transactionally consistent, and `bench execute` or custom hooks may have side effects. Do not run it on a working or production site without separate approval. Review aggregate output before sharing; no asset or URL values are needed in chat.

For each real asset or pack, retain a **private** mapping of a random asset ID to the actual file/URL and evidence. A sanitized review sheet may contain only that random ID, broad asset category, provider/creator (if safe to disclose), license name/version, permitted commercial use, redistribution and offline terms, required attribution, expiration, evidence held yes/no and replacement decision. Do not include personal names, record identifiers, file paths, URL/query tokens, contracts or the image itself in chat or Git. Rights and consent must be checked per item; counts alone never prove licensing.
