# ARCHITECTURE

**System Design and Structure**

> **Auto-generated from code annotations**  
> **Last Updated**: February 2026  
> **Status**: Living Document

---

## Table of Contents

1. [System Overview](#system-overview)
2. [FeedAdapter](#feedadapter)

---

## System Overview

```
```
    ┌─────────────────────────────────────────────────────────┐
    │                  EntityResolver                         │
    │                                                         │
    │  Input Identifier ──► Normalize ──► Lookup ──► Entity   │
    │  (CIK, ticker,        (clean,       (local    (canonical│
    │   name, CUSIP)         format)       cache)    entity)  │
    │                                        │                │
    │                                        ▼                │
    │                              Fallback: SEC EDGAR API    │
    └─────────────────────────────────────────────────────────┘
    ```
```

*Source: [`EntityResolver`](/app/projects/spine-core/src/doc-automation/tests/fixtures/sample_annotated_class.py#L9)*


---

## ASTWalker

```
```
    Python File (.py)
          │
          ▼
    ast.parse() ──► AST Tree
          │
          ▼
    ast.walk() ──► Visit Nodes
          │
          ├──► ClassDef nodes ──► ClassInfo
          │         │
          │         └──► FunctionDef ──► MethodInfo
          │
          └──► Results: List[ClassInfo]
    ```
```

*Source: [`ASTWalker`](/app/projects/spine-core/src/doc-automation/src/doc_automation/parser/ast_walker.py#L90)*



## BaseRenderer

```
```
    Graph ──► DocumentationQuery
                   │
                   ▼
           get_fragments_for_doc_type()
                   │
                   ▼
           Renderer._group_by_section()
                   │
                   ▼
           Jinja2 Template
                   │
                   ▼
           Rendered Markdown
    ```
```

*Source: [`BaseRenderer`](/app/projects/spine-core/src/doc-automation/src/doc_automation/renderers/base.py#L18)*



## DocstringParser

```
```
    Docstring Text
          │
          ▼
    _split_sections() ──► {"Manifesto": "...", "Features": "..."}
          │
          ▼
    For each section:
          │
          ├──► Create DocumentationFragment
          │        - fragment_type = section name
          │        - content = section text
          │        - format = detect (md/python/diagram)
          │
          └──► Extract metadata
                   - tags from Tags: section
                   - doc_types from Doc-Types: section
                   - sections mapping
    ```
```

*Source: [`DocstringParser`](/app/projects/spine-core/src/doc-automation/src/doc_automation/parser/docstring_parser.py#L71)*



## DocumentationOrchestrator

```
```
    DocumentationOrchestrator
          │
          ├──► KnowledgeGraphBuilder.build()
          │         │
          │         ▼
          │    graph = {entities, claims, relationships}
          │
          ├──► For each doc type:
          │         │
          │         ├──► Renderer.render()
          │         │         │
          │         │         ▼
          │         │    content (string)
          │         │
          │         └──► Write to output_dir/DOC_TYPE.md
          │
          └──► Return summary
    ```
```

*Source: [`DocumentationOrchestrator`](/app/projects/spine-core/src/doc-automation/src/doc_automation/orchestrator.py#L32)*



## DocumentationQuery

```
```
    Graph Data (entities, claims, relationships)
          │
          ▼
    DocumentationQuery
          │
          ├──► get_fragments_for_doc_type("MANIFESTO")
          │         │
          │         ▼
          │    Filter entities by DOC_TYPE claims
          │         │
          │         ▼
          │    Sort by priority
          │         │
          │         ▼
          │    Return List[DocFragmentEntity]
          │
          ├──► get_fragments_by_tag("core_concept")
          │
          └──► get_fragments_for_section("ARCHITECTURE", "Data Model")
    ```
```

*Source: [`DocumentationQuery`](/app/projects/spine-core/src/doc-automation/src/doc_automation/graph/queries.py#L25)*



## EntityResolver

```
```
    ┌─────────────────────────────────────────────────────────┐
    │                  EntityResolver                         │
    │                                                         │
    │  Input Identifier ──► Normalize ──► Lookup ──► Entity   │
    │  (CIK, ticker,        (clean,       (local    (canonical│
    │   name, CUSIP)         format)       cache)    entity)  │
    │                                        │                │
    │                                        ▼                │
    │                              Fallback: SEC EDGAR API    │
    └─────────────────────────────────────────────────────────┘
    ```
```

*Source: [`EntityResolver`](/app/projects/spine-core/src/doc-automation/tests/fixtures/sample_annotated_class.py#L9)*



## FeedAdapter


```
    External Feed ──► FeedAdapter ──► Normalized Data ──► Storage
    (CSV, API,         (transform,     (standard         (DuckDB,
     JSON)              validate)       schema)           Parquet)
    ```



---

*6 architectural diagrams from 1 components*

*Generated by [doc-automation](https://github.com/your-org/py-sec-edgar/tree/main/spine-core/packages/doc-automation)*