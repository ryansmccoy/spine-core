"""Interactive HTML renderer for the commit review document.

Produces a single self-contained .html file with:
- Sidebar: search, phase/marker/feature-type/domain filters, date range
- Expand All / Collapse All controls per phase and globally
- Per-commit collapsible sections (files, docstrings, commit message)
- Commit counter badge that updates with active filters
- No external dependencies — all CSS/JS is embedded inline

Stability: stable
Tier: none
Since: 0.4.0
Dependencies: stdlib-only
Doc-Types: API_REFERENCE, TECHNICAL_DESIGN
Tags: changelog, html, renderer, interactive
"""

from __future__ import annotations

import html
import json
import re
from datetime import UTC, datetime

from .model import CommitNote, PhaseGroup

# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def render_html_review(
    phases: list[PhaseGroup],
    project_name: str = "spine-core",
    project_version: str = "",
    kg_data: dict | None = None,
) -> str:
    """Render an interactive single-file HTML commit review.

    Args:
        phases: Phase groups with populated commits.
        project_name: Display name for the project.
        project_version: Optional version string.
        kg_data: Optional D3-ready knowledge graph data (nodes/links).

    Returns:
        Complete HTML document as a string.
    """
    total_commits = sum(len(p.commits) for p in phases)
    total_files_set: set[str] = set()
    for p in phases:
        for c in p.commits:
            for f in c.files:
                total_files_set.add(f.path)

    # Build the JSON data blob for JS filters
    commits_data = _build_commits_json(phases)

    # Collect unique filter values
    all_markers: set[str] = set()
    all_feature_types: set[str] = set()
    all_domains: set[str] = set()
    all_architectures: set[str] = set()
    for p in phases:
        for c in p.commits:
            all_markers.update(c.trailers.markers)
            if c.trailers.feature_type:
                all_feature_types.add(c.trailers.feature_type)
            if c.trailers.domain:
                all_domains.add(c.trailers.domain)
            if c.trailers.architecture:
                all_architectures.add(c.trailers.architecture)

    # Build the body sections
    body_html = _render_body(phases, total_commits, len(total_files_set))

    title = f"{project_name} — Commit Review"
    subtitle = f"{total_commits} commits · {len(total_files_set)} files · {len(phases)} phases"
    if project_version:
        subtitle = f"v{project_version} · " + subtitle

    return _wrap_html(
        title=title,
        subtitle=subtitle,
        body_html=body_html,
        commits_json=json.dumps(commits_data, default=str),
        kg_json=json.dumps(kg_data, default=str) if kg_data else "null",
        phases=phases,
        all_markers=sorted(all_markers),
        all_feature_types=sorted(all_feature_types),
        all_domains=sorted(all_domains),
        all_architectures=sorted(all_architectures),
    )


# ---------------------------------------------------------------------------
# Data layer
# ---------------------------------------------------------------------------

_STATUS_ICONS = {"A": "➕", "M": "✏️", "D": "🗑️", "R": "🔄", "C": "📋"}
_MARKER_COLORS = {
    "NEW": "#22c55e",
    "FOUNDATIONAL": "#3b82f6",
    "EXPERIMENTAL": "#f59e0b",
    "REFACTOR": "#a855f7",
    "BREAKING": "#ef4444",
    "DEPRECATION": "#f97316",
}
_COMMIT_TYPE_COLORS = {
    "feat": "#22c55e",
    "fix": "#ef4444",
    "test": "#3b82f6",
    "build": "#f59e0b",
    "docs": "#a855f7",
    "refactor": "#f97316",
    "chore": "#6b7280",
    "perf": "#06b6d4",
}


def _commit_type(subject: str) -> str:
    m = re.match(r"^([a-z]+)[\(:]", subject)
    return m.group(1) if m else "other"


def _build_commits_json(phases: list[PhaseGroup]) -> list[dict]:
    rows = []
    commit_num = 0
    for phase in phases:
        for commit in phase.commits:
            commit_num += 1
            rows.append({
                "id": f"commit-{commit.short_sha}",
                "num": commit_num,
                "sha": commit.short_sha,
                "subject": commit.subject,
                "date": commit.date[:10] if commit.date and len(commit.date) >= 10 else "",
                "author": commit.author,
                "markers": list(commit.trailers.markers),
                "feature_type": commit.trailers.feature_type or "",
                "domain": commit.trailers.domain or "",
                "architecture": commit.trailers.architecture or "",
                "tags": list(commit.trailers.tags),
                "impact": commit.trailers.impact.value,
                "type": _commit_type(commit.subject),
                "phase": phase.number,
                "phase_name": phase.name,
                "file_count": len(commit.files),
            })
    return rows


# ---------------------------------------------------------------------------
# HTML body rendering
# ---------------------------------------------------------------------------


