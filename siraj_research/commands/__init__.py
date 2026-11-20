"""Bench commands contributed by Siraj Research.

Frappe's bench CLI imports ``<app>.commands`` and registers every click
command in the module-level ``commands`` list. Keeping the imports lazy inside
``geo.py`` means a broken optional dependency cannot take down the whole bench
CLI.
"""

from siraj_research.commands.geo import commands as geo_commands

commands = [*geo_commands]

__all__ = ["commands"]
