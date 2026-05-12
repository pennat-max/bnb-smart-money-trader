# BNB Smart Money AI Trader

Signal-only BNBUSDT perpetual trader dashboard.

## Safety defaults

- Signal-only mode is enabled by default.
- Real trading is not implemented.
- Order testing is allowed only when `BINANCE_USE_TESTNET=true`.
- API keys are loaded only from environment variables.

## Apps

- `apps/api`: Python FastAPI backend.
- `apps/web`: Next.js dashboard.
- `supabase/schema.sql`: trade journal schema.

## Environment

Copy the examples and fill only the values you need:

```powershell
Copy-Item apps/api/.env.example apps/api/.env
Copy-Item apps/web/.env.local.example apps/web/.env.local
```

Backend variables:

```env
APP_MODE=signal_only
BINANCE_USE_TESTNET=true
BINANCE_API_KEY=
BINANCE_API_SECRET=
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
```

Frontend variables:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Run locally

Backend:

```powershell
cd apps/api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Frontend:

```powershell
cd apps/web
npm install
npm run dev
```

Then open `http://localhost:3000`.

Or run both services after dependencies are installed:

```powershell
.\start-local.ps1
```

## Supabase

Supabase is optional during sandbox testing. If `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are empty, the backend writes journal entries to `apps/api/data/signals.jsonl`.

When you are ready for Supabase, run `supabase/schema.sql` in the Supabase SQL editor and fill `SUPABASE_URL` plus `SUPABASE_SERVICE_ROLE_KEY` in `apps/api/.env`.

## Notes

This project is for education and testnet workflows only. It does not provide financial advice.