def _render_body(phases: list[PhaseGroup], total_commits: int, total_files: int) -> str:
    parts: list[str] = []

    # Phase summary table
    parts.append('<div class="summary-table-wrap">')
    parts.append('<table class="summary-table"><thead><tr>')
    parts.append('<th>#</th><th>Phase</th><th>Commits</th><th>Files</th><th></th>')
    parts.append('</tr></thead><tbody>')
    for p in phases:
        anchor = f"phase-{p.number}"
        parts.append(
            f'<tr data-phase="{p.number}">'
            f'<td class="phase-num">{p.number}</td>'
            f'<td><a href="#{anchor}">{_h(p.name)}</a></td>'
            f'<td class="center">{len(p.commits)}</td>'
            f'<td class="center">{p.total_files}</td>'
            f'<td><button class="btn-xs" onclick="togglePhase({p.number})">toggle</button></td>'
            f'</tr>'
        )
    parts.append('</tbody></table></div>')

    commit_num = 0
    for phase in phases:
        parts.append(
            f'<section class="phase-section" id="phase-{phase.number}" data-phase="{phase.number}">'
        )
        parts.append(
            f'<div class="phase-header" onclick="togglePhase({phase.number})">'
            f'<span class="phase-chevron" id="chev-{phase.number}">▾</span>'
            f'<h2 class="phase-title">Phase {phase.number} — {_h(phase.name)}</h2>'
            f'<span class="phase-meta">{len(phase.commits)} commits · {phase.total_files} files</span>'
            f'<div class="phase-controls">'
            f'<button class="btn-xs" onclick="event.stopPropagation();expandPhase({phase.number})">expand all</button>'
            f'<button class="btn-xs" onclick="event.stopPropagation();collapsePhase({phase.number})">collapse all</button>'
            f'</div>'
            f'</div>'
        )
        parts.append(f'<div class="phase-body" id="phase-body-{phase.number}">')

        for commit in phase.commits:
            commit_num += 1
            parts.append(_render_commit_card(commit, commit_num, total_commits, phase))

        parts.append('</div></section>')  # close phase-body + phase-section

    return "\n".join(parts)


def _render_commit_card(
    commit: CommitNote,
    num: int,
    total: int,
    phase: PhaseGroup,
) -> str:
    sha = commit.short_sha
    ctype = _commit_type(commit.subject)
    type_color = _COMMIT_TYPE_COLORS.get(ctype, "#6b7280")

    added = sum(1 for f in commit.files if f.status == "A")
    modified = sum(1 for f in commit.files if f.status == "M")
    deleted = sum(1 for f in commit.files if f.status == "D")
    file_summary = f"{len(commit.files)} files"
    if added or modified or deleted:
        parts_ = []
        if added:
            parts_.append(f"+{added}")
        if modified:
            parts_.append(f"~{modified}")
        if deleted:
            parts_.append(f"-{deleted}")
        file_summary = f"{len(commit.files)} ({', '.join(parts_)})"

    # Marker badges
    marker_html = ""
    for m in commit.trailers.markers:
        color = _MARKER_COLORS.get(m, "#6b7280")
        marker_html += f'<span class="badge" style="background:{color}">{_h(m)}</span>'

    type_badge = f'<span class="badge-type" style="border-color:{type_color};color:{type_color}">{_h(ctype)}</span>'

    date_str = commit.date[:10] if commit.date and len(commit.date) >= 10 else ""

    # Build data attrs for JS filtering
    markers_attr = _h(",".join(commit.trailers.markers))
    tags_attr = _h(",".join(commit.trailers.tags))
    ft = _h(commit.trailers.feature_type)
    dom = _h(commit.trailers.domain)
    arch = _h(commit.trailers.architecture)

    card_id = f"commit-{sha}"
    detail_id = f"detail-{sha}"

    # ---------- header row ----------
    out = (
        f'<div class="commit-card" id="{card_id}" '
        f'data-sha="{sha}" data-date="{date_str}" data-type="{_h(ctype)}" '
        f'data-markers="{markers_attr}" data-tags="{tags_attr}" '
        f'data-feature-type="{ft}" data-domain="{dom}" data-architecture="{arch}" '
        f'data-phase="{phase.number}" data-subject="{_h(commit.subject)}">'
        f'<div class="commit-header" onclick="toggleCommit(\'{sha}\')">'
        f'<span class="commit-num">{num}/{total}</span>'
        f'<code class="commit-sha">{sha}</code>'
        f'{type_badge}'
        f'<span class="commit-subject">{_h(commit.subject)}</span>'
        f'<span class="commit-meta">{date_str} · {file_summary}</span>'
        f'{marker_html}'
        f'<span class="commit-chevron" id="commit-chev-{sha}">▾</span>'
        f'</div>'  # /commit-header
    )

    # ---------- collapsible detail ----------
    out += f'<div class="commit-detail" id="{detail_id}">'

    # Metadata strip
    meta_items = []
    if date_str:
        meta_items.append(f"<strong>Date:</strong> {date_str}")
    if commit.author:
        meta_items.append(f"<strong>Author:</strong> {_h(commit.author)}")
    if commit.trailers.feature_type:
        meta_items.append(f"<strong>Type:</strong> {_h(commit.trailers.feature_type)}")
    if commit.trailers.domain:
        meta_items.append(f"<strong>Domain:</strong> {_h(commit.trailers.domain)}")
    if commit.trailers.architecture:
        meta_items.append(f"<strong>Arch:</strong> {_h(commit.trailers.architecture)}")
    if commit.trailers.impact.value != "internal":
        meta_items.append(f"<strong>Impact:</strong> {_h(commit.trailers.impact.value)}")
    if meta_items:
        out += f'<div class="commit-meta-strip">{"&ensp;·&ensp;".join(meta_items)}</div>'

    # Commit message (what/why/tags)
    msg_parts: list[str] = []
    if commit.body_what:
        msg_parts.append("<strong>What:</strong>")
        for line in commit.body_what.strip().splitlines():
            line = line.lstrip("- ").strip()
            if line:
                msg_parts.append(f"<li>{_h(line)}</li>")
    if commit.body_why:
        msg_parts.append("<strong>Why:</strong>")
        for line in commit.body_why.strip().splitlines():
            line = line.lstrip("- ").strip()
            if line:
                msg_parts.append(f"<li>{_h(line)}</li>")
    if commit.trailers.tags:
        msg_parts.append(f'<strong>Tags:</strong> {_h(", ".join(commit.trailers.tags))}')
    if msg_parts:
        out += f'<div class="commit-body"><ul>{"".join(msg_parts)}</ul></div>'

    # Files accordion
    if commit.files:
        files_id = f"files-{sha}"
        out += (
            f'<div class="accordion">'
            f'<div class="accordion-header" onclick="toggleEl(\'{files_id}\')">'
            f'<span>📁 Files ({len(commit.files)})</span>'
            f'<span class="acc-chev" id="acc-chev-{files_id}">▾</span>'
            f'</div>'
            f'<div class="accordion-body open" id="{files_id}">'
            f'<table class="files-table"><tbody>'
        )
        for f in commit.files[:60]:  # cap at 60 for perf
            icon = _STATUS_ICONS.get(f.status, f.status)
            out += f'<tr><td class="file-icon">{icon}</td><td class="file-path"><code>{_h(f.path)}</code></td></tr>'
        if len(commit.files) > 60:
            out += f'<tr><td colspan="2" class="file-more">… {len(commit.files) - 60} more files</td></tr>'
        out += '</tbody></table></div></div>'  # files accordion

    # Docstrings accordion
    if commit.docstrings:
        # Filter trivial __init__ docstrings
        docs = {k: v for k, v in sorted(commit.docstrings.items())
                if not (k.endswith("__init__.py") and len(v) < 40)}
        if docs:
            docs_id = f"docs-{sha}"
            out += (
                f'<div class="accordion">'
                f'<div class="accordion-header" onclick="toggleEl(\'{docs_id}\')">'
                f'<span>📄 Module Docstrings ({len(docs)})</span>'
                f'<span class="acc-chev" id="acc-chev-{docs_id}">▾</span>'
                f'</div>'
                f'<div class="accordion-body open" id="{docs_id}">'
            )
            for mod_path, docstring in docs.items():
                display_path = mod_path.replace("\\", "/")
                ds_lines = docstring.splitlines()
                # Show the first 20 lines collapsed, rest hidden
                preview_lines = ds_lines[:20]
                rest_lines = ds_lines[20:] if len(ds_lines) > 20 else []
                preview = _h("\n".join(preview_lines))
                rest_html = ""
                rest_id = f"dsrest-{sha}-{re.sub(r'[^a-z0-9]', '_', display_path.lower())}"
                if rest_lines:
                    rest_count = len(rest_lines)
                    rest_html = (
                        f'<div class="ds-rest" id="{rest_id}" style="display:none">'
                        f'<pre class="docstring-pre">{_h(chr(10).join(rest_lines))}</pre>'
                        f'</div>'
                        f'<button class="btn-show-more" '
                        f'onclick="toggleDsRest(\'{rest_id}\', this)">'
                        f'+ {rest_count} more lines</button>'
                    )
                out += (
                    f'<div class="docstring-block">'
                    f'<div class="docstring-path">{_h(display_path)}</div>'
                    f'<pre class="docstring-pre">{preview}</pre>'
                    f'{rest_html}'
                    f'</div>'
                )
            out += '</div></div>'  # docs accordion

    # Sidecar content
    if commit.sidecar:
        sc = commit.sidecar
        if sc.migration_guide:
            out += f'<div class="sidecar-section"><strong>Migration Guide</strong><div class="sidecar-body">{_h(sc.migration_guide)}</div></div>'
        if sc.examples:
            out += f'<div class="sidecar-section"><strong>Examples</strong><div class="sidecar-body">{_h(sc.examples)}</div></div>'

    out += '</div>'  # /commit-detail
    out += '</div>'  # /commit-card
    return out


