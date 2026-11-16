# Offline basemap viewer prototype

This is an administrative prototype, not a complete interactive download feature. No imagery is supplied.

## Administrative offline package prototype

An administrator can build a **basemap-only** ZIP from a trusted, licensed local raster pack using the Python module below. This is a local command, not a Frappe API or interactive area-selection/download feature. Bounds are west, south, east, north in degrees, limited to Web Mercator (approximately ±85.0511° latitude); west greater than east crosses the antimeridian. The output must not already exist. Example only, with paths and bounds chosen by the administrator:

```sh
python -m siraj_research.utils.offline_viewer /private/path/aerial.mbtiles /private/path/area.zip \
  --bounds 43 32 45 34 --minzoom 4 --maxzoom 10 --confirm-redistribution-rights
```

The explicit flag is the administrator's confirmation that the source license permits distribution to disconnected devices. Confirm permitted area, resolution, retention and required attribution before creating or sharing any package. This command does not download imagery and must never be used to scrape public tile services. The source and output paths must be protected; the ZIP contains imagery in ordinary unencrypted files. Share only with authorized people using an approved secure transfer, and protect the extracted files and device. Temporary SQLite files are created in the operating system's temporary directory, whose storage and backups must also be suitable for the imagery. Interrupted or killed processes may leave temporary or partial files for an administrator to remove securely. No automatic revocation or expiry is provided.

Extract the ZIP completely and open `index.html` on the device. The viewer pans and zooms, fits the selected area, accepts decimal coordinates (including Arabic and Persian digits), shows clicked coordinates, and provides approximate distance and polygon-area measurements with undo and clear. Measurements use spherical approximations, are not survey-grade, and may be misleading for very large or self-intersecting polygons; changing modes clears the current geometry. The interface supports English and Arabic; it does not contain or sync SIRAJ records, edit them, or provide the Explorer's measurement and analysis tools. It makes no intentional internet requests. It uses local Leaflet assets and packaged tile images; some browsers or device policies may restrict local files, and mobile behavior has not been verified. Missing tiles produce empty areas. Tile availability and resolution depend on the provided pack, and a requested area can contain only partial coverage. The package contains no generalized fallback unless that fallback is included in the supplied tiles.

Exports are limited to 25,000 possible tiles and 200 MiB of actual tile payloads, with additional disk space needed for SQLite, the ZIP, extraction, and filesystem overhead. These are not full disk, time, concurrency or per-user quotas. Package creation is synchronous and is not intended to run concurrently on a live Frappe web worker. It is not a sandbox for malicious databases or an authorization layer. **There is still no user-facing area selection or download endpoint, and no disconnected Explorer with records**. Do not expose this tool as a web endpoint without a reviewed rights, security, quota, lifecycle and privacy design.


A synthetic package was smoke-tested with Chromium from a local `file://` URL. No real imagery, mobile device, Frappe integration or production-scale workload has been verified.
