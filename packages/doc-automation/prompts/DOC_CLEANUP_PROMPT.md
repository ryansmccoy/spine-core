# Documentation Cleanup & Organization Prompt

**For:** Systematically organizing documentation folders across all Spine ecosystem projects

**Context:** Preparing projects for self-documenting code migration

---

## Objective

Establish a clean, consistent documentation structure across all 8+ Spine projects, eliminating:
- Duplicate documentation files
- Historical planning docs mixed with current docs
- Unclear documentation ownership
- Stale/outdated content

**End goal:** Each project has a canonical doc structure ready for auto-generated documentation.

---

## Canonical Documentation Structure

Every project should follow this structure:

```
<project>/
├── docs/
│   ├── README.md or index.md       # MkDocs landing page
│   ├── MANIFESTO.md                # 🤖 AUTO-GENERATED (don't edit manually)
│   ├── FEATURES.md                 # 🤖 AUTO-GENERATED (don't edit manually)
│   ├── GUARDRAILS.md               # 🤖 AUTO-GENERATED (don't edit manually)
│   ├── CHANGELOG.md                # 🤖 AUTO-GENERATED from git + annotations
│   ├── TODO.md                     # ✍️ Hand-written (future work)
│   ├── adrs/                       # ✍️ Architecture Decision Records
│   │   ├── 001-decision.md
│   │   └── 002-decision.md
│   ├── api/                        # 🤖 AUTO-GENERATED from docstrings
│   │   ├── resolver.md
│   │   └── storage.md
│   ├── guides/                     # ✍️ Hand-written tutorials
│   │   ├── getting-started.md
│   │   ├── installation.md
│   │   └── advanced-usage.md
│   ├── tutorials/                  # ✍️ Hand-written step-by-step
│   │   └── your-first-entity.md
│   └── archive/                    # 📦 Historical docs (reference only)
│       ├── planning/
│       ├── design/
│       ├── rfcs/
│       └── working-notes/
├── mkdocs.yml                      # MkDocs configuration
└── README.md                       # GitHub repo readme
```

**Legend:**
- 🤖 **AUTO-GENERATED** - Never edit manually (will be overwritten by docbuilder)
- ✍️ **Hand-written** - Maintained manually
- 📦 **Archive** - Historical reference (git history is sufficient)

---

## Step-by-Step Cleanup Process

### Phase 1: Inventory (30 minutes per project)

```bash
# List all markdown files
cd <project>/docs
Get-ChildItem -Recurse -Filter "*.md" | Select-Object FullName, Length, LastWriteTime

# Categorize each file:
# - KEEP (essential current documentation)
# - ARCHIVE (historical/planning)
# - MERGE (duplicate content to consolidate)
# - DELETE (truly obsolete)
```

**Decision matrix:**

| File Type | Criteria | Action |
|-----------|----------|--------|
| **MANIFESTO.md** | Core principles document | KEEP (root only, archive duplicates) |
| **FEATURES.md** | Feature documentation | KEEP (root only, archive duplicates) |
| **GUARDRAILS.md** | Constraints/anti-patterns | KEEP (root only) |
| **README.md / index.md** | Landing page | KEEP (docs/ only) |
| **CHANGELOG.md** | Release history | KEEP (root only, consolidate if multiple) |
| **TODO.md** | Future work | KEEP |
| **ADRs (adrs/)** | Architecture decisions | KEEP |
| **Guides (guides/)** | User tutorials | KEEP |
| **API docs (api/)** | API reference | ARCHIVE (will be auto-generated) |
| **Design docs** | Past design decisions | ARCHIVE |
| **RFCs** | Historical proposals | ARCHIVE |
| **Planning docs** | Sprint planning, etc. | ARCHIVE |
| **HISTORY.md** | Development history | ARCHIVE (git log is sufficient) |
| **DEVELOPMENT_*.md** | Dev setup (if current) | KEEP in guides/, else ARCHIVE |
| **IMPLEMENTATION_*.md** | Implementation notes | ARCHIVE |
| **PROJECT_*.md** | Project tracking | ARCHIVE |

### Phase 2: Archive Historical Docs (1 hour per project)

