"""
Lightweight legal knowledge graph built on NetworkX.

WHY: A flat vector store knows "Article 21 is about life and liberty" but
doesn't know "Article 21A was added by the 86th Amendment" or that
"DPSP in Part IV relates to Article 37". A graph adds these explicit
*relationships* so the RAG pipeline can traverse them (e.g. when asked
about an amendment, it can jump to the original article automatically).

WHAT THIS GRAPH STORES:
  Nodes:
    - Article / Section / Rule / Chapter  (node_type="provision")
    - Act / Document                       (node_type="document")
    - Constitutional Concept               (node_type="concept")
    - Amendment                            (node_type="amendment")

  Edges (relationship types):
    - "part_of"      — Article 21 is part_of Constitution
    - "amended_by"   — Article 21 amended_by 44th Amendment
    - "related_to"   — DPSP related_to Fundamental Rights
    - "enables"      — Article 32 enables enforcement of Fundamental Rights
    - "repealed_by"  — (for deleted provisions)
    - "co-occurs"    — derived from co-citation in retrieved documents

USAGE:
  from app.nlp.knowledge_graph import get_graph, get_related_provisions
  graph = get_graph()
  related = get_related_provisions("Article", "21")

The graph is built once from MongoDB chunk metadata and persisted as a pickle
to storage/knowledge_graph.pkl for instant load on subsequent starts.
"""
import logging
import os
import pickle
from typing import List, Dict, Optional, Set

logger = logging.getLogger("doj_rag.knowledge_graph")

# NetworkX is imported lazily so the module loads even if nx isn't installed
_nx = None

def _import_nx():
    global _nx
    if _nx is None:
        try:
            import networkx as nx
            _nx = nx
        except ImportError:
            raise ImportError(
                "NetworkX is required for the knowledge graph. "
                "Install it: pip install networkx"
            )
    return _nx

# Singleton graph instance
_graph = None


# ─── Pre-defined legal relationships ─────────────────────────────────────────
# These are hard-coded constitutional relationships derived from authoritative
# sources. Auto-building from documents alone misses many of these because
# they're implied rather than explicitly stated in each article's text.

KNOWN_RELATIONSHIPS = [
    # Part III - Fundamental Rights cluster
    ("Article", "12", "part_of", "Concept", "Fundamental Rights"),
    ("Article", "13", "part_of", "Concept", "Fundamental Rights"),
    ("Article", "14", "part_of", "Concept", "Fundamental Rights"),
    ("Article", "15", "part_of", "Concept", "Fundamental Rights"),
    ("Article", "16", "part_of", "Concept", "Fundamental Rights"),
    ("Article", "17", "part_of", "Concept", "Fundamental Rights"),
    ("Article", "18", "part_of", "Concept", "Fundamental Rights"),
    ("Article", "19", "part_of", "Concept", "Fundamental Rights"),
    ("Article", "20", "part_of", "Concept", "Fundamental Rights"),
    ("Article", "21", "part_of", "Concept", "Fundamental Rights"),
    ("Article", "21A", "part_of", "Concept", "Fundamental Rights"),
    ("Article", "22", "part_of", "Concept", "Fundamental Rights"),
    ("Article", "23", "part_of", "Concept", "Fundamental Rights"),
    ("Article", "24", "part_of", "Concept", "Fundamental Rights"),
    ("Article", "25", "part_of", "Concept", "Fundamental Rights"),
    ("Article", "26", "part_of", "Concept", "Fundamental Rights"),
    ("Article", "32", "part_of", "Concept", "Fundamental Rights"),

    # Article 32 enables enforcement of all FRs
    ("Article", "32", "enables", "Concept", "Fundamental Rights"),
    ("Article", "226", "enables", "Concept", "Fundamental Rights"),

    # Part IV - DPSP cluster
    ("Article", "36", "part_of", "Concept", "Directive Principles"),
    ("Article", "37", "part_of", "Concept", "Directive Principles"),
    ("Article", "38", "part_of", "Concept", "Directive Principles"),
    ("Article", "39", "part_of", "Concept", "Directive Principles"),
    ("Article", "44", "part_of", "Concept", "Directive Principles"),

    # DPSP related to FRs (tension and interplay)
    ("Concept", "Directive Principles", "related_to", "Concept", "Fundamental Rights"),

    # Amendments
    ("Article", "21A", "amended_by", "Amendment", "86th Amendment 2002"),
    ("Article", "14", "related_to", "Article", "21"),
    ("Article", "19", "related_to", "Article", "21"),
    ("Article", "14", "related_to", "Article", "19"),
    ("Article", "21", "related_to", "Article", "14"),
    ("Article", "21", "related_to", "Article", "19"),

    # Article 21 sub-rights
    ("Article", "21", "enables", "Concept", "Right to Life"),
    ("Article", "21", "enables", "Concept", "Right to Privacy"),
    ("Article", "21", "enables", "Concept", "Right to Education"),

    # Emergency provisions
    ("Article", "352", "part_of", "Concept", "Emergency Provisions"),
    ("Article", "356", "part_of", "Concept", "Emergency Provisions"),
    ("Article", "360", "part_of", "Concept", "Emergency Provisions"),

    # Writs
    ("Article", "32", "enables", "Concept", "Habeas Corpus"),
    ("Article", "32", "enables", "Concept", "Mandamus"),
    ("Article", "32", "enables", "Concept", "Certiorari"),
    ("Article", "32", "enables", "Concept", "Prohibition"),
    ("Article", "32", "enables", "Concept", "Quo Warranto"),
    ("Article", "226", "enables", "Concept", "Habeas Corpus"),
    ("Article", "226", "enables", "Concept", "Mandamus"),

    # Part of Constitution sections
    ("Article", "14", "part_of", "Document", "Indian Constitution"),
    ("Article", "19", "part_of", "Document", "Indian Constitution"),
    ("Article", "21", "part_of", "Document", "Indian Constitution"),
    ("Article", "32", "part_of", "Document", "Indian Constitution"),
    ("Article", "356", "part_of", "Document", "Indian Constitution"),
]


