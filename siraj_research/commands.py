# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt
"""Bench commands for SIRAJ Research.

Loaded automatically by frappe's bench helper via ``{app}.commands``;
the module must expose a ``commands`` iterable (see
frappe/utils/bench_helper.py get_app_commands).

Usage:

    bench --site <site> siraj-research load-demo-data
    bench --site <site> siraj-research remove-demo-data
    bench --site <site> siraj-research isolate-demo-data
"""

from __future__ import annotations

import click
from frappe.commands import get_site, pass_context


@click.group("siraj-research")
@pass_context
def siraj_research(context):
    """SIRAJ Research dataset commands."""


def _with_site(context, fn):
    """Run ``fn`` inside an initialised site connection, then commit."""
    import frappe

    site = get_site(context)
    frappe.init(site=site)
    frappe.connect()
    try:
        result = fn()
        frappe.db.commit()
        return result
    finally:
        frappe.destroy()


@siraj_research.command("load-demo-data")
@pass_context
def load_demo_data(context):
    """Load the fictional [DEMO] dataset (idempotent, safe to re-run)."""

    def run():
        from siraj_research.setup.demo_data import seed_demo_data
        return seed_demo_data()

    return _with_site(context, run)


@siraj_research.command("remove-demo-data")
@pass_context
def remove_demo_data(context):
    """Remove every [DEMO] record (manifest first, tag sweep as fallback)."""

    def run():
        from siraj_research.setup.demo_data import teardown_demo_data
        return teardown_demo_data()

    return _with_site(context, run)


@siraj_research.command("isolate-demo-data")
@pass_context
def isolate_demo_data(context):
    """Report demo records per DocType and how to isolate them."""

    def run():
        from siraj_research.setup.demo_data import demo_status
        return demo_status()

    return _with_site(context, run)


#: frappe's bench helper collects ``module.commands`` (name -> command).
commands = [siraj_research]
