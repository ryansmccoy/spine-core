# Market Spine Workflows

**Operational playbooks and runbooks for Market Spine.**

---

## Quick Reference

| Workflow | Type | When to Use |
|----------|------|-------------|
| [Weekly Data Update](operational/WEEKLY_DATA_UPDATE.md) | Operational | Every Friday after FINRA publishes |
| [Backfill Historical Data](operational/BACKFILL_HISTORICAL.md) | Operational | Load past weeks |
| [Handle Data Revision](operational/HANDLE_REVISION.md) | Operational | FINRA updates old week |
| [Add New Data Source](development/ADD_DATASOURCE.md) | Development | New vendor/API connector |
| [Add New Calculation](development/ADD_CALCULATION.md) | Development | New metric/aggregation |
| [Debug Missing Data](incident/DEBUG_MISSING_DATA.md) | Incident | Expected data not present |
| [Resolve Quality Gate Failure](incident/RESOLVE_QUALITY_GATE.md) | Incident | Pipeline skipped due to validation |
| [Database Recovery](incident/DATABASE_RECOVERY.md) | Incident | DB corruption/migration issues |

---

## Workflow Types

### Operational Workflows
Daily/weekly operations, scheduled tasks, routine maintenance.

**Location:** `operational/`

- Standard data updates
- Scheduled ingestion
- Monitoring checks
- Routine backfills

### Development Workflows  
Feature implementation, code changes, testing.

**Location:** `development/`

- Adding datasources
- Adding calculations
- Schema changes
- Quality gate implementation

### Incident Response
Debugging, error resolution, recovery procedures.

**Location:** `incident/`

- Missing data investigation
- Anomaly resolution
- Restatement procedures
- Database recovery

---

## Workflow Structure

Each workflow document contains:

```markdown
# Workflow Name

## Trigger
When/why to run this workflow

## Prerequisites
- Required tools
- Required access
- Required knowledge

## Steps
1. Step-by-step instructions
2. With commands to run
3. And expected outcomes

## Success Criteria
How to verify it worked

## Rollback
How to undo if it fails

## References
- Related scripts
- Related prompts
- Related docs
```

---

## Integration with Other Docs

| This Workflow | Uses This Script | Uses This Prompt | Uses This Doc |
|---------------|-----------------|------------------|---------------|
| Weekly Data Update | `run_finra_weekly_schedule.py` | - | CLI.md |
| Add Datasource | - | `llm-prompts/prompts/A_DATASOURCE.md` | CONTEXT.md |
| Handle Revision | `run_finra_weekly_schedule.py` | - | FINRA_REVISION_HANDLING.md |

---

## Quick Start

### For Operators

1. **Weekly routine**: [Weekly Data Update](operational/WEEKLY_DATA_UPDATE.md)
2. **Something broke**: Check [incident/](incident/) workflows
3. **Need to backfill**: [Backfill Historical Data](operational/BACKFILL_HISTORICAL.md)

### For Developers

1. **New feature**: Check [development/](development/) workflows
2. **Reference implementation patterns**: See `llm-prompts/`
3. **Understand architecture**: See `docs/architecture/`

---

## Creating New Workflows

Use the template: [WORKFLOW_TEMPLATE.md](WORKFLOW_TEMPLATE.md)

```bash
cp workflows/WORKFLOW_TEMPLATE.md workflows/operational/MY_NEW_WORKFLOW.md
# Edit and commit
```
