#include "engine.hpp"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <iomanip>
#include <sstream>
#include <vector>

namespace quant {

static std::vector<std::string> split(const std::string& s, char delim) {
    std::vector<std::string> out;
    std::string cur;
    for (char c : s) {
        if (c == delim) { out.push_back(cur); cur.clear(); }
        else cur.push_back(c);
    }
    out.push_back(cur);
    return out;
}

static std::string esc(const std::string& s) {
    std::string o;
    o.reserve(s.size() + 8);
    for (char c : s) {
        if (c == '"' || c == '\\') o.push_back('\\');
        o.push_back(c);
    }
    return o;
}

ExecutionEngine::ExecutionEngine(RiskConfig cfg)
    : cfg_(cfg), cash_(cfg.initial_cash), realized_pnl_(0.0),
      peak_equity_(cfg.initial_cash), turnover_(0.0),
      trade_count_(0), rejection_count_(0), halted_(false) {}

ExecResult ExecutionEngine::reject(const std::string& reason, std::uint64_t latency_ns) {
    ++rejection_count_;
    if (static_cast<int>(rejection_count_) >= cfg_.circuit_breaker_rejections) halted_ = true;
    ExecResult r;
    r.allowed = false;
    r.reason = reason;
    r.realized_pnl = realized_pnl_;
    r.equity = cash_;
    r.drawdown_pct = peak_equity_ > 0 ? std::max(0.0, (peak_equity_ - cash_) / peak_equity_ * 100.0) : 0.0;
    r.latency_ns = latency_ns;
    r.trade_count = trade_count_;
    return r;
}

ExecResult ExecutionEngine::execute_arbitrage(const ExecRequest& req) {
    return decide_arbitrage(req, true);
}

ExecResult ExecutionEngine::evaluate_arbitrage(const ExecRequest& req) {
    return decide_arbitrage(req, false);
}

ExecResult ExecutionEngine::decide_arbitrage(const ExecRequest& req, bool commit) {
    const auto started = std::chrono::steady_clock::now();
    std::lock_guard<std::mutex> lock(mutex_);

    auto elapsed = [&]() -> std::uint64_t {
        return static_cast<std::uint64_t>(
            std::chrono::duration_cast<std::chrono::nanoseconds>(
                std::chrono::steady_clock::now() - started
            ).count()
        );
    };

    // Shadow/eval path must not trip the circuit breaker or mutate counters.
    auto soft_reject = [&](const std::string& reason) {
        if (commit) return reject(reason, elapsed());
        ExecResult r;
        r.allowed = false;
        r.reason = reason;
        r.realized_pnl = realized_pnl_;
        r.equity = cash_;
        r.drawdown_pct = peak_equity_ > 0
            ? std::max(0.0, (peak_equity_ - cash_) / peak_equity_ * 100.0) : 0.0;
        r.latency_ns = elapsed();
        r.trade_count = trade_count_;
        return r;
    };

    if (halted_) return soft_reject("circuit_breaker_halted");
    if (!std::isfinite(req.buy_price) || !std::isfinite(req.sell_price) ||
        req.buy_price <= 0 || req.sell_price <= 0)
        return soft_reject("invalid_price");
    if (req.sell_price <= req.buy_price)
        return soft_reject("non_positive_spread");
    if (req.net_edge_bps < cfg_.min_net_edge_bps)
        return soft_reject("edge_below_minimum");
    if (req.slippage_bps > cfg_.max_slippage_bps)
        return soft_reject("slippage_above_maximum");
    if (realized_pnl_ <= -cfg_.max_daily_loss)
        return soft_reject("daily_loss_limit");

    const double current_dd = peak_equity_ > 0
        ? std::max(0.0, (peak_equity_ - cash_) / peak_equity_ * 100.0) : 0.0;
    if (current_dd >= cfg_.max_drawdown_pct)
        return soft_reject("drawdown_limit");

    double approved = std::min(req.desired_notional, cfg_.max_order_notional);
    if (req.max_notional > 0.0) approved = std::min(approved, req.max_notional);
    approved = std::min(approved, std::max(0.0, cash_ * 0.05));
    if (approved <= 0.0) return soft_reject("zero_approved_notional");

    const double slip = req.slippage_bps / 10000.0;
    const double buy_exec = req.buy_price * (1.0 + slip);
    const double sell_exec = req.sell_price * (1.0 - slip);
    const double qty = approved / buy_exec;
    const double buy_notional = qty * buy_exec;
    const double sell_notional = qty * sell_exec;
    const double buy_fee = buy_notional * req.buy_fee_bps / 10000.0;
    const double sell_fee = sell_notional * req.sell_fee_bps / 10000.0;
    const double pnl = (sell_notional - buy_notional) - buy_fee - sell_fee;

    if (commit) {
        cash_ += pnl;
        realized_pnl_ += pnl;
        peak_equity_ = std::max(peak_equity_, cash_);
        turnover_ += buy_notional + sell_notional;
        ++trade_count_;
        // Successful trade heals one transient rejection, but does not auto-resume a halted system.
        if (rejection_count_ > 0) --rejection_count_;
    }

    ExecResult r;
    r.allowed = true;
    r.reason = commit ? "approved" : "shadow_approved";
    r.approved_notional = approved;
    r.quantity = qty;
    r.buy_exec_price = buy_exec;
    r.sell_exec_price = sell_exec;
    r.buy_fee = buy_fee;
    r.sell_fee = sell_fee;
    r.trade_pnl = pnl;
    r.realized_pnl = commit ? realized_pnl_ : (realized_pnl_ + pnl);
    r.equity = commit ? cash_ : (cash_ + pnl);
    r.drawdown_pct = peak_equity_ > 0
        ? std::max(0.0, (peak_equity_ - (commit ? cash_ : cash_ + pnl)) / peak_equity_ * 100.0) : 0.0;
    r.latency_ns = elapsed();
    r.trade_count = trade_count_;
    return r;
}

Snapshot ExecutionEngine::snapshot() const {
    std::lock_guard<std::mutex> lock(mutex_);
    Snapshot s;
    s.initial_cash = cfg_.initial_cash;
    s.cash = cash_;
    s.equity = cash_;
    s.realized_pnl = realized_pnl_;
    s.peak_equity = peak_equity_;
    s.drawdown_pct = peak_equity_ > 0
        ? std::max(0.0, (peak_equity_ - cash_) / peak_equity_ * 100.0) : 0.0;
    s.trade_count = trade_count_;
    s.rejection_count = rejection_count_;
    s.halted = halted_;
    s.turnover = turnover_;
    return s;
}

void ExecutionEngine::reset_circuit_breaker() {
    std::lock_guard<std::mutex> lock(mutex_);
    rejection_count_ = 0;
    halted_ = false;
}

void ExecutionEngine::reset() {
    std::lock_guard<std::mutex> lock(mutex_);
    cash_ = cfg_.initial_cash;
    realized_pnl_ = 0.0;
    peak_equity_ = cfg_.initial_cash;
    turnover_ = 0.0;
    trade_count_ = 0;
    rejection_count_ = 0;
    halted_ = false;
}

bool parse_exec_line(const std::string& line, ExecRequest& o, std::string& error, bool* dry_run) {
    auto p = split(line, '|');
    if (p.size() != 13 || (p[0] != "EXEC_ARB" && p[0] != "EVAL_ARB")) {
        error = "expected EXEC_ARB or EVAL_ARB with 12 fields";
        return false;
    }
    if (dry_run) *dry_run = (p[0] == "EVAL_ARB");
    try {
        o.opportunity_id = p[1];
        o.symbol = p[2];
        o.buy_venue = p[3];
        o.sell_venue = p[4];
        o.buy_price = std::stod(p[5]);
        o.sell_price = std::stod(p[6]);
        o.net_edge_bps = std::stod(p[7]);
        o.max_notional = std::stod(p[8]);
        o.desired_notional = std::stod(p[9]);
        o.buy_fee_bps = std::stod(p[10]);
        o.sell_fee_bps = std::stod(p[11]);
        o.slippage_bps = std::stod(p[12]);
        return true;
    } catch (...) {
        error = "invalid numeric field";
        return false;
    }
}

std::string result_json(const ExecResult& r) {
    std::ostringstream s; s << std::fixed << std::setprecision(10);
    s << "{\"type\":\"execution\",\"allowed\":" << (r.allowed ? "true" : "false")
      << ",\"reason\":\"" << esc(r.reason) << "\""
      << ",\"approved_notional\":" << r.approved_notional
      << ",\"quantity\":" << r.quantity
      << ",\"buy_exec_price\":" << r.buy_exec_price
      << ",\"sell_exec_price\":" << r.sell_exec_price
      << ",\"buy_fee\":" << r.buy_fee
      << ",\"sell_fee\":" << r.sell_fee
      << ",\"trade_pnl\":" << r.trade_pnl
      << ",\"realized_pnl\":" << r.realized_pnl
      << ",\"equity\":" << r.equity
      << ",\"drawdown_pct\":" << r.drawdown_pct
      << ",\"latency_ns\":" << r.latency_ns
      << ",\"trade_count\":" << r.trade_count << "}";
    return s.str();
}

std::string snapshot_json(const Snapshot& x) {
    std::ostringstream s; s << std::fixed << std::setprecision(10);
    s << "{\"type\":\"snapshot\""
      << ",\"initial_cash\":" << x.initial_cash
      << ",\"cash\":" << x.cash
      << ",\"equity\":" << x.equity
      << ",\"realized_pnl\":" << x.realized_pnl
      << ",\"unrealized_pnl\":0.0"
      << ",\"peak_equity\":" << x.peak_equity
      << ",\"drawdown_pct\":" << x.drawdown_pct
      << ",\"positions\":{}"
      << ",\"venue_exposure\":{}"
      << ",\"trade_count\":" << x.trade_count
      << ",\"rejection_count\":" << x.rejection_count
      << ",\"halted\":" << (x.halted ? "true" : "false")
      << ",\"turnover\":" << x.turnover << "}";
    return s.str();
}

} // namespace quant
