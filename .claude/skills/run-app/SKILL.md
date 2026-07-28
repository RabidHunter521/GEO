---
name: run-app
description: Starts the SeenBy SAAS local development environment — Next.js frontend on port 3000 and FastAPI backend on port 8000. Use this whenever the user says "run", "start", "localhost", "start the app", "spin up", "run-app", or wants to launch the local dev server.
---

# Run SeenBy SAAS Locally

Starts both dev servers for the SeenBy SAAS project. Always check ports first — skip starting any server that's already listening.

## Paths

- **Project root**: `c:\Users\IrfanFaris\OneDrive - NVD ASIA LIMITED\Desktop\SEENBY SAAS`
- **Poetry**: `C:\Users\IrfanFaris\AppData\Roaming\Python\Scripts\poetry.exe`
- **Frontend dir**: `<root>\frontend`
- **Backend dir**: `<root>\backend`

## Step 1 — Check what's already running

Run this PowerShell command:

```powershell
Get-NetTCPConnection -LocalPort 3000,8000 -ErrorAction SilentlyContinue | Select-Object LocalPort, State
```

- Port 3000 listening → frontend already up, skip it
- Port 8000 listening → backend already up, skip it

## Step 2 — Start frontend (if not running)

```powershell
Start-Process powershell -ArgumentList '-NoExit', '-Command', "cd 'c:\Users\IrfanFaris\OneDrive - NVD ASIA LIMITED\Desktop\SEENBY SAAS\frontend'; npm run dev"
```

## Step 3 — Start backend (if not running)

```powershell
$poetry = 'C:\Users\IrfanFaris\AppData\Roaming\Python\Scripts\poetry.exe'
Start-Process powershell -ArgumentList '-NoExit', '-Command', "cd 'c:\Users\IrfanFaris\OneDrive - NVD ASIA LIMITED\Desktop\SEENBY SAAS\backend'; & '$poetry' run uvicorn app.main:app --reload --port 8000"
```

## Step 4 — Verify

Wait 5 seconds, then confirm both ports are listening:

```powershell
Start-Sleep -Seconds 5
Get-NetTCPConnection -LocalPort 3000,8000 -ErrorAction SilentlyContinue | Select-Object LocalPort, State
```

## Step 5 — Report to user

Tell the user which servers were started (or already running) and their URLs:

- **Frontend**: http://localhost:3000
- **Backend**: http://localhost:8000
- **API docs**: http://localhost:8000/docs
