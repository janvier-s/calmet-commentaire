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
           possible_gap, missing_footnote, empty_page, seam_artifact)
  --book   only this book folder
  --skipped  only the issues you skipped (--resolved: only those marked resolved)

Keys: Cmd+Return = resolved, go to next   Cmd+] / Cmd+[ = next / previous issue
◀/▶ visit open and skipped issues (resolved ones are passed over); ↺ Reopen clears
the current issue's status.
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
    "psalm_missing_verse": "PSALM VERSE MISSING (from the Vulgate text)",
    "psalm_missing_title": "PSALM TITLE MISSING",
    "missing_french": "VERSE WITHOUT FRENCH",
    "vulgate_filled": "VERSE FILLED FROM THE VULGATE: TYPE THE FRENCH",
    "psalm_number": "PSALM VERSE NUMBER OUT OF STEP",
    "psalm_wrong_psalm": "VERSE UNDER THE WRONG PSALM",
    "psalm_unmatched": "VERSE NOT FOUND IN THE VULGATE",
    "duplicate_verse": "DUPLICATE VERSE",
    "chapter_field": "CHAPTER FIELD OUT OF STEP",
    "empty_summary": "CHAPTER SUMMARY EMPTY",
    "chapter_vulgate": "CHAPTER SET FROM THE VULGATE: CHECK THE VERSE NUMBER",
    "chapter_heading": "CHAPTER HEADING TO CHECK",
    "dropped_commentary": "COMMENTARY NOT ON SITE",
    "seam_missing": "TEXT MISSING AT PAGE BREAK",
    "seam_repeat": "TEXT REPEATED AT PAGE BREAK",
    "seam_unclear": "PAGE BREAK TO CHECK",
    "ref_order": "VERSE REFERENCE OUT OF ORDER",
    "no_verse_ref": "NOTE WITHOUT VERSE_REF",
    "no_lemma": "NOTE WITHOUT LATIN_QUOTE",
    "spaced_letters": "L E T T E R - S P A C E D WORD",
    "leading_punctuation": "COMMENT STARTS WITH PUNCTUATION",
    "italic_seam": "ITALICS BROKEN AT PAGE TURN",
    "period_seam": "FULL STOP AT PAGE END, LOWER CASE OVERLEAF",
    "etc_for_et": "“ETC.” WHERE “&” (ET) WAS MEANT?",
    "hyphen_cut": "LEMMA / TRANSLATION CUT AT PAGE TURN (hyphen or no full stop)",
    "long_translation": "TRANSLATION MUCH LONGER THAN THE LEMMA",
    "hebrew_in_translation": "“L'HÉBREU” IN THE TRANSLATION",
    "hebrew_recheck": "FOOTNOTE HEBREW UNCERTAIN: CHECK AGAINST THE SCAN",
    "guessed_ref": "BIBLE REFERENCE GUESSED (*) OR AS PRINTED: CHECK ON THE SCAN",
    "footnote_asterisk": "FOOTNOTE WITH GUESSED WORDS (*): CHECK AGAINST THE SCAN",
    "lowercase_lemma": "LOWER CASE IN THE LATIN LEMMA",
    "lemma_unknown_word": "LEMMA WORD NOT IN THE VULGATE (name? misreading?)",
    "extra_footnotes": "MORE FOOTNOTES THAN CALLS",
    "empty_commentary": "NOTE WITHOUT COMMENTARY",
    "caps_in_commentary": "CAPITALS IN COMMENTARY",
    "broken_marker": "BROKEN FOOTNOTE CALL",
    "possible_gap": "POSSIBLE GAP",
    "missing_footnote": "MISSING FOOTNOTE",
    "empty_page": "EMPTY PAGE",
    "seam_artifact": "PAGE-TURN GLITCH",
}

