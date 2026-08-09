#!/usr/bin/env python3
import argparse,json,socket,time,statistics

p=argparse.ArgumentParser()
p.add_argument("--host",default="127.0.0.1")
p.add_argument("--port",type=int,default=9100)
p.add_argument("-n","--iterations",type=int,default=10000)
a=p.parse_args()

with socket.create_connection((a.host,a.port),timeout=3) as s:
    f=s.makefile("rwb",buffering=0)
    internal=[];rtts=[]
    for i in range(a.iterations):
        line=f"EXEC_ARB|bench{i}|BTCUSDT|a|b|100|101|50|1000000|100|0|0|0\n".encode()
        t=time.perf_counter_ns()
        f.write(line)
        obj=json.loads(f.readline())
        rtts.append(time.perf_counter_ns()-t)
        internal.append(int(obj.get("latency_ns",0)))
def pct(xs,p):
    xs=sorted(xs);return xs[min(len(xs)-1,int(len(xs)*p))]
print(f"requests={a.iterations}")
print(f"internal engine ns: avg={int(statistics.mean(internal))} p50={pct(internal,.50)} p95={pct(internal,.95)} p99={pct(internal,.99)}")
print(f"local TCP RTT ns:   avg={int(statistics.mean(rtts))} p50={pct(rtts,.50)} p95={pct(rtts,.95)} p99={pct(rtts,.99)}")
