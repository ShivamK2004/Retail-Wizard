# Retail Wizard Web Edition 1.0 — Render Free Testing Deployment

## What this configuration is for

This Blueprint is intentionally configured for Render's **Free web service**. It has no attached persistent disk and uses the project's default SQLite database path (`data/retail_wizard.db`) on Render's ephemeral filesystem. This is only for a disposable preview/test environment. Do not use it for real retail transactions or real customer/payment data.

The app displays a warning banner on its pages whenever `RETAIL_WIZARD_DEMO_MODE=true`.

## Render Free limitations (check before deploying)

- Free web services spin down after 15 minutes without inbound traffic. Waking them can take about a minute.
- The filesystem is ephemeral. SQLite data, uploaded assets and generated files can be lost when the service spins down, restarts, or redeploys. Render may also restart free services at any time.
- Free web services cannot attach persistent disks.
- Render provides 750 free instance hours per workspace per calendar month. If the allowance is exhausted, free services are suspended until the next month. Bandwidth/build-pipeline quotas also apply.
- The app uses SQLite and one Uvicorn worker. Do not scale this service to multiple instances.

See Render's current official limits: https://render.com/docs/free

## Files and configuration

`render.yaml` contains a Python web service with `plan: free`, no `disk` section, Singapore region, and generated `SECRET_KEY` and `INITIAL_ADMIN_SETUP_KEY` values. The app uses the default project-local database under `data/`; do not set `RETAIL_WIZARD_DB` to a persistent-disk path for this Free-only setup.

## Deploy steps

1. Extract the ZIP. Open the inner `Retail_Wizard_Project` folder.
2. Check that `render.yaml` is at the repository root alongside `requirements-web.txt` and `webapp/`.
3. Create a **private** GitHub repository. Do not commit `.env` files, SQLite databases, database backups, invoice PDFs, real customer data, or secrets.
4. From PowerShell in the project root, upload the source:

   ```powershell
   git init
   git add .
   git commit -m "Retail Wizard free web test deployment"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/retail-wizard-web-free.git
   git push -u origin main
   ```

5. In Render, choose **New → Blueprint**, connect the private repository and select `main`.
6. Render should read `render.yaml`. Confirm the service plan says **Free** and that there is **no disk / persistent storage resource**. If Render shows a paid plan or disk, stop before confirming and re-check that the repository contains this free `render.yaml` at its root.
7. Apply/deploy the Blueprint. The service should build with `pip install -r requirements-web.txt` and start with Uvicorn.
8. After deployment, open the generated `onrender.com` URL. In Render → service → Environment, copy `INITIAL_ADMIN_SETUP_KEY`. Use it on the first-setup screen to create the admin.
9. **For this disposable Free test deployment, keep `INITIAL_ADMIN_SETUP_KEY` configured.** If the ephemeral SQLite database is erased, the app will need first-admin setup again. The setup page is still closed whenever a user already exists in the current database. Keep the setup key private.
10. Open `/health` on the service URL; it should return `{"status":"ok","service":"retail-wizard-web"}`. Test with fake products and fake transactions only.

## Temporary data: what to expect

The Free Blueprint does not attach a persistent disk. The default SQLite file is created inside the web service's project folder. Any products, user accounts, sales, refunds, expenses, settings and other database changes can disappear after an idle spin-down (15 minutes without inbound traffic), restart, redeploy or platform restart. Do not rely on this database as a backup. Keep any test scenarios you need outside Render so that you can recreate them.

The merchant QR image and other files committed into your repository are part of the deployed code, but files uploaded or generated at runtime are also temporary. PDF invoices are generated for download on request; do not assume server-side generated files remain stored.

## Moving from free test to real use

Before real sales, stop using the Free SQLite deployment. Migrate to a paid service with persistent storage or, preferably for a multi-user web app, to an appropriate managed PostgreSQL database with backups. Perform a controlled migration from a verified desktop database backup; never commit the database to GitHub. Validate user accounts, stock, sales, refunds and invoice history before switching the store to the online system.

## Local Windows test

Run `run_web_windows.bat`, then open `http://127.0.0.1:8000`. The launcher prints the one-time setup key for a new local test database.