def _make_node_id(node_type: str, identifier: str) -> str:
    return f"{node_type}:{identifier}"


def _build_graph_from_scratch() -> "networkx.DiGraph":
    """Builds the knowledge graph from pre-defined relationships + MongoDB metadata."""
    nx = _import_nx()
    G = nx.DiGraph()

    # Add pre-defined constitutional relationships
    for (src_type, src_id, rel, dst_type, dst_id) in KNOWN_RELATIONSHIPS:
        src_node = _make_node_id(src_type, src_id)
        dst_node = _make_node_id(dst_type, dst_id)
        G.add_node(src_node, node_type=src_type, identifier=src_id, label=f"{src_type} {src_id}")
        G.add_node(dst_node, node_type=dst_type, identifier=dst_id, label=f"{dst_type} {dst_id}")
        G.add_edge(src_node, dst_node, relation=rel)

    # Also build from MongoDB chunk co-occurrence
    try:
        from app.database.mongodb import chunks_col
        # Build article->document relationships from actual indexed data
        pipeline = [
            {"$match": {"article": {"$ne": None}, "source_type": "actual_law"}},
            {"$group": {
                "_id": {"article": "$article", "doc": "$document_name"},
                "title": {"$first": "$title"}
            }},
        ]
        for row in chunks_col().aggregate(pipeline):
            art_num = row["_id"]["article"]
            doc_name = row["_id"]["doc"] or "Unknown"
            src_node = _make_node_id("Article", art_num)
            doc_node = _make_node_id("Document", doc_name)
            if not G.has_node(src_node):
                G.add_node(src_node, node_type="Article", identifier=art_num,
                           label=f"Article {art_num}")
            if not G.has_node(doc_node):
                G.add_node(doc_node, node_type="Document", identifier=doc_name,
                           label=doc_name)
            if not G.has_edge(src_node, doc_node):
                G.add_edge(src_node, doc_node, relation="part_of")

    except Exception as e:
        logger.warning("Could not enrich knowledge graph from MongoDB: %s", e)

    logger.info("Knowledge graph built: %d nodes, %d edges", G.number_of_nodes(), G.number_of_edges())
    return G


