#include "engine.hpp"
#include <cmath>
#include <iostream>
#include <stdexcept>

static void check(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}

int main() {
    quant::RiskConfig cfg;
    cfg.initial_cash = 100000;
    cfg.min_net_edge_bps = 8;
    cfg.max_order_notional = 2500;
    cfg.max_slippage_bps = 15;

    quant::ExecutionEngine engine(cfg);

    quant::ExecRequest r;
    r.opportunity_id="x"; r.symbol="BTCUSDT"; r.buy_venue="a"; r.sell_venue="b";
    r.buy_price=100.0; r.sell_price=101.0; r.net_edge_bps=50;
    r.max_notional=10000; r.desired_notional=5000;
    r.buy_fee_bps=5; r.sell_fee_bps=5; r.slippage_bps=2;

    auto x = engine.execute_arbitrage(r);
    check(x.allowed, "positive opportunity should execute");
    check(std::abs(x.approved_notional - 2500.0) < 1e-9, "notional cap failed");
    check(x.trade_pnl > 0, "expected positive paper PnL");
    check(engine.snapshot().trade_count == 1, "trade count failed");

    r.net_edge_bps = 2;
    auto y = engine.execute_arbitrage(r);
    check(!y.allowed, "low edge should reject");
    check(y.reason == "edge_below_minimum", "wrong rejection reason");

    quant::ExecRequest parsed;
    std::string error;
    bool ok = quant::parse_exec_line(
        "EXEC_ARB|id|BTCUSDT|binance|coinbase|100|101|50|5000|1000|10|12|2",
        parsed, error
    );
    check(ok, "protocol parse failed");
    check(parsed.symbol == "BTCUSDT" && parsed.sell_price == 101, "protocol fields wrong");

    engine.reset_circuit_breaker();
    engine.reset();
    check(engine.snapshot().trade_count == 0, "reset trade count failed");
    check(std::abs(engine.snapshot().equity - 100000.0) < 1e-9, "reset equity failed");

    std::cout << "engine-tests: OK\n";
    return 0;
}