```bash
# Create archive structure
mkdir -p docs/archive/{planning,design,rfcs,working-notes}

# Example moves
Move-Item docs/design/ docs/archive/design/
Move-Item docs/rfcs/ docs/archive/rfcs/
Move-Item docs/prompts/ docs/archive/planning/prompts/
Move-Item docs/release/ docs/archive/planning/release/

# Individual files
Move-Item docs/DESIGN_*.md docs/archive/design/
Move-Item docs/IMPLEMENTATION_*.md docs/archive/working-notes/
Move-Item docs/PROJECT_*.md docs/archive/planning/
Move-Item docs/HISTORY.md docs/archive/
```

**Archive categories:**

```
archive/
├── planning/              # Sprint planning, roadmaps, trackers
│   ├── prompts/
│   ├── release/
│   └── PROJECT_TRACKER.md
├── design/                # Design documents, proposals
│   ├── DESIGN_REVIEW.md
│   └── PROPOSED_SCHEMA.md
├── rfcs/                  # Request for Comments
│   └── 001-progressive-storage.md
└── working-notes/         # Session notes, implementation logs
    ├── IMPLEMENTATION_AUDIT.md
    └── DEVELOPMENT_HISTORY.md
```

### Phase 3: Resolve Duplicates (30 minutes per project)

**Common duplicates:**

1. **MANIFESTO.md in multiple locations**
   ```bash
   # Find duplicates
   Get-ChildItem -Recurse -Filter "MANIFESTO.md"
   
   # Decision logic:
   # - Keep: docs/MANIFESTO.md (root)
   # - Archive: docs/architecture/MANIFESTO.md
   # - Archive: docs/FEATURES.md if in archive/working-notes/
   
   # Action
   Move-Item docs/architecture/MANIFESTO.md docs/archive/working-notes/MANIFESTO_v1.md
   ```

2. **README.md vs index.md**
   ```bash
   # Keep index.md for MkDocs (or README.md if index doesn't exist)
   # Delete the other or merge content
   ```

3. **Multiple CHANGELOG files**
   ```bash
   # Find
   Get-ChildItem -Recurse -Filter "CHANGELOG*"
   
   # Consolidate into docs/CHANGELOG.md
   # Archive old versions
   ```

4. **API documentation**
   ```bash
   # Archive manual API docs (will be auto-generated)
   Move-Item docs/api/ docs/archive/api-manual/
   ```

### Phase 4: Create Missing Structure (15 minutes per project)

```bash
# Create standard folders if missing
New-Item -ItemType Directory -Force -Path docs/adrs
New-Item -ItemType Directory -Force -Path docs/guides
New-Item -ItemType Directory -Force -Path docs/archive

# Create placeholder files
if (!(Test-Path docs/TODO.md)) {
    @"
# TODO

## High Priority
- [ ] Task 1

## Medium Priority
- [ ] Task 2

## Low Priority / Ideas
- [ ] Idea 1
"@ | Out-File docs/TODO.md
}
```

### Phase 5: Update MkDocs Config (15 minutes per project)

```yaml
# mkdocs.yml
site_name: "ProjectName Documentation"
site_description: "Description here"

nav:
  - Home: index.md
  - Manifesto: MANIFESTO.md
  - Features: FEATURES.md
  - Guardrails: GUARDRAILS.md
  - Getting Started:
      - Installation: guides/installation.md
      - Quickstart: guides/quickstart.md
  - Guides:
      - Advanced Usage: guides/advanced-usage.md
  - API Reference: api/  # Auto-generated
  - ADRs: adrs/
  - Changelog: CHANGELOG.md
  - TODO: TODO.md

theme:
  name: material
  palette:
    primary: indigo
    accent: indigo

plugins:
  - search
  - mkdocstrings:  # For API doc generation
      handlers:
        python:
          options:
            docstring_style: google

markdown_extensions:
  - admonition
  - codehilite
  - pymdownx.superfences
  - pymdownx.tabbed
  - toc:
      permalink: true
```

---

## Project-Specific Cleanup Plans

### EntitySpine

**Current issues:**
- Duplicate MANIFESTO.md (docs/ vs docs/architecture/)
- Duplicate FEATURES.md (docs/ vs docs/archive/working-notes/)
- Many historical docs (DESIGN_REVIEW_*, PROPOSED_SCHEMA_*, etc.)
- API docs folder (should be auto-generated)

