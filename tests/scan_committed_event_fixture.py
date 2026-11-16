"""Summarize Event candidates in committed app text; never inspect a site.

Run at the repository root. Reads `git archive HEAD` in memory, ignoring dirty
worktree edits in the scanned corpus. The scanner implementation is imported
from the working tree
 scanned source is never executed. Never writes files,
contacts Frappe or logs matching lines. Aggregate counts are not an exhaustive dependency inventory.
"""

import io
import json
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from collections import Counter

from siraj_research.setup.event_reference_review import discover

EXTENSIONS = {".py", ".js", ".json", ".sql", ".html", ".yaml", ".yml", ".csv", ".txt", ".md"}


def main():
	archive = subprocess.run(["git", "archive", "HEAD"], cwd=ROOT, check=True, stdout=subprocess.PIPE).stdout
	revision = subprocess.run(
		["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, stdout=subprocess.PIPE, text=True
	).stdout.strip()
	files, skipped = [], 0
	with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tree:
		for member in tree:
			path = Path(member.name)
			if (
				not member.isfile()
				or not member.name.startswith("siraj_research/")
				or path.suffix.lower() not in EXTENSIONS
			):
				continue
			stream = tree.extractfile(member)
			try:
				text = stream.read().decode("utf-8")
			except UnicodeError:
				skipped += 1
				continue
			files.append({"path": member.name, "text": text})
	result = discover(files)
	print(
		json.dumps(
			{
				"revision": revision,
				"files_scanned": result["files_scanned"],
				"findings": len(result["findings"]),
				"issues": len(result["issues"]),
				"skipped_invalid_utf8": skipped,
				"categories": dict(sorted(Counter(x["category"] for x in result["findings"]).items())),
				"kinds": dict(sorted(Counter(x["kind"] for x in result["findings"]).items())),
				"execution_ready": False,
				"warning": "Committed app text candidates only, not exhaustive, classified or site evidence.",
			},
			indent=2,
		)
	)


if __name__ == "__main__":
	main()