def _load_or_build() -> "networkx.DiGraph":
    from app.config import settings
    path = settings.KNOWLEDGE_GRAPH_PATH

    if os.path.exists(path):
        try:
            with open(path, "rb") as f:
                G = pickle.load(f)
            logger.info("Knowledge graph loaded from disk: %d nodes, %d edges",
                        G.number_of_nodes(), G.number_of_edges())
            return G
        except Exception as e:
            logger.warning("Could not load knowledge graph from disk (%s), rebuilding.", e)

    G = _build_graph_from_scratch()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(G, f)
        logger.info("Knowledge graph saved to %s", path)
    except Exception as e:
        logger.warning("Could not save knowledge graph: %s", e)
    return G


def get_graph():
    """Returns the singleton knowledge graph, building it on first call."""
    global _graph
    if _graph is None:
        _graph = _load_or_build()
    return _graph


def rebuild_graph():
    """Force-rebuilds and re-saves the knowledge graph (call after indexing new docs)."""
    global _graph
    _graph = _build_graph_from_scratch()
    from app.config import settings
    try:
        with open(settings.KNOWLEDGE_GRAPH_PATH, "wb") as f:
            pickle.dump(_graph, f)
        logger.info("Knowledge graph rebuilt and saved.")
    except Exception as e:
        logger.warning("Could not save rebuilt knowledge graph: %s", e)
    return _graph


def get_related_provisions(node_type: str, identifier: str,
                            max_hops: int = 2, max_results: int = 8) -> List[Dict]:
    """
    Returns a list of provisions related to the given node within max_hops.
    Used to augment retrieval — when Article 21 is retrieved, we also surface
    Article 14 and Article 19 as related provisions.

    Returns list of dicts: {node_type, identifier, label, relation, distance}
    """
    G = get_graph()
    nx = _import_nx()

    src_node = _make_node_id(node_type, identifier)
    if src_node not in G:
        return []

    results = []
    visited: Set[str] = {src_node}

    # BFS up to max_hops
    current_level = [(src_node, None, 0)]
    while current_level:
        next_level = []
        for node, via_relation, dist in current_level:
            if dist >= max_hops:
                continue
            for neighbor in list(G.successors(node)) + list(G.predecessors(node)):
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                edge_data = G.get_edge_data(node, neighbor) or G.get_edge_data(neighbor, node) or {}
                relation = edge_data.get("relation", "related_to")
                ndata = G.nodes[neighbor]
                results.append({
                    "node_type": ndata.get("node_type", ""),
                    "identifier": ndata.get("identifier", ""),
                    "label": ndata.get("label", neighbor),
                    "relation": relation,
                    "distance": dist + 1,
                })
                next_level.append((neighbor, relation, dist + 1))
        current_level = next_level

    # Sort by distance then by type (Articles first)
    results.sort(key=lambda x: (x["distance"], 0 if x["node_type"] == "Article" else 1))
    return results[:max_results]


def get_graph_summary() -> Dict:
    """Returns a summary dict for the /api/graph/summary endpoint."""
    G = get_graph()
    nx = _import_nx()
    return {
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "node_types": dict(
            nx.get_node_attributes(G, "node_type")
        ),
        "relation_types": list({
            d.get("relation") for _, _, d in G.edges(data=True) if d.get("relation")
        }),
    }


def get_full_graph_data(limit_nodes: int = 150) -> Dict:
    """Returns formatted node and edge dictionaries for interactive visualization."""
    G = get_graph()
    nodes = []
    edges = []
    
    selected_nodes = set(list(G.nodes)[:limit_nodes])
    for n in selected_nodes:
        data = G.nodes[n]
        nodes.append({
            "id": n,
            "label": data.get("label", n),
            "node_type": data.get("node_type", "Provisions"),
            "identifier": data.get("identifier", ""),
            "degree": G.degree(n)
        })
        
    for u, v, data in G.edges(data=True):
        if u in selected_nodes and v in selected_nodes:
            edges.append({
                "source": u,
                "target": v,
                "relation": data.get("relation", "related_to")
            })
            
    return {"nodes": nodes, "edges": edges}
