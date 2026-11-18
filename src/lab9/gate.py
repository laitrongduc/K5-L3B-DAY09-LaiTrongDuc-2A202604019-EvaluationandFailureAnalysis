"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems: list[str] = []

    def row_inventory(report: dict, label: str) -> tuple[set[tuple[str, int]], dict[str, tuple[str, ...]]]:
        manifest = report.get("manifest") or {}
        rows = report.get("rows")
        if not isinstance(rows, list):
            problems.append(f"{label} rows are missing or are not a list")
            return set(), {}
        items, seeds = manifest.get("items"), manifest.get("seeds")
        if (type(items) is not int or items < 0 or not isinstance(seeds, list)
                or any(type(seed) is not int for seed in seeds)):
            problems.append(f"{label} manifest has invalid items/seeds")
            expected = None
        else:
            if len(set(seeds)) != len(seeds):
                problems.append(f"{label} manifest contains duplicate seeds")
            expected = items * len(seeds)
        if expected is not None and len(rows) != expected:
            problems.append(f"{label} row count {len(rows)} != manifest items × seeds ({expected})")

        counts: dict[tuple[str, int], int] = {}
        slice_tags: dict[str, tuple[str, ...]] = {}
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                problems.append(f"{label} row {index} is not an object")
                continue
            item_id, seed = row.get("item_id"), row.get("seed")
            if not isinstance(item_id, str) or type(seed) is not int:
                problems.append(f"{label} row {index} has invalid item_id/seed")
                continue
            key = (item_id, seed)
            counts[key] = counts.get(key, 0) + 1
            tags = row.get("slices") or []
            if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
                problems.append(f"{label} row {item_id}@{seed} has invalid slice tags")
                tags = []
            elif len(set(tags)) != len(tags):
                problems.append(f"{label} row {item_id}@{seed} has duplicate slice tags")
            tag_tuple = tuple(sorted(tags))
            if item_id in slice_tags and slice_tags[item_id] != tag_tuple:
                problems.append(f"{label} slice tags vary across seeds for {item_id}")
            slice_tags[item_id] = tag_tuple
        duplicates = sorted(key for key, count in counts.items() if count != 1)
        if duplicates:
            problems.append(f"{label} duplicate (item_id, seed) rows: {duplicates[:3]}")
        return set(counts), slice_tags

    pr_keys, pr_slices = row_inventory(pr, "PR")
    base_keys, base_slices = row_inventory(base, "baseline")
    if pr_keys != base_keys:
        missing = sorted(base_keys - pr_keys)[:3]
        extra = sorted(pr_keys - base_keys)[:3]
        problems.append(f"PR (item_id, seed) set differs from baseline (missing={missing}, extra={extra})")
    if pr_slices != base_slices:
        changed = sorted(set(pr_slices) | set(base_slices))
        changed = [item for item in changed if pr_slices.get(item) != base_slices.get(item)]
        problems.append(f"PR slice tags differ from baseline for items: {changed[:3]}")

    failures = pr.get("evaluator_failures") or []
    if failures:
        count = len(failures) if isinstance(failures, (list, tuple, dict, str)) else 1
        problems.append(f"PR evaluator_failures is non-empty ({count} failure(s))")
    metrics = pr.get("metrics")
    if not isinstance(metrics, dict):
        problems.append("PR metrics is missing or is not an object")
        metrics = {}
    for metric, value in metrics.items():
        if value is None:
            continue
        if not isinstance(value, (int, float)):
            problems.append(f"PR metric {metric} is not numeric")
        elif not math.isfinite(float(value)):
            problems.append(f"PR metric {metric} is non-finite ({value})")

    # Every registered evaluator produces a per-row value. Missing values must not
    # silently disappear from the aggregate denominator.
    from lab9.graders import GRADERS

    graded = {m["id"] for m in spec.get("metrics", []) if m.get("id") in GRADERS}
    for row in pr.get("rows") or []:
        if not isinstance(row, dict):
            continue
        for metric in sorted(graded):
            if row.get(metric) is None:
                problems.append(f"PR row {row.get('item_id')}@{row.get('seed')} has missing {metric}")
                break

    if base_spec is not None and spec.get("eval_set_version") == base_spec.get("eval_set_version"):
        old_metrics = {m.get("id"): m for m in base_spec.get("metrics", []) if m.get("id")}
        new_metrics = {m.get("id"): m for m in spec.get("metrics", []) if m.get("id")}
        for metric_id, old in old_metrics.items():
            new = new_metrics.get(metric_id)
            if new is None:
                problems.append(f"ratchet removed metric {metric_id} on the same eval-set version")
                continue
            if old.get("blocking") and not new.get("blocking"):
                problems.append(f"ratchet made blocking metric {metric_id} non-blocking")
            old_threshold, new_threshold = old.get("threshold") or {}, new.get("threshold") or {}
            for key, direction in (("min", "may not fall"), ("max", "may not rise"),
                                   ("max_increase", "may not rise")):
                if key not in old_threshold:
                    continue
                if key not in new_threshold:
                    problems.append(f"ratchet {metric_id}.{key} {direction}")
                elif ((key == "min" and new_threshold[key] < old_threshold[key])
                      or (key != "min" and new_threshold[key] > old_threshold[key])):
                    problems.append(f"ratchet {metric_id}.{key} {direction}")
            if old_threshold.get("no_significant_drop") and not new_threshold.get("no_significant_drop"):
                problems.append(f"ratchet removed {metric_id}.no_significant_drop")

        def slice_map(source: dict) -> dict[tuple[str, str], dict]:
            return {(entry.get("name"), entry.get("metric")): entry
                    for entry in source.get("slices", []) if entry.get("name") and entry.get("metric")}

        old_slices, new_slices = slice_map(base_spec), slice_map(spec)
        for key, old in old_slices.items():
            name, metric_id = key
            new = new_slices.get(key)
            if new is None:
                problems.append(f"ratchet removed slice {name}/{metric_id} on the same eval-set version")
                continue
            if old.get("blocking") and not new.get("blocking"):
                problems.append(f"ratchet made slice {name}/{metric_id} non-blocking")
            for bound, direction in (("min", "may not fall"), ("max", "may not rise")):
                if bound not in old:
                    continue
                if bound not in new:
                    problems.append(f"ratchet slice {name}/{metric_id}.{bound} {direction}")
                elif ((bound == "min" and new[bound] < old[bound])
                      or (bound == "max" and new[bound] > old[bound])):
                    problems.append(f"ratchet slice {name}/{metric_id}.{bound} {direction}")
            if old.get("no_significant_drop") and not new.get("no_significant_drop"):
                problems.append(f"ratchet removed slice {name}/{metric_id}.no_significant_drop")
    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked: list[str] = []
    lines: list[str] = []
    bootstrap_spec = spec.get("bootstrap") or {}
    for entry in spec.get("slices") or []:
        name, metric = entry["name"], entry["metric"]
        pr_items = per_item(pr, metric, slice_name=name)
        base_items = per_item(base, metric, slice_name=name)
        failures: list[str] = []
        note = ""
        if not pr_items or not base_items:
            failures.append("slice has no scored items")
            value = None
        else:
            value = sum(pr_items.values()) / len(pr_items)
            if "min" in entry and value < entry["min"]:
                failures.append(f"mean {value:.3f} < min {entry['min']}")
            if "max" in entry and value > entry["max"]:
                failures.append(f"mean {value:.3f} > max {entry['max']}")
            if entry.get("no_significant_drop"):
                keys = sorted(set(pr_items) & set(base_items))
                if set(pr_items) != set(base_items) or not keys:
                    failures.append("PR and baseline slice items differ")
                else:
                    delta, lo, hi = stats.paired_bootstrap(
                        [pr_items[k] for k in keys], [base_items[k] for k in keys],
                        n_resamples=bootstrap_spec.get("n_resamples", 1000),
                        rng=bootstrap_spec.get("rng", 2027),
                        confidence=bootstrap_spec.get("confidence", 0.95),
                    )
                    note = f"Δ {delta:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                    if hi < 0:
                        failures.append("paired CI is entirely below 0")
        status = "BLOCK" if failures and entry.get("blocking") else ("warn" if failures else "ok")
        lines.append(f"  slice:{name}/{metric:<16} {value!s:<8} {note:<28} {status}"
                     + (f" ({'; '.join(failures)})" if failures else ""))
        if failures and entry.get("blocking"):
            blocked.append(f"slice:{name}/{metric}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    pr_sha = (pr.get("manifest") or {}).get("eval_set_sha")
    base_sha = (base.get("manifest") or {}).get("eval_set_sha")
    if not pr_sha or pr_sha != base_sha:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr.get('run_id', '?')} vs main {base.get('run_id', '?')} · eval set "
          f"{(pr.get('manifest') or {}).get('eval_set_sha', '?')}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
