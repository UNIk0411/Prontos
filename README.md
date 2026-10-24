# PRONTOS

PRONTOS is a locally runnable engineering simulation orchestration platform. It combines a Python FastAPI backend with a Next.js frontend for dependency-aware scheduling, per-organization resource controls, deterministic workload execution, benchmark comparisons, and role-based access.

## Quick start

1. Install JavaScript dependencies:
   npm install
2. Install Python dependencies:
   py -3.11 -m pip install -r apps/api/requirements.txt
3. Start the API:
   npm run dev:api
4. Start the web app:
   npm run dev:web
5. Open http://localhost:3000

### Use the linked Neon database locally

Install the Neon CLI with `npm i -g neon@latest`, then link this repository to its Neon project and PostgreSQL branch:

```sh
neon init -y --org-id org-small-sun-52118135 --project-id fancy-surf-92277450 --branch production --services postgres
neon deploy
```

The CLI writes `DATABASE_URL` and `DATABASE_URL_UNPOOLED` to the root `.env.local`; that file is git-ignored. The API loads this file and uses the pooled `DATABASE_URL` for SQLAlchemy/psycopg. The unpooled URL is reserved for schema migrations and administration. When a remote database URL is configured, the API defaults to production mode and requires a strong `PRONTOS_JWT_SECRET`, explicit `PRONTOS_CORS_ORIGINS`, and bootstrap administrator values instead of creating local demo accounts. Vercel does not read your local `.env.local`, so add the pooled `DATABASE_URL` and other production variables to the Vercel project's Production environment separately.

### Default login credentials

- admin@prontos.local / admin123 (platform administrator)
- operator@prontos.local / operator123
- viewer@prontos.local / viewer123

These accounts are for local development only. Production startup requires explicit bootstrap administrator settings and a non-default signing secret.

## Organizations and access

- Organizations have isolated users, experiments, jobs, and worker pools.
- Organization administrators manage users and organization quotas.
- A platform administrator can provision organizations and their first administrator.
- Experiment creation enforces organization CPU, memory, and committed-budget quotas.
- Scheduling dispatches only to online workers that support the workload and have enough free CPU and memory.
- JSON and CSV benchmark reports support status, category, policy, and creation-date filters.

## Container deployment

Copy `.env.example` to `.env` and set a unique `PRONTOS_JWT_SECRET` before using Docker Compose. For a production environment, also set `PRONTOS_ENV=production`, a trusted explicit `PRONTOS_CORS_ORIGINS` list, and all three `PRONTOS_BOOTSTRAP_ADMIN_*` values. Production startup rejects the development signing secret and wildcard CORS.

- Environment variables are defined in [.env.example](.env.example)
- Docker packaging is available via [docker-compose.yml](docker-compose.yml)
- Container images for both the API and web app are defined in [apps/api/Dockerfile](apps/api/Dockerfile) and [apps/web/Dockerfile](apps/web/Dockerfile)
- Start locally with `docker compose up --build`

Local development uses SQLite. Hosted deployments should use a managed database; SQLite on a hosting provider's ephemeral filesystem can lose data after restarts or redeploys. A horizontally scaled production deployment should also use a shared session/token strategy, TLS termination, and a dedicated workload executor.

### Free full-stack deployment with Vercel and Neon

The root [vercel.json](./vercel.json) deploys the Next.js frontend and FastAPI backend together as Vercel Services behind one website URL. Neon Postgres stores data outside the serverless function filesystem. Vercel Services are currently in Beta and available on all plans; Hobby usage limits and provider terms apply. This is a demo deployment, not a production SLA or horizontally scalable simulation worker system.

