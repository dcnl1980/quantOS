#!/usr/bin/env python3
import argparse
import json
import socket

p = argparse.ArgumentParser()
p.add_argument("--host", default="127.0.0.1")
p.add_argument("--port", type=int, default=9100)
a = p.parse_args()


def req(line: str):
    with socket.create_connection((a.host, a.port), timeout=2) as s:
        s.sendall((line + "\n").encode())
        data = b""
        while not data.endswith(b"\n"):
            chunk = s.recv(65536)
            if not chunk:
                break
            data += chunk
    return json.loads(data)


print("PING", req("PING"))
before = req("SNAPSHOT")
print("BEFORE", before)

shadow = req("EVAL_ARB|smoke|BTCUSDT|sim_a|sim_b|100|101|50|10000|1000|5|5|2")
print("EVAL_ARB", shadow)
assert shadow.get("allowed") is True
mid = req("SNAPSHOT")
assert abs(float(mid["cash"]) - float(before["cash"])) < 1e-9, "shadow must not mutate cash"
assert int(mid.get("trade_count", 0)) == int(before.get("trade_count", 0)), "shadow must not trade"

r = req("EXEC_ARB|smoke|BTCUSDT|sim_a|sim_b|100|101|50|10000|1000|5|5|2")
print("EXEC", r)
assert r["allowed"] and r["trade_pnl"] > 0
after = req("SNAPSHOT")
print("AFTER", after)
assert abs(float(after["cash"]) - float(before["cash"])) > 1e-9 or int(after.get("trade_count", 0)) > int(
    before.get("trade_count", 0)
)
print("RESET", req("RESET"))
print("SMOKE OK")
