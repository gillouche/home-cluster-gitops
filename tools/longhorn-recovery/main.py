#!/usr/bin/env python3
"""Longhorn recovery tool.

Diagnoses and fixes common Longhorn issues:
- Orphaned replicas and instances
- Stopped/errored replicas that exhausted rebuild retries
- Over-scheduled disks from failed replica accumulation
- Degraded volumes needing replica cleanup for fresh rebuild
- Node transition time mismatches causing unstable env detection

Usage:
    python -m tools.longhorn-recovery                # Diagnose only (dry-run)
    python -m tools.longhorn-recovery --fix          # Apply fixes
    python -m tools.longhorn-recovery --fix --yes    # Skip confirmation
"""

import argparse
import json
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone


NAMESPACE = "longhorn-system"


def run_kubectl(*args: str) -> dict | list | str:
    """Run a kubectl command and return parsed JSON or raw output."""
    cmd = ["kubectl", *args]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        print(f"  ERROR: {' '.join(cmd)}: {result.stderr.strip()}", file=sys.stderr)
        return {}
    if "-o" in args and "json" in args:
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return {}
    return result.stdout.strip()


def get_resources(kind: str) -> list[dict]:
    """Get all resources of a given kind in the longhorn namespace."""
    data = run_kubectl("get", f"{kind}.longhorn.io", "-n", NAMESPACE, "-o", "json")
    return data.get("items", []) if isinstance(data, dict) else []


def get_nodes() -> list[dict]:
    """Get Kubernetes nodes."""
    data = run_kubectl("get", "nodes", "-o", "json")
    return data.get("items", []) if isinstance(data, dict) else []


