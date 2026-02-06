# Market Spine Full - Design Document (Part 2: Kubernetes & CI)

---

## 8. Helm Chart

### 8.1 Chart.yaml

```yaml
apiVersion: v2
name: market-spine
description: Analytics pipeline system for market computations
type: application
version: 0.1.0
appVersion: "0.1.0"

dependencies:
  - name: postgresql
    version: "14.x.x"
    repository: https://charts.bitnami.com/bitnami
    condition: postgresql.enabled
  - name: redis
    version: "18.x.x"
    repository: https://charts.bitnami.com/bitnami
    condition: redis.enabled
  - name: rabbitmq
    version: "12.x.x"
    repository: https://charts.bitnami.com/bitnami
    condition: rabbitmq.enabled
```

### 8.2 values.yaml

```yaml
# Global settings
global:
  imageRegistry: ghcr.io
  imagePullSecrets: []

# API settings
api:
  replicaCount: 2
  image:
    repository: org/market-spine
    tag: latest
    pullPolicy: IfNotPresent
  resources:
    requests:
      cpu: 250m
      memory: 512Mi
    limits:
      cpu: 1000m
      memory: 1Gi
  autoscaling:
    enabled: true
    minReplicas: 2
    maxReplicas: 10
    targetCPUUtilization: 70

# Worker settings
worker:
  replicaCount: 3
  resources:
    requests:
      cpu: 500m
      memory: 1Gi
    limits:
      cpu: 2000m
      memory: 4Gi
  autoscaling:
    enabled: true
    minReplicas: 2
    maxReplicas: 20
    targetCPUUtilization: 70

# Beat scheduler
beat:
  enabled: true
  resources:
    requests:
      cpu: 100m
      memory: 256Mi

# Backend configuration
backend:
  type: local  # local | celery
  local:
    pollInterval: 0.5
    maxConcurrent: 4
  celery:
    queues:
      - pipelines.normal
      - pipelines.backfill

# Database
database:
  host: ""  # Set if using external DB
  port: 5432
  name: market_spine
  existingSecret: ""  # Secret with 'password' key

# Redis
redis:
  host: ""
  port: 6379

# Ingress
ingress:
  enabled: true
  className: nginx
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
  hosts:
    - host: spine.example.com
      paths:
        - path: /
          pathType: Prefix
  tls:
    - secretName: spine-tls
      hosts:
        - spine.example.com

# Migrations
migrations:
  enabled: true
  backoffLimit: 3

# Cleanup job
cleanup:
  enabled: true
  schedule: "0 2 * * *"  # 2 AM daily
  executionRetentionDays: 30
  eventRetentionDays: 30
  rawDataRetentionDays: 180

# Observability
observability:
  metrics:
    enabled: true
    serviceMonitor:
      enabled: true
      interval: 30s
  logging:
    format: json
    level: INFO

# Pod disruption budget
pdb:
  enabled: true
  minAvailable: 1

# Dependencies (Bitnami charts)
postgresql:
  enabled: true
  auth:
    database: market_spine
    existingSecret: spine-db-secret
  primary:
    persistence:
      size: 50Gi

redis:
  enabled: true
  auth:
    enabled: false
  master:
    persistence:
      size: 1Gi

rabbitmq:
  enabled: false  # Only for Celery backend
  auth:
    existingPasswordSecret: spine-rabbitmq-secret
```

### 8.3 API Deployment Template

