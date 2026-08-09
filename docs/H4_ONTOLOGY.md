# H4 market ontology

## What shipped

- **Instrument/venue/underlying/settlement graph** — `LISTED_ON`, `DERIVED_FROM`, `PRICED_IN`,
  `SETTLES_FROM`, `HEDGES`, `CORRELATED_WITH`, `ARBITRAGE_WITH`, `BASIS`, `DETECTED_BY`, `CAUSED_BY`
- **Prediction-market semantics** — binary YES/NO markets, probability normalization, complement edges
- **Contradiction detection** — complement violations, out-of-range probs, inverted books, cross-venue
  dispersion, missing settlement/underlying, extreme basis
- **Polymarket bridge** — ontology ingest boundary without stale token IDs

AI remains outside the hot path. Ontology findings inform research/control views only.

## Run

```bash
curl 'http://localhost:8000/api/v1/ontology'
curl 'http://localhost:8000/api/v1/ontology/graph'
curl 'http://localhost:8000/api/v1/ontology/prediction-markets'
curl -X POST 'http://localhost:8000/api/v1/ontology/scan'
```

## Key endpoints

- `GET /api/v1/ontology`
- `GET /api/v1/ontology/graph`
- `GET /api/v1/market-graph` (alias of ontology graph)
- `GET /api/v1/ontology/prediction-markets`
- `POST /api/v1/ontology/prediction-markets`
- `POST /api/v1/ontology/prediction-markets/{id}/probability`
- `GET /api/v1/ontology/contradictions`
- `POST /api/v1/ontology/scan`

## Graph shape

```text
instrument --LISTED_ON--> venue
instrument --DERIVED_FROM--> underlying
instrument --PRICED_IN--> currency
instrument --SETTLES_FROM--> settlement_source
instrument --HEDGES--> instrument (shared underlying)
prediction_market --SETTLES_FROM--> settlement_source
outcome --OUTCOME_OF--> prediction_market
outcome --COMPLEMENTS--> outcome (YES/NO)
```
