# config-spine

**Unified configuration management for the Spine Ecosystem**

Config-spine provides a unified approach to configuration across all Spine projects.

## Features

- Environment-based configuration (dev, staging, production)
- Hierarchical config merging
- Type validation
- Secrets management integration

## Usage

```python
from config_spine import Config, Environment

config = Config(
    environment=Environment.DEVELOPMENT,
    config_path="./config"
)

# Access configuration values
db_url = config.get("database.url")
api_key = config.secrets.get("api_key")
```

## Configuration Files

```
config/
├── base.yaml       # Base configuration
├── dev.yaml        # Development overrides
├── staging.yaml    # Staging overrides
└── production.yaml # Production overrides
```

## Environment Variables

Config-spine supports environment variable interpolation:

```yaml
database:
  url: ${DATABASE_URL:sqlite:///default.db}
```
