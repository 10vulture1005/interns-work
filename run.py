"""Command-line entrypoint.

    python run.py discover   # mine datasets + brute-force companies.txt -> companies.json
    python run.py harvest    # probe data/candidates.json -> companies.json
    python run.py update     # fetch -> filter -> store -> publish everything
    python run.py all        # discover + harvest + update
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from intern_engine import (  # noqa: E402
    dashboard,
    discover,
    harvester,
    pipeline,
    publish,
    readme,
)


def cmd_discover() -> None:
    companies, n_found = discover.discover()
    print(f"Discovered {n_found} new tokens.")
    print(f"Company list now has {len(companies)} companies -> data/companies.json")
    by_ats: dict[str, int] = {}
    for c in companies:
        by_ats[c["ats"]] = by_ats.get(c["ats"], 0) + 1
    for ats, n in sorted(by_ats.items()):
        print(f"  {ats:<16} {n}")


def cmd_harvest() -> None:
    found, candidates = harvester.harvest()
    print(f"Harvested {len(found)}/{len(candidates)} candidates -> data/companies.json")


def cmd_update() -> None:
    if not os.path.exists(os.path.join("data", "companies.json")):
        print("No data/companies.json yet — run `python run.py discover` first.")
        sys.exit(1)
    stats, store_data, new_ids = pipeline.run_update()
    summary = readme.generate(store_data)
    dashboard.generate(store_data, stats)
    feed_entries = publish.write_feed(store_data)
    publish.write_api(store_data, stats)
    print("Update complete:")
    for k, v in stats.items():
        if isinstance(v, (int, float, str)):
            print(f"  {k:<28} {v}")
    print(f"  README open roles            {summary['open']}")
    print(f"  feed entries                 {feed_entries}")


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "update"
    if cmd == "discover":
        cmd_discover()
    elif cmd == "harvest":
        cmd_harvest()
    elif cmd == "update":
        cmd_update()
    elif cmd == "all":
        cmd_discover()
        cmd_harvest()
        cmd_update()
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
