# Run it and put it live (beginner guide)

The app has three parts:

| Part | What it is | Where it runs live |
|---|---|---|
| **web** | the website you click in (Next.js) | Vercel, free |
| **api + worker** | the server and the background job runner (FastAPI) | Render, free |
| **database** | where everything is saved (MongoDB) | MongoDB Atlas, free (you already have it) |

Total cost: $0. The only catch of the free plan is that Render puts the server to sleep after 15 minutes
without visitors, so the first page after a quiet period takes about a minute to load. Paying Render $7 a
month (plan "Starter") removes that.

---

## Step 0: Make the database password safe (do this first)

The Atlas password was saved in the repository, so treat it as public.

1. Open <https://cloud.mongodb.com> → your project → **Database Access**.
2. Next to user `hamidi` click **Edit** → **Edit Password** → **Autogenerate** → copy it → **Update User**.
3. Put the new password into your own `.env` file (lines `MONGODB_URI` and `COMPOSE_MONGODB_URI`).
   Do not commit `.env` with the new password.

Your connection string from now on looks like this (replace `NEW_PASSWORD`):

```
mongodb+srv://hamidi:NEW_PASSWORD@cluster0.rxxertq.mongodb.net/AI
```

## Step 1: Run it on your own computer

1. Install **Docker Desktop**: <https://www.docker.com/products/docker-desktop/> and start it.
2. Install **Git**: <https://git-scm.com/downloads>.
3. Download the project and start it:

   ```bash
   git clone https://github.com/AbdullKarimHamidi/AI-Orchestrator.git
   cd AI-Orchestrator
   ```

   Open `.env` and check the two Mongo lines contain your new password. Then:

   - Windows (PowerShell): `./scripts/dev.ps1`
   - macOS / Linux: `./scripts/dev.sh`

   The first start takes a few minutes (it builds everything).
4. In **Atlas → Network Access → Add IP Address → Add Current IP Address** (otherwise the app cannot reach
   the database).
5. Open <http://localhost:3000>, click **Register**, create your account.
6. Get a free AI key, for example Groq: <https://console.groq.com/keys> → **Create API Key** → copy.
   In the app go to **Models → Free AI providers**, paste it, click **Connect**.
7. Go to **Agents → Install starter agents**, open one (e.g. *General Assistant*) and use the **Test console**.

Stop everything with `./scripts/dev.ps1 -Down` (Windows) or `./scripts/dev.sh --down`.

## Step 2: Put it live

You need three free accounts: GitHub (you have it), **Render** (<https://render.com>, sign in with GitHub)
and **Vercel** (<https://vercel.com>, sign in with GitHub).

### 2a. Prepare two values

- **Encryption key**: run `./scripts/new-key.ps1` (Windows) or `./scripts/new-key.sh` and copy the line it
  prints. Save it somewhere safe (a password manager): saved AI keys cannot be read without it.
- **Web address**: choose a name for the website, e.g. `ai-orchestrator-hamidi`. Your site will be
  `https://ai-orchestrator-hamidi.vercel.app`. (If Vercel gives you a different address later, just update
  it in Render.)

### 2b. Let Render reach the database

Atlas → **Network Access** → **Add IP Address** → **Allow access from anywhere** (`0.0.0.0/0`) → Confirm.
Render's free plan has no fixed address, so this is needed. Your strong password still protects the database.

### 2c. Start the server on Render

1. Render dashboard → **New +** → **Blueprint** → choose the `AI-Orchestrator` repository → **Connect**.
   (If the repository is not listed, click *Configure account* and give Render access to it.)
2. Render reads `render.yaml` and asks for these values:

   | Name | What to paste |
   |---|---|
   | `MONGODB_URI` | your connection string with the new password |
   | `ENCRYPTION_KEYS` | the key from 2a |
   | `PUBLIC_URL` | your web address from 2a, e.g. `https://ai-orchestrator-hamidi.vercel.app` |
   | `CORS_ORIGINS` | the same web address |
   | `GROQ_API_KEY`, `GEMINI_API_KEY` | optional free AI keys (can be left empty) |

3. Click **Apply**. Wait until the service shows **Live** (5 to 10 minutes the first time).
4. Copy its address at the top of the page, e.g. `https://ai-orchestrator-api.onrender.com`.
   Check it works: open `https://ai-orchestrator-api.onrender.com/api/v1/health/ready`. You should see
   `"mongodb": "ok"`. If it says `unreachable`, recheck 2b and the password in `MONGODB_URI`.

### 2d. Start the website on Vercel

1. Vercel dashboard → **Add New… → Project** → **Import** the `AI-Orchestrator` repository.
2. **Project Name**: the name from 2a.
3. **Root Directory**: click *Edit* and choose `apps/web`. Framework is detected as **Next.js**.
4. **Environment Variables**: add `API_INTERNAL_URL` = the Render address from 2c (no slash at the end).
5. Click **Deploy**. When it finishes, open your `https://….vercel.app` address.
6. **Register** your account, then connect a free AI provider and install the starter agents as in Step 1.

### 2e. Close the door behind you

When your account exists, stop strangers from signing up: Render → your service → **Environment** → add
`ALLOW_REGISTRATION` = `false` → **Save changes**. Teammates join with invitation links
(**Security → Users → Invite a teammate**).

## Updating

Push to the `main` branch on GitHub. Render and Vercel both redeploy automatically.

## If something goes wrong

| Problem | Fix |
|---|---|
| Render log says `ServerSelectionTimeoutError` or `bad auth` | Atlas Network Access is missing `0.0.0.0/0`, or the password in `MONGODB_URI` is wrong. |
| Render log says `PUBLIC_URL must be an https:// URL` | `PUBLIC_URL` must start with `https://`. |
| Website loads but login says "network error" or 404 | `API_INTERNAL_URL` in Vercel is wrong or missing. Fix it, then Vercel → Deployments → **Redeploy** (the value is read when the site is built). |
| First page takes a minute | Normal on Render's free plan (the server was asleep). |
| Agent answers `[DEMO]` | No real AI provider connected yet: **Models → Free AI providers**. |

## Other ways to host

- **Always on, one small server (about $5 a month)**: rent a Linux VPS (Hetzner, DigitalOcean…), then follow
  [`deployment.md`](deployment.md). Without a domain name you can use a free one like `1-2-3-4.sslip.io`
  (your server's IP with dashes) as `DOMAIN`.
- **Render without sleeping**: in `render.yaml` change `plan: free` to `plan: starter`.