def _h(s: str) -> str:
    """HTML-escape a string."""
    return html.escape(s, quote=True)


# ---------------------------------------------------------------------------
# Full HTML wrapper
# ---------------------------------------------------------------------------


def _wrap_html(
    title: str,
    subtitle: str,
    body_html: str,
    commits_json: str,
    kg_json: str,
    phases: list[PhaseGroup],
    all_markers: list[str],
    all_feature_types: list[str],
    all_domains: list[str],
    all_architectures: list[str],
) -> str:
    generated_at = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M UTC")

    # Sidebar filter checkboxes
    def _checkboxes(items: list[str], group: str, label: str) -> str:
        if not items:
            return ""
        html_parts = [f'<div class="filter-group"><div class="filter-group-label">{_h(label)}</div>']
        for item in items:
            item_id = f"filter-{group}-{re.sub(r'[^a-z0-9]', '_', item.lower())}"
            html_parts.append(
                f'<label class="filter-cb">'
                f'<input type="checkbox" id="{item_id}" checked '
                f'data-filter-group="{group}" data-filter-value="{_h(item)}" '
                f'onchange="applyFilters()">'
                f'<span>{_h(item)}</span>'
                f'</label>'
            )
        html_parts.append('</div>')
        return "\n".join(html_parts)

    phase_checkboxes_html = '<div class="filter-group"><div class="filter-group-label">Phase</div>'
    for p in phases:
        pid = f"filter-phase-{p.number}"
        phase_checkboxes_html += (
            f'<label class="filter-cb">'
            f'<input type="checkbox" id="{pid}" checked '
            f'data-filter-group="phase" data-filter-value="{p.number}" '
            f'onchange="applyFilters()">'
            f'<span>{_h(str(p.number))}. {_h(p.name)}</span>'
            f'</label>'
        )
    phase_checkboxes_html += '</div>'

    marker_checkboxes = _checkboxes(all_markers, "marker", "Markers")
    feature_type_checkboxes = _checkboxes(all_feature_types, "feature_type", "Feature Type")
    domain_checkboxes = _checkboxes(all_domains, "domain", "Domain")
    arch_checkboxes = _checkboxes(all_architectures, "architecture", "Architecture")

    commit_types = sorted({"feat", "fix", "test", "build", "docs", "refactor", "chore", "perf"})
    type_checkboxes = _checkboxes(commit_types, "type", "Commit Type")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_h(title)}</title>
