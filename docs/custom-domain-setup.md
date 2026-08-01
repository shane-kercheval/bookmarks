# Custom Domain Setup Guide

This guide walks through configuring a custom domain (e.g., `tiddly.me`) for the Bookmarks application deployed on Railway.

> **IdP note (2026-07-31):** the identity-provider steps below were written in the Auth0 era and are retained as the historical record of how the domain was originally set up. Auth0 was decommissioned at M6b; the Clerk equivalents are README_DEPLOY Step 6b (the `clerk.tiddly.me` DNS records) and the Clerk `allowed_origins` operator steps in the migration plan. The Railway/DNS steps remain accurate.

## Overview

You'll configure:
- `tiddly.me` → Frontend (React app)
- `api.tiddly.me` → API (FastAPI backend)
- `content-mcp.tiddly.me` → Content MCP Server (bookmarks/notes, for AI agents)
- `prompts-mcp.tiddly.me` → Prompt MCP Server (prompts capability, for AI agents)

## Prerequisites

- Domain purchased (e.g., from Porkbun)
- Railway project deployed and working with Railway-generated domains
- Access to Auth0 dashboard

---

## Step 1: Add Custom Domains in Railway

### Frontend Service

1. Go to Railway dashboard → Click **frontend** service → **Settings** → **Networking**
2. Click **+ Custom Domain**
3. Enter: `tiddly.me`
4. For the port field, use the default (`8080`) - Railway routes this to your app's internal port
5. Click **Add Domain**
6. Note the CNAME target Railway shows (e.g., `bookmarks-app.up.railway.app`) - you'll need this for DNS setup

### API Service

1. Click **api** service → **Settings** → **Networking**
2. Click **+ Custom Domain**
3. Enter: `api.tiddly.me`
4. For the port field, use the default (`8080`)
5. Click **Add Domain**
6. Note the CNAME target Railway provides

### Content MCP Service (Optional)

1. Click **content-mcp** service → **Settings** → **Networking**
2. Click **+ Custom Domain**
3. Enter: `content-mcp.tiddly.me`
4. For the port field, use the default (`8080`)
5. Click **Add Domain**
6. Note the CNAME target Railway provides

### Prompt MCP Service (Optional)

1. Click **prompt-mcp** service → **Settings** → **Networking**
2. Click **+ Custom Domain**
3. Enter: `prompts-mcp.tiddly.me`
4. For the port field, use the default (`8080`)
5. Click **Add Domain**
6. Note the CNAME target Railway provides

---

## Step 2: Configure DNS at Porkbun

