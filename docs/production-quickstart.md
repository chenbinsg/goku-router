# Production Quickstart

This path is for a single-host Docker deployment behind an existing HTTPS
reverse proxy such as Goku-AIOS nginx. It generates local secrets and keeps
Router ports bound to `127.0.0.1` by default.

## 1. Generate Environment

```bash
python3 scripts/prepare_prod_env.py \
  --allowed-origin https://aipass.example.com \
  --public-admin-url https://aipass.example.com/router/
```

The script creates:

- `.env`
- `backend/.env`
- `ROUTER_CREDENTIALS.txt`

It does not print generated secrets. Store `ROUTER_CREDENTIALS.txt` in a
password manager and keep all three files out of git.

## 2. Start Router

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
curl -fsS http://127.0.0.1:8159/health
```

By default the admin UI listens on `127.0.0.1:5159` and the backend listens on
`127.0.0.1:8159`. Do not expose these ports directly to the Internet.

## 3. Reverse Proxy

When the reverse proxy runs on the host OS, use the loopback ports:

```nginx
location /router-api/ {
    proxy_pass http://127.0.0.1:8159/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 600s;
}

location /router/ {
    proxy_pass http://127.0.0.1:5159/;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

When Router is hosted behind containerized AIOS nginx, both compose files join
the shared `goku_edge` Docker network. Use the container aliases instead:

```nginx
location /router-api/ {
    proxy_pass http://goku-router-backend:8000/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 600s;
}

location /router/ {
    proxy_pass http://goku-router-frontend:80/;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

For AIOS LLM routing, use the generated Router API key:

```dotenv
OPENAI_BASE_URL=http://127.0.0.1:8159/v1
OPENAI_API_KEY=<generated router api key>
GOKU_ROUTER_URL=http://127.0.0.1:8159
GOKU_ROUTER_API_KEY=<generated router api key>
```

## 4. Rotate Credentials

To rotate local generated values:

```bash
python3 scripts/prepare_prod_env.py \
  --allowed-origin https://aipass.example.com \
  --public-admin-url https://aipass.example.com/router/ \
  --force
docker compose -f docker-compose.prod.yml up -d --build
```

The script creates timestamped backups before overwriting existing files.