<style>
/* ── Reset & base ───────────────────────────────────────────── */
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
:root {{
  --bg: #0f1117;
  --bg2: #161b22;
  --bg3: #1f2937;
  --bg4: #374151;
  --border: #30363d;
  --text: #e6edf3;
  --text2: #8b949e;
  --text3: #6b7280;
  --accent: #58a6ff;
  --accent2: #1d4ed8;
  --green: #22c55e;
  --sidebar-w: 280px;
  --header-h: 56px;
  --radius: 6px;
  --transition: 0.18s ease;
}}
html {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; font-size: 14px; }}
body {{ background: var(--bg); color: var(--text); min-height: 100vh; }}
a {{ color: var(--accent); text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
code, pre {{ font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace; font-size: 12px; }}

/* ── Top bar ────────────────────────────────────────────────── */
.topbar {{
  position: fixed; top: 0; left: 0; right: 0; height: var(--header-h);
  background: var(--bg2); border-bottom: 1px solid var(--border);
  display: flex; align-items: center; gap: 12px; padding: 0 16px;
  z-index: 100;
}}
.topbar-title {{ font-weight: 700; font-size: 16px; color: var(--text); }}
.topbar-subtitle {{ font-size: 12px; color: var(--text2); flex: 1; }}
.topbar-controls {{ display: flex; gap: 8px; align-items: center; }}
.topbar-count {{
  background: var(--bg3); border: 1px solid var(--border);
  border-radius: 12px; padding: 2px 10px; font-size: 12px;
  color: var(--text2);
}}
.topbar-count strong {{ color: var(--text); }}
#search-input {{
  background: var(--bg3); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 5px 10px;
  color: var(--text); font-size: 13px; width: 220px;
  outline: none;
}}
#search-input:focus {{ border-color: var(--accent); }}
input::placeholder {{ color: var(--text3); }}

/* ── Sidebar ────────────────────────────────────────────────── */
.sidebar {{
  position: fixed; top: var(--header-h); left: 0;
  width: var(--sidebar-w); height: calc(100vh - var(--header-h));
  background: var(--bg2); border-right: 1px solid var(--border);
  overflow-y: auto; padding: 12px 0;
  transition: transform var(--transition);
  z-index: 90;
}}
.sidebar.collapsed {{ transform: translateX(calc(-1 * var(--sidebar-w))); }}
.sidebar-section {{ padding: 0 14px 10px; }}
.sidebar-heading {{
  font-size: 11px; font-weight: 600; text-transform: uppercase;
  letter-spacing: 0.06em; color: var(--text3); margin-bottom: 6px;
  display: flex; justify-content: space-between; align-items: center;
}}
.sidebar-heading button {{ font-size: 10px; cursor: pointer; background: none; border: none; color: var(--text2); padding: 0; }}
.sidebar-heading button:hover {{ color: var(--text); }}
.filter-group {{ margin-bottom: 14px; }}
.filter-group-label {{
  font-size: 11px; font-weight: 600; text-transform: uppercase;
  letter-spacing: 0.06em; color: var(--text3); margin-bottom: 5px;
}}
.filter-cb {{ display: flex; align-items: center; gap: 6px; padding: 2px 0; cursor: pointer; font-size: 12px; color: var(--text2); line-height: 1.4; }}
.filter-cb:hover {{ color: var(--text); }}
.filter-cb input {{ accent-color: var(--accent); cursor: pointer; flex-shrink: 0; }}
.filter-cb span {{ word-break: break-word; }}
.date-range {{ display: flex; flex-direction: column; gap: 6px; }}
.date-range label {{ font-size: 11px; color: var(--text3); }}
.date-range input {{
  background: var(--bg3); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 4px 8px; color: var(--text);
  font-size: 12px; outline: none; width: 100%;
}}
.date-range input:focus {{ border-color: var(--accent); }}
.sort-select {{
  background: var(--bg3); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 4px 8px; color: var(--text);
  font-size: 12px; outline: none; width: 100%; cursor: pointer;
}}
hr.sidebar-divider {{ border: none; border-top: 1px solid var(--border); margin: 8px 0; }}

/* ── Main content ───────────────────────────────────────────── */
.main {{
  margin-left: var(--sidebar-w);
  margin-top: var(--header-h);
  padding: 24px;
  transition: margin-left var(--transition);
}}
.main.sidebar-collapsed {{ margin-left: 0; }}
.no-results {{
  display: none; text-align: center; padding: 48px;
  color: var(--text3); font-size: 16px;
}}

/* ── Summary table ──────────────────────────────────────────── */
.summary-table-wrap {{ overflow-x: auto; margin-bottom: 28px; }}
.summary-table {{
  width: 100%; border-collapse: collapse; font-size: 13px;
  background: var(--bg2); border-radius: var(--radius);
  overflow: hidden; border: 1px solid var(--border);
}}
.summary-table th {{
  background: var(--bg3); color: var(--text2); font-weight: 600;
  padding: 8px 12px; text-align: left; font-size: 11px; text-transform: uppercase;
  letter-spacing: 0.04em;
}}
.summary-table td {{ padding: 7px 12px; border-top: 1px solid var(--border); }}
.summary-table tbody tr:hover {{ background: var(--bg3); }}
.summary-table .phase-num {{ color: var(--text3); font-size: 11px; width: 32px; }}
.center {{ text-align: center; }}

