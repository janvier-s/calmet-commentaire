#!/usr/bin/env python3
"""
Review Editor: page_editor.py driven by the integrity-audit worklist.

Walks the issues in docs/review_queue.json (written by Lectio/build/audit_integrity.py),
showing each one in a banner above the usual scan + JSON view, and adds what the
plain editor lacks: add/delete verses, commentary blocks and footnotes, and creating
a page that has a scan but no JSON.

Usage: python3 review_editor.py [--all] [--kind missing_verse] [--book 05_deuteronome] [--queue path]
  --all    include optional items (page-turn glitches)
  --kind   only this kind of issue (missing_page, missing_verse, duplicate_verse,
           possible_gap, missing_footnote, empty_page, seam_artifact)
  --book   only this book folder

Keys: Cmd+Return = resolved, go to next   Cmd+] / Cmd+[ = next / previous issue
Progress is kept in data/.review_queue_progress.json; resolved items stay resolved
across runs. Changes reach the website only after the book is re-exported.
"""

import json
import sys
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

import page_editor
from page_editor import PageEditor, find_source_image

DATA_DIR = page_editor.DATA_DIR
QUEUE_FILE = DATA_DIR.parent / "docs" / "review_queue.json"
PROGRESS_FILE = DATA_DIR / ".review_queue_progress.json"

KIND_LABELS = {
    "reported": "REPORTED BY YOU",
    "duplicate_page": "PAGE COPIED FROM ANOTHER",
    "malformed_page": "MALFORMED PAGE",
    "missing_page": "MISSING PAGE",
    "missing_verse": "MISSING VERSE",
    "duplicate_verse": "DUPLICATE VERSE",
    "dropped_commentary": "COMMENTARY NOT ON SITE",
    "seam_missing": "TEXT MISSING AT PAGE BREAK",
    "seam_repeat": "TEXT REPEATED AT PAGE BREAK",
    "seam_unclear": "PAGE BREAK TO CHECK",
    "ref_order": "VERSE REFERENCE OUT OF ORDER",
    "empty_commentary": "NOTE WITHOUT COMMENTARY",
    "caps_in_commentary": "CAPITALS IN COMMENTARY",
    "broken_marker": "BROKEN FOOTNOTE CALL",
    "possible_gap": "POSSIBLE GAP",
    "missing_footnote": "MISSING FOOTNOTE",
    "empty_page": "EMPTY PAGE",
    "seam_artifact": "PAGE-TURN GLITCH",
}

EMPTY_PAGE = {"book_title": None, "chapter_title": None, "chapter_summary": None,
              "verses": [], "commentary": [], "footnotes": []}


def book_pages(book_path):
    return sorted(int(f.stem[5:9]) for f in (book_path / "normalized").glob("page_*.json")
                  if f.stem[5:9].isdigit() and " " not in f.name)


class Progress:
    def __init__(self, path):
        self.path = path
        try:
            self.data = json.loads(path.read_text())
        except Exception:
            self.data = {}

    def status(self, item_id):
        return self.data.get(item_id)

    def set(self, item_id, status):
        self.data[item_id] = status
        self.save()

    def save(self):
        try:
            self.path.write_text(json.dumps(self.data, indent=1))
        except Exception:
            pass


