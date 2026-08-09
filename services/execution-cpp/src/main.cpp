#include "engine.hpp"
#include <arpa/inet.h>
#include <cerrno>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <netinet/in.h>
#include <sstream>
#include <string>
#include <sys/socket.h>
#include <thread>
#include <unistd.h>

using quant::ExecutionEngine;
using quant::ExecRequest;
using quant::RiskConfig;

static double envd(const char* k, double d) {
    const char* v = std::getenv(k);
    if (!v || !*v) return d;
    try { return std::stod(v); } catch (...) { return d; }
}
static int envi(const char* k, int d) {
    const char* v = std::getenv(k);
    if (!v || !*v) return d;
    try { return std::stoi(v); } catch (...) { return d; }
}

static bool send_all(int fd, const std::string& s) {
    const char* p = s.data();
    size_t left = s.size();
    while (left) {
        ssize_t n = ::send(fd, p, left, MSG_NOSIGNAL);
        if (n <= 0) return false;
        p += n; left -= static_cast<size_t>(n);
    }
    return true;
}

static std::string error_json(const std::string& msg) {
    std::string m;
    for (char c : msg) { if (c=='"' || c=='\\') m.push_back('\\'); m.push_back(c); }
    return "{\"type\":\"error\",\"error\":\"" + m + "\"}";
}

static void client_loop(int fd, ExecutionEngine& engine) {
    std::string buffer;
    char chunk[4096];
    while (true) {
        ssize_t n = ::recv(fd, chunk, sizeof(chunk), 0);
        if (n <= 0) break;
        buffer.append(chunk, chunk+n);
        size_t pos;
        while ((pos = buffer.find('\n')) != std::string::npos) {
            std::string line = buffer.substr(0, pos);
            buffer.erase(0, pos+1);
            if (!line.empty() && line.back()=='\r') line.pop_back();

            std::string response;
            if (line == "PING") response = "{\"type\":\"pong\",\"engine\":\"cpp20\"}";
            else if (line == "SNAPSHOT") response = quant::snapshot_json(engine.snapshot());
            else if (line == "RESET") { engine.reset(); response = "{\"type\":\"reset\",\"ok\":true}"; }
            else if (line == "RESET_CB") { engine.reset_circuit_breaker(); response = "{\"type\":\"reset_cb\",\"ok\":true}"; }
            else {
                ExecRequest req; std::string err; bool dry_run = false;
                if (!quant::parse_exec_line(line, req, err, &dry_run)) response = error_json(err);
                else if (dry_run) response = quant::result_json(engine.evaluate_arbitrage(req));
                else response = quant::result_json(engine.execute_arbitrage(req));
            }
            response.push_back('\n');
            if (!send_all(fd, response)) { ::close(fd); return; }
        }
    }
    ::close(fd);
}

int main() {
    RiskConfig cfg;
    cfg.initial_cash = envd("INITIAL_CASH", 100000);
    cfg.min_net_edge_bps = envd("MIN_NET_EDGE_BPS", 8);
    cfg.max_order_notional = envd("MAX_ORDER_NOTIONAL", 2500);
    cfg.max_daily_loss = envd("MAX_DAILY_LOSS", 3000);
    cfg.max_drawdown_pct = envd("MAX_DRAWDOWN_PCT", 5);
    cfg.max_slippage_bps = envd("MAX_SLIPPAGE_BPS", 15);
    cfg.circuit_breaker_rejections = envi("CIRCUIT_BREAKER_REJECTIONS", 25);

    const int port = envi("EXECUTION_ENGINE_PORT", 9100);
    ExecutionEngine engine(cfg);

    int server = ::socket(AF_INET, SOCK_STREAM, 0);
    if (server < 0) { std::cerr << "socket failed\n"; return 1; }
    int yes = 1;
    ::setsockopt(server, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof(yes));

    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = htonl(INADDR_ANY);
    addr.sin_port = htons(static_cast<uint16_t>(port));

    if (::bind(server, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) < 0) {
        std::cerr << "bind failed: " << std::strerror(errno) << "\n"; return 1;
    }
    if (::listen(server, 256) < 0) { std::cerr << "listen failed\n"; return 1; }

    std::cout << "Quant C++20 execution engine listening on 0.0.0.0:" << port << std::endl;
    while (true) {
        int fd = ::accept(server, nullptr, nullptr);
        if (fd < 0) continue;
        std::thread(client_loop, fd, std::ref(engine)).detach();
    }
}