1. Create a free project at [Neon](https://neon.tech/). Choose Singapore if available, then copy the pooled connection string from Neon's **Connect** dialog. Keep `sslmode=require` and keep the string private.
2. In Vercel, import `UNIk0411/Prontos` (or open its existing project), select branch `main`, and set **Root Directory** to `.` (the repository root). Do not set it to `apps/web`; Vercel needs the root `vercel.json` to configure both services. Vercel routes `/api/*` to FastAPI and other paths to Next.js.
3. In the Vercel project's **Environment Variables**, add for Production:
   - `DATABASE_URL`: the Neon pooled connection string (`PRONTOS_DATABASE_URL` is also accepted by the API).
   - `PRONTOS_ENV`: `production`.
   - `PRONTOS_JWT_SECRET`: a unique random value of at least 32 characters.
   - `PRONTOS_CORS_ORIGINS`: your exact Vercel website origin, e.g. `https://your-project.vercel.app` (no trailing slash).
   - `PRONTOS_BOOTSTRAP_ADMIN_EMAIL`, `PRONTOS_BOOTSTRAP_ADMIN_USERNAME`, and `PRONTOS_BOOTSTRAP_ADMIN_PASSWORD`: your own administrator details; use a unique password of at least 12 characters.
4. Remove any old `NEXT_PUBLIC_API_URL` value that points to Render. The frontend uses the same-origin `/api` routes in production; local development continues to use `http://localhost:8000`.
5. Redeploy from `main`. Check `<your Vercel URL>/api/health`, then sign in with the bootstrap email and password you set in Vercel. Do not use the local demo credentials.

Vercel Functions are request-based and have execution limits; this setup is for trying the app and short simulations, not long-running jobs or persistent workers. Neon Free has quotas and scales to zero when idle. Review current [Vercel plan limits](https://vercel.com/pricing) and [Neon pricing](https://neon.com/pricing). The race-strategy simulator remains unvalidated.

## Race strategy prototype

Experiments can use the `Race strategy simulation` category to evaluate a simple deterministic pit strategy from lap count, baseline lap time, fuel use, tire wear, pit loss, and maximum stint length. The optimizer chooses feasible pit laps; manual mode accepts explicit pit laps through the API or UI. Results include per-lap timing, fuel, tire age, and pit-stop records.

This is a strategy-planning prototype, **not** an F1 vehicle or race simulator. Its model is explicitly marked `UNVALIDATED` and omits weather, traffic, overtaking, incidents, safety cars, tire compounds, vehicle dynamics, and regulatory details. The project has no calibrated telemetry, validated reference runs, or production worker queue. Do not use its outputs for real-world race decisions. Production readiness requires domain-approved requirements and data, model calibration and independent validation, durable asynchronous workers, production database/deployment controls, and operational testing.

### Inspect a free historical race-data sample

OpenF1 provides free historical data from 2023 onward without authentication. To inspect timed laps and tire stints for Max Verstappen at the 2024 Bahrain Grand Prix:

```powershell
cd apps/api
py -3.11 scripts/inspect_race_reference.py
```

The script uses only Python's standard library, fetches the race session, driver, lap, and tire-stint records, writes them to `apps/api/data/reference/2024_Bahrain_VER_laps.csv`, and prints fastest and median lap-time summaries. It needs internet access. Change the selection with `--year`, `--event`, `--session`, and `--driver`, or choose a CSV destination with `--output`.

This is a data-access and inspection demo, **not model validation**. A race's observed lap times alone do not provide calibrated fuel, tire degradation, pit-loss, traffic, or weather inputs. OpenF1 is an unofficial community project that describes historical data use as educational and research; check its current terms before other use or redistribution. OpenF1 is not affiliated with Formula 1.

To compare the observed stint/pit pattern with a sensitivity sweep of the prototype’s optimizer (not a validation), run:

```powershell
py -3.11 scripts/compare_race_reference.py
```

This writes `apps/api/data/reference/2024_Bahrain_VER_comparison.json`. By default it explores pit losses of 18, 22, and 26 seconds and tire-wear assumptions of 0.03, 0.06, 0.09, and 0.12 seconds per lap of tire age. These are illustrative sweep values, not Bahrain measurements. Change them with `--pit-loss-seconds` and `--tire-wear-seconds-per-lap`; results remain exploratory because observed strategy, fuel load, tire condition, and race circumstances are not fully modeled.

## Demo

The default organization includes a deterministic dependency graph, sample workers, and demo workloads. Reset is scoped to the signed-in administrator's organization.

## Tests

- Backend: `cd apps/api; py -3.11 -m pytest`
- Or from the repository root: `npm run test:api`
- Frontend: `npm --prefix apps/web run test`
- Frontend type check: `& .\node_modules\.bin\tsc.cmd --noEmit -p .\apps\web\tsconfig.json`