/* ── Phase sections ─────────────────────────────────────────── */
.phase-section {{ margin-bottom: 20px; }}
.phase-header {{
  display: flex; align-items: center; gap: 10px; cursor: pointer;
  padding: 10px 14px; background: var(--bg2); border: 1px solid var(--border);
  border-radius: var(--radius); user-select: none;
  transition: background var(--transition);
}}
.phase-header:hover {{ background: var(--bg3); }}
.phase-chevron {{ font-size: 14px; color: var(--text2); width: 16px; text-align: center; transition: transform var(--transition); }}
.phase-chevron.collapsed {{ transform: rotate(-90deg); }}
.phase-title {{ font-size: 15px; font-weight: 700; flex: 1; }}
.phase-meta {{ font-size: 12px; color: var(--text3); }}
.phase-controls {{ display: flex; gap: 6px; }}
.phase-body {{ margin-top: 4px; }}
.phase-body.collapsed {{ display: none; }}

/* ── Commit cards ───────────────────────────────────────────── */
.commit-card {{
  border: 1px solid var(--border); border-radius: var(--radius);
  margin-bottom: 6px; background: var(--bg2); overflow: hidden;
  transition: border-color var(--transition);
}}
.commit-card:hover {{ border-color: var(--text3); }}
.commit-card.hidden {{ display: none; }}
.commit-header {{
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  padding: 8px 12px; cursor: pointer; user-select: none;
  transition: background var(--transition);
}}
.commit-header:hover {{ background: var(--bg3); }}
.commit-num {{ font-size: 11px; color: var(--text3); min-width: 40px; }}
.commit-sha {{ font-size: 11px; color: var(--accent); background: var(--bg3); padding: 1px 6px; border-radius: 3px; }}
.commit-subject {{ flex: 1; font-weight: 600; font-size: 13px; }}
.commit-meta {{ font-size: 11px; color: var(--text3); white-space: nowrap; }}
.commit-chevron {{ color: var(--text3); font-size: 12px; margin-left: auto; transition: transform var(--transition); }}
.commit-chevron.collapsed {{ transform: rotate(-90deg); }}
.commit-detail {{ padding: 0 12px 12px; border-top: 1px solid var(--border); }}
.commit-detail.collapsed {{ display: none; }}

/* badges */
.badge {{
  display: inline-block; font-size: 10px; font-weight: 700;
  padding: 1px 7px; border-radius: 10px; color: #fff;
  text-transform: uppercase; letter-spacing: 0.04em;
}}
.badge-type {{
  display: inline-block; font-size: 10px; font-weight: 600;
  padding: 1px 7px; border-radius: 3px; border: 1px solid;
  background: transparent;
}}

/* ── Commit detail internals ────────────────────────────────── */
.commit-meta-strip {{ font-size: 12px; color: var(--text2); padding: 8px 0 4px; display: flex; gap: 8px; flex-wrap: wrap; }}
.commit-body {{ font-size: 13px; color: var(--text2); padding: 6px 0; }}
.commit-body ul {{ list-style: none; padding: 0; }}
.commit-body li {{ padding: 2px 0 2px 12px; position: relative; }}
.commit-body li::before {{ content: "–"; position: absolute; left: 0; color: var(--text3); }}
.commit-body strong {{ color: var(--text); }}

/* ── Accordion ──────────────────────────────────────────────── */
.accordion {{ margin-top: 8px; border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; }}
.accordion-header {{
  display: flex; justify-content: space-between; align-items: center;
  padding: 7px 10px; background: var(--bg3); cursor: pointer; font-size: 12px;
  user-select: none;
}}
.accordion-header:hover {{ background: var(--bg4); }}
.acc-chev {{ color: var(--text3); font-size: 11px; transition: transform var(--transition); }}
.acc-chev.collapsed {{ transform: rotate(-90deg); }}
.accordion-body {{ padding: 8px; background: var(--bg); }}
.accordion-body.collapsed {{ display: none; }}

/* ── Files table ────────────────────────────────────────────── */
.files-table {{ width: 100%; border-collapse: collapse; }}
.files-table td {{ padding: 3px 6px; font-size: 12px; vertical-align: top; }}
.file-icon {{ width: 22px; text-align: center; }}
.file-path code {{ color: var(--text2); word-break: break-all; }}
.file-more {{ text-align: center; color: var(--text3); font-style: italic; padding: 6px; }}

/* ── Docstrings ─────────────────────────────────────────────── */
.docstring-block {{ margin-bottom: 12px; }}
.docstring-path {{
  font-size: 11px; font-weight: 600; color: var(--accent);
  padding: 4px 0 2px; border-bottom: 1px solid var(--border); margin-bottom: 6px;
}}
.docstring-pre {{
  background: var(--bg2); border-radius: var(--radius); padding: 10px 12px;
  font-size: 11px; line-height: 1.6; color: var(--text2);
  white-space: pre-wrap; word-break: break-word; overflow-x: auto;
}}

/* ── Sidecar ────────────────────────────────────────────────── */
.sidecar-section {{ margin-top: 8px; font-size: 12px; }}
.sidecar-body {{ background: var(--bg3); border-radius: var(--radius); padding: 8px 10px; margin-top: 4px; color: var(--text2); white-space: pre-wrap; font-family: monospace; }}

