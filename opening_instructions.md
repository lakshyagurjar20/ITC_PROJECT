# CyberSentinel quick start

The project setup, scenarios, verification, restart, and GitHub upload instructions are in README.md.

For a first Docker run, from this folder:

1. Create .env from .env.example if needed and set a fresh HMAC_SECRET_KEY and private GRAFANA_ADMIN_PASSWORD.
2. Run docker compose config --quiet.
3. Run docker compose up --build -d.
4. Check docker compose ps; open http://localhost:5000 and the Grafana dashboard at http://localhost:3000/d/cybersentinel.

To reopen later, start Docker Desktop and run docker compose up -d from this folder. Use docker compose down to stop while preserving data.