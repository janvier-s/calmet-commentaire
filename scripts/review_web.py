#!/usr/bin/env python3
"""
The review editor in the browser: the integrity-audit queue (docs/review_queue.json) and every page,
scan beside text. Replaces review_editor.py and page_editor.py; works on the same files.

Usage: python3 review_web.py [VOLUME [PAGE]] [--resume] [filters] [--port N] [--no-open]
  filters  --all (optional items too), --kind K, --category C, --type T, --book B,
           --skipped | --resolved | --false-positive | --all-status (the view to start in)
  --queue PATH, --data DIR, --docs DIR   other files (a copy for testing)
  --list-fp  print the issues marked false positive and exit

Serves on 127.0.0.1 only; the printed link carries the session key.
"""
import json
import mimetypes
import re
import secrets
import shutil
import subprocess
import sys
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import review_proposals as rp
import review_store as rs
import review_turns as rt
from page_text import load_state, save_state, toggle_italics
from review_search import Searcher

STATIC = Path(__file__).resolve().parent / "review_web"
REF = re.compile(r"\s*(\d+)\s*(?:[:.,]\s*(\d+))?\s*")


class ApiError(Exception):
    def __init__(self, code, body):
        super().__init__(body)
        self.code, self.body = code, body


def make_server(store, queue_path, port=0, token=None, include_optional=False, start=None, recheck=None):
    """The HTTP server over `store` and the queue at `queue_path`, not yet serving."""
    token = token or secrets.token_hex(16)
    fp_path = store.docs / "false_positives.json"
    items = rs.load_queue(queue_path, fp_path, include_optional)
    at = {it["id"]: i for i, it in enumerate(items)}
    for g in rp.generated_items(store):  # write-outs and reference candidates, after the audit's
        if g["id"] in at:
            items[at[g["id"]]] = g  # a false positive kept from an earlier session
        else:
            items.append(g)
    progress = rs.Progress(store.data / ".review_queue_progress.json", fp_path)
    state_file = store.data / ".page_editor_state.json"
    by_id = {it["id"]: it for it in items}

    def close_stale_repeats(vols=None):
        """Repeats at a page turn (seam_check.py's verdicts) the pages no longer show are fixed."""
        gone = [it for it in items if it["kind"] == "seam_repeat" and (vols is None or it["book_dir"] in vols)
                and rs.in_status(it, progress, "open") and rt.repeat_gone(store, it)]
        for it in gone:
            it["fixed"] = True
        if gone:
            progress.update({it["id"]: "resolved" for it in gone})
        return [it["id"] for it in gone]

    close_stale_repeats()

    def vol_page(q):
        vol = q.get("vol")
        if vol not in store.volumes():
            raise ApiError(404, {"error": f"no volume {vol}"})
        try:
            page = int(q.get("page"))
        except (TypeError, ValueError):
            raise ApiError(400, {"error": "bad page"})
        if page < 1:
            raise ApiError(400, {"error": "bad page"})
        return vol, page

    def page_payload(vol, page, data, version):
        return {"page": page, "data": data, "version": version, "scan": store.scan(vol, page) is not None,
                "context": store.context(vol, page), "pages": store.pages(vol),
                "issues": rs.page_issues(items, progress, vol, page),
                "around": rs.neighbour_issue_pages(items, progress, vol, page)}

    def save(vol, page, body):
        try:
            return store.save(vol, page, body["data"], body.get("version"), bool(body.get("force")))
        except FileNotFoundError:
            raise ApiError(404, {"error": f"{vol} page {page} has no JSON: nothing saved"})
        except rs.Conflict as c:
            raise ApiError(409, {"error": "changed on disk", "disk": c.disk, "version": c.version})

    def get_page(q):
        if q.get("page") in (None, "", "null") and q.get("vol") in store.volumes() and store.pages(q["vol"]):
            q = dict(q, page=store.pages(q["vol"])[0])  # a book opens at its first page
        vol, page = vol_page(q)
        if not store.path(vol, page).exists():
            raise ApiError(404, {"missing": True, "scan": store.scan(vol, page) is not None,
                                 "issues": rs.page_issues(items, progress, vol, page)})
        return page_payload(vol, page, *store.read(vol, page))

    def queue(q):
        f = {k: q.get(k) or None for k in ("cat", "kind", "book")}
        status = q.get("status") or "open"
        sel = rs.select(items, progress, status, **f)
        return {"items": [dict({k: v for k, v in it.items() if k != "proposal"}, status=progress.status(it["id"]))
                          for it in sel],
                "counts": rs.counts(items, progress, status, f["cat"], f["kind"], f["book"])}

    def locate(q):
        vol = q.get("vol")
        m = REF.fullmatch(q.get("ref") or "")
        if vol not in store.volumes() or not m:
            raise ApiError(400, {"error": "bad reference"})
        page = store.locate(vol, int(m.group(1)), int(m.group(2)) if m.group(2) else None)
        if page is None:
            raise ApiError(404, {"error": "not found"})
        return {"page": page}

    def op(body):
        vol, page = vol_page(body)
        data, version = save(vol, page, body)
        prev = store.context(vol, page)["prev"]
        prev_page = store.read(vol, prev["page"])[0] if prev else None
        data, version = store.save(vol, page, rs.apply_op(data, body["op"], prev_page), version)
        return {"data": data, "version": version}

    lock = threading.Lock()  # every change to the progress and the queue: marks and re-checks

    def mark(body):
        it = by_id.get(body.get("id"))
        if not it:
            raise ApiError(404, {"error": "no such item"})
        with lock:
            progress.set(it["id"], body.get("status"),
                         {k: it.get(k) for k in ("book_dir", "page", "kind", "msg")})
        return {"ok": True}

    def flag(body):
        vol, page = vol_page(body)
        raw = store.data / vol / "raw_json" / "commentaire" / f"page_{page:04d}.json"
        sources = [p for p in (raw, store.scan(vol, page)) if p and p.exists()]
        if not sources:
            raise ApiError(404, {"error": "neither the raw JSON nor the scan was found"})
        dest = store.data / vol / "modernization_error"
        dest.mkdir(exist_ok=True)
        for src in sources:
            shutil.copy(src, dest / f"page_{page:04d}{src.suffix}")
        return {"copied": [f"page_{page:04d}{s.suffix}" for s in sources], "to": str(dest)}

    def open_file(body):
        vol, page = vol_page(body)
        if body.get("what") == "png":
            img = store.scan(vol, page)
            if not img:
                raise ApiError(404, {"error": "no scan"})
            subprocess.Popen(["open", "-R", str(img)])
        else:
            try:
                subprocess.Popen(["code", str(store.path(vol, page))])
            except FileNotFoundError:
                subprocess.Popen(["open", str(store.path(vol, page))])
        return {"ok": True}

    def latin(body):
        from calmet import latin_case
        return {"text": latin_case(body.get("text") or "")}

    def italics(body):
        r = toggle_italics(body.get("text") or "", int(body["start"]), int(body["end"]))
        return r and {"text": r[0], "start": r[1], "end": r[2]}

    def state(body):
        if body is None:
            vol, page = load_state(state_file)
            return {"vol": vol, "page": page}
        save_state(body["vol"], int(body["page"]), state_file)
        return {"ok": True}

    def run_recheck(body):
        vol, page = vol_page(body)
        audit = recheck
        if audit is None:
            from page_audit import recheck_book
            audit = lambda v: recheck_book(v, store.data)
        with lock:  # one at a time: a second save waits and audits the later file
            new = audit(vol)
            r = rs.merge_recheck(items, progress, rs.book_volumes(vol), new, include_optional) \
                if new is not None else {"fixed": [], "added": []}  # a book the full audit leaves out
            by_id.update({it["id"]: it for it in items})
            r["fixed"] = r["fixed"] + close_stale_repeats(set(rs.book_volumes(vol)))
        also = [int(p) for p in body.get("also") or [] if str(p).isdigit() and int(p) != page]
        return {"fixed": len(r["fixed"]), "added": len(r["added"]),
                "issues": [i for p in [page, *also] for i in rs.page_issues(items, progress, vol, p)],
                "around": rs.neighbour_issue_pages(items, progress, vol, page)}

    def item_of(iid):
        it = by_id.get(iid)
        if not it:
            raise ApiError(404, {"error": "no such item"})
        return it

    def turn_issues(vol, a, b):
        return [dict({k: v for k, v in it.items() if k != "proposal"}, status=progress.status(it["id"]))
                for it in items if it["book_dir"] == vol and it["page"] in (a, b) and it["kind"] in rt.TURN_KINDS
                and rt.turn_of(store, it) == (vol, a, b)]

    def turn_around(vol, a):
        turns = {t[1] for it in items if it["book_dir"] == vol and it["kind"] in rt.TURN_KINDS
                 and rs.in_status(it, progress, "open") and (t := rt.turn_of(store, it))}
        return {"prev": max((x for x in turns if x < a), default=None),
                "next": min((x for x in turns if x > a), default=None)}

    def get_turn(q):
        if q.get("id"):
            t = rt.turn_of(store, item_of(q["id"]))
            if not t:
                raise ApiError(404, {"error": "not a page-turn issue"})
            vol, a, b = t
        else:
            vol, a = vol_page(dict(q, page=q.get("a")))
            pages = store.pages(vol)
            later = [p for p in pages if p > a]
            if a not in pages or not later:
                raise ApiError(404, {"error": f"no page turn after {vol} p.{a}"})
            b = later[0]
        return dict(rt.turn(store, vol, a, b), issues=turn_issues(vol, a, b), around=turn_around(vol, a))

    def get_proposal(q):
        return {"proposal": rp.proposal_for(store, progress, item_of(q.get("id")))}

    def info(it):
        return {k: it.get(k) for k in ("book_dir", "page", "kind", "msg")}

    def accept_one(it, proposal_id=None, option=0, edited=None):
        """Apply the item's proposal and mark it resolved; the caller holds the lock."""
        p = rp.proposal_for(store, progress, it)
        if not p or (proposal_id is not None and p["id"] != proposal_id):
            raise ApiError(409, {"error": "the proposal changed since it was shown: reload"})
        try:
            r = rp.apply(store, p, int(option), edited)
        except rs.Conflict:
            raise ApiError(409, {"error": "the text changed since the proposal was made: reload"})
        except (IndexError, ValueError, TypeError):
            raise ApiError(400, {"error": "bad option"})
        progress.set(it["id"], "resolved", info(it))
        return r

    def accept(body):
        it = item_of(body.get("id"))
        with lock:
            return accept_one(it, body.get("proposal_id"), body.get("option") or 0, body.get("edited"))

    def reject(body):
        it = item_of(body.get("id"))
        with lock:
            if it.get("proposal"):  # the proposal was the issue: a false positive
                progress.set(it["id"], "false_positive", info(it))
            else:
                progress.set("proposal:" + str(body.get("proposal_id")), "rejected")
        return {"ok": True}

    def batch(q):
        f = {k: q.get(k) or None for k in ("cat", "kind", "book")}
        rows = []
        for it in rs.select(items, progress, q.get("status") or "open", **f):
            ctx = None
            if it["kind"] in rt.TURN_KINDS:
                t = rt.turn_of(store, it)
                if t:
                    tt = rt.turn(store, *t)
                    ctx = tt["join"] and {k: tt["join"][k] for k in ("tail", "head", "joined")}
            elif it.get("where"):
                w = it["where"]
                entries = (store._load(it["book_dir"], it["page"]) or {}).get(w.get("section")) or []
                i = w.get("index")
                ctx = entries[i].get(w.get("field")) if isinstance(i, int) and i < len(entries) else None
            rows.append({"id": it["id"], "book_dir": it["book_dir"], "page": it["page"], "kind": it["kind"],
                         "msg": it["msg"], "status": progress.status(it["id"]), "context": ctx,
                         "proposal": rp.proposal_for(store, progress, it)})
        return {"rows": rows}

    def batch_accept(body):
        done, failed = [], []
        with lock:
            # each row carries the proposal it showed: one that changed since is not applied
            for row in body.get("ids") or []:
                row = row if isinstance(row, dict) else {"id": row}
                iid = row.get("id")
                try:
                    accept_one(item_of(iid), row.get("proposal_id"))
                    done.append(iid)
                except ApiError as e:
                    failed.append({"id": iid, "error": e.body.get("error")})
                except Exception as e:  # reported with the row; the others go on
                    failed.append({"id": iid, "error": f"{type(e).__name__}: {e}"})
        return {"done": done, "failed": failed}

    def create(body):
        vol, page = vol_page(body)
        try:
            return page_payload(vol, page, *store.create(vol, page))
        except FileExistsError:
            raise ApiError(409, {"error": "the page exists"})

    def versions(q):
        """The pages' versions on disk (None: no JSON), for the editor to see edits made outside it."""
        vol = q.get("vol")
        if vol not in store.volumes():
            raise ApiError(404, {"error": f"no volume {vol}"})
        out = {}
        for n in (q.get("pages") or "").split(","):
            if n.strip().isdigit():
                try:
                    out[n.strip()] = store._version(store.path(vol, int(n)))
                except OSError:
                    out[n.strip()] = None
        return {"versions": out}

    searcher = Searcher(store)
    threading.Thread(target=searcher.warm, args=(store.volumes(),), daemon=True).start()

    def search(q):
        vol = q.get("vol")
        if vol and vol not in store.volumes():
            raise ApiError(400, {"error": "no such book"})
        return searcher.search(q.get("q") or "", [vol] if vol else store.volumes())

    config = {"token": token, "labels": rs.KIND_LABELS,
              "kind_category": {k: rs.kind_category(k) for k in rs.KIND_LABELS}, "categories": list(rs.CATEGORIES),
              "statuses": list(rs.STATUSES), "volumes": store.volumes(), "start": start or {},
              "turn_kinds": sorted(rt.TURN_KINDS)}
    GET = {"/api/config": lambda q: config, "/api/page": get_page, "/api/queue": queue,
           "/api/locate": locate, "/api/state": lambda q: state(None), "/api/turn": get_turn,
           "/api/proposal": get_proposal, "/api/batch": batch, "/api/search": search, "/api/versions": versions}
    POST = {"/api/page": lambda b: (lambda r: {"data": r[0], "version": r[1]})(save(*vol_page(b), b)),
            "/api/page/create": create, "/api/op": op, "/api/mark": mark, "/api/flag": flag,
            "/api/open": open_file, "/api/recheck": run_recheck, "/api/latin_case": latin, "/api/italics": italics, "/api/state": state,
            "/api/proposal/accept": accept, "/api/proposal/reject": reject, "/api/batch/accept": batch_accept}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json; charset=utf-8", headers=()):
            if ctype.startswith("application/json"):
                body = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for h in headers:
                self.send_header(*h)
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self):
            if secrets.compare_digest(self.headers.get("X-Token", ""), token):
                return True
            cookies = dict(c.strip().split("=", 1) for c in self.headers.get("Cookie", "").split(";") if "=" in c)
            return secrets.compare_digest(cookies.get("rw_key", ""), token)

        def _file(self, path):
            if path is None or not path.is_file():
                return self._send(404, b"not found", "text/plain")
            self._send(200, path.read_bytes(), mimetypes.guess_type(path.name)[0] or "application/octet-stream")

        def _route(self, table, arg):
            url = urllib.parse.urlsplit(self.path)
            fn = table.get(url.path)
            if fn is None:
                return self._send(404, {"error": "no such route"})
            try:
                self._send(200, fn(arg(url)))
            except ApiError as e:
                self._send(e.code, e.body)
            except Exception as e:  # shown in the page, not swallowed
                self._send(500, {"error": f"{type(e).__name__}: {e}"})

        def do_GET(self):
            url = urllib.parse.urlsplit(self.path)
            path = urllib.parse.unquote(url.path)
            if path == "/":
                key = urllib.parse.parse_qs(url.query).get("key", [""])[0]
                if key and secrets.compare_digest(key, token):
                    return self._send(303, b"", "text/plain", [
                        ("Location", "/"), ("Set-Cookie", f"rw_key={token}; Path=/; HttpOnly; SameSite=Strict")])
                if not self._authorized():
                    return self._send(403, b"Open the link printed by review_web.py (it carries the key).",
                                      "text/plain; charset=utf-8")
                return self._file(STATIC / "index.html")
            if path.startswith("/static/"):
                target = (STATIC / path[len("/static/"):]).resolve()
                return self._file(target if STATIC.resolve() in target.parents else None)
            if not self._authorized():
                return self._send(403, {"error": "missing session key"})
            if path.startswith("/scan/"):
                parts = path.split("/")
                if len(parts) != 4 or parts[2] not in store.volumes() or not parts[3].isdigit():
                    return self._send(404, b"not found", "text/plain")
                return self._file(store.scan(parts[2], int(parts[3])))
            self._route(GET, lambda u: {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()})

        def do_POST(self):
            if not self._authorized():
                return self._send(403, {"error": "missing session key"})
            n = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return self._send(400, {"error": "bad JSON"})
            self._route(POST, lambda u: body)

    return ThreadingHTTPServer(("127.0.0.1", port), Handler), token


