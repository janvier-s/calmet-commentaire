#!/usr/bin/env python3
"""
Review Editor: page_editor.py driven by the integrity-audit worklist.

Walks the issues in docs/review_queue.json (written by audit_integrity.py),
showing each one in a banner above the usual scan + JSON view, and adds what the
plain editor lacks: add/delete verses, commentary blocks and footnotes, and creating
a page that has a scan but no JSON.

Usage: python3 review_editor.py [--all] [--kind missing_verse] [--book 05_deuteronome] [--queue path]
  --all    include optional items (page-turn glitches)
  --kind   only this kind of issue (missing_page, missing_verse, duplicate_verse,
           possible_gap, missing_footnote, empty_page, seam_artifact,
           translation_no_punct, lowercase_translation)
  --book   only this book folder
  --skipped  only the issues you skipped (--resolved: only those marked resolved)

Keys: Cmd+Return = resolved, go to next   Cmd+] / Cmd+[ = next / previous issue
◀/▶ visit open and skipped issues (resolved ones are passed over).
Progress is kept in data/.review_queue_progress.json; resolved items stay resolved
across runs. Changes reach the website only after the book is re-exported.
"""

import json
import re
import sys
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

import page_editor
from page_editor import PageEditor, find_source_image
from review_store import EMPTY_PAGE, KIND_LABELS, kind_category