```yaml
# templates/api-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "market-spine.fullname" . }}-api
  labels:
    {{- include "market-spine.labels" . | nindent 4 }}
    app.kubernetes.io/component: api
spec:
  {{- if not .Values.api.autoscaling.enabled }}
  replicas: {{ .Values.api.replicaCount }}
  {{- end }}
  selector:
    matchLabels:
      {{- include "market-spine.selectorLabels" . | nindent 6 }}
      app.kubernetes.io/component: api
  template:
    metadata:
      labels:
        {{- include "market-spine.selectorLabels" . | nindent 8 }}
        app.kubernetes.io/component: api
    spec:
      containers:
        - name: api
          image: "{{ .Values.global.imageRegistry }}/{{ .Values.api.image.repository }}:{{ .Values.api.image.tag }}"
          imagePullPolicy: {{ .Values.api.image.pullPolicy }}
          ports:
            - name: http
              containerPort: 8000
          env:
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: {{ include "market-spine.fullname" . }}-secrets
                  key: database-url
            - name: BACKEND_TYPE
              value: {{ .Values.backend.type | quote }}
            - name: LOG_FORMAT
              value: {{ .Values.observability.logging.format | quote }}
          resources:
            {{- toYaml .Values.api.resources | nindent 12 }}
          livenessProbe:
            httpGet:
              path: /api/v1/health
              port: http
            initialDelaySeconds: 10
            periodSeconds: 30
          readinessProbe:
            httpGet:
              path: /api/v1/health/ready
              port: http
            initialDelaySeconds: 5
            periodSeconds: 10
```

### 8.4 Migration Job Template

```yaml
# templates/migration-job.yaml
{{- if .Values.migrations.enabled }}
apiVersion: batch/v1
kind: Job
metadata:
  name: {{ include "market-spine.fullname" . }}-migrations
  labels:
    {{- include "market-spine.labels" . | nindent 4 }}
  annotations:
    "helm.sh/hook": pre-install,pre-upgrade
    "helm.sh/hook-weight": "-5"
    "helm.sh/hook-delete-policy": before-hook-creation
spec:
  backoffLimit: {{ .Values.migrations.backoffLimit }}
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: migrations
          image: "{{ .Values.global.imageRegistry }}/{{ .Values.api.image.repository }}:{{ .Values.api.image.tag }}"
          command: ["spine", "db", "init"]
          env:
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: {{ include "market-spine.fullname" . }}-secrets
                  key: database-url
{{- end }}
```

### 8.5 Cleanup CronJob Template

```yaml
# templates/cleanup-cronjob.yaml
{{- if .Values.cleanup.enabled }}
apiVersion: batch/v1
kind: CronJob
metadata:
  name: {{ include "market-spine.fullname" . }}-cleanup
spec:
  schedule: {{ .Values.cleanup.schedule | quote }}
  concurrencyPolicy: Forbid
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: OnFailure
          containers:
            - name: cleanup
              image: "{{ .Values.global.imageRegistry }}/{{ .Values.api.image.repository }}:{{ .Values.api.image.tag }}"
              command: ["spine", "cleanup", "run"]
              env:
                - name: DATABASE_URL
                  valueFrom:
                    secretKeyRef:
                      name: {{ include "market-spine.fullname" . }}-secrets
                      key: database-url
                - name: EXECUTION_RETENTION_DAYS
                  value: {{ .Values.cleanup.executionRetentionDays | quote }}
{{- end }}
```

### 8.6 ServiceMonitor Template

```yaml
# templates/servicemonitor.yaml
{{- if and .Values.observability.metrics.enabled .Values.observability.metrics.serviceMonitor.enabled }}
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: {{ include "market-spine.fullname" . }}
  labels:
    {{- include "market-spine.labels" . | nindent 4 }}
spec:
  selector:
    matchLabels:
      {{- include "market-spine.selectorLabels" . | nindent 6 }}
      app.kubernetes.io/component: api
  endpoints:
    - port: http
      path: /api/v1/health/metrics
      interval: {{ .Values.observability.metrics.serviceMonitor.interval }}
{{- end }}
```

---

## 9. CI Guardrails

### 9.1 GitHub Actions CI

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install dependencies
        run: pip install ruff mypy
      - name: Ruff
        run: ruff check src/
      - name: Mypy
        run: mypy src/

  test-unit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install
        run: pip install -e ".[dev]"
      - name: Unit tests
        run: pytest tests/unit -v --cov=market_spine

  test-architecture:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install
        run: pip install -e ".[dev]"
      - name: Architecture tests
        run: pytest tests/architecture -v

  test-integration:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: spine
          POSTGRES_PASSWORD: test
          POSTGRES_DB: market_spine
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
      redis:
        image: redis:7
        ports:
          - 6379:6379
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install
        run: pip install -e ".[dev]"
      - name: Integration tests
        run: pytest tests/integration -v
        env:
          DATABASE_URL: postgresql://spine:test@localhost:5432/market_spine
          REDIS_URL: redis://localhost:6379/0