def list_fp(docs):
    try:
        fps = json.loads((docs / "false_positives.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        fps = {}
    if not fps:
        print("No issues currently marked as false positives.")
        return
    print(f"{len(fps)} issues marked as false positive:\n")
    for item_id, info in sorted(fps.items()):
        if isinstance(info, dict):
            kind = rs.KIND_LABELS.get(info.get("kind", ""), info.get("kind", ""))
            print(f"  • {info.get('book_dir', '')} p.{info.get('page', '')} [{kind}]")
            print(f"    {info.get('msg', '')}\n")
        else:
            print(f"  • {item_id}\n")


def main(argv):
    def opt(name, default=None):
        return argv[argv.index(name) + 1] if name in argv else default

    data = Path(opt("--data", rs.Path(__file__).resolve().parent.parent / "data"))
    docs = Path(opt("--docs", data.parent / "docs"))
    if "--list-fp" in argv or "--list-false-positives" in argv:
        return list_fp(docs)
    store = rs.Store(data, docs)
    queue_path = Path(opt("--queue", docs / "review_queue.json"))
    if not queue_path.exists():
        sys.exit(f"No queue found at {queue_path}. Run audit_integrity.py first.")
    status = ("false_positive" if {"--false-positive", "--false-positives"} & set(argv) else
              "skipped" if "--skipped" in argv else "resolved" if "--resolved" in argv else
              "all" if {"--all-status", "--all-statuses"} & set(argv) else "open")
    typ = (opt("--type") or "").lower()
    start = {"status": status, "book": opt("--book"), "kind": opt("--kind"),
             "cat": (opt("--category") or "").lower() or (typ if typ in rs.CATEGORIES else None)}
    if typ and typ not in rs.CATEGORIES:
        start["kind"] = typ
    with_value = {"--port", "--kind", "--category", "--type", "--book", "--queue", "--data", "--docs"}
    positional, skip = [], False
    for a in argv:
        if not skip and not a.startswith("--"):
            positional.append(a)
        skip = a in with_value
    if positional:
        start["vol"] = positional[0]
        start["page"] = int(positional[1]) if len(positional) > 1 else None
    elif "--resume" in argv:
        vol, page = load_state(data / ".page_editor_state.json")
        if vol:
            start["vol"], start["page"] = vol, page
    server, token = make_server(store, queue_path, int(opt("--port", 0)), None, "--all" in argv, start)
    url = f"http://127.0.0.1:{server.server_address[1]}/?key={token}"
    print(f"Review editor: {url}\n(Ctrl+C to stop)")
    if "--no-open" not in argv:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main(sys.argv[1:])
