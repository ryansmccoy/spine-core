"""Build a knowledge graph from parsed module metadata.

Bridges spine-core's changelog extractor with entityspine's graph services.
Treats modules as entities, imports as relationships.
"""

import ast
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .model import ModuleInfo

logger = logging.getLogger(__name__)


def build_module_graph(modules: list["ModuleInfo"], src_root: Path) -> dict | None:
    """Build D3-ready knowledge graph from parsed module metadata.

    Treats each module as an entity, import statements as relationships.
    Returns a dict ready for D3 force-directed graph visualization:
    {
        "nodes": [{"id": str, "label": str, "depth": int, "group": str}, ...],
        "links": [{"source": str, "target": str, "relationship_type": str}, ...]
    }

    Args:
        modules: List of ModuleInfo from changelog scanner
        src_root: Root directory of source code (for AST parsing)

    Returns:
        D3-ready graph dict, or None if entityspine unavailable
    """
    if not modules:
        logger.warning("No modules provided to build_module_graph")
        return None

    try:
        # Import entityspine dependencies (optional)
        from entityspine import create_entity
        from entityspine.domain import RelationshipType
        from entityspine.domain.enums import EntityType
        from entityspine.services.graph_export import export_d3_json
    except ImportError as e:
        logger.warning(f"entityspine not available, skipping KG: {e}")
        return None

    entity_map: dict[str, str] = {}  # module_path → entity_id

    # Step 1: Create Entity per module
    logger.info(f"Creating entities for {len(modules)} modules")
    for mod in modules:
        try:
            entity = create_entity(
                primary_name=mod.module_path,
                entity_type=EntityType.ORGANIZATION,  # Repurpose as "Module"
                source_system="spine-changelog",
                source_id=str(mod.path),
            )
            entity_map[mod.module_path] = entity.entity_id
        except Exception as e:
            logger.warning(f"Failed to create entity for {mod.module_path}: {e}")
            continue

    if not entity_map:
        logger.warning("No entities created, aborting KG build")
        return None

    logger.debug(f"Sample entity_map keys: {list(entity_map.keys())[:5]}")

    # Step 2: Walk AST for import edges
    logger.info("Scanning for import relationships")
    import_count = 0
    imports_checked = 0
    imports_not_in_map = 0
    all_edges: list[tuple[str, str, str]] = []
    module_root = src_root.parent

    for mod in modules:
        full_path = module_root / mod.path
        if not full_path.exists():
            continue

        try:
            tree = ast.parse(full_path.read_text(encoding="utf-8"), filename=str(full_path))
        except (SyntaxError, UnicodeDecodeError, FileNotFoundError) as e:
            logger.debug(f"Could not parse {mod.path}: {e}")
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imports_checked += 1
                # Support both "from x import y" and "from . import y"
                base_target = _resolve_import(node.module or "", mod.module_path, node.level or 0)
                candidate_targets: list[str] = [base_target] if base_target else []
                for alias in node.names:
                    if alias.name != "*":
                        if base_target:
                            candidate_targets.append(f"{base_target}.{alias.name}")
                        else:
                            candidate_targets.append(alias.name)

                linked = False
                for target in candidate_targets:
                    if target in entity_map:
                        all_edges.append(
                            (
                                entity_map[mod.module_path],
                                entity_map[target],
                                RelationshipType.OTHER.value,
                            )
                        )
                        import_count += 1
                        linked = True
                        break

                if not linked:
                    imports_not_in_map += 1
                    if imports_not_in_map <= 5:  # Log first few
                        logger.debug(f"Import target not in map: {mod.module_path} imports {candidate_targets}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports_checked += 1
                    full_target = alias.name
                    top_target = alias.name.split(".")[0]
                    if full_target in entity_map:
                        all_edges.append(
                            (
                                entity_map[mod.module_path],
                                entity_map[full_target],
                                RelationshipType.OTHER.value,
                            )
                        )
                        import_count += 1
                    elif top_target in entity_map:
                        all_edges.append(
                            (
                                entity_map[mod.module_path],
                                entity_map[top_target],
                                RelationshipType.OTHER.value,
                            )
                        )
                        import_count += 1
                    else:
                        imports_not_in_map += 1

    logger.info(f"Checked {imports_checked} imports, created {import_count} relationships, {imports_not_in_map} not in map")

    # Step 3: Build EntityNetwork manually to include ALL modules (not just connected ones)
    try:
        from entityspine.domain.graph.traversal import EntityNetwork

        # Deduplicate edges while preserving order
        all_edges = list(dict.fromkeys(all_edges))

        # Build nodes dict mapping entity_id → module_path
        nodes_dict = {entity_id: module_path for module_path, entity_id in entity_map.items()}

        # Create EntityNetwork with all modules
        network = EntityNetwork(
            center_id=next(iter(entity_map.values())) if entity_map else "",
            center_name=next(iter(entity_map.keys())) if entity_map else "",
            nodes=nodes_dict,
            edges=all_edges,
            depth_map=dict.fromkeys(nodes_dict.keys(), 0),  # All at same depth
        )

        d3_data = export_d3_json(network)
        logger.info(
            f"Generated KG with {len(d3_data.get('nodes', []))} nodes, "
            f"{len(d3_data.get('links', []))} links"
        )
        return d3_data
    except Exception as e:
        logger.error(f"Failed to export D3 graph: {e}", exc_info=True)
        return None


def _resolve_import(module: str, current_module: str, level: int) -> str:
    """Resolve relative imports to absolute module paths.

    Args:
        module: Import target (e.g., "utils" or None for "from . import")
        current_module: Dotted path of importing module (e.g., "spine.tools.changelog.parser")
        level: Number of leading dots (0=absolute, 1=., 2=.., etc.)

    Returns:
        Absolute module path (e.g., "spine.tools.utils")
    """
    if level == 0:
        # Absolute import
        return module

    # Relative import: walk up the package hierarchy
    parts = current_module.split(".")
    # Remove 'level' parts from the end (module itself + parent packages)
    base_parts = parts[: -level] if level < len(parts) else []

    if module:
        return ".".join(base_parts + [module])
    else:
        # "from . import xyz" → just return parent package
        return ".".join(base_parts) if base_parts else current_module
