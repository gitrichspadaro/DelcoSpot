# DelcoSpot API

Minimal starting point for the DelcoSpot backend. Right now this is
intentionally small — a health check and a root route — just enough to
prove the deployment pipeline (GitHub → Render) works end to end. Real
routes, database models, and auth get layered on top of this as the
Implementation Checklist items get built out.

## Run it locally

```bash
python3 -m venv venv
source venv/bin/activate        # on Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Then visit http://localhost:5000 and http://localhost:5000/healthz.

## Push this to GitHub

```bash
git init
git add .
git commit -m "Initial DelcoSpot API scaffold"
```

Create a new, empty repository on GitHub (don't let GitHub add its own
README or .gitignore — this project already has them), then:

```bash
git remote add origin https://github.com/<your-username>/<your-repo>.git
git branch -M main
git push -u origin main
```

## Connect it to Render

1. In the Render dashboard, click **New +** → **Web Service**.
2. Click **Connect a repository** and select this repo.
3. Render will detect `render.yaml` and pre-fill the build command
   (`pip install -r requirements.txt`), start command (`gunicorn app:app`),
   and health check path (`/healthz`) automatically.
4. Click **Create Web Service**. Once it deploys, your health check should
   be live at `https://<your-service-name>.onrender.com/healthz`.

From here, the Settings tab (Custom Domains, Environment, etc.) will be
fully available, since the service now has real code behind it.

## What's next

See the "Backend & data" section of the Implementation Checklist for the
next steps: a real database (PostgreSQL), the data models, and the first
real API routes.
