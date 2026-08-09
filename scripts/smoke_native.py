#!/usr/bin/env python3
import argparse,json,socket

p=argparse.ArgumentParser()
p.add_argument("--host",default="127.0.0.1")
p.add_argument("--port",type=int,default=9100)
a=p.parse_args()

def req(line):
    with socket.create_connection((a.host,a.port),timeout=2) as s:
        s.sendall((line+"\n").encode())
        data=b""
        while not data.endswith(b"\n"):
            chunk=s.recv(65536)
            if not chunk:break
            data+=chunk
    return json.loads(data)

print("PING",req("PING"))
print("BEFORE",req("SNAPSHOT"))
r=req("EXEC_ARB|smoke|BTCUSDT|sim_a|sim_b|100|101|50|10000|1000|5|5|2")
print("EXEC",r)
assert r["allowed"] and r["trade_pnl"]>0
print("AFTER",req("SNAPSHOT"))
print("RESET",req("RESET"))
print("SMOKE OK")
