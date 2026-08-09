# Production extension boundary:
# 1) discover current markets and outcome token IDs from official market/CLOB APIs;
# 2) persist market -> outcome token -> settlement source semantics;
# 3) subscribe to the official public market WebSocket with current asset IDs;
# 4) maintain L2 books from snapshots/deltas;
# 5) normalize outcome probabilities and model YES/NO complement constraints + fees.
# Stale hard-coded token IDs are intentionally not included.
