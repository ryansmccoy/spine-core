# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.4.x   | :white_check_mark: |
| < 0.4   | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability in spine-core, please report it responsibly.

### How to Report

1. **Do NOT open a public GitHub issue** for security vulnerabilities.
2. Email the maintainers directly with:
   - A description of the vulnerability
   - Steps to reproduce
   - Potential impact assessment
   - Suggested fix (if any)

### What to Expect

- **Acknowledgment**: Within 48 hours of your report.
- **Assessment**: We will evaluate severity and impact within 5 business days.
- **Fix timeline**: Critical vulnerabilities will be patched within 7 days. High-severity within 14 days.
- **Disclosure**: We will coordinate disclosure timing with you.

## Security Considerations

### Authentication & Authorization

- spine-core API does **not** include built-in authentication by default.
- Production deployments MUST add authentication middleware or use a reverse proxy (e.g., nginx, Traefik) with auth.
- Set `CORS_ORIGINS` to specific allowed origins — never use `*` in production.

### Database Security

- Connection strings containing credentials should use environment variables, never hardcoded values.
- SQLite databases should have restricted file permissions (`chmod 600`).
- PostgreSQL connections should use SSL in production (`?sslmode=require`).

### API Security

- Rate limiting is available but disabled by default. Enable via `RATE_LIMIT_ENABLED=true`.
- Input validation is handled by Pydantic models on all API endpoints.
- All SQL queries use parameterized statements — no raw string interpolation.

### LLM / GenAI Security

- Prompt injection defenses should be applied when processing user-supplied text.
- LLM API keys must be stored as environment variables or via the secrets backend.
- Cost tracking is available to prevent runaway API spend.

### Docker Security

- Run containers as non-root user.
- Use read-only filesystem where possible.
- Pin base image versions in Dockerfiles.
- Do not mount host secrets directories into containers.

## Dependencies

We monitor dependencies for known vulnerabilities using:
- `pip-audit` for Python package CVEs
- GitHub Dependabot alerts (when hosted on GitHub)
- Regular `uv lock --upgrade` cycles to pick up patches

## Best Practices for Deployers

1. Always run behind a reverse proxy with TLS termination
2. Enable rate limiting for public-facing deployments
3. Use PostgreSQL (not SQLite) for multi-user / production use
4. Restrict CORS origins to your specific frontend domains
5. Rotate API keys and database credentials regularly
6. Enable structured logging (`LOG_FORMAT=json`) for audit trails
7. Monitor the `/health/ready` endpoint for service health
