"""Strategy governance and promotion gates (deterministic, no LLM bypass)."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class GateVerdict(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"


@dataclass(slots=True)
class GateCheck:
    name: str
    verdict: GateVerdict
    observed: Any
    threshold: Any
    detail: str

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "verdict": self.verdict.value,
            "observed": self.observed,
            "threshold": self.threshold,
            "detail": self.detail,
        }


@dataclass
class PromotionDecision:
    approved: bool
    stage: str
    score: float
    checks: list[GateCheck] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "approved": self.approved,
            "stage": self.stage,
            "score": self.score,
            "checks": [c.to_dict() for c in self.checks],
            "reasons": self.reasons,
        }


@dataclass
class PromotionGate:
    """
    Deterministic promotion criteria from Strategy Factory docs:
    min sample, positive expectancy, max drawdown, OOS stability, robustness.
    """

    min_trades: int = 20
    min_expectancy: float = 0.0
    max_drawdown_pct: float = 5.0
    min_oos_stability: float = 0.5
    min_mc_robustness: float = 0.5
    min_mc_p05_pnl: float = 0.0
    min_sensitivity_stability: float = 0.4
    min_win_rate: float = 45.0
    require_positive_oos: bool = True

    def evaluate(self, metrics: dict[str, Any], stage: str = "paper") -> PromotionDecision:
        checks: list[GateCheck] = []

        traded = float(metrics.get("traded", metrics.get("oos_traded", 0)) or 0)
        checks.append(self._cmp(
            "min_sample_size", traded, self.min_trades, traded >= self.min_trades,
            f"trades={traded}",
        ))

        expectancy = float(metrics.get("expectancy", metrics.get("oos_expectancy", 0)) or 0)
        checks.append(self._cmp(
            "positive_expectancy", expectancy, self.min_expectancy,
            expectancy >= self.min_expectancy, f"expectancy={expectancy}",
        ))

        dd = float(metrics.get("max_drawdown_pct", metrics.get("oos_max_drawdown_pct", 0)) or 0)
        checks.append(self._cmp(
            "max_drawdown", dd, self.max_drawdown_pct, dd <= self.max_drawdown_pct,
            f"max_drawdown_pct={dd}",
            higher_is_better=False,
        ))

        win_rate = float(metrics.get("win_rate", metrics.get("oos_win_rate", 0)) or 0)
        checks.append(self._cmp(
            "min_win_rate", win_rate, self.min_win_rate, win_rate >= self.min_win_rate,
            f"win_rate={win_rate}",
        ))

        stability = float(metrics.get("stability_score", metrics.get("oos_stability", 0)) or 0)
        checks.append(self._cmp(
            "oos_stability", stability, self.min_oos_stability,
            stability >= self.min_oos_stability, f"stability={stability}",
        ))

        robustness = float(metrics.get("robustness_score", 0) or 0)
        checks.append(self._cmp(
            "monte_carlo_robustness", robustness, self.min_mc_robustness,
            robustness >= self.min_mc_robustness, f"robustness={robustness}",
        ))

        p05 = float(metrics.get("p05_net_pnl", 0) or 0)
        checks.append(self._cmp(
            "monte_carlo_p05", p05, self.min_mc_p05_pnl, p05 >= self.min_mc_p05_pnl,
            f"p05_net_pnl={p05}",
        ))

        sens = float(metrics.get("sensitivity_stability", 0) or 0)
        checks.append(self._cmp(
            "parameter_robustness", sens, self.min_sensitivity_stability,
            sens >= self.min_sensitivity_stability, f"sensitivity_stability={sens}",
        ))

        oos_pnl = float(metrics.get("oos_net_pnl", metrics.get("net_pnl", 0)) or 0)
        if self.require_positive_oos:
            checks.append(self._cmp(
                "positive_oos_pnl", oos_pnl, 0.0, oos_pnl > 0, f"oos_net_pnl={oos_pnl}",
            ))

        # Stage-specific gates.
        if stage in {"shadow", "testnet", "live", "canary"}:
            tracking_error = float(metrics.get("tracking_error", 0) or 0)
            checks.append(self._cmp(
                "tracking_error", tracking_error, 0.25, tracking_error <= 0.25,
                f"tracking_error={tracking_error}", higher_is_better=False,
            ))

        fails = [c for c in checks if c.verdict == GateVerdict.FAIL]
        warns = [c for c in checks if c.verdict == GateVerdict.WARN]
        score = sum(1 for c in checks if c.verdict == GateVerdict.PASS) / max(1, len(checks))
        approved = not fails and score >= 0.8
        reasons = [c.detail for c in fails] or (
            ["all_hard_gates_passed"] if approved else [c.detail for c in warns]
        )
        return PromotionDecision(
            approved=approved,
            stage=stage,
            score=round(score, 4),
            checks=checks,
            reasons=reasons,
        )

    def _cmp(
        self, name, observed, threshold, ok, detail, higher_is_better: bool = True
    ) -> GateCheck:
        if ok:
            verdict = GateVerdict.PASS
        else:
            # Soft warn band: within 10% of threshold.
            try:
                obs = float(observed)
                thr = float(threshold)
                near = abs(obs - thr) <= abs(thr) * 0.1 + 1e-9 if thr != 0 else abs(obs) < 1e-9
            except Exception:
                near = False
            verdict = GateVerdict.WARN if near else GateVerdict.FAIL
        return GateCheck(name, verdict, observed, threshold, detail)


@dataclass
class StrategyGovernor:
    """Tracks strategy lifecycle and applies promotion gates."""

    gate: PromotionGate = field(default_factory=PromotionGate)
    promotions: list[dict] = field(default_factory=list)
    statuses: dict[str, str] = field(default_factory=dict)

    def evaluate_promotion(
        self,
        strategy_id: str,
        metrics: dict[str, Any],
        stage: str = "paper",
        experiment_id: str | None = None,
    ) -> PromotionDecision:
        decision = self.gate.evaluate(metrics, stage=stage)
        record = {
            "strategy_id": strategy_id,
            "experiment_id": experiment_id,
            "decision": decision.to_dict(),
        }
        self.promotions.append(record)
        if len(self.promotions) > 200:
            self.promotions = self.promotions[-100:]
        if decision.approved:
            self.statuses[strategy_id] = f"promoted_to_{stage}"
        else:
            self.statuses[strategy_id] = f"rejected_at_{stage}"
        return decision

    def snapshot(self) -> dict:
        return {
            "statuses": dict(self.statuses),
            "promotion_count": len(self.promotions),
            "recent": self.promotions[-20:],
            "gate": {
                "min_trades": self.gate.min_trades,
                "min_expectancy": self.gate.min_expectancy,
                "max_drawdown_pct": self.gate.max_drawdown_pct,
                "min_oos_stability": self.gate.min_oos_stability,
                "min_mc_robustness": self.gate.min_mc_robustness,
            },
        }
