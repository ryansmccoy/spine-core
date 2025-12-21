# spine-core Docker Infrastructure

Tiered Docker setup for spine-core. Three profiles give you progressively
more infrastructure — from a zero-dependency SQLite setup to the full
production stack with Celery, TimescaleDB, and monitoring.

## Quick Start

```bash
# Tier 1 — API + Frontend (SQLite, zero dependencies)
docker compose -f docker/compose.yml up -d

# Tier 2 — + PostgreSQL + Worker + Docs
docker compose -f docker/compose.yml --profile standard up -d

# Tier 3 — + TimescaleDB + Redis + Celery + Prometheus + Grafana
docker compose -f docker/compose.yml --profile full up -d

# Or from project root (uses docker-compose.yml include redirect):
docker compose up -d
```

If you have `make` installed:

```bash
make up            # Tier 1
make up-standard   # Tier 2 (also sets SPINE_DATABASE_URL for API → Postgres)
make up-full       # Tier 3 (also sets DB/Redis/Celery URLs for API)
make down          # Stop everything
make logs          # Tail logs
make ps            # Show running containers
```

## Tier Architecture

### Tier 1: Minimal (default)

| Service   | Container            | Port  | URL                                  |
|-----------|----------------------|-------|--------------------------------------|
| API       | spine-core-api       | 12000 | http://localhost:12000               |
| Frontend  | spine-core-frontend  | 12001 | http://localhost:12001               |

- **Database**: SQLite (embedded, zero config)
- **Worker**: None (runs inline)
- **Swagger**: http://localhost:12000/api/v1/docs
- **Health**: http://localhost:12000/health

### Tier 2: Standard (`--profile standard`)

| Service   | Container            | Port  | URL / Address                        |
|-----------|----------------------|-------|--------------------------------------|
| API       | spine-core-api       | 12000 | http://localhost:12000               |
| Frontend  | spine-core-frontend  | 12001 | http://localhost:12001               |
| PostgreSQL| spine-core-postgres  | 10432 | localhost:10432                      |
| Worker    | spine-core-worker    | —     | Background poll-based worker         |
| Docs      | spine-core-docs      | 12002 | http://localhost:12002               |

- **Database**: PostgreSQL 16 (persistent volume)
- **Worker**: WorkerLoop (polling, thread pool)
- **Docs**: MkDocs Material static site

### Tier 3: Full (`--profile full`)

| Service     | Container               | Port  | URL / Address                      |
|-------------|-------------------------|-------|------------------------------------|
| API         | spine-core-api          | 12000 | http://localhost:12000             |
| Frontend    | spine-core-frontend     | 12001 | http://localhost:12001             |
| TimescaleDB | spine-core-timescaledb  | 10432 | localhost:10432                    |
| Redis       | spine-core-redis        | 10379 | localhost:10379                    |
| Celery Worker| spine-core-celery-worker| —    | Celery task executor (4 workers)   |
| Celery Beat | spine-core-celery-beat  | —     | Scheduled task runner              |
| Docs        | spine-core-docs         | 12002 | http://localhost:12002             |
| Prometheus  | spine-core-prometheus   | 12500 | http://localhost:12500             |
| Grafana     | spine-core-grafana      | 12501 | http://localhost:12501             |

- **Database**: TimescaleDB (PostgreSQL 16 + time-series extensions)
- **Cache/Broker**: Redis 7
- **Worker**: Celery with Redis broker
- **Monitoring**: Prometheus scraping + Grafana dashboards

## Port Allocation

spine-core reserves ports **12000–12099** in the Spine ecosystem
(infrastructure uses the **10xxx** block):

| Port  | Service               |
|-------|-----------------------|
| 12000 | API (FastAPI)         |
| 12001 | Frontend (React)      |
| 12002 | Documentation (MkDocs)|
| 12004 | Docs Dev (hot-reload) |
| 10432 | PostgreSQL/TimescaleDB|
| 10379 | Redis                 |
| 12500 | Prometheus            |
| 12501 | Grafana               |

## Environment Configuration

### Env File Layering

```
.env.base           ← Shared defaults (ports, paths, flags)
.env.minimal        ← Tier 1 overrides (SQLite, no cache)
.env.standard       ← Tier 2 overrides (Postgres, APScheduler)
.env.full           ← Tier 3 overrides (TimescaleDB, Redis, Celery)
docker/.env.standard ← Docker-internal hostname overrides for Tier 2
docker/.env.full     ← Docker-internal hostname overrides for Tier 3
```

Inside Docker, services communicate via container names (e.g.,
`postgres:5432`), not `localhost:10432`. The `docker/.env.*` files
provide these Docker-internal overrides.

### Key Environment Variables

| Variable                  | Default                        | Description                  |
|---------------------------|--------------------------------|------------------------------|
| `SPINE_DATABASE_URL`      | `sqlite:////app/data/spine.db` | Database connection URL      |
| `SPINE_API_PORT`          | `12000`                        | API external port            |
| `SPINE_FRONTEND_PORT`     | `12001`                        | Frontend external port       |
| `SPINE_REDIS_URL`         | `redis://redis:6379/0`         | Redis connection (Tier 3)    |
| `SPINE_CELERY_BROKER_URL` | `redis://redis:6379/1`         | Celery broker (Tier 3)       |
| `POSTGRES_USER`           | `spine`                        | PostgreSQL username          |
| `POSTGRES_PASSWORD`       | `spine`                        | PostgreSQL password          |

## Commands

### Database

```bash
# Connect to PostgreSQL (Tier 2)
docker exec -it spine-core-postgres psql -U spine -d spine

# Connect to TimescaleDB (Tier 3)
docker exec -it spine-core-timescaledb psql -U spine -d spine

# Reset database
docker compose -f docker/compose.yml --profile standard down -v
docker compose -f docker/compose.yml --profile standard up -d
```

### Health Checks

```bash
# API health
curl http://localhost:12000/health
curl http://localhost:12000/health/live
curl http://localhost:12000/health/ready
```

### Development (Hot Reload)

```bash
# MkDocs with live reload
docker compose -f docker/compose.yml --profile dev up docs-dev
# → http://localhost:12004
```

### Rebuild

```bash
# Rebuild all images (no cache)
make rebuild

# Or manually:
docker compose -f docker/compose.yml --profile standard --profile full build --no-cache
```

## File Layout

```
docker/
├── compose.yml          # Unified compose with profiles
├── Dockerfile           # API backend (Python + uvicorn)
├── Dockerfile.docs      # MkDocs → nginx static site
├── Dockerfile.frontend  # React Vite → nginx SPA
├── Dockerfile.health    # Minimal health demo
├── nginx.conf           # Reverse proxy config (gateway)
├── nginx-frontend.conf  # Frontend SPA + API proxy
├── prometheus.yml       # Prometheus scrape targets
├── .env.standard        # Docker-internal URLs for Tier 2
├── .env.full            # Docker-internal URLs for Tier 3
└── README.md            # This file
```
