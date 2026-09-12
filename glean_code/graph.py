"""A knowledge graph over a set of search results.

Glean's Client API has no graph endpoint, so the graph is synthesised from
what a search response already carries: the author, datasource and container
of every result, plus the language of its title and snippets. That keeps one
code path for mock, local and live — the same fields come back from all three
— and it keeps the claim honest: this is the graph of one query's result set,
not a crawl of the whole index.

Four kinds of node, and every edge carries the evidence that produced it:

    doc         a document in the result set
    person      an author
    source      a datasource
    container   a folder, channel or space

    authored_by   doc -> person     the author on the result
    in_source     doc -> source     the datasource it came from
    in_container  doc -> container  the space it lives in
    shares_term   doc <-> doc       vocabulary shared by two documents,
                                    weighted by how rare it is in the set

Rendered two ways: a terminal summary (hubs, clusters, strongest links) and a
self-contained HTML page with a force-directed layout — no CDN, no framework,
no network, matching flow.render_timeline.
"""

from __future__ import annotations

import html
import json
import math
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# Words too common to say anything about how two documents relate.
STOPWORDS = frozenset("""
about above after again against alone along already also although always among
another around because been before being below between both came come could
does doing done down during each either else enough even ever every from
further gave give given goes going gone have having here hers herself himself
however into itself just last later least less like made make many maybe mean
might more most much must myself never next none nothing once only onto other
ought ours ourselves over rather really same seem seen several shall should
since some such take taken than that their them themselves then there these
they this those though through thus together took toward under until upon used
uses using very want wants well were what when where which while whom whose
will with within without would your yours yourself
""".split())

TERM_RE = re.compile(r"[a-z][a-z0-9_.\-]{3,}")

NODE_KINDS = ("doc", "person", "source", "container")
EDGE_KINDS = ("authored_by", "in_source", "in_container", "shares_term")

DEFAULT_MIN_SHARED = 2
DEFAULT_MAX_TERM_SHARE = 0.6  # a term in more than this share of docs says nothing


# --------------------------------------------------------------------------
# building
# --------------------------------------------------------------------------

def _text_of(result: Dict[str, Any]) -> str:
    parts = [str(result.get("title") or "")]
    for snippet in result.get("snippets") or []:
        parts.append(str(snippet.get("text") or ""))
    return " ".join(parts)


def _terms(text: str) -> set:
    return {t for t in TERM_RE.findall(text.lower()) if t not in STOPWORDS}