**Actions:**
```bash
cd b:\github\py-sec-edgar\entityspine\docs

# Resolve duplicates
Move-Item architecture/MANIFESTO.md archive/working-notes/MANIFESTO_architecture_version.md
Move-Item archive/working-notes/FEATURES.md archive/working-notes/FEATURES_old.md

# Archive historical docs
Move-Item design/ archive/design/
Move-Item rfcs/ archive/rfcs/
Move-Item prompts/ archive/planning/prompts/
Move-Item release/ archive/planning/release/
Move-Item features/ archive/design/features/
Move-Item integration/ archive/design/integration/

# Archive individual files
Move-Item DESIGN_REVIEW_*.md archive/design/
Move-Item PROPOSED_SCHEMA_*.md archive/design/
Move-Item IMPLEMENTATION_*.md archive/working-notes/
Move-Item PROJECT_*.md archive/planning/
Move-Item FEATURE_MATRIX.md archive/working-notes/
Move-Item HISTORY.md archive/
Move-Item README_v*.md archive/

# Archive API docs (will be auto-generated)
Move-Item api/ archive/api-manual/

# Archive architecture/ folder (duplicate content)
Move-Item architecture/ archive/architecture-old/

# Keep essential structure
# ✓ docs/MANIFESTO.md
# ✓ docs/FEATURES.md
# ✓ docs/GUARDRAILS.md
# ✓ docs/adrs/
# ✓ docs/guides/
# ✓ docs/archive/
```

### FeedSpine

**Current issues:**
- Historical DOCUMENTATION_GUIDE.md (docstring standards)
- Implementation audit files
- Design/concept folders

**Actions:**
```bash
cd b:\github\py-sec-edgar\feedspine\docs

# Archive
Move-Item prompts/ archive/planning/prompts/
Move-Item release/ archive/planning/release/
Move-Item concepts/ archive/design/concepts/
Move-Item features/ archive/design/features/
Move-Item design/ archive/design/

# Archive individual files
Move-Item DOCUMENTATION_GUIDE.md archive/working-notes/
Move-Item IMPLEMENTATION_AUDIT.md archive/working-notes/
```

### Capture-Spine

**Unique needs:**
- Has active feature documentation (keep features/ folder)
- Development guides are current (keep docs/development/)
- Prompts are templates (keep docs/development/prompts/)

**Actions:**
```bash
cd b:\github\py-sec-edgar\capture-spine\docs

# Keep:
# - features/ (active feature docs)
# - development/ (current dev guides)
# - how-to/, tutorials/, getting-started/ (MkDocs content)

# Archive only truly historical docs
Move-Item archive-old/ archive/
Move-Item old-design/ archive/design/ (if exists)
```

### GenAI-Spine, Market-Spine, etc.

Apply same process:
1. Identify core docs (MANIFESTO, FEATURES, GUARDRAILS)
2. Move historical planning docs to archive/
3. Keep current guides/tutorials
4. Archive old API docs (will be auto-generated)

---

## Verification Checklist

After cleanup, each project should pass:

```bash
# Verify structure
Test-Path docs/MANIFESTO.md        # Should exist (or be ready for generation)
Test-Path docs/FEATURES.md          # Should exist (or be ready for generation)
Test-Path docs/GUARDRAILS.md        # Should exist (or be ready for generation)
Test-Path docs/adrs                 # Should exist (empty OK)
Test-Path docs/guides               # Should exist
Test-Path docs/archive              # Should exist

# No duplicates
@(Get-ChildItem -Recurse -Filter "MANIFESTO.md").Count -le 1
@(Get-ChildItem -Recurse -Filter "FEATURES.md").Count -le 1

# No old design docs in root
!(Test-Path docs/DESIGN_*.md)
!(Test-Path docs/IMPLEMENTATION_*.md)
!(Test-Path docs/PROJECT_*.md)

# MkDocs builds without errors
python -m mkdocs build
```

**Checklist:**
- [ ] Single MANIFESTO.md in docs/ (not in subfolders)
- [ ] Single FEATURES.md in docs/
- [ ] GUARDRAILS.md exists
- [ ] Historical docs moved to docs/archive/
- [ ] adrs/, guides/, archive/ folders exist
- [ ] MkDocs builds successfully
- [ ] No design/planning docs in docs root
- [ ] API docs archived (will be auto-generated)

---

## Automation Script (PowerShell)

