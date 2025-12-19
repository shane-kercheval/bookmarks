# Deployment Guide

Deploy the Bookmarks application to Railway using Railpack (Railway's auto-build system).

## Architecture

| Service | Description | Root Directory |
|---------|-------------|----------------|
| **api** | FastAPI backend | `/` |
| **mcp** | MCP server for AI agents | `/` |
| **frontend** | React SPA | `/frontend` |
| **Postgres** | PostgreSQL database | (managed by Railway) |

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
DATABASE_URL=${{Postgres.DATABASE_URL}}
CORS_ORIGINS=${{frontend.RAILWAY_PUBLIC_DOMAIN}}
VITE_AUTH0_DOMAIN=<your-auth0-domain>
VITE_AUTH0_CLIENT_ID=<your-auth0-client-id>
VITE_AUTH0_AUDIENCE=<your-auth0-api-identifier>
```

**Note:** The `${{Postgres.DATABASE_URL}}` syntax automatically references the Postgres service's DATABASE_URL. Railway will show an autocomplete dropdown.

**Important:** Your app uses `postgresql+asyncpg://` but Railway provides `postgresql://`. You may need to handle this in your app config or set DATABASE_URL manually by copying from Postgres and changing the prefix.

#### MCP Service Variables

```
VITE_API_URL=https://${{api.RAILWAY_PUBLIC_DOMAIN}}
MCP_HOST=0.0.0.0
MCP_PORT=${{PORT}}
```

#### Frontend Service Variables

```
VITE_API_URL=https://${{api.RAILWAY_PUBLIC_DOMAIN}}
VITE_AUTH0_DOMAIN=<your-auth0-domain>
VITE_AUTH0_CLIENT_ID=<your-auth0-client-id>
VITE_AUTH0_AUDIENCE=<your-auth0-api-identifier>
```

### Step 6: Deploy

Click **Deploy** in the top bar to deploy all services.

### Step 7: Run Database Migrations

After the API service deploys successfully:

```bash
railway link  # Select your project
railway run -s api -- alembic upgrade head
```

---

## Verify Deployment

1. **API:** Visit `https://<api-domain>/docs` - should show FastAPI docs
2. **Frontend:** Visit `https://<frontend-domain>` - should show login page
3. **MCP:** Visit `https://<mcp-domain>/mcp` - should respond to MCP requests

---

## Handling DATABASE_URL Prefix

Your app expects `postgresql+asyncpg://` but Railway provides `postgresql://`. Options:

**Option A: Update your app** to accept both formats (recommended)

**Option B: Set DATABASE_URL manually:**
1. Click Postgres service → Variables → Copy `DATABASE_URL`
2. Click API service → Variables
3. Add `DATABASE_URL` with the copied value, changing `postgresql://` to `postgresql+asyncpg://`

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

After deploying code with new migrations:

```bash
railway run -s api -- alembic upgrade head
```

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

### Database connection fails

1. Verify `DATABASE_URL` references Postgres correctly: `${{Postgres.DATABASE_URL}}`
2. Check if you need `postgresql+asyncpg://` prefix (see above)

### CORS errors

Verify `CORS_ORIGINS` on API service includes your frontend domain with `https://`

### Frontend shows blank page

Check browser console. Verify `VITE_API_URL` points to your API's Railway domain.

---

## GitHub Actions (Optional)

The `.github/workflows/deploy.yml` can automate deployments. Update it to use:

```yaml
- name: Deploy
  run: railway up -s ${{ matrix.service }}
  env:
    RAILWAY_TOKEN: ${{ secrets.RAILWAY_TOKEN }}
```

Required secrets:
- `RAILWAY_TOKEN`: From Railway dashboard → Account → Tokens

---

## Cost Estimate

Railway pricing is usage-based (~$5 credit free tier):

| Resource | Estimate |
|----------|----------|
| API | ~$5-8/month |
| MCP | ~$2-4/month |
| Frontend | ~$2-3/month |
| PostgreSQL | ~$5-7/month |
| **Total** | **~$15-22/month** |
