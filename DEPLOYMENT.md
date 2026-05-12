# Cloud Deployment

Use this order when moving out of local sandbox.

## 1. Supabase

Create a new Supabase project for this bot, then run:

```sql
-- contents of supabase/schema.sql
```

Backend environment variables:

```env
SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...
```

Keep `SUPABASE_SERVICE_ROLE_KEY` only in the backend service. Do not add it to Vercel.

## 2. Backend

Recommended: Railway or Render.

Required backend variables:

```env
APP_MODE=signal_only
BINANCE_USE_TESTNET=true
BINANCE_API_KEY=
BINANCE_API_SECRET=
SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...
FRONTEND_ORIGINS=https://your-vercel-domain.vercel.app,http://127.0.0.1:3001
RISK_DAILY_TARGET_PCT=1
RISK_MAX_DAILY_LOSS_PCT=2
RISK_MIN_CONFIDENCE=70
RISK_MAX_ACTIVE_BNB_POSITIONS=1
```

## 3. Vercel Dashboard

Create a new Vercel project with root directory:

```text
apps/web
```

Vercel environment variable:

```env
NEXT_PUBLIC_API_URL=https://your-backend-domain
```

After Vercel gives you a domain, add it to the backend `FRONTEND_ORIGINS`.