def delete_resources(kind: str, names: list[str], dry_run: bool = True) -> int:
    """Delete Longhorn resources. Returns count deleted."""
    if not names:
        return 0
    if dry_run:
        return len(names)

    deleted = 0
    # Batch delete in groups of 50
    for i in range(0, len(names), 50):
        batch = names[i : i + 50]
        cmd = ["kubectl", "delete", f"{kind}.longhorn.io", "-n", NAMESPACE, *batch]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            deleted += len(batch)
        else:
            # Try one by one for partial failures
            for name in batch:
                r = subprocess.run(
                    ["kubectl", "delete", f"{kind}.longhorn.io", "-n", NAMESPACE, name],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if r.returncode == 0:
                    deleted += 1
    return deleted


def check_node_transitions(nodes: list[dict], longhorn_nodes: list[dict]) -> list[dict]:
    """Check for node Ready transition time mismatches (Longhorn storage nodes only)."""
    issues = []
    storage_nodes = []

    # Only check nodes that have Longhorn scheduling enabled (storage nodes)
    longhorn_schedulable = set()
    for ln in longhorn_nodes:
        has_disks = False
        for disk in ln.get("spec", {}).get("disks", {}).values():
            if disk.get("allowScheduling", False):
                has_disks = True
                break
        if has_disks:
            longhorn_schedulable.add(ln["metadata"]["name"])

    for node in nodes:
        name = node["metadata"]["name"]
        if name not in longhorn_schedulable:
            continue
        for cond in node.get("status", {}).get("conditions", []):
            if cond["type"] == "Ready":
                transition = cond.get("lastTransitionTime", "")
                if transition:
                    dt = datetime.fromisoformat(transition.replace("Z", "+00:00"))
                    storage_nodes.append({"name": name, "transition": dt, "raw": transition})

    if len(storage_nodes) < 2:
        return issues

    storage_nodes.sort(key=lambda x: x["transition"])
    earliest = storage_nodes[0]
    now = datetime.now(timezone.utc)

    for node in storage_nodes[1:]:
        diff = node["transition"] - earliest["transition"]
        if diff.total_seconds() > 1800:  # 30 minutes
            issues.append(
                {
                    "node": node["name"],
                    "transition": node["raw"],
                    "earliest_node": earliest["name"],
                    "earliest_transition": earliest["raw"],
                    "diff_hours": diff.total_seconds() / 3600,
                }
            )

    return issues


def check_orphans() -> tuple[list[str], dict]:
    """Check for orphaned resources."""
    orphans = get_resources("orphans")
    names = [o["metadata"]["name"] for o in orphans]
    by_node = Counter(
        o["metadata"].get("labels", {}).get("longhorn.io/node", "unknown")
        for o in orphans
    )
    return names, dict(by_node)


def check_stuck_replicas(replicas: list[dict]) -> dict:
    """Find stopped/errored replicas that need cleanup."""
    stuck = defaultdict(list)

    for r in replicas:
        state = r.get("status", {}).get("currentState", "")
        desire = r.get("spec", {}).get("desireState", "")
        node = r.get("spec", {}).get("nodeID", "(unassigned)")
        name = r["metadata"]["name"]
        retry = r.get("spec", {}).get("rebuildRetryCount", 0)

        if state == "stopped" and desire == "running":
            stuck["stopped_want_running"].append(
                {"name": name, "node": node, "retries": retry}
            )
        elif state == "stopped" and not node:
            stuck["unassigned"].append({"name": name, "node": node, "retries": retry})
        elif state == "error":
            stuck["error"].append({"name": name, "node": node, "retries": retry})

    return dict(stuck)


def check_disk_scheduling(longhorn_nodes: list[dict]) -> list[dict]:
    """Check for over-scheduled disks."""
    issues = []

    for node in longhorn_nodes:
        name = node["metadata"]["name"]
        for disk_name, disk_status in node.get("status", {}).get("diskStatus", {}).items():
            scheduled = disk_status.get("storageScheduled", 0)
            maximum = disk_status.get("storageMaximum", 0)
            if maximum == 0:
                continue

            ratio = scheduled / maximum
            for cond in disk_status.get("conditions", []):
                if cond["type"] == "Schedulable" and cond["status"] == "False":
                    issues.append(
                        {
                            "node": name,
                            "disk": disk_name,
                            "scheduled_gi": round(scheduled / (1024**3), 1),
                            "max_gi": round(maximum / (1024**3), 1),
                            "ratio": round(ratio, 1),
                            "message": cond.get("message", "")[:100],
                        }
                    )
                elif ratio > 1.5:
                    issues.append(
                        {
                            "node": name,
                            "disk": disk_name,
                            "scheduled_gi": round(scheduled / (1024**3), 1),
                            "max_gi": round(maximum / (1024**3), 1),
                            "ratio": round(ratio, 1),
                            "message": f"Scheduled {ratio:.1f}x disk capacity (likely failed replica accumulation)",
                        }
                    )

    return issues


def check_degraded_volumes(volumes: list[dict]) -> list[dict]:
    """Find degraded/faulted volumes."""
    issues = []
    for v in volumes:
        robustness = v.get("status", {}).get("robustness", "")
        state = v.get("status", {}).get("state", "")
        if robustness in ("degraded", "faulted"):
            pvc = v.get("status", {}).get("kubernetesStatus", {}).get("pvcName", "")
            ns = v.get("status", {}).get("kubernetesStatus", {}).get("namespace", "")
            issues.append(
                {
                    "volume": v["metadata"]["name"],
                    "pvc": f"{ns}/{pvc}" if pvc else "",
                    "state": state,
                    "robustness": robustness,
                    "node": v.get("status", {}).get("currentNodeID", ""),
                    "desired_replicas": v.get("spec", {}).get("numberOfReplicas", 0),
                }
            )
    return issues


def diagnose(fix: bool = False, auto_yes: bool = False) -> None:
    """Run full diagnosis and optionally fix issues."""
    dry_run = not fix
    mode = "DRY-RUN" if dry_run else "FIX"

    print(f"=== Longhorn Recovery Tool ({mode}) ===\n")

    # Gather data
    print("Gathering cluster state...")
    k8s_nodes = get_nodes()
    longhorn_nodes = get_resources("nodes")
    replicas = get_resources("replicas")
    volumes = get_resources("volumes")

    all_clean = True

    # 1. Node transition times
    print("\n--- Node Transition Times ---")
    transition_issues = check_node_transitions(k8s_nodes, longhorn_nodes)
    if transition_issues:
        all_clean = False
        print("WARNING: Node Ready transition time mismatch detected!")
        print("  Longhorn may delete replicas on 'unstable' nodes (>30min newer than oldest).")
        for issue in transition_issues:
            print(
                f"  {issue['node']}: {issue['transition']} "
                f"({issue['diff_hours']:.1f}h newer than {issue['earliest_node']})"
            )
        print("  FIX: Restart k3s on the oldest node one-at-a-time (wait 50s between).")
    else:
        print("  OK: All node transition times within 30-minute window.")

    # 2. Orphans
    print("\n--- Orphaned Resources ---")
    orphan_names, orphans_by_node = check_orphans()
    if orphan_names:
        all_clean = False
        print(f"  Found {len(orphan_names)} orphans: {dict(orphans_by_node)}")
        if fix:
            if auto_yes or confirm(f"Delete {len(orphan_names)} orphans?"):
                deleted = delete_resources("orphans", orphan_names, dry_run=False)
                print(f"  Deleted {deleted} orphans.")
            else:
                print("  Skipped.")
        else:
            print(f"  Would delete {len(orphan_names)} orphans.")
    else:
        print("  OK: No orphans found.")

    # 3. Stuck replicas
    print("\n--- Stuck Replicas ---")
    stuck = check_stuck_replicas(replicas)
    total_stuck = sum(len(v) for v in stuck.values())
    if total_stuck:
        all_clean = False
        for category, items in stuck.items():
            by_node = Counter(i["node"] for i in items)
            print(f"  {category}: {len(items)} replicas {dict(by_node)}")

        to_delete = []
        for items in stuck.values():
            to_delete.extend(i["name"] for i in items)

        if fix:
            if auto_yes or confirm(f"Delete {len(to_delete)} stuck replicas?"):
                deleted = delete_resources("replicas", to_delete, dry_run=False)
                print(f"  Deleted {deleted} stuck replicas.")
            else:
                print("  Skipped.")
        else:
            print(f"  Would delete {len(to_delete)} stuck replicas.")
    else:
        print("  OK: No stuck replicas.")

    # 4. Disk scheduling
    print("\n--- Disk Scheduling ---")
    disk_issues = check_disk_scheduling(longhorn_nodes)
    if disk_issues:
        all_clean = False
        for issue in disk_issues:
            print(
                f"  {issue['node']}/{issue['disk']}: "
                f"scheduled={issue['scheduled_gi']}Gi / max={issue['max_gi']}Gi "
                f"({issue['ratio']}x)"
            )
        print("  FIX: Clean stuck replicas first (above), then disk scheduling recovers.")
    else:
        print("  OK: All disks within normal scheduling limits.")

    # 5. Degraded volumes
    print("\n--- Volume Health ---")
    degraded = check_degraded_volumes(volumes)
    healthy_count = sum(
        1
        for v in volumes
        if v.get("status", {}).get("robustness") == "healthy"
    )
    print(f"  Healthy: {healthy_count}, Degraded/Faulted: {len(degraded)}")
    if degraded:
        all_clean = False
        for d in degraded:
            pvc_info = f" ({d['pvc']})" if d["pvc"] else ""
            print(
                f"  {d['volume']}{pvc_info}: "
                f"{d['state']}/{d['robustness']} on {d['node']}"
            )
        print("  FIX: Cleaning stuck replicas allows Longhorn to schedule fresh rebuilds.")

    # 6. Longhorn settings check
    print("\n--- Settings Check ---")
    settings = get_resources("settings")
    settings_map = {s["metadata"]["name"]: s.get("value", "") for s in settings}

    orphan_auto = settings_map.get("orphan-resource-auto-deletion", "")
    if not orphan_auto or orphan_auto in ("false", ""):
        all_clean = False
        print(f"  WARNING: orphan-resource-auto-deletion = '{orphan_auto}' (should be 'replica-data;instance')")
    else:
        print(f"  orphan-resource-auto-deletion: {orphan_auto}")

    replenish = settings_map.get("replica-replenishment-wait-interval", "30")
    print(f"  replica-replenishment-wait-interval: {replenish}s")

    # Summary
    print("\n" + "=" * 50)
    if all_clean:
        print("All checks passed. Longhorn is healthy.")
    else:
        if dry_run:
            print("Issues found. Run with --fix to apply fixes.")
        else:
            print("Fixes applied. Re-run to verify.")


def confirm(message: str) -> bool:
    """Ask for user confirmation."""
    try:
        response = input(f"  {message} [y/N] ").strip().lower()
        return response in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Longhorn recovery tool - diagnose and fix common issues"
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Apply fixes (default is dry-run diagnosis only)",
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip confirmation prompts (use with --fix)",
    )
    args = parser.parse_args()

    diagnose(fix=args.fix, auto_yes=args.yes)


if __name__ == "__main__":
    main()
