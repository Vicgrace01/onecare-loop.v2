# Publishing OneCare Loop v2 to GitHub (Windows PowerShell)

The release ZIP contains the complete combined FastAPI project: foundation, care engine, responsive web interface, Alembic migrations, tests, deployment files and documentation. It is not an overlay patch. Extract it into a new folder and keep your current working directory untouched until the release has been tested.

## 1. Extract the release into a clean folder

```powershell
$Project = Join-Path $HOME "Projects\onecare-loop-v2-final"
New-Item -ItemType Directory -Force -Path $Project | Out-Null
Expand-Archive -LiteralPath (Join-Path $HOME "Downloads\onecare-loop-v2-final.zip") -DestinationPath $Project -Force
Set-Location $Project
```

Confirm the expected files exist:

```powershell
Test-Path .\app\main.py
Test-Path .\app\web\index.html
Test-Path .\migrations\env.py
Test-Path .\tests\test_care_workflows.py
Test-Path .\docs\competition-demo-guide.md
```

Every command should return `True`.

## 2. Install and validate locally

```powershell
py -3.12 -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
python -m playwright install chromium
Copy-Item .env.example .env
notepad .env
```

In `.env`, generate three different secrets:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Use separate values for `SECRET_KEY`, `SIGNING_MASTER_KEY` and `PII_ENCRYPTION_KEY`. Keep `.env` private. Do not use real patient information or production keys in a competition demo.

Apply migrations and create the first administrator:

```powershell
alembic upgrade head
python -m app.cli create-admin
```

Run the release checks:

```powershell
python -m compileall -q app tests migrations
node --check .\app\web\assets\js\app.js
node --check .\app\web\assets\js\heritage-motion.js
python -m pytest -q
```

Start the application:

```powershell
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`. API documentation is at `http://127.0.0.1:8000/docs` in development mode.

## 3. Publish safely to a new branch in the existing repository

This keeps the existing `main` branch intact. It does not delete the GitHub repository or rewrite its history.

```powershell
$Project = Join-Path $HOME "Projects\onecare-loop-v2-final"
$Publish = Join-Path $HOME "Projects\onecare-loop-publish"
git clone https://github.com/Vicgrace01/onecare-loop.git $Publish
Set-Location $Publish
git switch -c rewrite/fastapi-v2
```

Replace the cloned working-tree files with the tested FastAPI release. The `.git` directory is excluded so the clone's Git history and remote remain intact.

```powershell
git rm -r .
robocopy $Project $Publish /E /XD .git .venv venv __pycache__ .pytest_cache .ruff_cache /XF .env onecare.db *.db *.sqlite *.sqlite3 *.pyc
if ($LASTEXITCODE -gt 7) { throw "Robocopy failed with exit code $LASTEXITCODE" }
```

Review the staged project before committing:

```powershell
git status --short
git add -A
git diff --cached --check
git diff --cached --stat
```

Confirm `.env`, database files, virtual environments, caches and private credentials are not staged. Then publish the branch:

```powershell
git commit -m "Replace Flask prototype with improved OneCare Loop FastAPI v2"
git push -u origin rewrite/fastapi-v2
```

Open a pull request from `rewrite/fastapi-v2` into `main`:

`https://github.com/Vicgrace01/onecare-loop/compare/main...rewrite/fastapi-v2`

Review the changed-file list and GitHub Actions checks before merging. Keep `main` available for rollback until you have inspected the replacement.

## 4. Alternative: publish as a separate repository

This is the cleanest way to preserve the original Flask project unchanged. Create a new empty repository in GitHub (no README, licence or `.gitignore` pre-created), then run from the extracted `$Project` directory:

```powershell
Set-Location $Project
git init -b main
git add -A
git diff --cached --check
git commit -m "Initial OneCare Loop v2 release"
git remote add origin https://github.com/Vicgrace01/onecare-loop-v2.git
git push -u origin main
```

Choose public or private visibility deliberately. A private repository is safer while the prototype is still under security, clinical and privacy review.

## 5. What CI checks

GitHub Actions runs the Python suite on Python 3.11 and 3.12, compiles the source, runs the Chromium browser test, exercises the Alembic upgrade/downgrade/re-upgrade path and builds the Docker image. A green CI result is engineering evidence, not clinical, security, privacy or regulatory approval.

## 6. Important boundaries

- Never commit `.env`, real patient records, database files, production passwords or encryption/signing keys.
- The Compose profile is a deployment smoke-test configuration, not a managed production service.
- Use managed PostgreSQL, TLS, backups, a secrets manager/KMS, controlled migrations, rate limits and monitoring before a real pilot.
- Live NHIA/DHIN, SMS/WhatsApp, claims settlement and emergency dispatch integrations are not connected.
- Keep the old `main` branch and inspect the pull request before merging. Never force-push over `main` for this replacement.
