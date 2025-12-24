# Deployment Guide

Deploy the Bookmarks application to Railway using Railpack (Railway's auto-build system).

## Architecture

| Service | Description | Root Directory |
|---------|-------------|----------------|
| **api** | FastAPI backend | `/` |
| **mcp** | MCP server for AI agents | `/` |
| **frontend** | React SPA | `/frontend` |
| **Postgres** | PostgreSQL database | (managed by Railway) |
| **Redis** | Rate limiting and auth cache | (managed by Railway) |

---

## Prerequisites

1. [Railway account](https://railway.app)
2. [Railway CLI](https://docs.railway.com/guides/cli) installed:
   ```bash
   npm install -g @railway/cli
   railway login
   ```
3. Auth0 account configured (see main README)

---

## Initial Setup

### Step 1: Create Railway Project

```bash
railway init
```

Or via dashboard: Click **+ New Project** → **Empty Project**

### Step 2: Add PostgreSQL

In the Railway dashboard:
1. Press `Cmd+K` (Mac) or `Ctrl+K` (Windows)
2. Type "Postgres" and select **Add PostgreSQL**

Railway automatically creates these variables on the Postgres service:
- `DATABASE_URL`
- `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE`

### Step 2b: Add Redis

In the Railway dashboard:
1. Press `Cmd+K` (Mac) or `Ctrl+K` (Windows)
2. Type "Redis" and select **Add Redis**

Railway automatically creates these variables on the Redis service:
- `REDIS_URL`
- `REDISHOST`, `REDISPORT`, `REDISUSER`, `REDISPASSWORD`

Redis is used for:
- **Rate limiting**: Tiered limits by auth type (PAT vs Auth0) and operation type
- **Auth caching**: 5-minute TTL cache for user lookups to reduce database load
- **Fail-open mode**: If Redis is unavailable, requests are allowed (degraded mode)

### Step 3: Create Services

Create 3 services, each connected to your GitHub repo:

1. Click **+ Create** → **GitHub Repo** → Select `bookmarks`
2. Repeat 2 more times (you'll have 3 services all pointing to the same repo)

### Step 4: Configure Each Service

Click on each service → **Settings** tab → Configure as follows:

#### API Service

**Settings → Source:**
- Rename service to `api` (click the name at top)
- Enable **Wait for CI** (deploys only after GitHub Actions pass)

**Settings → Build:**
- Build Command: `uv sync --no-dev`
- Watch Paths: `backend/**`, `pyproject.toml`

**Settings → Deploy:**
- Start Command: `cd backend/src && uv run uvicorn api.main:app --host 0.0.0.0 --port $PORT`

**Settings → Networking:**
- Click **Generate Domain**

#### MCP Service

**Settings → Source:**
- Rename service to `mcp`
- Enable **Wait for CI**

**Settings → Build:**
- Build Command: `uv sync --no-dev`
- Watch Paths: `backend/**`, `pyproject.toml`

**Settings → Deploy:**
- Start Command: `cd backend/src && uv run python -m mcp_server`

**Settings → Networking:**
- Click **Generate Domain**

#### Frontend Service

**Settings → Source:**
- Rename service to `frontend`
- Root Directory: `/frontend`
- Enable **Wait for CI**

**Settings → Networking:**
- Click **Generate Domain**

### Step 5: Configure Environment Variables

Click on each service → **Variables** tab.

#### API Service Variables

Click **New Variable** or use **RAW Editor** to add:

```
DATABASE_URL=postgresql+asyncpg://<manually-set-see-below>
REDIS_URL=${{Redis.REDIS_URL}}
CORS_ORIGINS=https://${{frontend.RAILWAY_PUBLIC_DOMAIN}}
VITE_AUTH0_DOMAIN=<your-auth0-domain>
VITE_AUTH0_CLIENT_ID=<your-auth0-client-id>
VITE_AUTH0_AUDIENCE=<your-auth0-api-identifier>
VITE_API_URL=https://${{api.RAILWAY_PUBLIC_DOMAIN}}
VITE_FRONTEND_URL=https://${{frontend.RAILWAY_PUBLIC_DOMAIN}}
```

**Note:** `VITE_API_URL` and `VITE_FRONTEND_URL` are used by the backend to generate helpful error messages (e.g., consent enforcement instructions).

**Important: DATABASE_URL must be set manually.** Railway's Postgres provides `postgresql://` but this app requires `postgresql+asyncpg://` for async SQLAlchemy. Do NOT use `${{Postgres.DATABASE_URL}}`.

**Note:** `REDIS_URL` can use the Railway variable reference `${{Redis.REDIS_URL}}`. Redis fails open, so the app works even if Redis is temporarily unavailable.

To set DATABASE_URL:
1. Click the **Postgres** service → **Variables** tab
2. Copy the `DATABASE_URL` value (e.g., `postgresql://user:pass@host:5432/railway`)
3. Go back to the **api** service → **Variables** tab
4. Add `DATABASE_URL` and paste the copied value
5. Change `postgresql://` to `postgresql+asyncpg://` at the start of the URL

#### MCP Service Variables

```
VITE_API_URL=https://${{api.RAILWAY_PUBLIC_DOMAIN}}
```

**Note:** Railway automatically provides the `PORT` variable - do not set it manually.

#### Frontend Service Variables

```
VITE_API_URL=https://${{api.RAILWAY_PUBLIC_DOMAIN}}
VITE_MCP_URL=https://${{mcp.RAILWAY_PUBLIC_DOMAIN}}
VITE_AUTH0_DOMAIN=<your-auth0-domain>
VITE_AUTH0_CLIENT_ID=<your-auth0-client-id>
VITE_AUTH0_AUDIENCE=<your-auth0-api-identifier>
```

**Note:** Railway may warn about egress fees for `VITE_API_URL` and `VITE_MCP_URL` referencing public endpoints. You can ignore this - the frontend is a static SPA, so all API calls happen from the user's browser, not between Railway services.

### Step 6: Configure Auth0 for Deployed URLs

After generating your frontend domain (Step 4), add it to Auth0:

1. Go to [Auth0 Dashboard](https://manage.auth0.com/) → **Applications** → Your SPA Application → **Settings**

2. Add your Railway frontend URL to these fields (replace with your actual domain):

   **Allowed Callback URLs:**
   ```
   http://localhost:5173, https://frontend-production-XXXX.up.railway.app
   ```

   **Allowed Logout URLs:**
   ```
   http://localhost:5173, https://frontend-production-XXXX.up.railway.app
   ```

   **Allowed Web Origins:**
   ```
   http://localhost:5173, https://frontend-production-XXXX.up.railway.app
   ```

3. Click **Save Changes**

**Note:** Keep `http://localhost:5173` for local development. Separate multiple URLs with commas.

### Step 7: Configure Pre-Deploy Command (Migrations)

Set up automatic database migrations for the **api** service:

1. Click on the **api** service → **Settings** → **Deploy**
2. Find **Pre-Deploy Command** and set:
   ```
   uv run alembic upgrade head
   ```

This runs migrations automatically before each deployment.

### Step 8: Deploy

Push your changes to `main` branch. With **Wait for CI** enabled, Railway will:
1. Wait for GitHub Actions tests to pass
2. Then automatically deploy all services

**Note:** If you click **Deploy** in the dashboard before pushing, you'll see "Deployment waiting" until CI passes. Push to `main` to trigger the GitHub Actions workflow.

---

## Verify Deployment

1. **API:** Visit `https://<api-domain>/docs` - should show FastAPI docs
2. **Frontend:** Visit `https://<frontend-domain>` - should show login page
3. **MCP:** Visit `https://<mcp-domain>/mcp` - should respond to MCP requests

---

## Customizing Domain URLs

Railway generates random subdomains like `frontend-production-fb79.up.railway.app`. To customize:

### Change Railway Subdomain

1. Click on a service → **Settings** → **Networking**
2. Click the **edit icon** (pencil) next to the generated domain
3. Change the subdomain (e.g., `my-bookmarks` → `https://my-bookmarks.up.railway.app`)
4. Click **Save**

### Use a Custom Domain

See [docs/custom-domain-setup.md](docs/custom-domain-setup.md) for detailed instructions on configuring a custom domain with DNS and Auth0.

Quick summary:
1. Add custom domain in Railway (each service → **Settings** → **Networking** → **+ Custom Domain**)
2. Add CNAME records at your DNS provider
3. Update Railway environment variables (`CORS_ORIGINS`, `VITE_API_URL`, etc.)
4. Update Auth0 Allowed URLs
5. Redeploy all services

**Important:** After changing any domain, update:
- `CORS_ORIGINS` on the **api** service (must include `https://`)
- Auth0's Allowed Callback/Logout/Web Origins URLs
- **Redeploy the frontend** if you changed the API URL - Vite bakes `VITE_API_URL` at build time, so a rebuild is required for changes to take effect

---

## Deploying Changes

Push to `main` branch - Railway auto-deploys from connected GitHub repo.

For manual deploy:
```bash
railway up -s api      # Deploy API
railway up -s frontend # Deploy frontend
railway up -s mcp      # Deploy MCP
```

---

## Running Migrations

Migrations run automatically via the pre-deploy command configured in Step 6.

To run migrations manually (if needed):
1. Go to Railway dashboard → **api** service → **Settings** → **Deploy**
2. The pre-deploy command `uv run alembic upgrade head` runs before each deployment

---

## Viewing Logs

```bash
railway logs -s api
railway logs -s frontend
railway logs -s mcp
```

Or use Railway dashboard → Click service → **Logs** tab

---

## Troubleshooting

### Build fails

Check build logs in Railway dashboard. Common issues:
- Missing dependencies in `pyproject.toml`
- Wrong root directory for frontend

### Database connection fails / ModuleNotFoundError: psycopg2

1. Verify `DATABASE_URL` uses `postgresql+asyncpg://` prefix (NOT `postgresql://`)
2. Do NOT use `${{Postgres.DATABASE_URL}}` - you must manually copy and modify the URL
3. See Step 5 above for detailed instructions

### CORS errors

Verify `CORS_ORIGINS` on API service includes your frontend domain with `https://`

### Frontend shows blank page

Check browser console. Verify `VITE_API_URL` points to your API's Railway domain.
