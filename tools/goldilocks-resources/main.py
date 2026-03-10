#!/usr/bin/env python3
"""Compare Goldilocks VPA recommendations with current workload resource configuration.

Queries the cluster for VPA recommendations and current resource settings,
then produces a report showing mismatches and suggested changes.

Usage:
    python -m tools.goldilocks-resources.main
    # or directly:
    python tools/goldilocks-resources/main.py
    python tools/goldilocks-resources/main.py --format markdown
    python tools/goldilocks-resources/main.py --threshold 50
    python tools/goldilocks-resources/main.py --only-missing
    python tools/goldilocks-resources/main.py --namespace monitoring
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Kubernetes resource quantity parsing
# ---------------------------------------------------------------------------

_CPU_SUFFIXES: dict[str, float] = {"n": 1e-9, "u": 1e-6, "m": 1e-3}
_MEM_SUFFIXES: dict[str, int] = {
    "Ki": 1024,
    "Mi": 1024**2,
    "Gi": 1024**3,
    "Ti": 1024**4,
    "k": 1000,
    "M": 1000**2,
    "G": 1000**3,
    "T": 1000**4,
}


def parse_cpu(value: str) -> float:
    """Parse a Kubernetes CPU quantity to cores (float)."""
    for suffix, multiplier in _CPU_SUFFIXES.items():
        if value.endswith(suffix):
            return float(value[: -len(suffix)]) * multiplier
    return float(value)


def parse_memory(value: str) -> int:
    """Parse a Kubernetes memory quantity to bytes (int)."""
    for suffix, multiplier in _MEM_SUFFIXES.items():
        if value.endswith(suffix):
            return int(float(value[: -len(suffix)]) * multiplier)
    return int(value)


def format_cpu(cores: float) -> str:
    """Format cores as a human-readable CPU string (millicores or whole cores)."""
    if cores >= 1:
        if cores == int(cores):
            return f"{int(cores)}"
        return f"{cores:.1f}"
    return f"{int(cores * 1000 + 0.5)}m"


def format_memory(mem_bytes: int) -> str:
    """Format bytes as a human-readable memory string."""
    if mem_bytes >= 1024**3:
        gi = mem_bytes / (1024**3)
        if gi == int(gi):
            return f"{int(gi)}Gi"
        return f"{gi:.1f}Gi"
    if mem_bytes >= 1024**2:
        mi = mem_bytes / (1024**2)
        return f"{int(mi + 0.5)}Mi"
    if mem_bytes >= 1024:
        return f"{int(mem_bytes / 1024 + 0.5)}Ki"
    return str(mem_bytes)


def _round_memory_nice(mem_bytes: int) -> int:
    """Round memory to the next 'nice' Kubernetes value."""
    mi = mem_bytes / (1024**2)
    nice_values = [
        32, 48, 64, 96, 128, 192, 256, 384, 512, 768,
        1024, 1536, 2048, 3072, 4096, 6144, 8192, 12288, 16384,
    ]
    for nv in nice_values:
        if mi <= nv:
            return nv * 1024**2
    return mem_bytes


def _round_cpu_nice(cores: float) -> float:
    """Round CPU to a nice millicores value."""
    m = cores * 1000
    nice_values = [10, 15, 25, 50, 75, 100, 150, 200, 250, 500, 750, 1000, 1500, 2000, 4000]
    for nv in nice_values:
        if m <= nv:
            return nv / 1000
    return cores


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ResourceSpec:
    cpu: float | None = None  # cores
    memory: int | None = None  # bytes

    def __str__(self) -> str:
        parts = []
        parts.append(f"cpu={format_cpu(self.cpu)}" if self.cpu is not None else "cpu=-")
        parts.append(f"mem={format_memory(self.memory)}" if self.memory is not None else "mem=-")
        return " ".join(parts)


@dataclass
class ContainerResources:
    requests: ResourceSpec = field(default_factory=ResourceSpec)
    limits: ResourceSpec = field(default_factory=ResourceSpec)

    @property
    def is_empty(self) -> bool:
        return (
            self.requests.cpu is None
            and self.requests.memory is None
            and self.limits.cpu is None
            and self.limits.memory is None
        )


@dataclass
class VPARecommendation:
    target: ResourceSpec = field(default_factory=ResourceSpec)
    lower_bound: ResourceSpec = field(default_factory=ResourceSpec)
    upper_bound: ResourceSpec = field(default_factory=ResourceSpec)


@dataclass
class ContainerInfo:
    namespace: str
    workload_name: str
    workload_kind: str
    container_name: str
    current: ContainerResources = field(default_factory=ContainerResources)
    recommendation: VPARecommendation | None = None


@dataclass
class SuggestedChange:
    field: str  # e.g. "requests.cpu"
    current_value: str
    recommended_value: str
    reason: str


# ---------------------------------------------------------------------------
# Kubectl helpers
# ---------------------------------------------------------------------------

def kubectl_json(args: list[str]) -> dict:
    """Run kubectl with given args and return parsed JSON."""
    cmd = ["kubectl"] + args + ["-o", "json"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        print(f"Error running kubectl {' '.join(args)}: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return json.loads(result.stdout)


# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------

def collect_workloads() -> dict[tuple[str, str, str], ContainerResources]:
    """Collect current resources for all workload containers.

    Returns a dict keyed by (namespace, workload_name, container_name).
    """
    workloads: dict[tuple[str, str, str], ContainerResources] = {}
    data = kubectl_json(["get", "deploy,statefulset,daemonset", "-A"])
    for item in data.get("items", []):
        ns = item["metadata"]["namespace"]
        name = item["metadata"]["name"]
        containers = item.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
        for c in containers:
            res = c.get("resources", {})
            req = res.get("requests", {})
            lim = res.get("limits", {})
            cr = ContainerResources(
                requests=ResourceSpec(
                    cpu=parse_cpu(req["cpu"]) if "cpu" in req else None,
                    memory=parse_memory(req["memory"]) if "memory" in req else None,
                ),
                limits=ResourceSpec(
                    cpu=parse_cpu(lim["cpu"]) if "cpu" in lim else None,
                    memory=parse_memory(lim["memory"]) if "memory" in lim else None,
                ),
            )
            workloads[(ns, name, c["name"])] = cr
    return workloads


def collect_vpas() -> dict[tuple[str, str], list[VPARecommendation]]:
    """Collect VPA recommendations.

    Returns a dict keyed by (namespace, targetRef_name) -> list of per-container recs.
    Each rec is augmented with a .container_name attribute.
    """
    vpas: dict[tuple[str, str], list[tuple[str, VPARecommendation]]] = {}
    data = kubectl_json(["get", "vpa", "-A"])
    for item in data.get("items", []):
        ns = item["metadata"]["namespace"]
        target_ref = item.get("spec", {}).get("targetRef", {})
        target_name = target_ref.get("name", "")
        # Strip goldilocks- prefix if present
        if target_name.startswith("goldilocks-"):
            target_name = target_name[len("goldilocks-"):]

        recs = (
            item.get("status", {})
            .get("recommendation", {})
            .get("containerRecommendations", [])
        )
        if not recs:
            continue

        entries: list[tuple[str, VPARecommendation]] = []
        for r in recs:
            target = r.get("target", {})
            lower = r.get("lowerBound", {})
            upper = r.get("upperBound", {})
            rec = VPARecommendation(
                target=ResourceSpec(
                    cpu=parse_cpu(target["cpu"]) if "cpu" in target else None,
                    memory=parse_memory(target["memory"]) if "memory" in target else None,
                ),
                lower_bound=ResourceSpec(
                    cpu=parse_cpu(lower["cpu"]) if "cpu" in lower else None,
                    memory=parse_memory(lower["memory"]) if "memory" in lower else None,
                ),
                upper_bound=ResourceSpec(
                    cpu=parse_cpu(upper["cpu"]) if "cpu" in upper else None,
                    memory=parse_memory(upper["memory"]) if "memory" in upper else None,
                ),
            )
            entries.append((r.get("containerName", ""), rec))
        vpas[(ns, target_name)] = entries
    return vpas


def match_workloads_to_vpas(
    workloads: dict[tuple[str, str, str], ContainerResources],
    vpas: dict[tuple[str, str], list[tuple[str, VPARecommendation]]],
) -> list[ContainerInfo]:
    """Match VPA recommendations to workload containers."""
    results: list[ContainerInfo] = []
    matched_workloads: set[tuple[str, str, str]] = set()

    for (ns, workload_name, container_name), current in workloads.items():
        info = ContainerInfo(
            namespace=ns,
            workload_name=workload_name,
            workload_kind="",
            container_name=container_name,
            current=current,
        )
        # Try to find matching VPA
        if (ns, workload_name) in vpas:
            for cname, rec in vpas[(ns, workload_name)]:
                if cname == container_name:
                    info.recommendation = rec
                    matched_workloads.add((ns, workload_name, container_name))
                    break
        results.append(info)

    return results


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def analyze_container(info: ContainerInfo, threshold_pct: float) -> list[SuggestedChange]:
    """Analyze a single container and return suggested changes."""
    if info.recommendation is None:
        return []

    changes: list[SuggestedChange] = []
    rec = info.recommendation

    # --- CPU requests ---
    if rec.target.cpu is not None:
        suggested_cpu = _round_cpu_nice(rec.target.cpu)
        if info.current.requests.cpu is None:
            changes.append(SuggestedChange(
                field="requests.cpu",
                current_value="-",
                recommended_value=format_cpu(suggested_cpu),
                reason="missing",
            ))
        else:
            ratio = info.current.requests.cpu / rec.target.cpu if rec.target.cpu > 0 else 1
            if ratio > (1 + threshold_pct / 100) or ratio < (1 - threshold_pct / 100):
                changes.append(SuggestedChange(
                    field="requests.cpu",
                    current_value=format_cpu(info.current.requests.cpu),
                    recommended_value=format_cpu(suggested_cpu),
                    reason=f"{'over' if ratio > 1 else 'under'}-provisioned ({ratio:.1f}x)",
                ))

    # --- Memory requests ---
    if rec.target.memory is not None:
        suggested_mem = _round_memory_nice(rec.target.memory)
        if info.current.requests.memory is None:
            changes.append(SuggestedChange(
                field="requests.memory",
                current_value="-",
                recommended_value=format_memory(suggested_mem),
                reason="missing",
            ))
        else:
            ratio = info.current.requests.memory / rec.target.memory if rec.target.memory > 0 else 1
            if ratio > (1 + threshold_pct / 100) or ratio < (1 - threshold_pct / 100):
                changes.append(SuggestedChange(
                    field="requests.memory",
                    current_value=format_memory(info.current.requests.memory),
                    recommended_value=format_memory(suggested_mem),
                    reason=f"{'over' if ratio > 1 else 'under'}-provisioned ({ratio:.1f}x)",
                ))

    # --- Memory limits (based on upperBound) ---
    if rec.upper_bound.memory is not None:
        suggested_limit = _round_memory_nice(rec.upper_bound.memory)
        if info.current.limits.memory is None:
            changes.append(SuggestedChange(
                field="limits.memory",
                current_value="-",
                recommended_value=format_memory(suggested_limit),
                reason="missing",
            ))
        else:
            # Only flag if current limit is below upper bound (risk of OOM)
            if info.current.limits.memory < rec.upper_bound.memory:
                changes.append(SuggestedChange(
                    field="limits.memory",
                    current_value=format_memory(info.current.limits.memory),
                    recommended_value=format_memory(suggested_limit),
                    reason=f"below upper bound ({format_memory(rec.upper_bound.memory)}), OOM risk",
                ))
            # Flag if limit is excessively high (> 3x upper bound)
            elif info.current.limits.memory > rec.upper_bound.memory * 3:
                changes.append(SuggestedChange(
                    field="limits.memory",
                    current_value=format_memory(info.current.limits.memory),
                    recommended_value=format_memory(suggested_limit),
                    reason=f"over-provisioned ({info.current.limits.memory / rec.upper_bound.memory:.1f}x upper bound)",
                ))

    return changes


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------

class Colors:
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


def _colorize(text: str, color: str, use_color: bool) -> str:
    if not use_color:
        return text
    return f"{color}{text}{Colors.RESET}"


def print_text_report(
    containers: list[ContainerInfo],
    threshold_pct: float,
    only_missing: bool,
    use_color: bool,
) -> int:
    """Print a human-readable text report. Returns count of containers with changes."""
    change_count = 0
    ns_groups: dict[str, list[tuple[ContainerInfo, list[SuggestedChange]]]] = {}

    for info in containers:
        changes = analyze_container(info, threshold_pct)
        if only_missing:
            changes = [c for c in changes if c.reason == "missing"]
        if not changes:
            continue
        change_count += 1
        ns_groups.setdefault(info.namespace, []).append((info, changes))

    if not ns_groups:
        print(_colorize("All workloads with VPA data are properly configured.", Colors.GREEN, use_color))
        return 0

    for ns in sorted(ns_groups):
        print(f"\n{_colorize(f'[{ns}]', Colors.BOLD + Colors.CYAN, use_color)}")
        for info, changes in ns_groups[ns]:
            label = f"  {info.workload_name}/{info.container_name}"
            print(_colorize(label, Colors.BOLD, use_color))
            if info.recommendation:
                rec = info.recommendation
                print(
                    _colorize(
                        f"    VPA target:  {rec.target}",
                        Colors.DIM, use_color,
                    )
                )
                print(
                    _colorize(
                        f"    VPA upper:   {rec.upper_bound}",
                        Colors.DIM, use_color,
                    )
                )
                print(
                    _colorize(
                        f"    Current req: {info.current.requests}",
                        Colors.DIM, use_color,
                    )
                )
                print(
                    _colorize(
                        f"    Current lim: {info.current.limits}",
                        Colors.DIM, use_color,
                    )
                )
            for change in changes:
                color = Colors.RED if change.reason == "missing" else Colors.YELLOW
                print(
                    f"    {_colorize('>', color, use_color)} "
                    f"{change.field}: "
                    f"{_colorize(change.current_value, Colors.RED, use_color)} -> "
                    f"{_colorize(change.recommended_value, Colors.GREEN, use_color)} "
                    f"({change.reason})"
                )

    return change_count


def print_markdown_report(
    containers: list[ContainerInfo],
    threshold_pct: float,
    only_missing: bool,
) -> int:
    """Print a markdown-formatted report. Returns count of containers with changes."""
    all_changes: list[tuple[ContainerInfo, list[SuggestedChange]]] = []
    for info in containers:
        changes = analyze_container(info, threshold_pct)
        if only_missing:
            changes = [c for c in changes if c.reason == "missing"]
        if changes:
            all_changes.append((info, changes))

    if not all_changes:
        print("All workloads with VPA data are properly configured.")
        return 0

    print("# Goldilocks Resource Recommendations Report\n")
    print("| Namespace | Workload | Container | Field | Current | Recommended | Reason |")
    print("|-----------|----------|-----------|-------|---------|-------------|--------|")
    for info, changes in all_changes:
        for change in changes:
            print(
                f"| {info.namespace} | {info.workload_name} | {info.container_name} "
                f"| {change.field} | {change.current_value} | {change.recommended_value} "
                f"| {change.reason} |"
            )

    return len(all_changes)


def print_json_report(
    containers: list[ContainerInfo],
    threshold_pct: float,
    only_missing: bool,
) -> int:
    """Print a JSON report. Returns count of containers with changes."""
    output: list[dict] = []
    for info in containers:
        changes = analyze_container(info, threshold_pct)
        if only_missing:
            changes = [c for c in changes if c.reason == "missing"]
        if not changes:
            continue
        entry: dict = {
            "namespace": info.namespace,
            "workload": info.workload_name,
            "container": info.container_name,
            "current": {
                "requests": {
                    "cpu": format_cpu(info.current.requests.cpu) if info.current.requests.cpu is not None else None,
                    "memory": format_memory(info.current.requests.memory) if info.current.requests.memory is not None else None,
                },
                "limits": {
                    "cpu": format_cpu(info.current.limits.cpu) if info.current.limits.cpu is not None else None,
                    "memory": format_memory(info.current.limits.memory) if info.current.limits.memory is not None else None,
                },
            },
            "changes": [
                {
                    "field": c.field,
                    "current": c.current_value,
                    "recommended": c.recommended_value,
                    "reason": c.reason,
                }
                for c in changes
            ],
        }
        if info.recommendation:
            entry["vpa"] = {
                "target": str(info.recommendation.target),
                "upperBound": str(info.recommendation.upper_bound),
            }
        output.append(entry)
    print(json.dumps(output, indent=2))
    return len(output)


# ---------------------------------------------------------------------------
# Summary statistics
# ---------------------------------------------------------------------------

def print_summary(containers: list[ContainerInfo], use_color: bool) -> None:
    """Print a summary of coverage."""
    total_workloads = len(containers)
    with_vpa = sum(1 for c in containers if c.recommendation is not None)
    without_resources = sum(1 for c in containers if c.current.is_empty)
    without_resources_with_vpa = sum(
        1 for c in containers if c.current.is_empty and c.recommendation is not None
    )
    without_limits_mem = sum(
        1 for c in containers
        if c.current.limits.memory is None and c.recommendation is not None
    )

    print(f"\n{_colorize('--- Summary ---', Colors.BOLD, use_color)}")
    print(f"  Total containers:                  {total_workloads}")
    print(f"  With VPA recommendations:          {with_vpa}")
    print(f"  Without any resources set:          {without_resources}")
    print(f"    ...of those, with VPA data:       {without_resources_with_vpa}")
    print(f"  Without memory limits (w/ VPA):     {without_limits_mem}")

    no_vpa = [
        c for c in containers if c.recommendation is None and c.current.is_empty
    ]
    if no_vpa:
        print(f"\n{_colorize('Containers without resources AND without VPA data:', Colors.YELLOW, use_color)}")
        for c in sorted(no_vpa, key=lambda x: (x.namespace, x.workload_name)):
            print(f"  {c.namespace}/{c.workload_name}/{c.container_name}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare Goldilocks VPA recommendations with current workload resources."
    )
    parser.add_argument(
        "--format",
        choices=["text", "markdown", "json"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=50,
        help="Percentage threshold for flagging over/under-provisioned resources (default: 50%%)",
    )
    parser.add_argument(
        "--only-missing",
        action="store_true",
        help="Only show containers with missing resources (no requests/limits set)",
    )
    parser.add_argument(
        "--namespace", "-n",
        help="Filter to a specific namespace",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored output",
    )
    parser.add_argument(
        "--no-summary",
        action="store_true",
        help="Skip the summary section",
    )
    args = parser.parse_args()

    use_color = not args.no_color and sys.stdout.isatty() and args.format == "text"

    print(_colorize("Fetching VPA recommendations...", Colors.DIM, use_color), file=sys.stderr)
    vpas = collect_vpas()

    print(_colorize("Fetching workload resources...", Colors.DIM, use_color), file=sys.stderr)
    workloads = collect_workloads()

    containers = match_workloads_to_vpas(workloads, vpas)

    if args.namespace:
        containers = [c for c in containers if c.namespace == args.namespace]

    containers.sort(key=lambda c: (c.namespace, c.workload_name, c.container_name))

    if args.format == "text":
        count = print_text_report(containers, args.threshold, args.only_missing, use_color)
    elif args.format == "markdown":
        count = print_markdown_report(containers, args.threshold, args.only_missing)
    else:
        count = print_json_report(containers, args.threshold, args.only_missing)

    if not args.no_summary and args.format == "text":
        print_summary(containers, use_color)

    print(f"\n{count} container(s) with suggested changes.", file=sys.stderr)


if __name__ == "__main__":
    main()