```

### 9.2 Architecture Tests

```python
# tests/architecture/test_no_forbidden_imports.py
import ast
import sys
from pathlib import Path

FORBIDDEN_IN_CORE = {'celery', 'prefect', 'dagster', 'airflow', 'temporalio'}
CORE_PATHS = ['dispatcher.py', 'runner.py', 'pipelines/', 'services/', 'repositories/']
ALLOWED_PATHS = ['orchestration/backends/']

def get_imports(filepath: Path) -> set[str]:
    """Extract all imports from a Python file."""
    tree = ast.parse(filepath.read_text())
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module.split('.')[0])
    return imports

def test_core_does_not_import_backends():
    """Core code must not import backend-specific libraries."""
    src = Path('src/market_spine')
    
    for core_path in CORE_PATHS:
        path = src / core_path
        if path.is_file():
            files = [path]
        else:
            files = path.rglob('*.py')
        
        for filepath in files:
            # Skip allowed paths
            rel_path = str(filepath.relative_to(src))
            if any(rel_path.startswith(allowed) for allowed in ALLOWED_PATHS):
                continue
            
            imports = get_imports(filepath)
            forbidden_found = imports & FORBIDDEN_IN_CORE
            
            assert not forbidden_found, (
                f"{filepath} imports forbidden modules: {forbidden_found}"
            )

# tests/architecture/test_invariants.py
def test_all_pipelines_registered():
    """All pipeline modules must register their pipelines."""
    from market_spine.registry import list_pipelines
    
    expected = {'otc_ingest', 'otc_normalize', 'otc_compute_daily_metrics', 
                'otc_backfill_range', 'otc_full_refresh'}
    actual = set(list_pipelines())
    
    assert expected <= actual, f"Missing pipelines: {expected - actual}"

def test_run_pipeline_is_only_entrypoint():
    """Only run_pipeline should execute pipeline logic."""
    # This is enforced by code review and architecture tests
    # The test validates the function signature
    from market_spine.runner import run_pipeline
    import inspect
    
    sig = inspect.signature(run_pipeline)
    params = list(sig.parameters.keys())
    
    assert params == ['execution_id'], (
        "run_pipeline must have single parameter: execution_id"
    )
```

---

## 10. Integration Test

```python
# tests/integration/test_e2e.py
import pytest
import httpx
import asyncio

@pytest.fixture
def api_url():
    return "http://localhost:8000/api/v1"

@pytest.mark.integration
async def test_full_pipeline_flow(api_url):
    """End-to-end test: submit → poll → verify metrics."""
    async with httpx.AsyncClient() as client:
        # Submit execution
        response = await client.post(f"{api_url}/executions", json={
            "pipeline": "otc_full_refresh",
            "params": {}
        })
        assert response.status_code == 202
        execution_id = response.json()["id"]
        
        # Poll until complete (max 60s)
        for _ in range(60):
            response = await client.get(f"{api_url}/executions/{execution_id}")
            status = response.json()["status"]
            
            if status == "completed":
                break
            elif status == "failed":
                pytest.fail(f"Execution failed: {response.json().get('error')}")
            
            await asyncio.sleep(1)
        else:
            pytest.fail("Execution did not complete in 60s")
        
        # Verify metrics exist
        response = await client.get(f"{api_url}/otc/metrics/daily", params={
            "symbol": "ACME"
        })
        assert response.status_code == 200
        metrics = response.json()
        assert len(metrics) > 0
        assert metrics[0]["symbol"] == "ACME"
        assert metrics[0]["vwap"] > 0
```

---

## 11. Key Differences from Advanced

| Aspect | Advanced | Full |
|--------|----------|------|
| Deployment | Docker Compose | Kubernetes + Helm |
| Backend | Local + Celery | Plugin system + stubs |
| Observability | Basic | Prometheus + structured logs |
| CI | None | GitHub Actions + guardrails |
| Cleanup | None | CronJob-based retention |
| Scaling | Manual | HPA + PDB |
| Tests | Unit + dispatcher | + Integration + architecture |