/* ── Buttons ────────────────────────────────────────────────── */
.btn-xs {{
  padding: 2px 8px; font-size: 11px; border-radius: 4px;
  background: var(--bg3); border: 1px solid var(--border);
  color: var(--text2); cursor: pointer; white-space: nowrap;
}}
.btn-xs:hover {{ background: var(--bg4); color: var(--text); }}
.btn-sidebar-toggle {{
  position: fixed; top: 12px; left: 12px;
  background: var(--bg3); border: 1px solid var(--border);
  color: var(--text2); border-radius: var(--radius);
  padding: 5px 8px; cursor: pointer; font-size: 16px;
  z-index: 200; display: none;
}}
.btn-show-more {{
  display: inline-block; margin-top: 4px; font-size: 11px;
  background: none; border: 1px solid var(--border);
  border-radius: 3px; color: var(--text3); cursor: pointer; padding: 2px 8px;
}}
.btn-show-more:hover {{ color: var(--text); border-color: var(--text2); }}

/* ── Highlight search match ─────────────────────────────────── */
.search-match {{ background: rgba(88, 166, 255, 0.2); border-radius: 2px; }}

/* ── Knowledge Graph Panel ──────────────────────────────────── */
.kg-overlay {{ position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.75);
  z-index: 9999; display: none; align-items: center; justify-content: center; }}
.kg-overlay.active {{ display: flex; }}
.kg-panel {{ background: var(--bg); border: 1px solid var(--border); border-radius: 6px;
  width: 90%; height: 90%; max-width: 1400px; max-height: 900px; display: flex; flex-direction: column;
  box-shadow: 0 8px 32px rgba(0,0,0,0.5); }}
.kg-header {{ padding: 16px 20px; border-bottom: 1px solid var(--border); display: flex;
  justify-content: space-between; align-items: center; }}
.kg-title {{ font-size: 16px; font-weight: 600; }}
.kg-body {{ flex: 1; position: relative; overflow: hidden; }}
.kg-svg {{ width: 100%; height: 100%; }}
.kg-node {{ cursor: pointer; }}
.kg-node circle {{ fill: var(--bg3); stroke: var(--text2); stroke-width: 1.5px; transition: all 0.2s; }}
.kg-node:hover circle {{ fill: var(--text2); stroke: var(--text); stroke-width: 2px; }}
.kg-node text {{ font-size: 10px; fill: var(--text); pointer-events: none; }}
.kg-link {{ stroke: var(--text3); stroke-opacity: 0.3; stroke-width: 1px; }}

/* ── Footer ─────────────────────────────────────────────────── */
.footer {{ text-align: center; padding: 32px; color: var(--text3); font-size: 11px; margin-top: 24px; border-top: 1px solid var(--border); }}

/* ── Scrollbar ──────────────────────────────────────────────── */
::-webkit-scrollbar {{ width: 6px; height: 6px; }}
::-webkit-scrollbar-track {{ background: var(--bg); }}
::-webkit-scrollbar-thumb {{ background: var(--bg4); border-radius: 3px; }}
::-webkit-scrollbar-thumb:hover {{ background: var(--text3); }}
</style>
</head>
<body>

<!-- Top bar -->
<header class="topbar">
  <button class="btn-xs" id="sidebar-toggle-btn" onclick="toggleSidebar()" title="Toggle sidebar">☰</button>
  <div class="topbar-title">{_h(title)}</div>
  <div class="topbar-subtitle">{_h(subtitle)}</div>
  <div class="topbar-controls">
    <input type="text" id="search-input" placeholder="Search commits…" oninput="applyFilters()">
    <div class="topbar-count"><strong id="visible-count">56</strong> / <span id="total-count">56</span> commits</div>
    <button class="btn-xs" onclick="expandAll()">Expand All</button>
    <button class="btn-xs" onclick="collapseAll()">Collapse All</button>
    <button class="btn-xs" onclick="resetFilters()">Reset Filters</button>
    <button class="btn-xs" onclick="toggleKG()" id="kg-btn" style="display:none;">📊 Knowledge Graph</button>
  </div>
</header>

<!-- Sidebar -->
<aside class="sidebar" id="sidebar">
  <div class="sidebar-section">
    <div class="sidebar-heading">
      Sort
    </div>
    <select class="sort-select" id="sort-select" onchange="applySort()">
      <option value="chrono">Chronological (oldest first)</option>
      <option value="reverse">Reverse chronological</option>
      <option value="files_desc">Most files changed</option>
      <option value="phase">By phase</option>
    </select>
  </div>
  <hr class="sidebar-divider">
  <div class="sidebar-section">
    <div class="sidebar-heading">
      Date Range
    </div>
    <div class="date-range">
      <label>From <input type="date" id="date-from" onchange="applyFilters()"></label>
      <label>Until <input type="date" id="date-until" onchange="applyFilters()"></label>
    </div>
  </div>
  <hr class="sidebar-divider">
  <div class="sidebar-section">
    <div class="sidebar-heading">
      Filter <button onclick="selectAll()">all</button> <button onclick="selectNone()">none</button>
    </div>
    {phase_checkboxes_html}
    {marker_checkboxes}
    {type_checkboxes}
    {feature_type_checkboxes}
    {domain_checkboxes}
    {arch_checkboxes}
  </div>
</aside>

<!-- Main content -->
<main class="main" id="main">
  {body_html}
  <div class="no-results" id="no-results">No commits match the current filters.</div>
</main>

<footer class="footer">Generated {_h(generated_at)} · spine.tools.changelog</footer>

<!-- Knowledge Graph Overlay -->
<div class="kg-overlay" id="kg-overlay" onclick="if(event.target===this) toggleKG()">
  <div class="kg-panel">
    <div class="kg-header">
      <div class="kg-title">Module Dependency Graph</div>
      <button class="btn-xs" onclick="toggleKG()">✕ Close</button>
    </div>
    <div class="kg-body">
      <svg class="kg-svg" id="kg-svg"></svg>
    </div>
  </div>
