from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple, cast


def _status_of_connected_realm(cr: Dict[str, Any]) -> str:
    status_obj = cr.get("status")
    t: Any = None
    if isinstance(status_obj, dict):
        t = status_obj.get("type")  # type: ignore[no-untyped-call]
    if isinstance(t, str) and t:
        return t.upper()
    return "OTHER"


def _realm_count_in_connected_realm(cr: Dict[str, Any]) -> int:
    realms_val = cr.get("realms")
    if isinstance(realms_val, list):
        lst = cast(List[Any], realms_val)
        return len(lst)
    return 0


@dataclass
class Snapshot:
    available_count: int
    status_counts: Dict[str, int]
    total: int
    timestamp: str


class StateStore:
    def __init__(self, path: str):
        self.path = path

    def load(self) -> Snapshot | None:
        if not os.path.exists(self.path):
            return None
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
                sc = data.get("status_counts")
                sc_dict: Dict[str, int] = {}
                if isinstance(sc, dict):
                    for k, v in sc.items():
                        k_str = k if isinstance(k, str) else None
                        if k_str is None:
                            continue
                        try:
                            sc_dict[k_str] = int(v)  # type: ignore[arg-type]
                        except Exception:
                            continue
                return Snapshot(
                    available_count=int(data.get("available_count", 0)),
                    status_counts=sc_dict,
                    total=int(data.get("total", 0)),
                    timestamp=str(data.get("timestamp")),
                )
        except Exception:
            return None

    def save(self, snap: Snapshot) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "available_count": snap.available_count,
                    "status_counts": snap.status_counts,
                    "total": snap.total,
                    "timestamp": snap.timestamp,
                },
                f,
                indent=2,
                sort_keys=True,
            )


def compute_counts(connected_realms: List[Dict[str, Any]]) -> Tuple[int, Dict[str, int], int]:
    status_counts: Dict[str, int] = {}
    total_realms = 0
    for cr in connected_realms:
        st = _status_of_connected_realm(cr)
        n = _realm_count_in_connected_realm(cr)
        total_realms += n
        status_counts[st] = status_counts.get(st, 0) + n
    available = status_counts.get("UP", 0)
    return available, status_counts, total_realms


def make_snapshot(available: int, status_counts: Dict[str, int], total: int) -> Snapshot:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return Snapshot(available_count=available, status_counts=status_counts, total=total, timestamp=ts)


@dataclass
class Diff:
    should_post: bool
    prev: Snapshot | None
    curr: Snapshot


def diff_snapshots(prev: Snapshot | None, curr: Snapshot) -> Diff:
    if prev is None:
        # First run: set baseline without posting
        return Diff(should_post=False, prev=None, curr=curr)
    changed = prev.available_count != curr.available_count
    return Diff(should_post=changed, prev=prev, curr=curr)


def format_message(diff: Diff) -> str:
    curr = diff.curr
    prev = diff.prev
    lines: List[str] = []
    if prev is not None:
        lines.append("Realm availability changed")
        lines.append(f"- Available (UP): {curr.available_count} (was {prev.available_count})")
    else:
        lines.append("Realm availability baseline")
        lines.append(f"- Available (UP): {curr.available_count}")

    # Include per-status counts sorted by key for stability
    keys = sorted(curr.status_counts.keys())
    for k in keys:
        if k == "UP":
            continue
        prev_v = prev.status_counts.get(k, 0) if prev else None
        if prev_v is None:
            lines.append(f"- {k}: {curr.status_counts[k]}")
        else:
            lines.append(f"- {k}: {curr.status_counts[k]} (was {prev_v})")

    lines.append(f"Total realms: {curr.total} • {curr.timestamp}")
    return "\n".join(lines)