```powershell
# cleanup-docs.ps1
param(
    [Parameter(Mandatory=$true)]
    [string]$ProjectPath
)

$docsPath = Join-Path $ProjectPath "docs"
if (!(Test-Path $docsPath)) {
    Write-Error "No docs/ folder found at $docsPath"
    exit 1
}

Write-Host "=== Cleaning up documentation for $ProjectPath ===" -ForegroundColor Cyan

# Create archive structure
$archivePaths = @(
    "archive/planning",
    "archive/design",
    "archive/rfcs",
    "archive/working-notes"
)
foreach ($path in $archivePaths) {
    $fullPath = Join-Path $docsPath $path
    if (!(Test-Path $fullPath)) {
        New-Item -ItemType Directory -Force -Path $fullPath | Out-Null
        Write-Host "  Created: $path" -ForegroundColor Green
    }
}

# Archive patterns
$archivePatterns = @{
    "DESIGN_*.md" = "archive/design/"
    "IMPLEMENTATION_*.md" = "archive/working-notes/"
    "PROJECT_*.md" = "archive/planning/"
    "HISTORY.md" = "archive/"
    "DEVELOPMENT_HISTORY.md" = "archive/"
    "FEATURE_MATRIX.md" = "archive/working-notes/"
}

foreach ($pattern in $archivePatterns.Keys) {
    $files = Get-ChildItem -Path $docsPath -Filter $pattern -File
    foreach ($file in $files) {
        $dest = Join-Path $docsPath $archivePatterns[$pattern]
        Move-Item -Path $file.FullName -Destination $dest -Force
        Write-Host "  Archived: $($file.Name) -> $($archivePatterns[$pattern])" -ForegroundColor Yellow
    }
}

# Archive folders
$archiveFolders = @("design", "rfcs", "prompts", "release", "features", "integration", "concepts")
foreach ($folder in $archiveFolders) {
    $folderPath = Join-Path $docsPath $folder
    if (Test-Path $folderPath) {
        $dest = Join-Path $docsPath "archive/$folder"
        if (Test-Path $dest) {
            # Merge if destination exists
            Get-ChildItem -Path $folderPath | Move-Item -Destination $dest -Force
            Remove-Item $folderPath -Force -Recurse
        } else {
            Move-Item -Path $folderPath -Destination $dest -Force
        }
        Write-Host "  Archived folder: $folder/ -> archive/$folder/" -ForegroundColor Yellow
    }
}

# Check for duplicates
$manifestos = @(Get-ChildItem -Path $docsPath -Recurse -Filter "MANIFESTO.md")
if ($manifestos.Count -gt 1) {
    Write-Host "  WARNING: Multiple MANIFESTO.md files found:" -ForegroundColor Red
    foreach ($m in $manifestos) {
        Write-Host "    - $($m.FullName.Replace($docsPath, 'docs'))" -ForegroundColor Red
    }
}

Write-Host "`n=== Cleanup complete ===" -ForegroundColor Green
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Review docs/archive/ to ensure nothing critical was moved"
Write-Host "  2. Resolve any duplicate files"
Write-Host "  3. Update mkdocs.yml navigation"
Write-Host "  4. Run: python -m mkdocs build"
```

**Usage:**
```powershell
.\cleanup-docs.ps1 -ProjectPath "b:\github\py-sec-edgar\entityspine"
.\cleanup-docs.ps1 -ProjectPath "b:\github\py-sec-edgar\feedspine"
# etc.
```

---

## Timeline

| Week | Activity | Projects |
|------|----------|----------|
| Week 1 | Cleanup entityspine & feedspine | 2 projects |
| Week 2 | Cleanup genai-spine & capture-spine | 2 projects |
| Week 3 | Cleanup market-spine & spine-core | 2 projects |
| Week 4 | Cleanup remaining projects & validation | All projects |

**Total effort:** ~8 hours (1 hour per project)

---

## Next Steps

1. **Run inventory** on each project (30 min/project)
2. **Execute cleanup** using automation script (30 min/project)
3. **Manual review** of archived content (15 min/project)
4. **MkDocs validation** (build & preview) (15 min/project)
5. **Commit changes** with clear message:
   ```bash
   git add docs/
   git commit -m "docs: organize documentation structure, archive historical docs"
   ```

---

## Related Documentation

- [../README.md](../README.md) - Documentation automation overview
- [CODE_ANNOTATION_PROMPT.md](CODE_ANNOTATION_PROMPT.md) - Annotating code for auto-generation
- [../design/SELF_DOCUMENTING_CODE.md](../design/SELF_DOCUMENTING_CODE.md) - Feature design

---

*Clean documentation starts with clean organization.*