EMPTY_PAGE = {"book_title": None, "chapter_title": None, "chapter_summary": None, "chapter_intro": None,
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
        if status:
            self.data[item_id] = status
        else:
            self.data.pop(item_id, None)
        self.save()

    def save(self):
        try:
            self.path.write_text(json.dumps(self.data, indent=1))
        except Exception:
            pass


class ReviewEditor(PageEditor):
    BANNER_BG = "#2b2416"

    def __init__(self, root, items, progress):
        self.all_items = items
        self.items = items
        self.progress = progress
        self.item_idx = next((i for i, it in enumerate(items) if not progress.status(it["id"])),
                             next((i for i, it in enumerate(items) if progress.status(it["id"]) != "resolved"), 0))
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
        filters = tk.Frame(left, bg=self.BANNER_BG)
        filters.pack(fill=tk.X, pady=(0, 4))
        tk.Label(filters, text="Type:", bg=self.BANNER_BG, fg="#f0e6d2").pack(side=tk.LEFT)
        self.kind_box = ttk.Combobox(filters, state="readonly", width=42)
        self.kind_box.pack(side=tk.LEFT, padx=(4, 12))
        tk.Label(filters, text="Book:", bg=self.BANNER_BG, fg="#f0e6d2").pack(side=tk.LEFT)
        self.book_box = ttk.Combobox(filters, state="readonly", width=22)
        self.book_box.pack(side=tk.LEFT, padx=4)
        self.kind_box.bind("<<ComboboxSelected>>", lambda e: self._apply_filter())
        self.book_box.bind("<<ComboboxSelected>>", lambda e: self._apply_filter())
        self._kind_choice, self._book_choice = None, None
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

        right = tk.Frame(bar, bg=self.BANNER_BG)
        right.pack(side=tk.RIGHT, padx=8, pady=6)
        self.counter = tk.Label(right, text="", bg=self.BANNER_BG, fg="#f0e6d2", font=("Helvetica", 10))
        self.counter.grid(row=0, column=0, columnspan=5, sticky="e")
        ttk.Button(right, text="◀ Issue", command=self._prev_item).grid(row=1, column=0, padx=2)
        ttk.Button(right, text="Issue ▶", command=self._next_item).grid(row=1, column=1, padx=2)
        ttk.Button(right, text="✓ Resolved", command=lambda: self._mark("resolved")).grid(row=1, column=2, padx=2)
        ttk.Button(right, text="Skip", command=lambda: self._mark("skipped")).grid(row=1, column=3, padx=2)
        ttk.Button(right, text="↺ Reopen", command=self._reopen).grid(row=1, column=4, padx=2)
        ttk.Button(right, text="+ Verse", command=self._add_verse).grid(row=2, column=0, padx=2, pady=(4, 0))
        ttk.Button(right, text="+ Comment", command=self._add_commentary).grid(row=2, column=1, padx=2, pady=(4, 0))
        ttk.Button(right, text="+ Footnote", command=self._add_footnote).grid(row=2, column=2, padx=2, pady=(4, 0))
        ttk.Button(right, text="Delete…", command=self._delete_entry).grid(row=2, column=3, padx=2, pady=(4, 0))
        ttk.Button(right, text="Reorder…", command=self._reorder).grid(row=2, column=4, padx=2, pady=(4, 0))

        for seq in ("<Command-Return>", "<Control-Return>"):
            self.root.bind(seq, lambda e: self._mark("resolved") or "break")
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
        self._commit_and_rebuild()

    def _load_page(self, page_num):
        super()._load_page(page_num)
        self._refresh_banner()

    # --- Type / book selectors ---
    def _fill_filters(self):
        """Choices with the number of issues not yet resolved, in queue order."""
        def left(pred):
            return sum(1 for it in self.all_items if pred(it) and self.progress.status(it["id"]) != "resolved")
        kinds = list(dict.fromkeys(it["kind"] for it in self.all_items))
        books = list(dict.fromkeys(sorted(it["book_dir"] for it in self.all_items)))
        self._kind_values = [None] + kinds
        self._book_values = [None] + books
        # each list counts within the other selector's choice
        in_book = lambda it: self._book_choice is None or it["book_dir"] == self._book_choice
        of_kind = lambda it: self._kind_choice is None or it["kind"] == self._kind_choice
        self.kind_box["values"] = [f"All types ({left(in_book)})"] + [
            f"{KIND_LABELS.get(k, k)} ({left(lambda it, k=k: it['kind'] == k and in_book(it))})" for k in kinds]
        self.book_box["values"] = [f"All books ({left(of_kind)})"] + [
            f"{b} ({left(lambda it, b=b: it['book_dir'] == b and of_kind(it))})" for b in books]
        self.kind_box.current(self._kind_values.index(self._kind_choice))
        self.book_box.current(self._book_values.index(self._book_choice))

    def _apply_filter(self):
        kind = self._kind_values[self.kind_box.current()]
        book = self._book_values[self.book_box.current()]
        items = [it for it in self.all_items
                 if (kind is None or it["kind"] == kind) and (book is None or it["book_dir"] == book)]
        if not items:
            messagebox.showinfo("Queue", "No issues of this type in this book.")
            self._fill_filters()
            return
        self._kind_choice, self._book_choice = kind, book
        self.items = items
        start = next((i for i, it in enumerate(items) if not self.progress.status(it["id"])),
                     next((i for i, it in enumerate(items) if self.progress.status(it["id"]) != "resolved"), 0))
        self._goto_item(start)

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
        skipped = sum(1 for o in self.items if self.progress.status(o["id"]) == "skipped")
        self.counter.config(text=f"issue {self.item_idx + 1}/{len(self.items)} · {self._open_count()} open · {skipped} skipped")
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
            if self.progress.status(self.items[i]["id"]) != "resolved":
                return self._goto_item(i)
        messagebox.showinfo("Queue", "No open or skipped issues after this one.")

    def _prev_item(self):
        for i in range(self.item_idx - 1, -1, -1):
            if self.progress.status(self.items[i]["id"]) != "resolved":
                return self._goto_item(i)

    def _mark(self, status):
        if self.dirty:
            self._save()
            if self.dirty:  # the save failed (error shown): stay on the page, nothing lost
                return
        self.progress.set(self.items[self.item_idx]["id"], status)
        self._refresh_banner()
        self._next_item()

    def _reopen(self):
        """Clear the status of the current issue (undo a Skip or a Resolved)."""
        self.progress.set(self.items[self.item_idx]["id"], None)
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
        verses.insert(pos, {"verse_number": n, "chapter": self._neighbour_chapter(verses, pos),
                            "latin": "", "french": "", "annotations": None})
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
        print(f"No queue found at {QUEUE_FILE}. Run audit_integrity.py first.")
        sys.exit(1)
    if not items:
        print("Nothing to review with these filters.")
        sys.exit(0)
    progress = Progress(PROGRESS_FILE)
    for flag in ("--skipped", "--resolved"):
        if flag in args:
            items = [it for it in items if progress.status(it["id"]) == flag[2:]]
    if not items:
        print("Nothing to review with these filters.")
        sys.exit(0)
    print(f"{len(items)} issues, {sum(1 for it in items if not progress.status(it['id']))} open")
    root = tk.Tk()
    ReviewEditor(root, items, progress)
    root.mainloop()
