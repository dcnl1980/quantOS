#pragma once
#include <cstdint>
#include <string>
#include <unordered_map>
#include <mutex>

namespace quant {

struct RiskConfig {
    double initial_cash = 100000.0;
    double min_net_edge_bps = 8.0;
    double max_order_notional = 2500.0;
    double max_daily_loss = 3000.0;
    double max_drawdown_pct = 5.0;
    double max_slippage_bps = 15.0;
    int circuit_breaker_rejections = 25;
};

struct ExecRequest {
    std::string opportunity_id;
    std::string symbol;
    std::string buy_venue;
    std::string sell_venue;
    double buy_price = 0.0;
    double sell_price = 0.0;
    double net_edge_bps = 0.0;
    double max_notional = 0.0;
    double desired_notional = 0.0;
    double buy_fee_bps = 0.0;
    double sell_fee_bps = 0.0;
    double slippage_bps = 0.0;
};

struct ExecResult {
    bool allowed = false;
    std::string reason;
    double approved_notional = 0.0;
    double quantity = 0.0;
    double buy_exec_price = 0.0;
    double sell_exec_price = 0.0;
    double buy_fee = 0.0;
    double sell_fee = 0.0;
    double trade_pnl = 0.0;
    double realized_pnl = 0.0;
    double equity = 0.0;
    double drawdown_pct = 0.0;
    std::uint64_t latency_ns = 0;
    std::uint64_t trade_count = 0;
};

struct Snapshot {
    double initial_cash = 0.0;
    double cash = 0.0;
    double equity = 0.0;
    double realized_pnl = 0.0;
    double peak_equity = 0.0;
    double drawdown_pct = 0.0;
    std::uint64_t trade_count = 0;
    std::uint64_t rejection_count = 0;
    bool halted = false;
    double turnover = 0.0;
};

class ExecutionEngine {
public:
    explicit ExecutionEngine(RiskConfig cfg);
    ExecResult execute_arbitrage(const ExecRequest& req);
    // Dry-run risk + hypothetical fill math; never mutates portfolio state.
    ExecResult evaluate_arbitrage(const ExecRequest& req);
    Snapshot snapshot() const;
    void reset();
    void reset_circuit_breaker();

private:
    ExecResult decide_arbitrage(const ExecRequest& req, bool commit);
    ExecResult reject(const std::string& reason, std::uint64_t latency_ns);
    RiskConfig cfg_;
    mutable std::mutex mutex_;
    double cash_;
    double realized_pnl_;
    double peak_equity_;
    double turnover_;
    std::uint64_t trade_count_;
    std::uint64_t rejection_count_;
    bool halted_;
};

std::string result_json(const ExecResult& r);
std::string snapshot_json(const Snapshot& s);
// Accepts EXEC_ARB|... or EVAL_ARB|... (same payload). Sets dry_run when EVAL_ARB.
bool parse_exec_line(const std::string& line, ExecRequest& out, std::string& error, bool* dry_run = nullptr);

} // namespace quant