DATA_DIR = page_editor.DATA_DIR
QUEUE_FILE = DATA_DIR.parent / "docs" / "review_queue.json"
PROGRESS_FILE = DATA_DIR / ".review_queue_progress.json"


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
        # Keep in sync with docs/false_positives.json
        fp_path = DATA_DIR.parent / "docs" / "false_positives.json"
        if fp_path.exists():
            try:
                fps = json.loads(fp_path.read_text(encoding="utf-8"))
                for k in fps:
                    if self.data.get(k) != "false_positive":
                        self.data[k] = "false_positive"
            except Exception:
                pass

    def status(self, item_id):
        return self.data.get(item_id)

    def set(self, item_id, status, item_info=None):
        if status:
            self.data[item_id] = status
        else:
            self.data.pop(item_id, None)
        self.save()
        # Keep docs/false_positives.json in sync
        fp_path = DATA_DIR.parent / "docs" / "false_positives.json"
        fps = {}
        if fp_path.exists():
            try:
                fps = json.loads(fp_path.read_text(encoding="utf-8"))
            except Exception:
                fps = {}
        if status == "false_positive":
            fps[item_id] = item_info or True
            try:
                fp_path.write_text(json.dumps(fps, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass
        elif item_id in fps:
            fps.pop(item_id, None)
            try:
                fp_path.write_text(json.dumps(fps, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass

    def save(self):
        try:
            self.path.write_text(json.dumps(self.data, indent=1))
        except Exception:
            pass


class ReviewEditor(PageEditor):
    BANNER_BG = "#2b2416"

    def __init__(self, root, items, progress, initial_status="open"):
        self.all_items = items
        self.progress = progress
        self._status_choice = initial_status
        self._cat_choice = None
        self._kind_choice = None
        self._book_choice = None

        def matches_status(it, st):
            s = self.progress.status(it["id"])
            if st == "open":
                return s not in ("resolved", "false_positive", "skipped")
            elif st == "false_positive":
                return s == "false_positive"
            elif st == "skipped":
                return s == "skipped"
            elif st == "resolved":
                return s == "resolved"
            return True

        matching = [it for it in items if matches_status(it, self._status_choice)]
        self.items = matching if matching else items
        self.item_idx = 0
        first = self.items[0]
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
        filters = tk.Frame(left, bg=self.BANNER_BG)
        filters.pack(fill=tk.X, pady=(0, 4))

        tk.Label(filters, text="Status:", bg=self.BANNER_BG, fg="#f0e6d2").pack(side=tk.LEFT)
        self.status_box = ttk.Combobox(filters, state="readonly", width=14)
        self.status_box.pack(side=tk.LEFT, padx=(4, 10))

        tk.Label(filters, text="Category:", bg=self.BANNER_BG, fg="#f0e6d2").pack(side=tk.LEFT)
        self.cat_box = ttk.Combobox(filters, state="readonly", width=12)
        self.cat_box.pack(side=tk.LEFT, padx=(4, 10))

        tk.Label(filters, text="Type:", bg=self.BANNER_BG, fg="#f0e6d2").pack(side=tk.LEFT)
        self.kind_box = ttk.Combobox(filters, state="readonly", width=32)
        self.kind_box.pack(side=tk.LEFT, padx=(4, 10))

        tk.Label(filters, text="Book:", bg=self.BANNER_BG, fg="#f0e6d2").pack(side=tk.LEFT)
        self.book_box = ttk.Combobox(filters, state="readonly", width=16)
        self.book_box.pack(side=tk.LEFT, padx=4)

        self.status_box.bind("<<ComboboxSelected>>", lambda e: self._on_status_select())
        self.cat_box.bind("<<ComboboxSelected>>", lambda e: self._on_cat_select())
        self.kind_box.bind("<<ComboboxSelected>>", lambda e: self._apply_filter())
        self.book_box.bind("<<ComboboxSelected>>", lambda e: self._apply_filter())
        self._fill_filters()
        self.issue_kind = tk.Label(left, text="", bg=self.BANNER_BG, fg="#ffb347",
                                   font=("Helvetica", 12, "bold"), anchor="w")
        self.issue_kind.pack(fill=tk.X)
        self.issue_msg = tk.Label(left, text="", bg=self.BANNER_BG, fg="#f0e6d2",
                                  font=("Helvetica", 12), anchor="w", justify=tk.LEFT, wraplength=900)
        self.issue_msg.pack(fill=tk.X)
        self.issue_more = tk.Label(left, text="", bg=self.BANNER_BG, fg="#b0a080",
                                   font=("Helvetica", 10), anchor="w", justify=tk.LEFT, wraplength=900)
        self.issue_more.pack(fill=tk.X)

        self.style.configure("Resolved.TButton", background="#2e7d32", foreground="#ffffff", font=("Helvetica", 10, "bold"))
        self.style.map("Resolved.TButton",
                       background=[("active", "#388e3c"), ("pressed", "#1b5e20")],
                       foreground=[("active", "#ffffff"), ("pressed", "#ffffff")])

        self.style.configure("FalsePositive.TButton", background="#d35400", foreground="#ffffff", font=("Helvetica", 10, "bold"))
        self.style.map("FalsePositive.TButton",
                       background=[("active", "#e67e22"), ("pressed", "#a04000")],
                       foreground=[("active", "#ffffff"), ("pressed", "#ffffff")])

        right = tk.Frame(bar, bg=self.BANNER_BG)
        right.pack(side=tk.RIGHT, padx=8, pady=6)
        self.counter = tk.Label(right, text="", bg=self.BANNER_BG, fg="#f0e6d2", font=("Helvetica", 10))
        self.counter.grid(row=0, column=0, columnspan=5, sticky="e")
        ttk.Button(right, text="◀ Issue", command=self._prev_item).grid(row=1, column=0, padx=2)
        ttk.Button(right, text="Issue ▶", command=self._next_item).grid(row=1, column=1, padx=2)
        ttk.Button(right, text="✓ Resolved", style="Resolved.TButton", command=lambda: self._mark("resolved")).grid(row=1, column=2, padx=2)
        ttk.Button(right, text="False Positive", style="FalsePositive.TButton", command=lambda: self._mark("false_positive")).grid(row=1, column=3, padx=2)
        ttk.Button(right, text="Skip", command=lambda: self._mark("skipped")).grid(row=1, column=4, padx=2)
        ttk.Button(right, text="+ Verse", command=self._add_verse).grid(row=2, column=0, padx=2, pady=(4, 0))
        ttk.Button(right, text="+ Comment", command=self._add_commentary).grid(row=2, column=1, padx=2, pady=(4, 0))
        ttk.Button(right, text="+ Footnote", command=self._add_footnote).grid(row=2, column=2, padx=2, pady=(4, 0))
        ttk.Button(right, text="Delete…", command=self._delete_entry).grid(row=2, column=3, padx=2, pady=(4, 0))
        ttk.Button(right, text="Reorder…", command=self._reorder).grid(row=2, column=4, padx=2, pady=(4, 0))

        for seq in ("<Command-Return>", "<Control-Return>"):
            self.root.bind(seq, lambda e: self._mark("resolved") or "break")
        for seq in ("<Command-p>", "<Control-p>"):
            self.root.bind(seq, lambda e: self._mark("false_positive") or "break")
        for seq in ("<Command-bracketright>", "<Control-bracketright>"):
            self.root.bind(seq, lambda e: self._next_item() or "break")
        for seq in ("<Command-bracketleft>", "<Control-bracketleft>"):
            self.root.bind(seq, lambda e: self._prev_item() or "break")

    def _build_json_editor(self):
        super()._build_json_editor()
        self._add_delete_buttons()
        # The base editor doesn't show chapter_title, which a newly created page may need.
        if self.data is not None:
            row = self._add_section_header(self.json_inner, self.json_inner.grid_size()[1], "PAGE HEADING")
            self._add_field(self.json_inner, row, "chapter_title", self.data.get("chapter_title"),
                            ("chapter_title",))

    def _add_delete_buttons(self):
        """A small ✕ on each verse and commentary header: delete that entry."""
        if self.data is None:
            return
        counters = {"verses": 0, "commentary": 0}
        for w in list(self.json_inner.winfo_children()):
            text = w.cget("text") if isinstance(w, tk.Label) else ""
            section = "verses" if text.startswith("  Verse ") else "commentary" if text.startswith("  Commentary ") else None
            if not section:
                continue
            i = counters[section]
            counters[section] += 1
            btn = tk.Button(self.json_inner, text="✕ delete", font=("Helvetica", 9), fg="#c0392b",
                            relief="flat", cursor="hand2",
                            command=lambda s=section, i=i: self._delete_one(s, i))
            btn.grid(row=w.grid_info()["row"], column=1, sticky="e", padx=5)

    def _delete_one(self, section, i):
        entry = (self.data.get(section) or [])[i]
        what = (f"verse {entry.get('verse_number')}: {(entry.get('latin') or entry.get('french') or '')[:60]}"
                if section == "verses" else
                f"commentary {entry.get('commentary_id')} (v.{entry.get('verse_ref')}): "
                f"{(entry.get('latin_quote') or entry.get('french_commentary') or '')[:60]}")
        if not messagebox.askyesno("Delete", f"Delete {what}?", default="yes"):
            return
        self._save()  # keep edits typed elsewhere on the page
        del self.data[section][i]
        if section == "commentary":
            for idx, c in enumerate(self.data.get("commentary") or [], start=1):
                c["commentary_id"] = idx
        self._commit_and_rebuild()

    def _load_page(self, page_num):
        super()._load_page(page_num)
        self._refresh_banner()

    def _on_status_select(self):
        st = self._status_values[self.status_box.current()]
        self._status_choice = st
        self._kind_choice = None
        self._apply_filter()

    def _on_cat_select(self):
        cat = self._cat_values[self.cat_box.current()]
        self._cat_choice = cat
        self._kind_choice = None
        self._apply_filter()

    # --- Status / Category / Type / book selectors ---
    def _fill_filters(self):
        statuses = [
            ("open", "Open"),
            ("false_positive", "False Positives"),
            ("skipped", "Skipped"),
            ("resolved", "Resolved"),
            ("all", "All"),
        ]
        self._status_values = [s[0] for s in statuses]

        def matches_status(it, st):
            s = self.progress.status(it["id"])
            if st == "open":
                return s not in ("resolved", "false_positive", "skipped")
            elif st == "false_positive":
                return s == "false_positive"
            elif st == "skipped":
                return s == "skipped"
            elif st == "resolved":
                return s == "resolved"
            return True

        in_status = lambda it: matches_status(it, self._status_choice)
        in_book = lambda it: self._book_choice is None or it["book_dir"] == self._book_choice
        in_cat = lambda it: self._cat_choice is None or kind_category(it["kind"]) == self._cat_choice
        of_kind = lambda it: (self._kind_choice is None or it["kind"] == self._kind_choice) and in_cat(it)

        # Status choices
        status_labels = []
        for sval, slabel in statuses:
            cnt = sum(1 for it in self.all_items if matches_status(it, sval) and in_book(it) and in_cat(it))
            prefix = "🔴 " if cnt > 0 and sval == "open" else ("🏷 " if cnt > 0 and sval == "false_positive" else "   ")
            status_labels.append(f"{prefix}({cnt}) {slabel}")
        self.status_box["values"] = status_labels
        if self._status_choice in self._status_values:
            self.status_box.current(self._status_values.index(self._status_choice))
        else:
            self.status_box.current(0)

        # Category choices
        cats = [("all", "All"), ("verses", "Verses"), ("commentary", "Commentary"), ("footnotes", "Footnotes")]
        self._cat_values = [None if c[0] == "all" else c[0] for c in cats]

        def left(pred):
            return sum(1 for it in self.all_items if pred(it) and in_status(it))

        cat_labels = []
        for cval, clabel in cats:
            pred = (lambda it: in_book(it)) if cval == "all" else (lambda it, cv=cval: kind_category(it["kind"]) == cv and in_book(it))
            cnt = left(pred)
            cat_labels.append(f"🔴 ({cnt}) {clabel}" if cnt > 0 else f"   (0) {clabel}")
        self.cat_box["values"] = cat_labels
        self.cat_box.current(self._cat_values.index(self._cat_choice))

        relevant_items = [it for it in self.all_items
                          if self._cat_choice is None or kind_category(it["kind"]) == self._cat_choice]
        kinds = list(dict.fromkeys(it["kind"] for it in relevant_items if in_status(it)))
        if not kinds:
            kinds = list(dict.fromkeys(it["kind"] for it in relevant_items))
        books = list(dict.fromkeys(sorted(it["book_dir"] for it in self.all_items if in_status(it))))
        if not books:
            books = list(dict.fromkeys(sorted(it["book_dir"] for it in self.all_items)))
        self._kind_values = [None] + kinds
        self._book_values = [None] + books

        tot = left(lambda it: in_book(it) and in_cat(it))
        tot_label = f"🔴 ({tot}) All types" if tot > 0 else f"   (0) All types"
        def format_kind(k):
            c = left(lambda it, k=k: it["kind"] == k and in_book(it))
            return f"🔴 ({c}) {KIND_LABELS.get(k, k)}" if c > 0 else f"   (0) {KIND_LABELS.get(k, k)}"
        self.kind_box["values"] = [tot_label] + [format_kind(k) for k in kinds]
        self.book_box["values"] = [f"All books ({left(of_kind)})"] + [
            f"{b} ({left(lambda it, b=b: it['book_dir'] == b and of_kind(it))})" for b in books]

        if self._kind_choice in self._kind_values:
            self.kind_box.current(self._kind_values.index(self._kind_choice))
        else:
            self._kind_choice = None
            self.kind_box.current(0)

        if self._book_choice in self._book_values:
            self.book_box.current(self._book_values.index(self._book_choice))
        else:
            self._book_choice = None
            self.book_box.current(0)

    def _apply_filter(self):
        st = self._status_values[self.status_box.current()] if hasattr(self, "status_box") else self._status_choice
        cat = self._cat_values[self.cat_box.current()]
        kind = self._kind_values[self.kind_box.current()]
        book = self._book_values[self.book_box.current()]

        def matches_status(it, status_name):
            s = self.progress.status(it["id"])
            if status_name == "open":
                return s not in ("resolved", "false_positive", "skipped")
            elif status_name == "false_positive":
                return s == "false_positive"
            elif status_name == "skipped":
                return s == "skipped"
            elif status_name == "resolved":
                return s == "resolved"
            return True

        items = [it for it in self.all_items
                 if matches_status(it, st)
                 and (cat is None or kind_category(it["kind"]) == cat)
                 and (kind is None or it["kind"] == kind)
                 and (book is None or it["book_dir"] == book)]
        if not items:
            messagebox.showinfo("Queue", "No issues matching these filters.")
            self._fill_filters()
            return
        self._status_choice, self._cat_choice, self._kind_choice, self._book_choice = st, cat, kind, book
        self.items = items
        self._goto_item(0)

    # --- Queue navigation ---
    def _open_count(self):
        return sum(1 for it in self.all_items if self.progress.status(it["id"]) not in ("resolved", "false_positive", "skipped"))

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
                  and (self._status_choice != "open" or self.progress.status(o["id"]) not in ("resolved", "false_positive"))]
        self.issue_more.config(text=("Also on this page: " + " · ".join(
            f"{KIND_LABELS.get(o['kind'], o['kind']).lower()}: {o['msg'][:70]}" for o in others[:3]))
            if others else "")
        skipped = sum(1 for o in self.all_items if self.progress.status(o["id"]) == "skipped")
        fp_count = sum(1 for o in self.all_items if self.progress.status(o["id"]) == "false_positive")
        open_count = self._open_count()
        self.counter.config(text=f"issue {self.item_idx + 1}/{len(self.items)} ({self._status_choice}) · {open_count} open · {skipped} skipped · {fp_count} false pos")
        self._fill_filters()

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
            if self._status_choice == "open":
                if self.progress.status(self.items[i]["id"]) in ("resolved", "false_positive"):
                    continue
            return self._goto_item(i)
        messagebox.showinfo("Queue", f"No more issues after this one in {self._status_choice} view.")

    def _prev_item(self):
        for i in range(self.item_idx - 1, -1, -1):
            if self._status_choice == "open":
                if self.progress.status(self.items[i]["id"]) in ("resolved", "false_positive"):
                    continue
            return self._goto_item(i)
        messagebox.showinfo("Queue", f"No earlier issues in {self._status_choice} view.")

    def _mark(self, status):
        if self.dirty:
            self._save()
            if self.dirty:  # the save failed (error shown): stay on the page, nothing lost
                return
        it = self.items[self.item_idx]
        self.progress.set(it["id"], status, {
            "book_dir": it.get("book_dir"),
            "page": it.get("page"),
            "kind": it.get("kind"),
            "msg": it.get("msg"),
        })
        self._refresh_banner()
        self._next_item()

    def _reopen(self):
        """Clear the status of the current issue (undo a Skip, Resolved, or False Positive)."""
        it = self.items[self.item_idx]
        self.progress.set(it["id"], None)
        self._refresh_banner()

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
        self.data = page_editor.trim(page_editor.clean_page(self.data))
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
        verses.insert(pos, {"chapter": self._neighbour_chapter(verses, pos),
                            "verse_number": n, "latin": "", "french": "", "annotations": None})
        self._commit_and_rebuild()

    def _neighbour_chapter(self, entries, pos):
        """The chapter of the entry before position `pos` (or after it): a new entry's default."""
        for e in list(reversed(entries[:pos])) + entries[pos:]:
            if isinstance(e.get("chapter"), int):
                return e["chapter"]
        return None

    def _add_commentary(self):
        if self.data is None:
            return
        self._save()
        comms = self.data.setdefault("commentary", [])
        next_id = max([c.get("commentary_id") or 0 for c in comms] + [0]) + 1
        comms.append({"commentary_id": next_id, "verse_ref": None, "chapter": self._neighbour_chapter(comms, len(comms)),
                      "latin_quote": None, "french_translation": None, "french_commentary": ""})
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
                if section == "commentary":
                    for idx, c in enumerate(self.data.get("commentary") or [], start=1):
                        c["commentary_id"] = idx
                win.destroy()
                self._commit_and_rebuild()

        ttk.Button(win, text="Delete selected", command=go).pack(pady=(0, 10))


    def _reorder(self):
        """Move verses or commentary blocks up and down; saved when the window closes."""
        if self.data is None:
            return
        self._save()
        win = tk.Toplevel(self.root)
        win.title("Reorder")
        win.transient(self.root)
        section = tk.StringVar(value="commentary")
        renumber = tk.BooleanVar(value=True)
        moved = [False]

        def label(sec, x):
            if sec == "verses":
                return f"Verse {x.get('verse_number')}: {(x.get('latin') or x.get('french') or '')[:70]}"
            text = x.get("latin_quote") or x.get("french_translation") or x.get("french_commentary") or ""
            return f"#{x.get('commentary_id')} (℣ {x.get('verse_ref')}): {text[:70]}"

        top = tk.Frame(win)
        top.pack(fill=tk.X, padx=10, pady=(10, 0))
        for value, text in (("commentary", "Commentary"), ("verses", "Verses")):
            ttk.Radiobutton(top, text=text, value=value, variable=section,
                            command=lambda: fill()).pack(side=tk.LEFT, padx=(0, 10))
        body = tk.Frame(win)
        body.pack(padx=10, pady=10)
        lb = tk.Listbox(body, width=100, height=18, exportselection=False)
        lb.pack(side=tk.LEFT)
        buttons = tk.Frame(body)
        buttons.pack(side=tk.LEFT, padx=(8, 0), fill=tk.Y)

        def fill(select=None):
            items = self.data.get(section.get()) or []
            lb.delete(0, tk.END)
            for x in items:
                lb.insert(tk.END, label(section.get(), x))
            if select is not None and items:
                lb.selection_set(select)
                lb.see(select)

        def move(step):
            sel = lb.curselection()
            items = self.data.get(section.get()) or []
            if not sel:
                return
            i, j = sel[0], sel[0] + step
            if not 0 <= j < len(items):
                return
            items[i], items[j] = items[j], items[i]
            moved[0] = True
            fill(j)

        def to_end(end):
            sel = lb.curselection()
            items = self.data.get(section.get()) or []
            if not sel:
                return
            x = items.pop(sel[0])
            items.insert(0 if end == "top" else len(items), x)
            moved[0] = True
            fill(0 if end == "top" else len(items) - 1)

        ttk.Button(buttons, text="⤒ Top", command=lambda: to_end("top")).pack(fill=tk.X)
        ttk.Button(buttons, text="↑ Up", command=lambda: move(-1)).pack(fill=tk.X, pady=(4, 0))
        ttk.Button(buttons, text="↓ Down", command=lambda: move(1)).pack(fill=tk.X, pady=(4, 0))
        ttk.Button(buttons, text="⤓ Bottom", command=lambda: to_end("bottom")).pack(fill=tk.X, pady=(4, 0))
        for seq, step in (("<Up>", -1), ("<Down>", 1)):
            lb.bind(f"<Option-{seq[1:-1]}>", lambda e, s=step: move(s) or "break")
        ttk.Checkbutton(win, text="Renumber commentary_id 1, 2, 3… in the new order",
                        variable=renumber).pack(anchor="w", padx=10)

        def done():
            if moved[0]:
                if renumber.get():
                    for k, c in enumerate(self.data.get("commentary") or [], 1):
                        c["commentary_id"] = k
                self._commit_and_rebuild()
            win.destroy()

        ttk.Button(win, text="Done", command=done).pack(pady=10)
        win.protocol("WM_DELETE_WINDOW", done)
        fill()


def load_queue(args):
    path = QUEUE_FILE
    if "--queue" in args:
        path = page_editor.Path(args[args.index("--queue") + 1])
    items = json.loads(path.read_text())

    # Include false positives from docs/false_positives.json so they remain visible even after audit prune
    fp_path = DATA_DIR.parent / "docs" / "false_positives.json"
    if fp_path.exists():
        try:
            fps = json.loads(fp_path.read_text(encoding="utf-8"))
            existing_ids = {it["id"] for it in items}
            for fp_id, val in fps.items():
                if fp_id not in existing_ids:
                    items.append({
                        "id": fp_id,
                        "book_dir": val.get("book_dir", fp_id.split("/")[0]) if isinstance(val, dict) else fp_id.split("/")[0],
                        "page": val.get("page", int(fp_id.split("/")[1])) if isinstance(val, dict) else int(fp_id.split("/")[1]),
                        "kind": val.get("kind", fp_id.split("/")[2]) if isinstance(val, dict) else fp_id.split("/")[2],
                        "msg": val.get("msg", "Marked false positive") if isinstance(val, dict) else "Marked false positive",
                        "optional": False,
                    })
        except Exception:
            pass

    if "--all" not in args:
        items = [it for it in items if not it.get("optional")]
    if "--category" in args:
        cat = args[args.index("--category") + 1].lower()
        items = [it for it in items if kind_category(it["kind"]) == cat]
    if "--type" in args:
        val = args[args.index("--type") + 1].lower()
        if val in ("verses", "commentary", "footnotes"):
            items = [it for it in items if kind_category(it["kind"]) == val]
        else:
            items = [it for it in items if it["kind"] == val]
    if "--kind" in args:
        kind = args[args.index("--kind") + 1]
        items = [it for it in items if it["kind"] == kind]
    if "--book" in args:
        book = args[args.index("--book") + 1]
        items = [it for it in items if it["book_dir"] == book]
    return items


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--list-fp" in args or "--list-false-positives" in args:
        fp_file = DATA_DIR.parent / "docs" / "false_positives.json"
        fps = {}
        if fp_file.exists():
            try:
                fps = json.loads(fp_file.read_text(encoding="utf-8"))
            except Exception:
                fps = {}
        if not fps:
            print("No issues currently marked as false positives.")
        else:
            print(f"{len(fps)} issues marked as false positive:\n")
            for item_id, info in sorted(fps.items()):
                if isinstance(info, dict):
                    b = info.get("book_dir", "")
                    p = info.get("page", "")
                    k = KIND_LABELS.get(info.get("kind", ""), info.get("kind", ""))
                    m = info.get("msg", "")
                    print(f"  • {b} p.{p} [{k}]")
                    print(f"    {m}\n")
                else:
                    print(f"  • {item_id}\n")
        sys.exit(0)

    try:
        items = load_queue(args)
    except FileNotFoundError:
        print(f"No queue found at {QUEUE_FILE}. Run audit_integrity.py first.")
        sys.exit(1)
    if not items:
        print("Nothing to review with these filters.")
        sys.exit(0)
    progress = Progress(PROGRESS_FILE)

    init_status = "open"
    if "--false-positive" in args or "--false-positives" in args:
        init_status = "false_positive"
    elif "--skipped" in args:
        init_status = "skipped"
    elif "--resolved" in args:
        init_status = "resolved"
    elif "--all-status" in args or "--all-statuses" in args:
        init_status = "all"

    root = tk.Tk()
    ReviewEditor(root, items, progress, initial_status=init_status)
    try:
        root.mainloop()
    except KeyboardInterrupt:  # Ctrl+C in the terminal: quit quietly
        pass