class ReviewEditor(PageEditor):
    BANNER_BG = "#2b2416"

    def __init__(self, root, items, progress):
        self.items = items
        self.progress = progress
        self.item_idx = next((i for i, it in enumerate(items) if not progress.status(it["id"])), 0)
        first = items[self.item_idx]
        book_path = DATA_DIR / first["book_dir"]
        pages = book_pages(book_path)
        # The base editor needs an existing page to start on; the queue item is opened right after.
        start = first["page"] if first["page"] in pages else pages[0]
        super().__init__(root, book_path, start, pages)
        self.root.after(300, lambda: self._goto_item(self.item_idx))

    # --- UI ---
    def _build_ui(self):
        super()._build_ui()
        bar = tk.Frame(self.root, bg=self.BANNER_BG, bd=1, relief="groove")
        bar.pack(fill=tk.X, padx=10, pady=(0, 5), before=self.paned)

        left = tk.Frame(bar, bg=self.BANNER_BG)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8, pady=6)
        self.issue_kind = tk.Label(left, text="", bg=self.BANNER_BG, fg="#ffb347",
                                   font=("Helvetica", 12, "bold"), anchor="w")
        self.issue_kind.pack(fill=tk.X)
        self.issue_msg = tk.Label(left, text="", bg=self.BANNER_BG, fg="#f0e6d2",
                                  font=("Helvetica", 12), anchor="w", justify=tk.LEFT, wraplength=900)
        self.issue_msg.pack(fill=tk.X)
        self.issue_more = tk.Label(left, text="", bg=self.BANNER_BG, fg="#b0a080",
                                   font=("Helvetica", 10), anchor="w", justify=tk.LEFT, wraplength=900)
        self.issue_more.pack(fill=tk.X)

        right = tk.Frame(bar, bg=self.BANNER_BG)
        right.pack(side=tk.RIGHT, padx=8, pady=6)
        self.counter = tk.Label(right, text="", bg=self.BANNER_BG, fg="#f0e6d2", font=("Helvetica", 10))
        self.counter.grid(row=0, column=0, columnspan=4, sticky="e")
        ttk.Button(right, text="◀ Issue", command=self._prev_item).grid(row=1, column=0, padx=2)
        ttk.Button(right, text="Issue ▶", command=self._next_item).grid(row=1, column=1, padx=2)
        ttk.Button(right, text="✓ Resolved", command=lambda: self._mark("resolved")).grid(row=1, column=2, padx=2)
        ttk.Button(right, text="Skip", command=lambda: self._mark("skipped")).grid(row=1, column=3, padx=2)
        ttk.Button(right, text="+ Verse", command=self._add_verse).grid(row=2, column=0, padx=2, pady=(4, 0))
        ttk.Button(right, text="+ Comment", command=self._add_commentary).grid(row=2, column=1, padx=2, pady=(4, 0))
        ttk.Button(right, text="+ Footnote", command=self._add_footnote).grid(row=2, column=2, padx=2, pady=(4, 0))
        ttk.Button(right, text="Delete…", command=self._delete_entry).grid(row=2, column=3, padx=2, pady=(4, 0))

        for seq in ("<Command-Return>", "<Control-Return>"):
            self.root.bind(seq, lambda e: self._mark("resolved") or "break")
        for seq in ("<Command-bracketright>", "<Control-bracketright>"):
            self.root.bind(seq, lambda e: self._next_item() or "break")
        for seq in ("<Command-bracketleft>", "<Control-bracketleft>"):
            self.root.bind(seq, lambda e: self._prev_item() or "break")

    def _build_json_editor(self):
        super()._build_json_editor()
        # The base editor doesn't show chapter_title, which a newly created page may need.
        if self.data is not None:
            row = self._add_section_header(self.json_inner, self.json_inner.grid_size()[1], "PAGE HEADING")
            self._add_field(self.json_inner, row, "chapter_title", self.data.get("chapter_title"),
                            ("chapter_title",))

    def _load_page(self, page_num):
        super()._load_page(page_num)
        self._refresh_banner()

    # --- Queue navigation ---
    def _open_count(self):
        return sum(1 for it in self.items if not self.progress.status(it["id"]))

    def _refresh_banner(self):
        if not hasattr(self, "issue_kind") or not self.items:
            return
        it = self.items[self.item_idx]
        here = it["book_dir"] == self.book_path.name and it["page"] == self.page_num
        status = self.progress.status(it["id"])
        self.issue_kind.config(text=KIND_LABELS.get(it["kind"], it["kind"])
                               + (f"  [{status}]" if status else "")
                               + ("" if here else "  (you have navigated away from this issue's page)"))
        self.issue_msg.config(text=f"{it['book_dir']} p.{it['page']}: {it['msg']}")
        others = [o for o in self.items
                  if o is not it and o["book_dir"] == self.book_path.name and o["page"] == self.page_num
                  and not self.progress.status(o["id"])]
        self.issue_more.config(text=("Also on this page: " + " · ".join(
            f"{KIND_LABELS.get(o['kind'], o['kind']).lower()}: {o['msg'][:70]}" for o in others[:3]))
            if others else "")
        self.counter.config(text=f"issue {self.item_idx + 1}/{len(self.items)} · {self._open_count()} open")

    def _goto_item(self, idx):
        if not self.items:
            return
        self.item_idx = max(0, min(idx, len(self.items) - 1))
        it = self.items[self.item_idx]
        book_path = DATA_DIR / it["book_dir"]
        if book_path != self.book_path:
            if self.dirty and messagebox.askyesno("Unsaved changes", "Save changes before leaving?"):
                self._save()
            self.dirty = False
            self.book_path = book_path
            self.all_pages = book_pages(book_path)
        if it["page"] not in self.all_pages:
            if not self._create_page(it["page"]):
                self._refresh_banner()
                return
        self._load_page(it["page"])

    def _next_item(self):
        for i in range(self.item_idx + 1, len(self.items)):
            if not self.progress.status(self.items[i]["id"]):
                return self._goto_item(i)
        messagebox.showinfo("Queue", "No open issues after this one.")

    def _prev_item(self):
        for i in range(self.item_idx - 1, -1, -1):
            if not self.progress.status(self.items[i]["id"]):
                return self._goto_item(i)

    def _mark(self, status):
        if self.dirty:
            self._save()
        self.progress.set(self.items[self.item_idx]["id"], status)
        self._refresh_banner()
        self._next_item()

    # --- Creating pages and entries ---
    def _create_page(self, page):
        img = find_source_image(self.book_path, page)
        note = "" if img else "\n\n(No scan was found for this page either.)"
        if not messagebox.askyesno("Create page",
                                   f"{self.book_path.name} page {page} has no JSON.\n"
                                   f"Create an empty page to transcribe from the scan?{note}"):
            return False
        path = self.book_path / "normalized" / f"page_{page:04d}.json"
        path.write_text(json.dumps(EMPTY_PAGE, ensure_ascii=False, indent=2), encoding="utf-8")
        self.all_pages = book_pages(self.book_path)
        return True

    def _commit_and_rebuild(self):
        with open(self.json_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        self._build_json_editor()
        self.dirty = False
        self.dirty_label.config(text="saved", foreground=self.SAVE_COLOR)
        self.json_inner.update_idletasks()
        self.json_canvas.configure(scrollregion=self.json_canvas.bbox("all"))

    def _add_verse(self):
        if self.data is None:
            return
        n = simpledialog.askinteger("Add verse", "Number of the new verse:", parent=self.root)
        if n is None:
            return
        self._save()  # keep anything typed so far
        verses = self.data.setdefault("verses", [])
        # Insert after the last lower-numbered verse before the numbering restarts
        # (a page can end one chapter and start the next).
        pos, prev = 0, None
        for i, v in enumerate(verses):
            k = v.get("verse_number")
            if isinstance(k, int):
                if prev is not None and k < prev:
                    break
                prev = k
                if k < n:
                    pos = i + 1
        verses.insert(pos, {"verse_number": n, "latin": "", "french": "", "annotations": None})
        self._commit_and_rebuild()

    def _add_commentary(self):
        if self.data is None:
            return
        self._save()
        comms = self.data.setdefault("commentary", [])
        next_id = max([c.get("commentary_id") or 0 for c in comms] + [0]) + 1
        comms.append({"commentary_id": next_id, "verse_ref": None, "latin_quote": None,
                      "french_translation": None, "french_commentary": ""})
        self._commit_and_rebuild()
        self.json_canvas.yview_moveto(1.0)

    def _add_footnote(self):
        if self.data is None:
            return
        marker = simpledialog.askstring("Add footnote", "Marker letter (e.g. a):", parent=self.root)
        if not marker:
            return
        self._save()
        self.data.setdefault("footnotes", []).append({"marker": f"({marker.strip('() ')})", "text": ""})
        self._commit_and_rebuild()
        self.json_canvas.yview_moveto(1.0)

    def _delete_entry(self):
        if self.data is None:
            return
        self._save()
        entries = []
        for i, v in enumerate(self.data.get("verses") or []):
            entries.append(("verses", i, f"Verse {v.get('verse_number')}: {(v.get('latin') or v.get('french') or '')[:60]}"))
        for i, c in enumerate(self.data.get("commentary") or []):
            entries.append(("commentary", i, f"Commentary {c.get('commentary_id')} (v.{c.get('verse_ref')}): "
                                              f"{(c.get('latin_quote') or c.get('french_commentary') or '')[:50]}"))
        for i, fn in enumerate(self.data.get("footnotes") or []):
            entries.append(("footnotes", i, f"Footnote {fn.get('marker')}: {(fn.get('text') or '')[:60]}"))
        if not entries:
            return

        win = tk.Toplevel(self.root)
        win.title("Delete an entry")
        win.transient(self.root)
        lb = tk.Listbox(win, width=100, height=min(20, len(entries)))
        for _, _, label in entries:
            lb.insert(tk.END, label)
        lb.pack(padx=10, pady=10)

        def go():
            sel = lb.curselection()
            if not sel:
                return
            section, i, label = entries[sel[0]]
            if messagebox.askyesno("Delete", f"Delete this entry?\n\n{label}", parent=win):
                del self.data[section][i]
                win.destroy()
                self._commit_and_rebuild()

        ttk.Button(win, text="Delete selected", command=go).pack(pady=(0, 10))


def load_queue(args):
    path = QUEUE_FILE
    if "--queue" in args:
        path = page_editor.Path(args[args.index("--queue") + 1])
    items = json.loads(path.read_text())
    if "--all" not in args:
        items = [it for it in items if not it.get("optional")]
    if "--kind" in args:
        kind = args[args.index("--kind") + 1]
        items = [it for it in items if it["kind"] == kind]
    if "--book" in args:
        book = args[args.index("--book") + 1]
        items = [it for it in items if it["book_dir"] == book]
    return items


if __name__ == "__main__":
    args = sys.argv[1:]
    try:
        items = load_queue(args)
    except FileNotFoundError:
        print(f"No queue found at {QUEUE_FILE}. Run Lectio/build/audit_integrity.py first.")
        sys.exit(1)
    if not items:
        print("Nothing to review with these filters.")
        sys.exit(0)
    progress = Progress(PROGRESS_FILE)
    print(f"{len(items)} issues, {sum(1 for it in items if not progress.status(it['id']))} open")
    root = tk.Tk()
    ReviewEditor(root, items, progress)
    root.mainloop()