def _author_of(result: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """(email, display name) for a result, from wherever the shape carries it."""
    meta = result.get("metadata") or {}
    author = meta.get("author") or result.get("author")
    if isinstance(author, dict):
        email = author.get("email") or author.get("id")
        return email, (author.get("name") or email)
    if isinstance(author, str) and author:
        return author, author
    return None, None


def build(results: Sequence[Dict[str, Any]], query: str = "",
          source_label: str = "", min_shared: int = DEFAULT_MIN_SHARED,
          with_terms: bool = True) -> Dict[str, Any]:
    """Turn search results into nodes and edges."""
    nodes: Dict[str, Dict[str, Any]] = {}
    edges: List[Dict[str, Any]] = []

    def node(node_id: str, kind: str, label: str, **meta) -> str:
        existing = nodes.get(node_id)
        if existing is None:
            nodes[node_id] = {"id": node_id, "kind": kind, "label": label, "meta": meta}
        elif meta:
            existing["meta"].update({k: v for k, v in meta.items() if v})
        return node_id

    def edge(a: str, b: str, kind: str, score: float, why: str) -> None:
        edges.append({"a": a, "b": b, "kind": kind, "score": round(float(score), 3), "why": why})

    doc_terms: Dict[str, set] = {}

    for result in results:
        raw_id = str(result.get("id") or result.get("url") or result.get("title") or "")
        if not raw_id:
            continue
        doc = node(
            "doc:" + raw_id, "doc", str(result.get("title") or raw_id),
            url=result.get("url") or "",
            datasource=str(result.get("datasource") or (result.get("metadata") or {}).get("datasource") or ""),
            doc_type=str((result.get("metadata") or {}).get("documentType") or ""),
            updated=str((result.get("metadata") or {}).get("updatedAgo") or ""),
        )

        email, name = _author_of(result)
        if email:
            person = node("person:" + email, "person", name or email, email=email)
            edge(doc, person, "authored_by", 1.0, "author of this document")

        datasource = nodes[doc]["meta"].get("datasource")
        if datasource:
            source = node("source:" + datasource, "source", datasource)
            edge(doc, source, "in_source", 0.5, "indexed from " + datasource)

        container = str((result.get("metadata") or {}).get("container") or "")
        if container:
            key = "container:" + (datasource or "") + "/" + container
            box = node(key, "container", container, datasource=datasource or "")
            edge(doc, box, "in_container", 0.8, "lives in " + container)

        if with_terms:
            doc_terms[doc] = _terms(_text_of(result))

    if with_terms and len(doc_terms) > 1:
        edges.extend(_term_edges(doc_terms, min_shared))

    return {
        "query": query,
        "source": source_label,
        "nodes": sorted(nodes.values(), key=lambda n: (NODE_KINDS.index(n["kind"]), n["label"].lower())),
        "edges": edges,
    }


def _term_edges(doc_terms: Dict[str, set], min_shared: int) -> List[Dict[str, Any]]:
    """doc <-> doc edges for shared vocabulary, weighted by rarity.

    A term carried by most of the result set is usually the query itself, so it
    is dropped before scoring — what is left is what actually distinguishes one
    pair of documents from the rest.
    """
    total = len(doc_terms)
    counts: Dict[str, int] = {}
    for terms in doc_terms.values():
        for term in terms:
            counts[term] = counts.get(term, 0) + 1

    ceiling = max(2, int(total * DEFAULT_MAX_TERM_SHARE))
    weight = {
        term: math.log(total / count)
        for term, count in counts.items()
        # count == total gives log(1) == 0: shared by everything, so it
        # distinguishes nothing and must not draw a zero-weight edge
        if 1 < count <= ceiling and count < total
    }

    out: List[Dict[str, Any]] = []
    ids = sorted(doc_terms)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            shared = doc_terms[a] & doc_terms[b] & weight.keys()
            if len(shared) < min_shared:
                continue
            ranked = sorted(shared, key=lambda t: (-weight[t], t))
            score = sum(weight[t] for t in ranked)
            if score <= 0:
                continue
            out.append({
                "a": a, "b": b, "kind": "shares_term",
                "score": round(score, 3),
                "why": ", ".join(ranked[:4]),
            })
    out.sort(key=lambda e: -e["score"])
    return out


# --------------------------------------------------------------------------
# reading it
# --------------------------------------------------------------------------

def _degrees(graph: Dict[str, Any]) -> Dict[str, int]:
    degrees = {n["id"]: 0 for n in graph["nodes"]}
    for e in graph["edges"]:
        if e["a"] in degrees:
            degrees[e["a"]] += 1
        if e["b"] in degrees:
            degrees[e["b"]] += 1
    return degrees


def _clusters(graph: Dict[str, Any]) -> List[List[str]]:
    parent = {n["id"]: n["id"] for n in graph["nodes"]}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for e in graph["edges"]:
        a, b = e["a"], e["b"]
        if a in parent and b in parent:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

    groups: Dict[str, List[str]] = {}
    for node_id in parent:
        groups.setdefault(find(node_id), []).append(node_id)
    return sorted(groups.values(), key=len, reverse=True)


def summarize(graph: Dict[str, Any], hubs: int = 6, links: int = 4) -> Dict[str, Any]:
    by_kind = {kind: 0 for kind in NODE_KINDS}
    for n in graph["nodes"]:
        by_kind[n["kind"]] = by_kind.get(n["kind"], 0) + 1
    edge_kinds = {kind: 0 for kind in EDGE_KINDS}
    for e in graph["edges"]:
        edge_kinds[e["kind"]] = edge_kinds.get(e["kind"], 0) + 1

    degrees = _degrees(graph)
    labels = {n["id"]: n for n in graph["nodes"]}
    ranked = sorted(graph["nodes"], key=lambda n: (-degrees[n["id"]], n["label"].lower()))

    groups = _clusters(graph)
    described = []
    for group in groups:
        anchor = max(group, key=lambda i: (degrees[i], labels[i]["label"]))
        described.append({"size": len(group), "anchor": labels[anchor]["label"],
                          "anchor_kind": labels[anchor]["kind"]})

    strongest = [e for e in graph["edges"] if e["kind"] == "shares_term"][:links]
    return {
        "nodes": len(graph["nodes"]),
        "edges": len(graph["edges"]),
        "by_kind": by_kind,
        "edge_kinds": edge_kinds,
        "hubs": [{"label": n["label"], "kind": n["kind"], "degree": degrees[n["id"]]}
                 for n in ranked[:hubs]],
        "clusters": described,
        "strongest": [{"a": labels[e["a"]]["label"], "b": labels[e["b"]]["label"],
                       "score": e["score"], "why": e["why"]} for e in strongest],
    }


# --------------------------------------------------------------------------
# terminal
# --------------------------------------------------------------------------

_KIND_MARK = {"doc": "▪", "person": "◆", "source": "▸", "container": "▫"}


def _fit(text: str, width: int) -> str:
    text = " ".join(str(text or "").split())
    if width <= 1 or len(text) <= width:
        return text
    return text[: max(1, width - 1)].rstrip() + "…"


def render_terminal(graph: Dict[str, Any], summary: Optional[Dict[str, Any]] = None,
                    width: int = 80) -> str:
    """Plain text; the caller styles it. Kept free of ANSI so it stays testable."""
    summary = summary or summarize(graph)
    if not graph["nodes"]:
        return "No graph: the result set was empty."

    counts = "  ·  ".join(
        "%d %s" % (summary["by_kind"][k], k if summary["by_kind"][k] != 1 else k.rstrip("s"))
        for k in NODE_KINDS if summary["by_kind"].get(k))
    edge_counts = "  ·  ".join(
        "%d %s" % (v, k) for k, v in summary["edge_kinds"].items() if v)

    lines = [
        "%d nodes   %s" % (summary["nodes"], counts),
        "%d edges   %s" % (summary["edges"], edge_counts),
        "",
        "hubs",
    ]
    for hub in summary["hubs"]:
        lines.append("  %s %-9s %s   %d edges" % (
            _KIND_MARK.get(hub["kind"], "·"), hub["kind"],
            _fit(hub["label"], max(20, width - 28)), hub["degree"]))

    if summary["clusters"]:
        lines += ["", "clusters (%d)" % len(summary["clusters"])]
        for cluster in summary["clusters"][:5]:
            lines.append("  %d nodes — anchored on %s %s" % (
                cluster["size"], cluster["anchor_kind"],
                _fit(cluster["anchor"], max(20, width - 34))))

    if summary["strongest"]:
        lines += ["", "strongest content links"]
        for link in summary["strongest"]:
            lines.append("  %s" % _fit(link["a"], width - 4))
            lines.append("    ↓ shares %s (%.1f)" % (link["why"], link["score"]))
            lines.append("  %s" % _fit(link["b"], width - 4))
            lines.append("")
        lines.pop()

    return "\n".join(lines)


# --------------------------------------------------------------------------
# html
# --------------------------------------------------------------------------

def _layout(graph: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Deterministic starting positions, so the same graph opens the same way."""
    laid = []
    rings = {"doc": 0.62, "person": 0.30, "source": 0.90, "container": 0.78}
    per_kind: Dict[str, int] = {}
    totals: Dict[str, int] = {}
    for n in graph["nodes"]:
        totals[n["kind"]] = totals.get(n["kind"], 0) + 1
    for n in graph["nodes"]:
        kind = n["kind"]
        index = per_kind.get(kind, 0)
        per_kind[kind] = index + 1
        count = max(1, totals[kind])
        angle = (2 * math.pi * index / count) + (0.7 if kind == "person" else 0.0)
        radius = rings.get(kind, 0.7)
        laid.append(dict(n, x=round(math.cos(angle) * radius, 4),
                         y=round(math.sin(angle) * radius, 4)))
    return laid


HTML_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
  :root {
    color-scheme: light dark;
    --ground: #fbfbfd; --panel: #ffffff; --ink: #1b1b23; --ink-2: #55556a;
    --ink-3: #8a8aa0; --rule: #e3e3ee;
    --doc: #343ced; --person: #be185d; --source: #0f766e; --container: #b45309;
    --edge: rgba(90, 90, 120, .35); --term: rgba(52, 60, 237, .45);
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --ground: #0e0e15; --panel: #16161f; --ink: #e9e9f1; --ink-2: #adadc0;
      --ink-3: #7e7e95; --rule: #292935;
      --doc: #8f94ff; --person: #f472b6; --source: #2dd4bf; --container: #fbbf24;
      --edge: rgba(160, 160, 200, .3); --term: rgba(143, 148, 255, .5);
    }
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--ground); color: var(--ink);
         font: 13px/1.5 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
  header { padding: 14px 18px; border-bottom: 1px solid var(--rule);
           display: flex; flex-wrap: wrap; gap: 6px 18px; align-items: baseline; }
  header h1 { margin: 0; font-size: 14px; font-weight: 600; }
  header .meta, header .counts { color: var(--ink-3); }
  header .src { color: var(--ink-2); }
  #wrap { position: relative; height: calc(100vh - 52px); }
  canvas { display: block; width: 100%; height: 100%; cursor: grab; }
  canvas.dragging { cursor: grabbing; }
  #legend, #panel, #hint { position: absolute; background: var(--panel);
    border: 1px solid var(--rule); border-radius: 8px; padding: 10px 12px; }
  #legend { left: 14px; top: 14px; }
  #legend div { display: flex; align-items: center; gap: 7px; }
  #legend i { width: 9px; height: 9px; border-radius: 50%; display: inline-block; }
  #hint { right: 14px; bottom: 14px; color: var(--ink-3); }
  #panel { right: 14px; top: 14px; width: min(330px, 46vw); max-height: 76%;
           overflow: auto; display: none; }
  #panel h2 { margin: 0 0 2px; font-size: 13px; }
  #panel .kind { color: var(--ink-3); margin-bottom: 8px; }
  #panel a { color: var(--doc); word-break: break-all; }
  #panel ul { margin: 8px 0 0; padding: 0; list-style: none; }
  #panel li { padding: 6px 0; border-top: 1px solid var(--rule); }
  #panel .why { color: var(--ink-2); }
  #panel .close { float: right; cursor: pointer; color: var(--ink-3);
                  border: 0; background: none; font: inherit; }
</style></head>
<body>
<header>
  <h1>__HEADING__</h1>
  <span class="src">__SOURCE__</span>
  <span class="counts">__COUNTS__</span>
  <span class="meta">click a node for its edges · drag to move · scroll to zoom</span>
</header>
<div id="wrap">
  <canvas id="c"></canvas>
  <div id="legend"></div>
  <div id="panel"></div>
  <div id="hint">shares_term edges are drawn thicker the more distinctive the shared words</div>
</div>
<script id="data" type="application/json">__DATA__</script>
<script>
(function () {
  var G = JSON.parse(document.getElementById("data").textContent);
  var nodes = G.nodes, edges = G.edges;
  var byId = {}; nodes.forEach(function (n) { byId[n.id] = n; });
  var deg = {}; nodes.forEach(function (n) { deg[n.id] = 0; });
  edges.forEach(function (e) { deg[e.a]++; deg[e.b]++; });

  var css = getComputedStyle(document.documentElement);
  function colour(kind) { return css.getPropertyValue("--" + kind).trim() || "#888"; }
  var KINDS = ["doc", "person", "source", "container"];
  var legend = document.getElementById("legend");
  legend.innerHTML = KINDS.map(function (k) {
    var n = nodes.filter(function (x) { return x.kind === k; }).length;
    return n ? '<div><i style="background:' + colour(k) + '"></i>' + k + ' <span style="color:var(--ink-3)">' + n + '</span></div>' : "";
  }).join("");

  var canvas = document.getElementById("c"), ctx = canvas.getContext("2d");
  var view = { x: 0, y: 0, k: 1 }, dpr = Math.min(window.devicePixelRatio || 1, 2);
  var W = 0, H = 0;

  function resize() {
    W = canvas.clientWidth; H = canvas.clientHeight;
    canvas.width = W * dpr; canvas.height = H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    draw();
  }

  // positions arrive laid out on rings; scale them into the viewport
  var scale = 0;
  function seed() {
    scale = Math.min(W, H) * 0.42;
    nodes.forEach(function (n) {
      n.px = n.x * scale + W / 2; n.py = n.y * scale + H / 2;
      n.vx = 0; n.vy = 0;
    });
  }

  var REST = { authored_by: 70, in_source: 130, in_container: 95, shares_term: 110 };
  function tick(alpha) {
    for (var i = 0; i < nodes.length; i++) {
      var a = nodes[i];
      for (var j = i + 1; j < nodes.length; j++) {
        var b = nodes[j], dx = b.px - a.px, dy = b.py - a.py;
        var d2 = dx * dx + dy * dy || 0.01, d = Math.sqrt(d2);
        var push = Math.min(1800 / d2, 3) * alpha;
        var ux = dx / d, uy = dy / d;
        a.vx -= ux * push; a.vy -= uy * push;
        b.vx += ux * push; b.vy += uy * push;
      }
    }
    edges.forEach(function (e) {
      var a = byId[e.a], b = byId[e.b];
      if (!a || !b) return;
      var dx = b.px - a.px, dy = b.py - a.py, d = Math.sqrt(dx * dx + dy * dy) || 0.01;
      var rest = REST[e.kind] || 100;
      var pull = ((d - rest) / d) * 0.06 * alpha;
      a.vx += dx * pull; a.vy += dy * pull;
      b.vx -= dx * pull; b.vy -= dy * pull;
    });
    nodes.forEach(function (n) {
      if (n === dragging) return;
      n.vx += (W / 2 - n.px) * 0.0016 * alpha;
      n.vy += (H / 2 - n.py) * 0.0016 * alpha;
      n.px += (n.vx *= 0.82); n.py += (n.vy *= 0.82);
    });
  }

  function radius(n) { return 4 + Math.min(9, Math.sqrt(deg[n.id] || 0) * 3); }

  function draw() {
    ctx.clearRect(0, 0, W, H);
    ctx.save();
    ctx.translate(view.x, view.y); ctx.scale(view.k, view.k);
    var maxTerm = 1;
    edges.forEach(function (e) { if (e.kind === "shares_term") maxTerm = Math.max(maxTerm, e.score); });
    edges.forEach(function (e) {
      var a = byId[e.a], b = byId[e.b];
      if (!a || !b) return;
      ctx.beginPath();
      ctx.moveTo(a.px, a.py); ctx.lineTo(b.px, b.py);
      if (e.kind === "shares_term") {
        ctx.strokeStyle = css.getPropertyValue("--term").trim();
        ctx.lineWidth = 0.6 + 2.4 * (e.score / maxTerm);
      } else {
        ctx.strokeStyle = css.getPropertyValue("--edge").trim();
        ctx.lineWidth = e.kind === "authored_by" ? 1.2 : 0.7;
      }
      if (selected && e.a !== selected.id && e.b !== selected.id) ctx.globalAlpha = 0.25;
      ctx.stroke();
      ctx.globalAlpha = 1;
    });
    nodes.forEach(function (n) {
      var r = radius(n);
      ctx.globalAlpha = (selected && selected !== n && !adjacent(selected, n)) ? 0.35 : 1;
      ctx.beginPath(); ctx.arc(n.px, n.py, r, 0, Math.PI * 2);
      ctx.fillStyle = colour(n.kind); ctx.fill();
      if (selected === n) {
        ctx.lineWidth = 2; ctx.strokeStyle = css.getPropertyValue("--ink").trim(); ctx.stroke();
      }
      if (view.k > 0.75 && (deg[n.id] > 1 || n.kind !== "doc" || selected === n)) {
        ctx.fillStyle = css.getPropertyValue("--ink-2").trim();
        ctx.font = "11px ui-monospace, Menlo, monospace";
        var label = n.label.length > 34 ? n.label.slice(0, 33) + "…" : n.label;
        ctx.fillText(label, n.px + r + 4, n.py + 3.5);
      }
      ctx.globalAlpha = 1;
    });
    ctx.restore();
  }

  function adjacent(a, b) {
    return edges.some(function (e) {
      return (e.a === a.id && e.b === b.id) || (e.b === a.id && e.a === b.id);
    });
  }

  function fit() {
    if (!nodes.length) return;
    var minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    nodes.forEach(function (n) {
      minX = Math.min(minX, n.px); maxX = Math.max(maxX, n.px);
      minY = Math.min(minY, n.py); maxY = Math.max(maxY, n.py);
    });
    var pad = 90;  // room for the labels, which sit to the right of each node
    var k = Math.min((W - pad * 2) / Math.max(1, maxX - minX),
                     (H - pad * 2) / Math.max(1, maxY - minY), 1.6);
    view.k = Math.max(0.3, k);
    view.x = (W - (maxX + minX) * view.k) / 2;
    view.y = (H - (maxY + minY) * view.k) / 2;
  }

  var selected = null, dragging = null, panning = false, last = null, alpha = 1;
  // the view tracks the graph while it relaxes, and stops the moment the
  // reader takes over -- nothing worse than a page that fights your pan
  var autofit = true;
  function loop() {
    if (autofit) fit();
    if (alpha > 0.02) { tick(alpha); alpha *= 0.985; draw(); requestAnimationFrame(loop); }
    else { draw(); }
  }

  function at(ev) {
    var rect = canvas.getBoundingClientRect();
    var x = (ev.clientX - rect.left - view.x) / view.k;
    var y = (ev.clientY - rect.top - view.y) / view.k;
    var hit = null, best = 1e9;
    nodes.forEach(function (n) {
      var d = Math.hypot(n.px - x, n.py - y), r = radius(n) + 6;
      if (d < r && d < best) { best = d; hit = n; }
    });
    return { x: x, y: y, node: hit };
  }

  // Titles, containers and evidence are tenant content, and the panel builds
  // markup from them -- so everything interpolated below is escaped, and a
  // document url is only linked when it is really http(s).
  function esc(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function safeUrl(value) {
    return /^https?:\/\//i.test(String(value || "")) ? String(value) : "";
  }

  function show(n) {
    var panel = document.getElementById("panel");
    if (!n) { panel.style.display = "none"; return; }
    var mine = edges.filter(function (e) { return e.a === n.id || e.b === n.id; })
      .sort(function (p, q) { return q.score - p.score; });
    var meta = n.meta || {};
    var bits = [];
    var url = safeUrl(meta.url);
    if (url) bits.push('<div><a href="' + esc(url) + '" target="_blank" rel="noopener">' + esc(url) + "</a></div>");
    if (meta.email) bits.push("<div>" + esc(meta.email) + "</div>");
    if (meta.doc_type) bits.push("<div>" + esc(meta.doc_type) + (meta.updated ? " · " + esc(meta.updated) : "") + "</div>");
    panel.innerHTML =
      '<button class="close" title="close">✕</button>' +
      "<h2>" + esc(n.label) + "</h2>" +
      '<div class="kind">' + esc(n.kind) + " · " + (deg[n.id] || 0) + " edges</div>" +
      bits.join("") +
      "<ul>" + mine.map(function (e) {
        var other = byId[e.a === n.id ? e.b : e.a];
        return "<li><b>" + esc(e.kind) + "</b> → " + esc(other ? other.label : "?") +
               '<div class="why">' + esc(e.why) + " (" + esc(e.score) + ")</div></li>";
      }).join("") + "</ul>";
    panel.style.display = "block";
    panel.querySelector(".close").onclick = function () { selected = null; show(null); draw(); };
  }

  canvas.addEventListener("mousedown", function (ev) {
    var hit = at(ev);
    last = { x: ev.clientX, y: ev.clientY };
    if (hit.node) { dragging = hit.node; selected = hit.node; show(hit.node); }
    else { panning = true; autofit = false; canvas.classList.add("dragging"); }
    draw();
  });
  window.addEventListener("mousemove", function (ev) {
    if (dragging) {
      var rect = canvas.getBoundingClientRect();
      dragging.px = (ev.clientX - rect.left - view.x) / view.k;
      dragging.py = (ev.clientY - rect.top - view.y) / view.k;
      dragging.vx = dragging.vy = 0; autofit = false;
      alpha = Math.max(alpha, 0.35); requestAnimationFrame(loop);
    } else if (panning) {
      view.x += ev.clientX - last.x; view.y += ev.clientY - last.y;
      last = { x: ev.clientX, y: ev.clientY }; draw();
    }
  });
  window.addEventListener("mouseup", function () {
    dragging = null; panning = false; canvas.classList.remove("dragging");
  });
  canvas.addEventListener("wheel", function (ev) {
    ev.preventDefault();
    var rect = canvas.getBoundingClientRect();
    var mx = ev.clientX - rect.left, my = ev.clientY - rect.top;
    var factor = Math.exp(-ev.deltaY * 0.0016);
    var k = Math.max(0.25, Math.min(4, view.k * factor));
    view.x = mx - (mx - view.x) * (k / view.k);
    view.y = my - (my - view.y) * (k / view.k);
    view.k = k; autofit = false; draw();
  }, { passive: false });

  window.addEventListener("resize", function () { resize(); seed(); alpha = 1; loop(); });
  resize(); seed();
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    for (var s = 0; s < 260; s++) tick(Math.pow(0.985, s));
    fit(); draw();
  } else { loop(); }
})();
</script>
</body></html>
"""


def render_html(graph: Dict[str, Any]) -> str:
    """A self-contained page. No CDN, no framework, no network."""
    summary = summarize(graph)
    query = graph.get("query") or ""
    heading = ("graph: " + query) if query else "knowledge graph"
    counts = "%d nodes · %d edges" % (summary["nodes"], summary["edges"])
    data = dict(graph, nodes=_layout(graph))
    return (HTML_TEMPLATE
            .replace("__TITLE__", html.escape(heading))
            .replace("__HEADING__", html.escape(heading))
            .replace("__SOURCE__", html.escape(graph.get("source") or ""))
            .replace("__COUNTS__", counts)
            .replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/")))


def write_html(path: Path, graph: Dict[str, Any]) -> Path:
    target = Path(path).expanduser()
    if target.parent and not target.parent.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_html(graph), encoding="utf-8")
    return target
