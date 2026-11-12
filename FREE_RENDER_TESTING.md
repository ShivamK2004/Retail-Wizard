# Render Free — Retail Wizard test deployment

**This is a disposable demonstration environment, not a production store.**

1. Use the `render.yaml` included in this project. It sets `plan: free` and does not define a persistent disk.
2. Push this folder to a private GitHub repository.
3. In Render choose **New → Blueprint**, connect that repository and deploy.
4. Before confirming, make sure Render shows the web service plan as **Free** and no persistent disk.
5. Retrieve `INITIAL_ADMIN_SETUP_KEY` from the service's Environment settings and use it to create the first administrator. Keep this key configured and private for the duration of testing.
6. Use test records only. The UI shows a warning banner because data loss is expected on this plan.

## Data loss warning

Render Free web services sleep after 15 minutes without inbound requests. Local filesystem changes, including the SQLite database, can be lost when the service sleeps, restarts or redeploys. Render can also restart a Free service at any time. This project intentionally stores its test SQLite database on that temporary filesystem. Products, accounts, sales, refunds, expenses and settings may need to be recreated. See https://render.com/docs/free.

Never use the Free SQLite test deployment for actual customer records, actual sales or as the only copy of store data.