</div>

<script src="https://d3js.org/d3.v7.min.js"></script>
<script>
// ── Data ─────────────────────────────────────────────────────────────────────
const COMMITS = {commits_json};
const KG_DATA = {kg_json};
const totalCount = COMMITS.length;
document.getElementById('total-count').textContent = totalCount;

// Show KG button if data available
if (KG_DATA && KG_DATA.nodes && KG_DATA.nodes.length > 0) {{
  document.getElementById('kg-btn').style.display = 'inline-block';
}}

// ── Sidebar toggle ────────────────────────────────────────────────────────────
function toggleSidebar() {{
  const sb = document.getElementById('sidebar');
  const main = document.getElementById('main');
  sb.classList.toggle('collapsed');
  main.classList.toggle('sidebar-collapsed');
}}

// ── Phase expand/collapse ─────────────────────────────────────────────────────
function togglePhase(num) {{
  const body = document.getElementById('phase-body-' + num);
  const chev = document.getElementById('chev-' + num);
  const collapsed = body.classList.toggle('collapsed');
  chev.classList.toggle('collapsed', collapsed);
}}
function expandPhase(num) {{
  document.querySelectorAll('#phase-body-' + num + ' .commit-detail').forEach(el => {{
    el.classList.remove('collapsed');
  }});
  document.querySelectorAll('#phase-body-' + num + ' .commit-chevron').forEach(el => {{
    el.classList.remove('collapsed');
  }});
}}
function collapsePhase(num) {{
  document.querySelectorAll('#phase-body-' + num + ' .commit-detail').forEach(el => {{
    el.classList.add('collapsed');
  }});
  document.querySelectorAll('#phase-body-' + num + ' .commit-chevron').forEach(el => {{
    el.classList.add('collapsed');
  }});
}}

// ── Commit expand/collapse ────────────────────────────────────────────────────
function toggleCommit(sha) {{
  const detail = document.getElementById('detail-' + sha);
  const chev = document.getElementById('commit-chev-' + sha);
  const collapsed = detail.classList.toggle('collapsed');
  chev.classList.toggle('collapsed', collapsed);
}}

// ── Accordion sections ────────────────────────────────────────────────────────
function toggleEl(id) {{
  const el = document.getElementById(id);
  const chev = document.getElementById('acc-chev-' + id);
  const collapsed = el.classList.toggle('collapsed');
  if (chev) chev.classList.toggle('collapsed', collapsed);
}}

// ── Show more docstring lines ─────────────────────────────────────────────────
function toggleDsRest(id, btn) {{
  const el = document.getElementById(id);
  if (!el) return;
  const showing = el.style.display !== 'none';
  el.style.display = showing ? 'none' : 'block';
  btn.textContent = showing ? btn.textContent.replace('− ', '+ ') : btn.textContent.replace('+ ', '− ');
}}

// ── Global expand all / collapse all ─────────────────────────────────────────
function expandAll() {{
  document.querySelectorAll('.commit-detail').forEach(el => el.classList.remove('collapsed'));
  document.querySelectorAll('.commit-chevron').forEach(el => el.classList.remove('collapsed'));
  document.querySelectorAll('.phase-body').forEach(el => el.classList.remove('collapsed'));
  document.querySelectorAll('.phase-chevron').forEach(el => el.classList.remove('collapsed'));
}}
function collapseAll() {{
  document.querySelectorAll('.commit-detail').forEach(el => el.classList.add('collapsed'));
  document.querySelectorAll('.commit-chevron').forEach(el => el.classList.add('collapsed'));
}}

// ── Filter logic ──────────────────────────────────────────────────────────────
function getCheckedValues(group) {{
  return [...document.querySelectorAll(`input[data-filter-group="${{group}}"]:checked`)]
    .map(el => el.dataset.filterValue);
}}

function applyFilters() {{
  const search = document.getElementById('search-input').value.toLowerCase().trim();
  const dateFrom = document.getElementById('date-from').value;
  const dateUntil = document.getElementById('date-until').value;

  const phases = getCheckedValues('phase').map(Number);
  const markers = getCheckedValues('marker');
  const types = getCheckedValues('type');
  const featureTypes = getCheckedValues('feature_type');
  const domains = getCheckedValues('domain');
  const arches = getCheckedValues('architecture');

  let visible = 0;
  for (const commit of COMMITS) {{
    const el = document.getElementById(commit.id);
    if (!el) continue;

    let show = true;

    // Phase
    if (phases.length && !phases.includes(commit.phase)) show = false;

    // Markers: if any markers are unchecked, hide commits that have those markers
    // Rule: show commit if it has NO unchecked markers (or has at least one checked)
    if (show && markers.length < document.querySelectorAll('input[data-filter-group="marker"]').length) {{
      // Some markers are unchecked — only show if ALL of commit's markers are in checked set
      if (commit.markers.length > 0 && !commit.markers.every(m => markers.includes(m))) show = false;
    }}

    // Type
    if (show && types.length && !types.includes(commit.type)) show = false;

    // Feature type
    if (show && featureTypes.length) {{
      if (commit.feature_type && !featureTypes.includes(commit.feature_type)) show = false;
    }}

    // Domain
    if (show && domains.length) {{
      if (commit.domain && !domains.includes(commit.domain)) show = false;
    }}

    // Architecture
    if (show && arches.length) {{
      if (commit.architecture && !arches.includes(commit.architecture)) show = false;
    }}

    // Date range
    if (show && dateFrom && commit.date && commit.date < dateFrom) show = false;
    if (show && dateUntil && commit.date && commit.date > dateUntil) show = false;

    // Search
    if (show && search) {{
      const haystack = (commit.subject + ' ' + commit.sha + ' ' + commit.tags.join(' ') +
        ' ' + commit.phase_name + ' ' + commit.feature_type + ' ' + commit.domain).toLowerCase();
      if (!haystack.includes(search)) show = false;
    }}

    el.classList.toggle('hidden', !show);
    if (show) visible++;
  }}

  document.getElementById('visible-count').textContent = visible;
  document.getElementById('no-results').style.display = visible === 0 ? 'block' : 'none';

  // Hide phases that have no visible commits
  document.querySelectorAll('.phase-section').forEach(section => {{
    const phaseNum = Number(section.dataset.phase);
    const anyVisible = [...section.querySelectorAll('.commit-card')]
      .some(c => !c.classList.contains('hidden'));
    section.style.display = anyVisible ? '' : 'none';
  }});
}}

