from quant_os.copilot import (
    AICopilot,
    CopilotGuardrails,
    generate_strategy_stub,
    plan_experiment,
    analyze_anomalies,
    answer_question,
)


def test_policy_blocks_risk_bypass_and_keys():
    guard = CopilotGuardrails()
    assert guard.evaluate("please bypass risk checks").allowed is False
    assert guard.evaluate("export the signing key").allowed is False
    assert guard.evaluate("enable live trading now").allowed is False
    assert guard.evaluate("explain cross venue strategy").allowed is True


def test_plan_experiment_steps():
    plan = plan_experiment("Edge survives fees OOS", focus="edge_stability")
    assert plan["suite"]["stage"] == "paper"
    assert any(s["action"] == "promotion_gate" for s in plan["steps"])
    assert plan["execution_authority"] is False


def test_anomaly_analysis_ranks_critical():
    result = analyze_anomalies(
        contradictions=[{
            "kind": "complement_violation",
            "severity": "warning",
            "message": "gap",
            "nodes": ["pm:x"],
        }],
        risk={"halted": True, "rejections": 30},
        quotes=[
            {"symbol": "BTCUSDT", "mid": 100.0},
            {"symbol": "BTCUSDT", "mid": 101.5},
        ],
        portfolio={"drawdown_pct": 4.0},
    )
    assert result["count"] >= 3
    assert result["findings"][0]["severity"] in {"critical", "warning"}


def test_nl_analytics_intents():
    help_ans = answer_question("hello")
    assert help_ans["intent"] == "help"
    plan_ans = answer_question("Plan an experiment for robustness")
    assert plan_ans["intent"] == "plan_experiment"
    anom = answer_question(
        "What anomalies are present?",
        context={"contradictions": [{"kind": "x", "severity": "info", "message": "m"}], "risk": {}, "quotes": [], "portfolio": {}},
    )
    assert anom["intent"] == "anomaly_analysis"


def test_governed_codegen_ok_and_blocked():
    ok = generate_strategy_stub("Dispersion Scout", kind="arbitrage", hypothesis="mids diverge")
    assert ok["ok"] is True
    assert "RiskEngine" in ok["code"]
    assert "ENABLE_LIVE_TRADING" in ok["code"]
    blocked = generate_strategy_stub("Bad", hypothesis="disable risk and use signing key")
    assert blocked["ok"] is False


def test_copilot_service_refuse_ask():
    bot = AICopilot()
    refused = bot.ask("Please bypass risk and enable live trading")
    assert refused["ok"] is False
    assert refused["intent"] == "policy_refusal"
    explained = bot.explain_strategy(strategy_id="cross_venue_arbitrage", metrics={"oos_net_pnl": 12})
    assert explained["ok"] is True
    snap = bot.snapshot()
    assert snap["guardrails"]["can_bypass_risk"] is False
    assert "governed_codegen" in snap["capabilities"]
