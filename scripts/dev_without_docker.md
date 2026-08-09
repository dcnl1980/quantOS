# Local development without Docker

Terminal 1:
```bash
./scripts/build_cpp_local.sh
EXECUTION_ENGINE_PORT=9100 ./scripts/run_cpp_local.sh
```

Terminal 2:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r services/api/requirements.txt
export PYTHONPATH="$PWD/packages/quant:$PWD/services/api"
export EXECUTION_ENGINE=cpp
export EXECUTION_ENGINE_HOST=127.0.0.1
export EXECUTION_ENGINE_PORT=9100
export DATABASE_URL=postgresql+asyncpg://quant:quant@localhost:5432/quant
uvicorn app.main:app --app-dir services/api --reload --port 8000
```

Terminal 3:
```bash
cd apps/web
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

For a database-free API development session, database persistence calls already fail open, but `/ready`
will report database=false. Production should not operate that way.