// ── Sort logic ────────────────────────────────────────────────────────────────
function applySort() {{
  const mode = document.getElementById('sort-select').value;
  // Sort within each phase body
  document.querySelectorAll('.phase-body').forEach(body => {{
    const cards = [...body.querySelectorAll(':scope > .commit-card')];
    cards.sort((a, b) => {{
      const ca = COMMITS.find(c => c.id === a.id);
      const cb = COMMITS.find(c => c.id === b.id);
      if (!ca || !cb) return 0;
      if (mode === 'reverse') return (cb.date || '').localeCompare(ca.date || '');
      if (mode === 'files_desc') return cb.file_count - ca.file_count;
      if (mode === 'phase') return ca.phase - cb.phase || ca.num - cb.num;
      return ca.num - cb.num; // chrono default
    }});
    cards.forEach(c => body.appendChild(c));
  }});
}}

// ── Select all / none ─────────────────────────────────────────────────────────
function selectAll() {{
  document.querySelectorAll('.sidebar input[type="checkbox"]').forEach(cb => {{ cb.checked = true; }});
  applyFilters();
}}
function selectNone() {{
  document.querySelectorAll('.sidebar input[type="checkbox"]').forEach(cb => {{ cb.checked = false; }});
  applyFilters();
}}
function resetFilters() {{
  selectAll();
  document.getElementById('search-input').value = '';
  document.getElementById('date-from').value = '';
  document.getElementById('date-until').value = '';
  document.getElementById('sort-select').value = 'chrono';
  applyFilters();
  applySort();
}}

// ── Knowledge Graph ───────────────────────────────────────────────────────────
function toggleKG() {{
  document.getElementById('kg-overlay').classList.toggle('active');
  if (document.getElementById('kg-overlay').classList.contains('active') && !window.kgRendered) {{
    renderKG();
    window.kgRendered = true;
  }}
}}

function renderKG() {{
  if (!KG_DATA || !KG_DATA.nodes || KG_DATA.nodes.length === 0) return;

  const svg = d3.select('#kg-svg');
  const width = svg.node().getBoundingClientRect().width;
  const height = svg.node().getBoundingClientRect().height;

  svg.selectAll('*').remove();

  const g = svg.append('g');

  // Zoom behavior
  const zoom = d3.zoom()
    .scaleExtent([0.1, 4])
    .on('zoom', (event) => {{
      g.attr('transform', event.transform);
    }});
  svg.call(zoom);

  // Force simulation
  const simulation = d3.forceSimulation(KG_DATA.nodes)
    .force('link', d3.forceLink(KG_DATA.links).id(d => d.id).distance(100))
    .force('charge', d3.forceManyBody().strength(-300))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('collision', d3.forceCollide().radius(30));

  // Links
  const link = g.append('g')
    .selectAll('line')
    .data(KG_DATA.links)
    .join('line')
    .attr('class', 'kg-link');

  // Nodes
  const node = g.append('g')
    .selectAll('g')
    .data(KG_DATA.nodes)
    .join('g')
    .attr('class', 'kg-node')
    .call(d3.drag()
      .on('start', dragstarted)
      .on('drag', dragged)
      .on('end', dragended));

  node.append('circle')
    .attr('r', 8);

  node.append('text')
    .text(d => d.label.split('.').pop())
    .attr('x', 12)
    .attr('y', 3);

  node.append('title')
    .text(d => d.label);

  // Update positions
  simulation.on('tick', () => {{
    link
      .attr('x1', d => d.source.x)
      .attr('y1', d => d.source.y)
      .attr('x2', d => d.target.x)
      .attr('y2', d => d.target.y);

    node.attr('transform', d => `translate(${{d.x}},${{d.y}})`);
  }});

  function dragstarted(event) {{
    if (!event.active) simulation.alphaTarget(0.3).restart();
    event.subject.fx = event.subject.x;
    event.subject.fy = event.subject.y;
  }}

  function dragged(event) {{
    event.subject.fx = event.x;
    event.subject.fy = event.y;
  }}

  function dragended(event) {{
    if (!event.active) simulation.alphaTarget(0);
    event.subject.fx = null;
    event.subject.fy = null;
  }}
}}

// ── Init ──────────────────────────────────────────────────────────────────────
// Start with all commit details collapsed for performance
document.querySelectorAll('.commit-detail').forEach(el => {{
  el.classList.add('collapsed');
}});
document.querySelectorAll('.commit-chevron').forEach(el => {{
  el.classList.add('collapsed');
}});
applyFilters();
</script>
</body>
</html>"""
