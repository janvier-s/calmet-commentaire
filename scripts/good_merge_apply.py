"""Build data/<vol>/merged/ from normalized + the /merge decisions (docs/good_merge/<vol>.json) + free edits.

    python good_merge_apply.py 01_genese            # rebuild every merged page
    python good_merge_apply.py 01_genese --dry-run  # write nothing: print each changed page's diff

merged is derived: normalized (still hand-fixed) is never written, and every run starts from it again. Decisions
whose change is no longer where it was decided (reopened, not found, overlapping another) are not applied and
are listed.
"""
import argparse
import difflib
import sys

import merge_build
import merge_decisions
import merge_view
import review_store
from paths import DATA, DOCS


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("vol")
    ap.add_argument("--dry-run", action="store_true", help="write nothing; print the diff of each changed page")
    a = ap.parse_args(argv)
    doc = merge_view.load(DATA, a.vol)
    if doc is None:
        sys.exit(f"{a.vol}: no good_units.json (run good_units.py)")
    store = review_store.Store(DATA, DOCS)
    decisions = merge_decisions.load(DOCS, a.vol)
    if a.dry_run:
        built, report = merge_build.merged_pages(store, a.vol, doc, decisions)
        changed = 0
        for p, (before, after) in built.items():
            if before == after:
                continue
            changed += 1
            sys.stdout.writelines(difflib.unified_diff(
                review_store.dumps(before).splitlines(True), review_store.dumps(after).splitlines(True),
                f"normalized/page_{p:04d}.json", f"merged/page_{p:04d}.json", n=1))
        print(f"{a.vol}: {changed} of {len(built)} pages would change (dry run, nothing written)")
    else:
        report = merge_build.build_pages(store, a.vol, doc, decisions)
        print(f"{a.vol}: {len(report['written'])} merged pages written to {merge_build.merged_dir(DATA, a.vol)}")
    for s in report["skipped"]:
        print(f"  not applied: {s['uid']} {s['key']} ({s['why']})")
    if report["reopened"]:
        print(f"  {report['reopened']} decision(s) reopened: the texts changed since; decide them again on /merge")


if __name__ == "__main__":
    main()
