"""``bench geo`` — seeding, auditing, spatial setup and offline verification.

Examples::

    bench --site research.local geo seed-levels
    bench --site research.local geo seed-core --report-dir /var/reports
    bench --site research.local geo import-csv ./lb-villages.csv --level 4 --country LB
    bench --site research.local geo audit --country IQ --fail-on-issues
    bench --site research.local geo postgis-init
    bench --site research.local geo verify-offline --lat 33.3152 --lon 44.3661

Every command prints one JSON document, so output can be captured by CI.
``bench --site <site> execute siraj_research.<module>.<function>`` remains
available for the same functions; these commands only add argument parsing,
site handling and report paths.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click


def _site(ctx) -> str:
    sites = list((ctx.obj or {}).get("sites") or [])
    if not sites:
        raise click.ClickException("Pass --site <site> (or 'bench use <site>' first).")
    if len(sites) > 1:
        raise click.ClickException("Run geo commands against one site at a time.")
    return sites[0]


def _connect(ctx):
    import frappe

    site = _site(ctx)
    frappe.init(site=site)
    frappe.connect()
    try:
        frappe.set_user("Administrator")
    except Exception:  # pragma: no cover
        pass
    return frappe


def _report_dir(override: str | None) -> str:
    if override:
        return str(Path(override).expanduser().resolve())
    import frappe

    return str(Path(frappe.get_site_path("private", "files", "siraj-geo-reports")))


def _echo(payload: Any) -> None:
    click.echo(json.dumps(payload, indent=2, default=str, ensure_ascii=False))


@click.group("geo")
def geo():
    """SIRAJ geographic hierarchy: seed, import, audit, verify."""


@geo.command("seed-levels")
@click.option("--report-dir", default=None, help="Directory for rejection/checkpoint reports.")
@click.pass_context
def seed_levels(ctx, report_dir):
    """Create the Admin Level catalogue and per-country level configurations."""
    _connect(ctx)
    from siraj_research.geo_seeding import seed_admin_levels, seed_country_level_configs

    report = _report_dir(report_dir)
    _echo(
        {
            "levels": seed_admin_levels(),
            "country_configs": seed_country_level_configs(report_dir=report),
            "reports": report,
        }
    )
    import frappe

    frappe.destroy()


@geo.command("seed-core")
@click.option("--country", default=None, help="Optional ISO code to limit the reference hierarchy seed.")
@click.option("--no-reference", is_flag=True, default=False, help="Skip the bundled reference hierarchy.")
@click.option("--report-dir", default=None)
@click.pass_context
def seed_core(ctx, country, no_reference, report_dir):
    """Seed levels → configurations → reference hierarchy → ancestry (idempotent)."""
    _connect(ctx)
    from siraj_research.geo_seeding import seed_core as run

    _echo(run(country=country, with_reference=not no_reference, report_dir=_report_dir(report_dir)))
    import frappe

    frappe.destroy()


@geo.command("seed-demo")
@click.option("--skip-demo", is_flag=True, default=False, help="Only create Geographic Administration rows.")
@click.option("--limit", default=500, show_default=True, help="Max rows per level for GA back-fill.")
@click.option("--report-dir", default=None)
@click.pass_context
def seed_demo(ctx, skip_demo, limit, report_dir):
    """Seed the full demo dataset, then link it to Geographic Administration."""
    _connect(ctx)
    from siraj_research.geo_seeding import seed_geographic_administration

    payload: dict[str, Any] = {}
    if not skip_demo:
        from siraj_research.setup.demo_data import seed_demo_data

        payload["demo"] = seed_demo_data()
    payload["geographic_administration"] = seed_geographic_administration(
        limit=limit, report_dir=_report_dir(report_dir)
    )
    _echo(payload)
    import frappe

    frappe.destroy()


@geo.command("import-csv")
@click.argument("path", type=click.Path(exists=True, dir_okay=False))
@click.option("--level", required=True, type=int, help="1=Governorate … 5=Community.")
@click.option("--country", default=None, help="ISO code or Country name (required for level 1).")
@click.option("--format", "fmt", default=None, type=click.Choice(["csv", "geojson", "json"]))
@click.option("--batch-size", default=500, show_default=True)
@click.option("--offset", default=0, show_default=True, help="Resume after this many processed rows.")
@click.option("--dry-run", is_flag=True, default=False)
@click.option("--report-dir", default=None)
@click.pass_context
def import_csv(ctx, path, level, country, fmt, batch_size, offset, dry_run, report_dir):
    """Import custom local CSV/GeoJSON rows for one level (parent-first)."""
    _connect(ctx)
    from siraj_research.geo_seeding import import_hierarchy_file

    summary = import_hierarchy_file(
        path,
        level,
        country=country,
        fmt=fmt,
        batch_size=batch_size,
        offset=offset,
        dry_run=dry_run,
        report_dir=_report_dir(report_dir),
    )
    _echo(summary)
    import frappe

    frappe.destroy()


@geo.command("audit")
@click.option("--country", default=None, help="Limit the audit to one country.")
@click.option("--report-dir", default=None)
@click.option("--fail-on-issues", is_flag=True, default=False, help="Exit non-zero when anything is rejected.")
@click.pass_context
def audit(ctx, country, report_dir, fail_on_issues):
    """Audit hierarchy integrity (skipped levels, holes, bad geometry)."""
    _connect(ctx)
    from siraj_research.geo_seeding import audit_hierarchy

    summary = audit_hierarchy(country=country, report_dir=_report_dir(report_dir))
    _echo(summary)
    import frappe

    frappe.destroy()
    if fail_on_issues and not summary.get("passed"):
        raise SystemExit(1)


@geo.command("backfill-ancestry")
@click.option("--batch-size", default=500, show_default=True)
@click.pass_context
def backfill_ancestry_cmd(ctx, batch_size):
    """Recompute ancestry_path / ancestry_labels / hierarchy_level."""
    _connect(ctx)
    from siraj_research.geo_seeding import backfill_ancestry

    _echo(backfill_ancestry(batch_size=batch_size))
    import frappe

    frappe.destroy()


@geo.command("seed-ga")
@click.option("--limit", default=500, show_default=True)
@click.option("--report-dir", default=None)
@click.pass_context
def seed_ga(ctx, limit, report_dir):
    """Create Geographic Administration rows for existing hierarchy records."""
    _connect(ctx)
    from siraj_research.geo_seeding import seed_geographic_administration

    _echo(seed_geographic_administration(limit=limit, report_dir=_report_dir(report_dir)))
    import frappe

    frappe.destroy()


@geo.command("postgis-init")
@click.pass_context
def postgis_init(ctx):
    """Create the PostGIS extension, geometry column and GiST index."""
    _connect(ctx)
    from siraj_research import geo_postgis

    _echo(
        {
            "extension": geo_postgis.ensure_extension(),
            "schema": geo_postgis.ensure_schema(),
            "health": geo_postgis.health(),
        }
    )
    import frappe

    frappe.destroy()


@geo.command("postgis-backfill")
@click.option("--dataset", default=None, help="Limit to one Boundary Dataset code.")
@click.option("--batch-size", default=500, show_default=True)
@click.pass_context
def postgis_backfill(ctx, dataset, batch_size):
    """Copy WKB hex into the PostGIS geometry column (resumable)."""
    _connect(ctx)
    from siraj_research import geo_postgis

    _echo(geo_postgis.backfill_geometries(dataset=dataset, batch_size=batch_size))
    import frappe

    frappe.destroy()


@geo.command("postgis-health")
@click.pass_context
def postgis_health(ctx):
    """Report PostGIS availability, schema and geometry counts."""
    _connect(ctx)
    from siraj_research import geo_postgis

    _echo(geo_postgis.health())
    import frappe

    frappe.destroy()


@geo.command("verify-offline")
@click.option("--lat", default=33.3152, show_default=True)
@click.option("--lon", default=44.3661, show_default=True)
@click.option("--expect", "expect_levels", default="", help="Comma-separated chain fields that must resolve.")
@click.pass_context
def verify_offline(ctx, lat, lon, expect_levels):
    """Resolve a point with outbound networking blocked and report the checks."""
    _connect(ctx)
    from siraj_research.offline_verify import run

    expected = [field.strip() for field in expect_levels.split(",") if field.strip()]
    report = run(lat, lon, expect_levels=expected or None)
    _echo(report)
    import frappe

    frappe.destroy()
    if not report.get("passed"):
        raise SystemExit(1)


@geo.command("benchmark")
@click.option("--dataset", default=None)
@click.option("--repeats", default=20, show_default=True)
@click.option("--lat", "latitude", default=None, type=float)
@click.option("--lon", "longitude", default=None, type=float)
@click.pass_context
def benchmark(ctx, dataset, repeats, latitude, longitude):
    """Time local resolution (target: < 200 ms p95)."""
    _connect(ctx)
    from siraj_research import geo_postgis

    points = [(latitude, longitude)] if latitude is not None and longitude is not None else None
    _echo(geo_postgis.benchmark(dataset, points=points, repeats=repeats))
    import frappe

    frappe.destroy()


@geo.command("resolve")
@click.option("--lat", required=True, type=float)
@click.option("--lon", required=True, type=float)
@click.option("--online", "use_online", is_flag=True, default=False,
              help="Allow the configured online fallback (default: offline only).")
@click.pass_context
def resolve(ctx, lat, lon, use_online):
    """Resolve one coordinate exactly as a form would and print the JSON."""
    _connect(ctx)
    from siraj_research.api.geo_resolve import resolve_point

    _echo(resolve_point(lat, lon, use_online=int(use_online)))
    import frappe

    frappe.destroy()


commands = [geo]
