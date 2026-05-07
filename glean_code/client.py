"""Glean Client REST API wrapper.

Implements the surfaces documented at https://developers.glean.com for the
Client API. When no token is configured, the client returns realistic mock
responses so you can try every command offline.

Endpoints covered (all POST unless noted):
  /chat                      Chat with the Glean Assistant
  /search                    Search the Glean index
  /autocomplete              Query autocomplete
  /recommendations           Recommended results for a user
  /feedback                  Send feedback on a result or chat turn
  /agents/search             List or search agents
  /agents/runs/wait          Run an agent and wait for the final response
  /agents/runs/stream        Run an agent with streaming output
  /tools/list                List callable tools
  /tools/call                Invoke a tool
  /getdocuments              Fetch documents by id or URL
  /getdocumentpermissions    Fetch permissions for a document
  /listentities              List entities (people, teams, etc.)
  /people                    Get a person profile
  /announcements/create      Create an announcement
  /announcements/list        List announcements
  /announcements/delete      Delete an announcement
  /listcollections           List collections
  /createcollection          Create a collection
  /listpins                  List pinned results
  /createpin                 Create a pinned result
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, List, Optional

try:
    import urllib.request
    import urllib.error
except Exception:  # pragma: no cover
    urllib = None  # type: ignore

from .config import Config


class GleanError(Exception):
    pass


class GleanClient:
    def __init__(self, config: Config):
        self.config = config

    # ---------------- low level ----------------

    def _headers(self) -> Dict[str, str]:
        h = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "glean-code/0.1",
        }
        if self.config.api_token:
            h["Authorization"] = f"Bearer {self.config.api_token}"
        if self.config.act_as:
            h["X-Glean-ActAs"] = self.config.act_as
        return h

    def _post(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        if self.config.effective_mode == "mock":
            return _mock_response(path, body)

        base = self.config.effective_base_url
        if not base:
            raise GleanError("No base URL configured. Run /login or /config set instance <name>.")
        url = f"{base}{path}"
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=self._headers(), method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8")
                if not raw:
                    return {}
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            body_text = e.read().decode("utf-8", "replace")
            raise GleanError(f"HTTP {e.code} from {path}: {body_text}") from None
        except urllib.error.URLError as e:
            raise GleanError(f"Network error calling {path}: {e.reason}") from None

    # ---------------- indexing API (low level) ----------------

    def _indexing_headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "glean-code/0.1",
            "Authorization": f"Bearer {self.config.indexing_token}",
        }

    def _indexing_post(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        if not self.config.indexing_token:
            raise GleanError(
                "No indexing token set. Add one with: /config set indexing_token <token>"
            )
        base = self.config.effective_indexing_base_url
        if not base:
            raise GleanError("No instance configured for indexing API calls.")
        url = f"{base}{path}"
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, headers=self._indexing_headers(), method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            body_text = e.read().decode("utf-8", "replace")
            raise GleanError(f"HTTP {e.code} from indexing{path}: {body_text}") from None
        except urllib.error.URLError as e:
            raise GleanError(f"Network error calling indexing{path}: {e.reason}") from None

    def datasource_status(self, datasource: str) -> Dict[str, Any]:
        """POST /api/index/v1/debug/{datasource}/status — beta endpoint."""
        return self._indexing_post(f"/debug/{datasource}/status", {})

    def rotate_indexing_token(self) -> Dict[str, Any]:
        """POST /api/index/v1/rotatetoken — rotates the indexing token secret."""
        return self._indexing_post("/rotatetoken", {})

    # ---------------- chat ----------------

    def chat(self, message: str, chat_id: Optional[str] = None,
             agent: Optional[str] = None, stream: bool = False) -> Dict[str, Any]:
        body = {
            "messages": [{"author": "USER", "messageType": "CONTENT",
                          "fragments": [{"text": message}]}],
            "stream": stream,
        }
        if chat_id:
            body["chatId"] = chat_id
        if agent:
            body["agentConfig"] = {"agent": agent}
        return self._post("/chat", body)

    # ---------------- search ----------------

    def search(self, query: str, page_size: int = 10,
               datasource: Optional[str] = None,
               request_options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        body: Dict[str, Any] = {"query": query, "pageSize": page_size}
        if datasource:
            body["requestOptions"] = {"datasourceFilter": datasource}
        if request_options:
            body.setdefault("requestOptions", {}).update(request_options)
        return self._post("/search", body)

    def autocomplete(self, query: str) -> Dict[str, Any]:
        return self._post("/autocomplete", {"query": query})

    def list_datasources(self, sample_size: int = 100) -> Dict[str, Any]:
        """Derive the set of datasources the caller can see.

        The Glean Client REST API does not expose a dedicated 'list
        datasources' endpoint. This method runs a broad search and reads
        the datasource field (and facet counts when present) off the
        response, so it respects the caller's permissions.
        """
        body = {
            "query": "*",
            "pageSize": sample_size,
            "requestOptions": {"facetBucketSize": 50,
                                "facetFilters": [],
                                "facets": ["datasource"]},
        }
        resp = self._post("/search", body)

        sources: Dict[str, int] = {}
        # Prefer facet data if the server returned it
        for facet in (resp.get("facetResults") or []):
            if facet.get("sourceName") == "datasource" or facet.get("name") == "datasource":
                for b in facet.get("buckets", []):
                    name = b.get("value") or b.get("name")
                    if name:
                        sources[name] = int(b.get("count", 0))
                break
        # Fallback: count datasources seen in the result list
        if not sources:
            for r in resp.get("results", []):
                ds = r.get("datasource")
                if ds:
                    sources[ds] = sources.get(ds, 0) + 1
        return {"datasources": [{"name": k, "count": v}
                                 for k, v in sorted(sources.items(),
                                                    key=lambda x: -x[1])]}

    def recommendations(self, user: Optional[str] = None) -> Dict[str, Any]:
        body: Dict[str, Any] = {}
        if user:
            body["user"] = user
        return self._post("/recommendations", body)

    def feedback(self, tracking_token: str, rating: str,
                 comments: Optional[str] = None) -> Dict[str, Any]:
        body = {"trackingToken": tracking_token, "category": rating}
        if comments:
            body["comments"] = comments
        return self._post("/feedback", body)

    # ---------------- agents and tools ----------------

    def agents_search(self, query: Optional[str] = None) -> Dict[str, Any]:
        return self._post("/agents/search", {"query": query or ""})

    def agent_run(self, agent_id: str, input: str, stream: bool = False) -> Dict[str, Any]:
        path = "/agents/runs/stream" if stream else "/agents/runs/wait"
        return self._post(path, {"agentId": agent_id, "input": input})

    def tools_list(self) -> Dict[str, Any]:
        return self._post("/tools/list", {})

    def tools_call(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return self._post("/tools/call", {"name": name, "arguments": arguments})

    # ---------------- documents and people ----------------

    def get_documents(self, ids: Optional[List[str]] = None,
                      urls: Optional[List[str]] = None) -> Dict[str, Any]:
        body: Dict[str, Any] = {}
        if ids:
            body["documentSpecs"] = [{"id": i} for i in ids]
        elif urls:
            body["documentSpecs"] = [{"url": u} for u in urls]
        return self._post("/getdocuments", body)

    def document_permissions(self, doc_id: str) -> Dict[str, Any]:
        return self._post("/getdocumentpermissions", {"documentSpec": {"id": doc_id}})

    def list_entities(self, kind: str = "PEOPLE", page_size: int = 10,
                      query: Optional[str] = None) -> Dict[str, Any]:
        body: Dict[str, Any] = {"entityType": kind, "pageSize": page_size}
        if query:
            body["query"] = query
        return self._post("/listentities", body)

    def person(self, email: str) -> Dict[str, Any]:
        return self._post("/people", {"email": email})

    # ---------------- announcements, collections, pins ----------------

    def announcements_list(self) -> Dict[str, Any]:
        return self._post("/announcements/list", {})

    def announcement_create(self, title: str, body_text: str,
                            audience: Optional[str] = None) -> Dict[str, Any]:
        body: Dict[str, Any] = {"title": title, "body": {"text": body_text}}
        if audience:
            body["audienceFilters"] = [{"filter": audience}]
        return self._post("/announcements/create", body)

    def announcement_delete(self, ann_id: str) -> Dict[str, Any]:
        return self._post("/announcements/delete", {"id": ann_id})

    def collections_list(self) -> Dict[str, Any]:
        return self._post("/listcollections", {})

    def collection_create(self, name: str, description: Optional[str] = None) -> Dict[str, Any]:
        body: Dict[str, Any] = {"name": name}
        if description:
            body["description"] = description
        return self._post("/createcollection", body)

    def pins_list(self) -> Dict[str, Any]:
        return self._post("/listpins", {})

    def pin_create(self, url: str, query: str) -> Dict[str, Any]:
        return self._post("/createpin", {"url": url, "query": query})

    # ---------------- insights ----------------

    def insights(self, overview: bool = True, assistant: bool = False,
                 agents: bool = False, disable_per_user: bool = False,
                 locale: Optional[str] = None) -> Dict[str, Any]:
        body: Dict[str, Any] = {}
        if overview:
            body["overviewRequest"] = {}
        if assistant:
            body["assistantRequest"] = {}
        if agents:
            body["agentsRequest"] = {}
        if disable_per_user:
            body["disablePerUserInsights"] = True
        if locale:
            body["locale"] = locale
        return self._post("/insights", body)


# -------------------- mocks --------------------

def _mock_response(path: str, body: Dict[str, Any]) -> Dict[str, Any]:
    time.sleep(0.25)  # feel of a network call
    if path == "/chat":
        q = body["messages"][-1]["fragments"][0]["text"]
        return {
            "chatId": body.get("chatId") or f"chat_{uuid.uuid4().hex[:8]}",
            "messages": [{
                "author": "GLEAN_AI",
                "messageType": "CONTENT",
                "fragments": [{"text":
                    f"[mock] You asked: {q}\n\nHere is a simulated answer. Configure "
                    f"a real token with /login to hit live Glean."}],
                "citations": [
                    {"sourceDocument": {"title": "Onboarding Guide",
                                         "url": "https://example.com/onboarding"}},
                    {"sourceDocument": {"title": "Q2 Planning Doc",
                                         "url": "https://example.com/q2"}},
                ],
            }],
        }
    if path == "/search":
        q = body.get("query", "")
        n = body.get("pageSize", 10)
        wants_facets = "datasource" in (
            (body.get("requestOptions") or {}).get("facets") or []
        )
        mock_sources = ["gdrive", "slack", "confluence", "jira", "github"]
        results = [{
            "title": f"Mock result {i+1} for '{q}'",
            "url": f"https://example.com/doc/{i+1}",
            "snippets": [{"text": f"...matching snippet about {q}..."}],
            "datasource": mock_sources[i % len(mock_sources)],
            "trackingToken": f"tok_{i}",
        } for i in range(min(n, 10))]
        resp = {"results": results}
        if wants_facets:
            resp["facetResults"] = [{
                "sourceName": "datasource",
                "buckets": [
                    {"value": "gdrive",     "count": 842},
                    {"value": "slack",      "count": 611},
                    {"value": "confluence", "count": 304},
                    {"value": "jira",       "count": 187},
                    {"value": "github",     "count": 96},
                ],
            }]
        return resp
    if path == "/autocomplete":
        q = body.get("query", "")
        return {"results": [{"suggestion": f"{q} report"},
                            {"suggestion": f"{q} metrics"},
                            {"suggestion": f"{q} onboarding"}]}
    if path == "/recommendations":
        return {"results": [{"title": "Weekly digest", "url": "https://example.com/digest"}]}
    if path == "/feedback":
        return {"status": "ok"}
    if path == "/agents/search":
        return {"agents": [
            {"id": "agt_research", "name": "Research Agent",
             "description": "Deep research across company knowledge."},
            {"id": "agt_sales", "name": "Sales Assistant",
             "description": "Summarises accounts and prepares call notes."},
        ]}
    if path in ("/agents/runs/wait", "/agents/runs/stream"):
        return {"runId": f"run_{uuid.uuid4().hex[:6]}",
                "output": f"[mock agent {body.get('agentId')}] Finished task: "
                          f"{body.get('input','')[:60]}..."}
    if path == "/tools/list":
        return {"tools": [
            {"name": "search", "description": "Search the company index."},
            {"name": "create_doc", "description": "Create a new document."},
        ]}
    if path == "/tools/call":
        return {"name": body.get("name"), "result": "ok",
                "output": f"[mock tool {body.get('name')}] args={body.get('arguments')}"}
    if path == "/getdocuments":
        specs = body.get("documentSpecs", [])
        return {"documents": [{"id": s.get("id") or s.get("url"),
                                 "title": "Mock document",
                                 "url": s.get("url", "https://example.com")}
                                for s in specs]}
    if path == "/getdocumentpermissions":
        return {"permissions": [{"email": "alice@example.com", "role": "owner"}]}
    if path == "/listentities":
        return {"results": [
            {"name": "Alice Example", "email": "alice@example.com", "title": "Engineer"},
            {"name": "Bev Example",   "email": "bev@example.com",   "title": "PM"},
        ]}
    if path == "/people":
        return {"name": "Alice Example", "email": body.get("email"),
                "title": "Engineer", "department": "Platform"}
    if path == "/announcements/list":
        return {"announcements": [{"id": "ann_1", "title": "Welcome to Glean"}]}
    if path == "/announcements/create":
        return {"id": f"ann_{uuid.uuid4().hex[:6]}", "status": "created"}
    if path == "/announcements/delete":
        return {"id": body.get("id"), "status": "deleted"}
    if path == "/listcollections":
        return {"collections": [{"id": "col_1", "name": "Onboarding"}]}
    if path == "/createcollection":
        return {"id": f"col_{uuid.uuid4().hex[:6]}", "name": body.get("name")}
    if path == "/listpins":
        return {"pins": [{"id": "pin_1", "query": "pto", "url": "https://example.com/pto"}]}
    if path == "/createpin":
        return {"id": f"pin_{uuid.uuid4().hex[:6]}", "status": "created"}
    if path == "/insights":
        resp: Dict[str, Any] = {}
        if "overviewRequest" in body:
            resp["overviewResponse"] = {
                "monthlyActiveUsers": 312,
                "weeklyActiveUsers": 148,
                "employeeCount": 520,
                "totalSignups": 401,
                "searchSessionSatisfaction": 0.87,
                "lastUpdatedTs": int(time.time()) - 3600,
                "searchDatasourceCounts": {
                    "gdrive": 1840, "confluence": 920,
                    "slack": 610, "jira": 430,
                },
            }
        if "assistantRequest" in body:
            resp["assistantResponse"] = {
                "monthlyActiveUsers": 198,
                "weeklyActiveUsers": 94,
                "lastUpdatedTs": int(time.time()) - 3600,
            }
        if "agentsRequest" in body:
            resp["agentsResponse"] = {
                "monthlyActiveUsers": 67,
                "weeklyActiveUsers": 31,
                "lastUpdatedTs": int(time.time()) - 3600,
            }
        return resp
    return {"mock": True, "path": path, "body": body}