1. Log in to [Porkbun](https://porkbun.com) → **Domain Management**
2. Find your domain in the list and click **Details** (dropdown on the right)
3. In the expanded panel, click **DNS RECORDS** (upper right area)

### Delete Default Records First

Scroll down to **Current Records**. You'll likely see default records pointing to `pixie.porkbun.com`:

| TYPE | HOST | ANSWER |
|------|------|--------|
| ALIAS | yourdomain.me | pixie.porkbun.com |
| CNAME | *.yourdomain.me | pixie.porkbun.com |

Click the **trash icon** (🗑️) next to each record to delete them.

### Add Root Domain Record (for frontend)

For the root domain, you cannot use a regular CNAME record (DNS standards prohibit it). Use Porkbun's ALIAS record instead:

1. In the **Type** dropdown, select **ALIAS - CNAME flattening**
2. Leave **Host** blank (this means the root domain)
3. In **Answer / Value**, enter your Railway frontend target (e.g., `3idji3i.up.railway.app`)
4. Leave **TTL** at 600
5. Click **Add**

### Add API Subdomain Record

1. In the **Type** dropdown, select **CNAME**
2. In **Host**, enter: `api`
3. In **Answer / Value**, enter your Railway API target
4. Click **Add**

### Add Content MCP Subdomain Record (Optional)

1. In the **Type** dropdown, select **CNAME**
2. In **Host**, enter: `content-mcp`
3. In **Answer / Value**, enter your Railway Content MCP target
4. Click **Add**

### Add Prompt MCP Subdomain Record (Optional)

1. In the **Type** dropdown, select **CNAME**
2. In **Host**, enter: `prompts-mcp`
3. In **Answer / Value**, enter your Railway Prompt MCP target
4. Click **Add**

---

## Step 3: Verify DNS Propagation

Wait a few minutes, then verify:

```bash
# Check frontend (ALIAS records resolve to A records, not CNAME)
dig tiddly.me A

# Check API
dig api.tiddly.me CNAME

# Check Content MCP
dig content-mcp.tiddly.me CNAME

# Check Prompt MCP
dig prompts-mcp.tiddly.me CNAME
```

- For `tiddly.me`: You should see an IP address in the ANSWER section (ALIAS flattens to A record)
- For subdomains: You should see a CNAME pointing to `*.up.railway.app`

Railway will show a green checkmark when the domain is verified.

---

## Step 4: Update Railway Environment Variables

### API Service Variables

1. Go to **api** service → **Variables** tab
2. Update these variables:

```
CORS_ORIGINS=https://tiddly.me
VITE_API_URL=https://api.tiddly.me
VITE_FRONTEND_URL=https://tiddly.me
```

### Content MCP Service Variables

1. Go to **content-mcp** service → **Variables** tab
2. Update:

```
VITE_API_URL=https://api.tiddly.me
```

### Prompt MCP Service Variables

1. Go to **prompt-mcp** service → **Variables** tab
2. Update:

```
VITE_API_URL=https://api.tiddly.me
```

### Frontend Service Variables

1. Go to **frontend** service → **Variables** tab
2. Update:

```
VITE_API_URL=https://api.tiddly.me
VITE_MCP_URL=https://content-mcp.tiddly.me
VITE_PROMPT_MCP_URL=https://prompts-mcp.tiddly.me
```

**Important:** After changing `VITE_*` variables on the frontend, you must redeploy the frontend service. Vite bakes these values at build time.

---

## Step 5: Update Auth0 Configuration

1. Go to [Auth0 Dashboard](https://manage.auth0.com/) → **Applications** → Your SPA Application → **Settings**

2. Update **Allowed Callback URLs**:
   ```
   http://localhost:5173, https://tiddly.me
   ```

3. Update **Allowed Logout URLs**:
   ```
   http://localhost:5173, https://tiddly.me
   ```

4. Update **Allowed Web Origins**:
   ```
   http://localhost:5173, https://tiddly.me
   ```

5. Click **Save Changes**

**Note:** You can keep the old Railway URLs temporarily during transition, then remove them later:
```
http://localhost:5173, https://frontend-production-xxxx.up.railway.app, https://tiddly.me
```

---

## Step 6: Redeploy Services

After updating environment variables, redeploy all services to apply changes:

1. In Railway dashboard, click each service → **Deployments** → **Redeploy** (three dots menu on latest deployment)

Or trigger via git push to main branch.

---

## Step 7: Verify Everything Works

1. **Frontend:** Visit `https://tiddly.me` - should show login page
2. **Auth0 Login:** Click login, complete Auth0 flow, should redirect back to `https://tiddly.me`
3. **API:** Visit `https://api.tiddly.me/docs` - should show FastAPI docs
4. **Content MCP:** Visit `https://content-mcp.tiddly.me/mcp` - should respond (or show auth required)
5. **Prompt MCP:** Visit `https://prompts-mcp.tiddly.me/mcp` - should respond (or show auth required)

---

## Troubleshooting

### "Domain not verified" in Railway
- DNS propagation can take up to 48 hours (usually 5-30 minutes)
- Verify CNAME record is correct with `dig <domain> CNAME`
- Check for conflicting A records

### Certificate stuck on "validating challenges"
If certificate validation is stuck for more than 10-15 minutes:
1. Remove the domain in Railway (trash icon)
2. Wait 10 seconds
3. Re-add the domain
4. **Important:** Railway may assign a NEW target hostname - check the new value
5. Update your DNS record in Porkbun with the new target
6. Certificate should issue within a few minutes

### Auth0 login fails / redirect issues
- Verify all three Auth0 URL fields include `https://tiddly.me`
- Clear browser cookies and try again
- Check browser console for CORS or redirect errors

### CORS errors
- Ensure `CORS_ORIGINS` on API service includes `https://tiddly.me` (with https://)
- Redeploy API service after changing

### Frontend still hitting old API URL
- Vite bakes `VITE_*` at build time - redeploy frontend after changing variables
- Clear browser cache / hard refresh

---

## Removing Old Railway Domains (Optional)

After verifying custom domains work:

1. Go to each service → **Settings** → **Networking**
2. Click the trash icon next to the old `*.up.railway.app` domain
3. Update Auth0 to remove old URLs

**Recommendation:** Keep old domains for a week before removing, in case of issues.
