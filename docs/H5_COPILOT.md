# H5 AI Quant Copilot

## What shipped

Deterministic research/control-plane copilot (no LLM required in the hot path):

- **Strategy explanations** — narrate detector logic, research metrics, governance status
- **Experiment planning** — Strategy Factory step plans (walk-forward → Monte Carlo → sensitivity → gates)
- **Anomaly analysis** — ontology contradictions, risk halt/rejections, quote dispersion, drawdown
- **NL analytics** — intent-routed answers over portfolio/ontology/strategy context
- **Governed codegen** — research strategy stubs that cannot disable risk, hold keys, or enable live

## Hard boundaries

```text
copilot  ->  research / ontology / explanations
         -x-> risk bypass
         -x-> venue signing keys
         -x-> live capital enablement
         -x-> promotion-gate skip
```

## Run

```bash
curl -X POST 'http://localhost:8000/api/v1/copilot/explain'
curl -X POST 'http://localhost:8000/api/v1/copilot/plan-experiment?hypothesis=Edge%20persists%20OOS'
curl -X POST 'http://localhost:8000/api/v1/copilot/analyze'
curl -X POST 'http://localhost:8000/api/v1/copilot/ask?question=What%20anomalies%20are%20present'
curl -X POST 'http://localhost:8000/api/v1/copilot/codegen?name=DispersionScout&kind=cross_venue_arbitrage'
```

## Key endpoints

- `GET /api/v1/copilot`
- `POST /api/v1/copilot/explain`
- `POST /api/v1/copilot/explain-fill`
- `POST /api/v1/copilot/plan-experiment`
- `POST /api/v1/copilot/analyze`
- `POST /api/v1/copilot/ask`
- `POST /api/v1/copilot/codegen`
