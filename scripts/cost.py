"""Shared cost tracker. Enforces MAX_DAILY_API_SPEND_USD hardcap across both clients."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


class CostCapExceeded(RuntimeError):
    pass


@dataclass
class CostTracker:
    cap_usd: float = float(os.environ.get("MAX_DAILY_API_SPEND_USD", "2.00"))
    spent_usd: float = 0.0
    breakdown: dict[str, float] = field(default_factory=dict)

    def charge(self, label: str, amount_usd: float) -> None:
        if self.spent_usd + amount_usd > self.cap_usd:
            raise CostCapExceeded(
                f"would exceed ${self.cap_usd:.2f} cap "
                f"(at ${self.spent_usd:.4f}, +{label} ${amount_usd:.4f})"
            )
        self.spent_usd += amount_usd
        self.breakdown[label] = self.breakdown.get(label, 0.0) + amount_usd

    def summary(self) -> str:
        if not self.breakdown:
            return "no API spend"
        nonzero = {k: v for k, v in self.breakdown.items() if v > 0}
        zero = {k: v for k, v in self.breakdown.items() if v == 0}
        out = [f"total ${self.spent_usd:.4f}"]
        for k, v in sorted(nonzero.items(), key=lambda kv: -kv[1]):
            out.append(f"  ${v:.4f}  {k}")
        if zero:
            # Group zero-cost calls by client prefix (e.g. bird.search.*)
            from collections import Counter
            prefixes = Counter(k.split("(")[0] for k in zero)
            for prefix, n in prefixes.most_common():
                out.append(f"  $0.0000  {prefix} × {n}")
        return "\n".join(out)
