# Online Operations

This project is set up so the live bot does not need the local computer.

## Live URLs

- Dashboard: https://bnb-smart-money-trader.vercel.app
- API health: https://bnb-smart-money-api-production.up.railway.app/health
- API status: https://bnb-smart-money-api-production.up.railway.app/api/status

## What Runs Online

- Vercel hosts the Next.js dashboard.
- Railway hosts the FastAPI backend and paper learning loop.
- Supabase stores signal history and paper-learning data.
- GitHub is the source of truth for code.
- GitHub Actions checks cloud health every 30 minutes.

## Mobile Workflow

1. Open the dashboard URL on mobile.
2. Check `Paper loop`, `AI Learning Memory`, and `Setup History`.
3. Ask Codex/ChatGPT to change features by referencing this GitHub repo.
4. Changes should be pushed to `main`.
5. Vercel and Railway redeploy automatically from GitHub.

## Safety Rules

- Real trading is disabled.
- The backend stays in `signal_only` mode.
- Paper trading is simulation only.
- Binance keys must stay in environment variables.
- Never put API keys in GitHub files.

## Cloud Health

Open GitHub Actions in the repo and check `Cloud health check`.

The workflow checks:

- Railway `/health`
- Railway `/api/status`
- Vercel `/status`
- Vercel `/live`

You can run it manually from mobile by pressing `Run workflow`.

## If Something Looks Quiet

If `AI Learning Memory` does not increase, it usually means the bot is waiting:

- Signal is `WAIT` or `CANCEL`
- Confidence is below 70
- A paper position is already open
- TP/SL has not been hit yet

Use `Run Paper Tick` on the dashboard to see the latest wait reason.

