"""Governance policies: copilot stays in research/control plane."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
import re


FORBIDDEN_PATTERNS = (
    (r"\bdisable\b.*\brisk\b", "cannot_disable_risk"),
    (r"\bbypass\b.*\brisk\b", "cannot_bypass_risk"),
    (r"\bturn\s*off\b.*\brisk\b", "cannot_disable_risk"),
    (r"\benable\b.*\blive\b.*\btrad", "cannot_enable_live"),
    (r"\blive\b.*\bcapital\b", "cannot_enable_live"),
    (r"\breal[- ]?money\b", "cannot_enable_live"),
    (r"\bsigning\s*key", "cannot_access_keys"),
    (r"\bapi[_\s-]?secret", "cannot_access_keys"),
    (r"\bprivate[_\s-]?key", "cannot_access_keys"),
    (r"\bexport\b.*\bkey", "cannot_access_keys"),
    (r"\bhold\b.*\bkey", "cannot_access_keys"),
    (r"\bskip\b.*\bpromotion\b", "cannot_skip_promotion"),
    (r"\bbypass\b.*\bgate", "cannot_skip_promotion"),
)


@dataclass(slots=True)
class PolicyDecision:
    allowed: bool
    reason: str
    category: str = "ok"
    advice: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CopilotGuardrails:
    refusals: list[str] = field(default_factory=list)

    def evaluate(self, text: str) -> PolicyDecision:
        lowered = (text or "").lower()
        for pattern, category in FORBIDDEN_PATTERNS:
            if re.search(pattern, lowered, flags=re.IGNORECASE | re.DOTALL):
                decision = PolicyDecision(
                    allowed=False,
                    reason=f"blocked_by_policy:{category}",
                    category=category,
                    advice=(
                        "Copilot is research/control-plane only. Risk gates, promotion, and "
                        "venue signing keys remain outside AI authority."
                    ),
                )
                self.refusals.append(decision.reason)
                return decision
        return PolicyDecision(allowed=True, reason="allowed", category="ok")

    def snapshot(self) -> dict[str, Any]:
        return {
            "plane": "research_control",
            "can_bypass_risk": False,
            "can_hold_signing_keys": False,
            "can_enable_live": False,
            "can_skip_promotion_gates": False,
            "refusals": len(self.refusals),
            "recent_refusals": self.refusals[-20:],
        }
