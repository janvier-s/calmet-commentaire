#!/usr/bin/env python3
"""
Page Editor GUI — view source images alongside editable normalized JSON.
Usage: python page_editor.py [book_dir] [page_number]
       python page_editor.py --resume
  e.g. python page_editor.py 01_genese 487
"""

import tkinter as tk
from tkinter import ttk, messagebox, Text
import json
import re
import subprocess
import sys
import time
import shutil
from pathlib import Path
from PIL import Image, ImageTk

from calmet import latin_case
from punctuation import clean_page

from page_text import (DATA_DIR, LRM, trim, isolate_hebrew, italic_runs,
                       toggle_italics, find_source_image, save_state, load_state)


class FileSelector:
    """Initial screen to pick a book and page."""

    def __init__(self, master, callback):
        self.master = master
        self.callback = callback
        self.books = {}
        self.pages = []

        self.frame = ttk.Frame(self.master, padding="20")
        self.frame.pack(fill=tk.BOTH, expand=True)

        self._discover_books()
        self._setup_widgets()

    def _discover_books(self):
        if not DATA_DIR.is_dir():
            messagebox.showerror("Error", f"Data directory not found: {DATA_DIR}")
            return
        for d in sorted(DATA_DIR.iterdir()):
            norm = d / "normalized"
            if d.is_dir() and norm.is_dir() and any(norm.glob("page_*.json")):
                self.books[d.name] = d

    def _setup_widgets(self):
        ttk.Label(self.frame, text="Select a Book:", font=("Helvetica", 13, "bold")).pack(pady=5)
        self.book_var = tk.StringVar()
        self.book_combo = ttk.Combobox(
            self.frame, textvariable=self.book_var,
            values=list(self.books.keys()), state="readonly", width=30
        )
        self.book_combo.pack(pady=5)
        self.book_combo.bind("<<ComboboxSelected>>", self._on_book_select)

        ttk.Label(self.frame, text="Page number:", font=("Helvetica", 13, "bold")).pack(pady=(15, 5))
        self.page_var = tk.StringVar()
        self.page_combo = ttk.Combobox(
            self.frame, textvariable=self.page_var, state="disabled", width=30
        )
        self.page_combo.pack(pady=5)

        self.start_button = ttk.Button(
            self.frame, text="Open Page", command=self._start, state="disabled"
        )
        self.start_button.pack(pady=20, ipadx=10, ipady=5)

    def _on_book_select(self, event=None):
        book_path = self.books.get(self.book_var.get())
        if not book_path:
            return
        norm_dir = book_path / "normalized"
        pages = []
        for f in norm_dir.glob("page_*.json"):
            m = re.search(r"page_(\d+)\.json$", f.name)
            if m:
                pages.append(int(m.group(1)))
        self.pages = sorted(pages)
        self.page_combo["values"] = self.pages
        self.page_combo.config(state="normal")
        self.page_var.set("")
        self.start_button.config(state="normal")

    def _start(self):
        book_name = self.book_var.get()
        page_str = self.page_var.get().strip()
        if not book_name:
            messagebox.showwarning("Missing", "Select a book.")
            return
        book_path = self.books[book_name]
        if not page_str:
            page_num = self.pages[0] if self.pages else None
        else:
            try:
                page_num = int(page_str)
            except ValueError:
                messagebox.showwarning("Invalid", "Enter a valid page number.")
                return

        if page_num is None or page_num not in self.pages:
            messagebox.showwarning("Not found", f"Page {page_num} not in normalized directory.")
            return

        self.frame.destroy()
        self.callback(book_path, page_num, self.pages)


def keypad_enter_as_return(root):
    """The numeric keypad's Enter does whatever Return does (with or without Cmd/Ctrl/Shift)."""
    def relay(event, mods):
        event.widget.event_generate(f"<{mods}Return>")
        return "break"
    for mods in ("", "Command-", "Control-", "Shift-"):
        for cls in ("Text", "Entry", "TEntry", "TCombobox", "Spinbox", "TSpinbox", "all"):
            root.bind_class(cls, f"<{mods}KP_Enter>", lambda e, m=mods: relay(e, m))


class PageEditor:
    """Main editor: source image on the left, editable JSON on the right."""

    FIELD_COLORS = {
        "verse_number": "#6ec6ff",
        "chapter": "#6ec6ff",
        "latin": "#c0c0c0",
        "french": "#ffffff",
        "annotations": "#aaaaaa",
        "commentary_id": "#6ec6ff",
        "verse_ref": "#6ec6ff",
        "latin_quote": "#e8c87a",
        "french_translation": "#d4a5e8",
        "french_commentary": "#c8c8c8",
        "marker": "#ff9966",
        "text": "#ffcc66",
    }
    # Printed in italics throughout: here _underscored_ stretches show in roman
    ITALIC_FIELDS = {"chapter_summary", "latin", "french_translation"}


    def __init__(self, root, book_path, page_num, all_pages):
        self.root = root
        keypad_enter_as_return(root)
        self.book_path = book_path
        self.page_num = page_num
        self.all_pages = all_pages
        self.page_idx = all_pages.index(page_num)
        self.data = None
        self.dirty = False
        self.field_widgets = []
        self.photo_image = None
        self.current_pil_img = None
        self.current_img_path = None
        self.zoom_factor = 1.0
        self._img_drag_active = False
        self._last_paste = {"text": None, "time": 0, "widget": None}
        self._last_text = None  # the field the italic button acts on
        self.show_marks = tk.BooleanVar(value=True)
        self.section_filter = tk.StringVar(value="All")

        self._define_styles()
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.update_idletasks()
        self.root.after(100, lambda: self._load_page(self.page_num))

    def _define_styles(self):
        self.BG = "#1e1e1e"
        self.PANEL_BG = "#252525"
        self.FIELD_BG = "#2d2d2d"
        self.FG = "#e0e0e0"
        self.ACCENT = "#569cd6"
        self.SAVE_COLOR = "#5af95c"
        self.WARN_COLOR = "#ff6565"
        self.PREV_COMM_BG = "#1a2a1a"
        self.NEXT_COMM_BG = "#1a1a2a"

        self.root.configure(bg=self.BG)
        self.root.geometry("1600x1000")

        self.style = ttk.Style(self.root)
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass
        self.style.configure("TFrame", background=self.BG)
        self.style.configure("TLabel", background=self.BG, foreground=self.FG, font=("Helvetica", 10))
        self.style.configure("TButton", background="#444", foreground=self.FG, font=("Helvetica", 10))
        self.style.map("TButton", background=[("active", "#666")])
        self.style.configure("Header.TLabel", font=("Helvetica", 12, "bold"), foreground=self.ACCENT)
        self.style.configure("Italic.TButton", font=("Helvetica", 12, "bold italic"))
        self.style.configure("TCheckbutton", background=self.BG, foreground=self.FG, font=("Helvetica", 10))
        self.style.map("TCheckbutton", background=[("active", self.BG)])

    def _build_ui(self):
        # Top bar
        top = ttk.Frame(self.root)
        top.pack(fill=tk.X, padx=10, pady=5)

        self.prev_btn = ttk.Button(top, text="< Prev (Left)", command=self._prev_page)
        self.prev_btn.pack(side=tk.LEFT, padx=5)

        self.page_label = ttk.Label(top, text="", style="Header.TLabel")
        self.page_label.pack(side=tk.LEFT, padx=15)

        self.next_btn = ttk.Button(top, text="Next (Right) >", command=self._next_page)
        self.next_btn.pack(side=tk.LEFT, padx=5)

        ttk.Button(top, text="I", width=2, style="Italic.TButton", takefocus=False,
                   command=self._toggle_italic).pack(side=tk.LEFT, padx=(15, 2))
        ttk.Checkbutton(top, text="Show _ marks", variable=self.show_marks,
                        command=self._on_show_marks).pack(side=tk.LEFT, padx=5)

        ttk.Label(top, text="Section:").pack(side=tk.LEFT, padx=(12, 2))
        self.section_box = ttk.Combobox(top, textvariable=self.section_filter, state="readonly", width=12,
                                        values=["All", "Verses", "Commentary", "Footnotes"])
        self.section_box.pack(side=tk.LEFT, padx=2)
        self.section_box.bind("<<ComboboxSelected>>", lambda e: self._build_json_editor())

        self.save_btn = ttk.Button(top, text="Save (Cmd+S)", command=self._save)
        self.save_btn.pack(side=tk.RIGHT, padx=5)

        self.flag_btn = ttk.Button(top, text="Flag for Review", command=self._flag_for_review)
        self.flag_btn.pack(side=tk.RIGHT, padx=5)

        self.open_png_btn = ttk.Button(top, text="Open PNG", command=self._open_png)
        self.open_png_btn.pack(side=tk.RIGHT, padx=5)

        self.open_btn = ttk.Button(top, text="Open JSON", command=self._open_in_editor)
        self.open_btn.pack(side=tk.RIGHT, padx=5)

        self.dirty_label = ttk.Label(top, text="", foreground=self.SAVE_COLOR)
        self.dirty_label.pack(side=tk.RIGHT, padx=10)

        ttk.Label(top, text="Go to page:").pack(side=tk.RIGHT, padx=(10, 2))
        self.jump_var = tk.StringVar()
        jump_entry = ttk.Entry(top, textvariable=self.jump_var, width=6)
        jump_entry.pack(side=tk.RIGHT)
        jump_entry.bind("<Return>", self._jump_to_page)

        ttk.Label(top, text="Image overlay:").pack(side=tk.RIGHT, padx=(10, 2))
        self.overlay_var = tk.IntVar(value=10)
        overlay_scale = ttk.Scale(top, from_=0, to=100, orient=tk.HORIZONTAL,
                                   variable=self.overlay_var, command=self._on_overlay_change,
                                   length=120)
        overlay_scale.pack(side=tk.RIGHT, padx=5)
        self.overlay_label = ttk.Label(top, text="10%", width=4)
        self.overlay_label.pack(side=tk.RIGHT, padx=(0, 5))

        # Main paned window
        self.paned = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, bg=self.BG,
                                     sashwidth=6, sashrelief=tk.RAISED)
        self.paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Left: image
        self.img_frame = tk.Frame(self.paned, bg=self.PANEL_BG)
        self.paned.add(self.img_frame, minsize=400, width=700)

        self.img_toolbar = tk.Frame(self.img_frame, bg=self.PANEL_BG)
        self.img_toolbar.pack(side=tk.TOP, fill=tk.X, padx=6, pady=(3, 2))

        tk.Label(self.img_toolbar, text="Zoom:", bg=self.PANEL_BG, fg="#ccc",
                 font=("Helvetica", 9, "bold")).pack(side=tk.LEFT, padx=(2, 4))
        ttk.Button(self.img_toolbar, text="−", width=3,
                   command=self._zoom_out).pack(side=tk.LEFT, padx=1)
        self.zoom_label = tk.Label(self.img_toolbar, text="100%", bg=self.PANEL_BG, fg=self.FG,
                                   font=("Helvetica", 9, "bold"), width=5)
        self.zoom_label.pack(side=tk.LEFT, padx=2)
        ttk.Button(self.img_toolbar, text="+", width=3,
                   command=self._zoom_in).pack(side=tk.LEFT, padx=1)
        ttk.Button(self.img_toolbar, text="Fit", width=4,
                   command=self._zoom_fit).pack(side=tk.LEFT, padx=(6, 2))
        ttk.Button(self.img_toolbar, text="1:1", width=4,
                   command=self._zoom_actual).pack(side=tk.LEFT, padx=2)
        tk.Label(self.img_toolbar, text="(Drag to pan · Cmd+scroll)",
                 bg=self.PANEL_BG, fg="#888", font=("Helvetica", 8)).pack(side=tk.RIGHT, padx=4)

        self.img_canvas = tk.Canvas(self.img_frame, bg=self.PANEL_BG, highlightthickness=0, cursor="hand2")
        self.img_scrollbar_y = ttk.Scrollbar(self.img_frame, orient=tk.VERTICAL, command=self.img_canvas.yview)
        self.img_scrollbar_x = ttk.Scrollbar(self.img_frame, orient=tk.HORIZONTAL, command=self.img_canvas.xview)
        self.img_canvas.configure(yscrollcommand=self.img_scrollbar_y.set,
                                   xscrollcommand=self.img_scrollbar_x.set)
        self.img_scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.img_scrollbar_x.pack(side=tk.BOTTOM, fill=tk.X)
        self.img_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.img_canvas.bind("<ButtonPress-1>", self._on_img_press)
        self.img_canvas.bind("<B1-Motion>", self._on_img_drag)
        self.img_canvas.bind("<ButtonRelease-1>", self._on_img_release)
        self.img_canvas.bind("<ButtonPress-2>", self._on_img_press)
        self.img_canvas.bind("<B2-Motion>", self._on_img_drag)
        self.img_canvas.bind("<ButtonRelease-2>", self._on_img_release)
        self.img_canvas.bind("<Double-Button-1>", self._on_img_double_click)
        self.img_canvas.bind("<Configure>", self._on_img_canvas_configure)

        self.no_img_label = tk.Label(self.img_canvas, text="No source image found",
                                      bg=self.PANEL_BG, fg="#888", font=("Helvetica", 14))

        # Right: JSON editor (scrollable vertically only)
        self.json_frame = tk.Frame(self.paned, bg=self.BG)
        self.paned.add(self.json_frame, minsize=400)

        self.json_canvas = tk.Canvas(self.json_frame, bg=self.BG, highlightthickness=0)
        self.json_scrollbar = ttk.Scrollbar(self.json_frame, orient=tk.VERTICAL,
                                             command=self.json_canvas.yview)
        self.json_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.json_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.json_canvas.configure(yscrollcommand=self.json_scrollbar.set)

        self.json_inner = tk.Frame(self.json_canvas, bg=self.BG)
        self.json_canvas_window = self.json_canvas.create_window((0, 0), window=self.json_inner, anchor="nw")
        self.json_inner.bind("<Configure>", self._on_inner_configure)
        self.json_canvas.bind("<Configure>", self._on_json_canvas_resize)

        # Key bindings
        self.root.bind("<Left>", self._on_left_key)
        self.root.bind("<Right>", self._on_right_key)
        self.root.bind("<Command-s>", lambda e: self._save() or "break")
        self.root.bind("<Command-S>", lambda e: self._save() or "break")
        self.root.bind("<Control-s>", lambda e: self._save() or "break")
        self.root.bind("<Control-S>", lambda e: self._save() or "break")
        for seq in ("<Command-plus>", "<Command-equal>", "<Control-plus>", "<Control-equal>"):
            self.root.bind(seq, lambda e: self._zoom_in() or "break")
        for seq in ("<Command-minus>", "<Control-minus>"):
            self.root.bind(seq, lambda e: self._zoom_out() or "break")
        for seq in ("<Command-0>", "<Control-0>"):
            self.root.bind(seq, lambda e: self._zoom_fit() or "break")

        # Scroll: global intercept, route to correct pane. "break" prevents
        # child Text widgets from also scrolling their own viewport.
        self._setup_scroll()

    def _on_overlay_change(self, value):
        """Update overlay when slider changes."""
        opacity = int(float(value))
        self.overlay_label.config(text=f"{opacity}%")
        self._render_image(preserve_view=True)

    def _on_left_key(self, event):
        if isinstance(event.widget, Text):
            return
        self._prev_page()

    def _on_right_key(self, event):
        if isinstance(event.widget, Text):
            return
        self._next_page()

    def _on_inner_configure(self, event):
        if hasattr(self, '_scroll_region_after'):
            self.root.after_cancel(self._scroll_region_after)
        self._scroll_region_after = self.root.after(
            50, lambda: self.json_canvas.configure(scrollregion=self.json_canvas.bbox("all"))
        )

    def _on_json_canvas_resize(self, event):
        self.json_canvas.itemconfig(self.json_canvas_window, width=event.width - 20)

    def _setup_scroll(self):
        """Global scroll intercept — routes all scroll to the correct canvas pane."""

        def _which_canvas(event):
            try:
                sash_x = self.paned.sash_coord(0)[0]
                pane_x = event.x_root - self.paned.winfo_rootx()
            except Exception:
                pane_x = event.x_root - self.root.winfo_rootx()
                sash_x = self.root.winfo_width() // 2
            return self.img_canvas if pane_x < sash_x else self.json_canvas

        self._scroll_accum = {"x": 0.0, "y": 0.0}
        PIXELS_PER_UNIT = 20

        def _on_touchpad_scroll(event):
            canvas = _which_canvas(event)
            d = event.delta
            y = d & 0xFFFF
            if y > 32767:
                y -= 65536
            x = (d >> 16) & 0xFFFF
            if x > 32767:
                x -= 65536
            self._scroll_accum["y"] += y
            self._scroll_accum["x"] += x
            units_y = int(self._scroll_accum["y"] / PIXELS_PER_UNIT)
            units_x = int(self._scroll_accum["x"] / PIXELS_PER_UNIT)
            if units_y != 0:
                canvas.yview_scroll(-units_y, "units")
                self._scroll_accum["y"] -= units_y * PIXELS_PER_UNIT
            if units_x != 0 and canvas is self.img_canvas:
                canvas.xview_scroll(-units_x, "units")
                self._scroll_accum["x"] -= units_x * PIXELS_PER_UNIT
            else:
                self._scroll_accum["x"] = 0
            return "break"

        def _on_mousewheel(event):
            canvas = _which_canvas(event)
            # If over image canvas and Command or Control is held, zoom
            if canvas is self.img_canvas and ((event.state & 0x4) or (event.state & 0x8) or (event.state & 0x10)):
                focus = (event.x_root - self.img_canvas.winfo_rootx(),
                         event.y_root - self.img_canvas.winfo_rooty())
                if event.delta > 0:
                    self._zoom_in(focus_point=focus)
                elif event.delta < 0:
                    self._zoom_out(focus_point=focus)
                return "break"
            d = event.delta
            if abs(d) >= 120:
                units = -(d // 120)
            else:
                units = -d
            canvas.yview_scroll(units * 3, "units")
            return "break"

        def _on_shift_mousewheel(event):
            canvas = _which_canvas(event)
            d = event.delta
            if abs(d) >= 120:
                units = -(d // 120)
            else:
                units = -d
            if canvas is self.img_canvas:
                canvas.xview_scroll(units * 3, "units")
            return "break"

        self.root.bind_all("<TouchpadScroll>", _on_touchpad_scroll)
        self.root.bind_all("<MouseWheel>", _on_mousewheel)
        self.root.bind_all("<Shift-MouseWheel>", _on_shift_mousewheel)
        self.img_canvas.bind("<Command-MouseWheel>", self._on_img_mousewheel_zoom)
        self.img_canvas.bind("<Control-MouseWheel>", self._on_img_mousewheel_zoom)

    # --- Prev/Next page commentary context ---
    def _get_next_page_commentary_head(self):
        if not self.data:
            return None
        if self.page_idx >= len(self.all_pages) - 1:
            return None

        next_page = self.all_pages[self.page_idx + 1]
        next_path = self.book_path / "normalized" / f"page_{next_page:04d}.json"
        try:
            with open(next_path, "r", encoding="utf-8") as f:
                next_data = json.load(f)
            next_comms = next_data.get("commentary", [])
            if not next_comms:
                return None
            first_comm = next_comms[0]
            fc = first_comm.get("french_commentary") or ""
            head = fc[:250] + ("..." if len(fc) > 250 else "")
            is_continuation = (
                first_comm.get("commentary_id") == 1
                and first_comm.get("verse_ref") is None
                and first_comm.get("latin_quote") is None
                and first_comm.get("french_translation") is None
            )
            return {
                "page": next_page,
                "commentary_id": first_comm.get("commentary_id"),
                "verse_ref": first_comm.get("verse_ref"),
                "head": head,
                "is_continuation": is_continuation,
            }
        except Exception:
            return None

    def _get_prev_page_commentary_tail(self):
        if not self.data:
            return None
        comms = self.data.get("commentary", [])
        if not comms:
            return None

        first = comms[0]
        # Check if first commentary is a continuation (no latin_quote and no french_translation)
        if (first.get("latin_quote") is None
                and first.get("french_translation") is None):
            if self.page_idx <= 0:
                return None
            prev_page = self.all_pages[self.page_idx - 1]
            prev_path = self.book_path / "normalized" / f"page_{prev_page:04d}.json"
            try:
                with open(prev_path, "r", encoding="utf-8") as f:
                    prev_data = json.load(f)
                prev_comms = prev_data.get("commentary", [])
                if prev_comms:
                    last_comm = prev_comms[-1]
                    fc = last_comm.get("french_commentary") or ""
                    # Get just the last line, limited to 7 words
                    lines = fc.strip().split('\n')
                    last_line = lines[-1] if lines else ""
                    words = last_line.split()
                    tail = " ".join(words[-7:]) if len(words) > 7 else last_line
                    return {
                        "page": prev_page,
                        "commentary_id": last_comm.get("commentary_id"),
                        "verse_ref": last_comm.get("verse_ref"),
                        "tail": f"...{tail}",
                    }
            except Exception:
                pass
        return None

    # --- Page loading ---
    def _load_page(self, page_num):
        if self.dirty:
            if messagebox.askyesno("Unsaved changes", "Save changes before leaving?"):
                self._save()

        self.page_num = page_num
        self.page_idx = self.all_pages.index(page_num)
        self.dirty = False
        self.field_widgets = []

        page_str = f"{page_num:04d}"
        json_path = self.book_path / "normalized" / f"page_{page_str}.json"
        self.json_path = json_path

        self.root.title(f"Page Editor -- {self.book_path.name} / page_{page_str}")
        self.page_label.config(
            text=f"{self.book_path.name}  --  page {page_num}  ({self.page_idx + 1}/{len(self.all_pages)})"
        )
        self.dirty_label.config(text="")

        # Persist state for --resume
        save_state(self.book_path.name, page_num)

        # Load JSON
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                self.data = json.load(f)
        except Exception as e:
            self.data = None
            messagebox.showerror("Error", f"Failed to load {json_path}:\n{e}")
            return

        self._load_image(page_num)
        self._build_json_editor()

        self.dirty = False
        self.dirty_label.config(text="")

        self.json_inner.update_idletasks()
        self.json_canvas.configure(scrollregion=self.json_canvas.bbox("all"))
        self.json_canvas.yview_moveto(0)

    ZOOM_STEPS = (0.5, 0.65, 0.8, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 4.0)

    def _load_image(self, page_num):
        self.img_canvas.delete("all")
        img_path = find_source_image(self.book_path, page_num)
        if img_path is None:
            self.no_img_label.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
            self.photo_image = None
            self.current_pil_img = None
            self.current_img_path = None
            return
        self.no_img_label.place_forget()

        try:
            if getattr(self, "current_img_path", None) != img_path or self.current_pil_img is None:
                self.current_pil_img = Image.open(img_path).convert("RGB")
                self.current_img_path = img_path
            self._render_image(preserve_view=False)
        except Exception as e:
            self.current_pil_img = None
            self.current_img_path = None
            self.no_img_label.config(text=f"Image load error: {e}")
            self.no_img_label.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

    def _render_image(self, preserve_view=True, focus_point=None):
        if self.current_pil_img is None:
            return

        canvas_w = self.img_canvas.winfo_width()
        if canvas_w <= 10:
            canvas_w = 700
        canvas_h = self.img_canvas.winfo_height()
        if canvas_h <= 10:
            canvas_h = 900

        fit_scale = canvas_w / self.current_pil_img.width
        scale = fit_scale * self.zoom_factor
        new_w = max(50, min(8000, int(self.current_pil_img.width * scale)))
        new_h = max(50, min(12000, int(self.current_pil_img.height * scale)))

        old_scrollregion = self.img_canvas.cget("scrollregion")
        old_w, old_h = 0, 0
        if old_scrollregion:
            try:
                coords = [float(c) for c in old_scrollregion.split()]
                if len(coords) == 4:
                    old_w, old_h = coords[2], coords[3]
            except Exception:
                pass

        if focus_point and old_w > 0 and old_h > 0:
            fx, fy = focus_point
            world_x = self.img_canvas.canvasx(fx)
            world_y = self.img_canvas.canvasy(fy)
            rx = world_x / old_w
            ry = world_y / old_h
        elif preserve_view:
            x_view = self.img_canvas.xview()
            y_view = self.img_canvas.yview()
            rx = (x_view[0] + x_view[1]) / 2.0
            ry = (y_view[0] + y_view[1]) / 2.0
        else:
            rx, ry = None, None

        resized_pil = self.current_pil_img.resize((new_w, new_h), Image.LANCZOS)

        overlay_opacity = self.overlay_var.get()
        if overlay_opacity > 0:
            resized_pil = resized_pil.convert("RGBA")
            overlay = Image.new("RGBA", resized_pil.size, (0, 0, 0, int(255 * overlay_opacity / 100)))
            resized_pil = Image.alpha_composite(resized_pil, overlay).convert("RGB")

        self.photo_image = ImageTk.PhotoImage(resized_pil)
        self.img_canvas.delete("all")
        self.img_canvas.create_image(0, 0, anchor=tk.NW, image=self.photo_image)
        self.img_canvas.configure(scrollregion=(0, 0, new_w, new_h))

        if focus_point and rx is not None:
            fx, fy = focus_point
            target_fx = (rx * new_w - fx) / new_w
            target_fy = (ry * new_h - fy) / new_h
            self.img_canvas.xview_moveto(max(0.0, min(1.0, target_fx)))
            self.img_canvas.yview_moveto(max(0.0, min(1.0, target_fy)))
        elif preserve_view and rx is not None:
            vx = canvas_w / new_w
            vy = canvas_h / new_h
            self.img_canvas.xview_moveto(max(0.0, min(1.0, rx - vx / 2.0)))
            self.img_canvas.yview_moveto(max(0.0, min(1.0, ry - vy / 2.0)))
        else:
            self.img_canvas.xview_moveto(0)
            self.img_canvas.yview_moveto(0)

        if hasattr(self, "zoom_label"):
            self.zoom_label.config(text=f"{int(round(self.zoom_factor * 100))}%")

    def _zoom_in(self, focus_point=None):
        for s in self.ZOOM_STEPS:
            if s > self.zoom_factor + 0.05:
                self.zoom_factor = s
                break
        else:
            self.zoom_factor = min(5.0, round(self.zoom_factor * 1.25, 2))
        self._render_image(preserve_view=True, focus_point=focus_point)

    def _zoom_out(self, focus_point=None):
        for s in reversed(self.ZOOM_STEPS):
            if s < self.zoom_factor - 0.05:
                self.zoom_factor = s
                break
        else:
            self.zoom_factor = max(0.4, round(self.zoom_factor / 1.25, 2))
        self._render_image(preserve_view=True, focus_point=focus_point)

    def _zoom_fit(self):
        self.zoom_factor = 1.0
        self._render_image(preserve_view=True)

    def _zoom_actual(self):
        if self.current_pil_img:
            canvas_w = self.img_canvas.winfo_width()
            if canvas_w <= 10:
                canvas_w = 700
            if canvas_w > 0:
                self.zoom_factor = min(5.0, max(0.5, round(self.current_pil_img.width / canvas_w, 2)))
        else:
            self.zoom_factor = 2.0
        self._render_image(preserve_view=True)

    def _on_img_mousewheel_zoom(self, event):
        focus = (event.x, event.y)
        if event.delta > 0:
            self._zoom_in(focus_point=focus)
        elif event.delta < 0:
            self._zoom_out(focus_point=focus)
        return "break"

    def _on_img_press(self, event):
        self.img_canvas.scan_mark(event.x, event.y)
        self._img_drag_active = True

    def _on_img_drag(self, event):
        if getattr(self, "_img_drag_active", False):
            self.img_canvas.scan_dragto(event.x, event.y, gain=1)

    def _on_img_release(self, event):
        self._img_drag_active = False

    def _on_img_double_click(self, event):
        if abs(self.zoom_factor - 1.0) < 0.1:
            self.zoom_factor = 2.0
            self._render_image(preserve_view=True, focus_point=(event.x, event.y))
        else:
            self._zoom_fit()

    def _on_img_canvas_configure(self, event):
        if abs(self.zoom_factor - 1.0) < 0.01 and self.current_pil_img is not None:
            if hasattr(self, "_img_resize_after"):
                self.root.after_cancel(self._img_resize_after)
            self._img_resize_after = self.root.after(100, lambda: self._render_image(preserve_view=True))

    # --- JSON editor ---
    def _build_json_editor(self):
        for w in self.json_inner.winfo_children():
            w.destroy()
        self.field_widgets = []

        if self.data is None:
            return

        sec = (self.section_filter.get() or "All").lower()
        row = 0

        if sec in ("all",):
            for key in ("book_title", "chapter_number", "chapter_summary", "chapter_intro", "book_end_marker"):
                if key in self.data:
                    row = self._add_field(self.json_inner, row, key, self.data.get(key), (key,))

        verses = self.data.get("verses", [])
        if verses and sec in ("all", "verses"):
            row = self._add_section_header(self.json_inner, row, f"VERSES ({len(verses)})")
            for i, v in enumerate(verses):
                row = self._add_section_header(self.json_inner, row,
                    f"  Verse {v.get('verse_number', '?')}", level=2)
                for field in ("chapter", "verse_number", "latin", "french", "annotations"):
                    if field in v:
                        row = self._add_field(self.json_inner, row, field, v.get(field),
                                              ("verses", i, field))

        comms = self.data.get("commentary", [])
        if comms and sec in ("all", "commentary"):
            row = self._add_section_header(self.json_inner, row, f"COMMENTARY ({len(comms)})")
            prev_tail = self._get_prev_page_commentary_tail()

            for i, c in enumerate(comms):
                vref = c.get("verse_ref", "?")
                # Handle case where verse_ref might be a long string
                if isinstance(vref, str) and len(str(vref)) > 20:
                    vref_display = str(vref)[:20] + "..."
                else:
                    vref_display = vref
                cid = c.get("commentary_id", "?")
                row = self._add_section_header(self.json_inner, row,
                    f"  Commentary {cid} (v.{vref_display})", level=2)
                for field in ("commentary_id", "chapter", "verse_ref", "latin_quote",
                              "french_translation", "french_commentary"):
                    if field == "french_commentary" and i == 0 and prev_tail:
                        row = self._add_prev_commentary_tail(self.json_inner, row, prev_tail)
                    if field in c:
                        row = self._add_field(self.json_inner, row, field, c.get(field),
                                              ("commentary", i, field))

            next_head = self._get_next_page_commentary_head()
            if next_head:
                row = self._add_next_commentary_head(self.json_inner, row, next_head)

        notes = self.data.get("footnotes", [])
        if notes and sec in ("all", "footnotes"):
            row = self._add_section_header(self.json_inner, row, f"FOOTNOTES ({len(notes)})")
            for i, fn in enumerate(notes):
                row = self._add_section_header(self.json_inner, row,
                    f"  {fn.get('marker', '?')}", level=2)
                for field in ("marker", "text"):
                    if field in fn:
                        row = self._add_field(self.json_inner, row, field, fn.get(field),
                                              ("footnotes", i, field))

    def _add_prev_commentary_tail(self, parent, row, prev_tail):
        lbl = tk.Label(parent, text=f"prev p.{prev_tail['page']}\ncomm {prev_tail['commentary_id']}\n(v.{prev_tail['verse_ref']})",
                       bg=self.BG, fg="#66aa66", font=("Helvetica", 8), anchor="ne", justify=tk.RIGHT)
        lbl.grid(row=row, column=0, sticky="ne", padx=(10, 5), pady=1)

        frame = tk.Frame(parent, bg=self.PREV_COMM_BG, bd=1, relief="groove")
        frame.grid(row=row, column=1, sticky="ew", padx=(0, 10), pady=(2, 4))

        txt = Text(frame, wrap=tk.WORD, font=("Helvetica", 10),
                   bg=self.PREV_COMM_BG, fg="#88cc88", relief="flat", bd=3)
        txt.insert("1.0", isolate_hebrew(prev_tail["tail"]))
        self._setup_italic_tags(txt)
        self._render_italics(txt)
        txt.config(state="disabled")
        # Auto-size height
        self._autosize_text(txt)
        txt.pack(fill=tk.BOTH, expand=True)

        content = prev_tail["tail"]
        if content.rstrip().endswith("-"):
            txt.config(state="normal")
            txt.tag_configure("hyphen_end", foreground="#ff6666", font=("Helvetica", 12, "bold"))
            pos = txt.search("-", "end-2c", backwards=True, stopindex="1.0")
            if pos:
                txt.tag_add("hyphen_end", pos, f"{pos}+1c")
            txt.config(state="disabled")

        return row + 1

    def _add_next_commentary_head(self, parent, row, next_head):
        cont_marker = " (CONTINUATION)" if next_head["is_continuation"] else ""

        lbl = tk.Label(parent,
                       text=f"next p.{next_head['page']}\ncomm {next_head['commentary_id']}\n(v.{next_head['verse_ref']})",
                       bg=self.BG, fg="#6688cc", font=("Helvetica", 8), anchor="ne", justify=tk.RIGHT)
        lbl.grid(row=row, column=0, sticky="ne", padx=(10, 5), pady=1)

        frame = tk.Frame(parent, bg=self.NEXT_COMM_BG, bd=1, relief="groove")
        frame.grid(row=row, column=1, sticky="ew", padx=(0, 10), pady=(4, 2))

        if cont_marker:
            tag_lbl = tk.Label(frame, text=cont_marker, bg=self.NEXT_COMM_BG, fg="#ff9944",
                               font=("Helvetica", 8, "bold"), anchor="w")
            tag_lbl.pack(fill=tk.X, padx=5, pady=(2, 0))

        txt = Text(frame, wrap=tk.WORD, font=("Helvetica", 10),
                   bg=self.NEXT_COMM_BG, fg="#8888cc", relief="flat", bd=3)
        txt.insert("1.0", isolate_hebrew(next_head["head"]))
        self._setup_italic_tags(txt)
        self._render_italics(txt)
        txt.config(state="disabled")
        self._autosize_text(txt)
        txt.pack(fill=tk.BOTH, expand=True)

        return row + 1

    def _add_section_header(self, parent, row, text, level=1):
        fg = self.ACCENT if level == 1 else "#999"
        sz = 11 if level == 1 else 10
        weight = "bold" if level == 1 else "normal"
        lbl = tk.Label(parent, text=text, bg=self.BG, fg=fg,
                       font=("Helvetica", sz, weight), anchor="w")
        lbl.grid(row=row, column=0, columnspan=2, sticky="w", padx=5, pady=(8 if level == 1 else 2, 0))
        return row + 1

    def _autosize_text(self, txt, chars_per_line=90):
        """Set Text widget height to fit content using text-length estimation (no layout calls)."""
        content = txt.get("1.0", "end-1c")
        total = 0
        for line in content.split("\n"):
            total += max(1, -(-len(line) // chars_per_line))  # ceil division
        txt.config(height=max(1, total))

    def _add_field(self, parent, row, field_name, value, json_path):
        fg = self.FIELD_COLORS.get(field_name, self.FG)

        lbl = tk.Label(parent, text=field_name, bg=self.BG, fg="#888",
                       font=("Helvetica", 9), anchor="ne")
        lbl.grid(row=row, column=0, sticky="ne", padx=(10, 5), pady=1)

        val_str = "" if value is None else str(value)
        is_null = value is None

        italic_field = field_name in self.ITALIC_FIELDS
        txt = Text(parent, wrap=tk.WORD, font=("Helvetica", 10, "italic" if italic_field else "normal"),
                   bg=self.FIELD_BG, fg=fg, insertbackground=fg,
                   relief="flat", bd=3, undo=True)
        txt.grid(row=row, column=1, sticky="ew", padx=(0, 10), pady=1)
        parent.grid_columnconfigure(1, weight=1)

        if is_null:
            txt.insert("1.0", "null")
            txt.config(fg="#888")
        else:
            txt.insert("1.0", isolate_hebrew(val_str))

        # Auto-size to fit content — no internal scrolling
        self._autosize_text(txt)
        if field_name == "french_commentary" and not val_str.strip():
            txt.config(height=4)  # room to type the comment in

        self._setup_italic_tags(txt, inverse=italic_field)
        self._render_italics(txt)
        if field_name == "latin_quote":
            txt.tag_configure("smallcap", font=("Helvetica", 8))
            self._render_smallcaps(txt)
        txt.edit_modified(False)
        txt.bind("<<Modified>>", lambda e, w=txt: self._on_modified(w))
        txt.bind("<FocusIn>", lambda e, w=txt: setattr(self, "_last_text", w))
        for seq in ("<Command-i>", "<Command-I>", "<Control-i>", "<Control-I>"):
            txt.bind(seq, lambda e, w=txt: self._toggle_italic(w) or "break")
        txt.bind("<Tab>", lambda e, w=txt: self._focus_field(w, 1))
        txt.bind("<Shift-Tab>", lambda e, w=txt: self._focus_field(w, -1))
        # Right click: Button-2 on macOS, Button-3 elsewhere, or Ctrl+click
        for seq in ("<Button-2>", "<Button-3>", "<Control-Button-1>"):
            txt.bind(seq, lambda e, w=txt: self._show_context_menu(e, w))

        # Prevent double paste by handling paste manually with debounce
        def handle_paste(event):
            try:
                text = event.widget.clipboard_get()
                current_time = time.time()

                # Check if this is a duplicate paste (same text, same widget, within 200ms)
                if (self._last_paste["text"] == text and
                    self._last_paste["widget"] == event.widget and
                    current_time - self._last_paste["time"] < 0.2):
                    return "break"

                # Record this paste
                self._last_paste["text"] = text
                self._last_paste["time"] = current_time
                self._last_paste["widget"] = event.widget

                # Perform the paste
                try:
                    event.widget.delete("sel.first", "sel.last")
                except tk.TclError:
                    pass
                event.widget.insert(tk.INSERT, text)
            except:
                pass
            return "break"

        txt.bind("<<Paste>>", handle_paste)
        txt.bind("<Command-v>", handle_paste)
        txt.bind("<Command-V>", handle_paste)
        txt.bind("<Control-v>", handle_paste)
        txt.bind("<Control-V>", handle_paste)

        self.field_widgets.append((json_path, txt, is_null))
        return row + 1

    def _on_modified(self, widget):
        if widget.edit_modified():
            if not self.dirty:
                self.dirty = True
                self.dirty_label.config(text="* unsaved changes", foreground=self.WARN_COLOR)
            widget.edit_modified(False)
            self._render_italics(widget)
            self._render_smallcaps(widget)

    # --- Italics (_underscores_ in the JSON) ---
    def _setup_italic_tags(self, txt, inverse=False):
        txt.tag_configure("italic", font=("Helvetica", 10, "normal" if inverse else "italic"))
        txt.tag_configure("mark", foreground="#5a5a5a", elide=not self.show_marks.get())
        # an unpaired mark: italics carried across a field or page break
        txt.tag_configure("mark_open", foreground="#ff9944")
        txt.tag_raise("mark_open", "mark")

    def _render_italics(self, txt):
        for tag in ("italic", "mark", "mark_open"):
            txt.tag_remove(tag, "1.0", "end")
        s = txt.get("1.0", "end-1c")
        if "_" not in s:
            return
        runs, marks, open_at = italic_runs(s)
        for a, b in runs:
            txt.tag_add("italic", f"1.0+{a}c", f"1.0+{b}c")
        for i in marks:
            txt.tag_add("mark", f"1.0+{i}c")
        if open_at:
            i = marks[0] if open_at == "start" else marks[-1]
            txt.tag_add("mark_open", f"1.0+{i}c")

    def _render_smallcaps(self, txt):
        """latin_quote as the site shows it: small caps, but for the first letter and the
        Vulgate's proper nouns (calmet.latin_case). The text itself stays in capitals."""
        if "smallcap" not in txt.tag_names():
            return
        txt.tag_remove("smallcap", "1.0", "end")
        s = txt.get("1.0", "end-1c")
        cased = latin_case(s)
        if len(cased) != len(s):
            return
        first = next((i for i, c in enumerate(cased) if c.isalpha()), None)
        for i, c in enumerate(cased):
            if c.islower() and i != first:
                txt.tag_add("smallcap", f"1.0+{i}c")

    def _toggle_italic(self, txt=None):
        """Cmd+I / the I button: italicize the selection, or make it roman if already italic."""
        txt = txt or self._last_text
        if txt is None or not txt.winfo_exists() or not txt.tag_ranges("sel"):
            return
        s = txt.get("1.0", "end-1c")
        sa = len(txt.get("1.0", "sel.first"))
        sb = len(txt.get("1.0", "sel.last"))
        result = toggle_italics(s, sa, sb)
        if result is None:
            return
        new, start, end = result
        # Replace only the stretch that changed, as one undo step
        p = 0
        while p < min(len(s), len(new)) and s[p] == new[p]:
            p += 1
        q = 0
        while q < min(len(s), len(new)) - p and s[-1 - q] == new[-1 - q]:
            q += 1
        txt.config(autoseparators=False)
        txt.edit_separator()
        txt.delete(f"1.0+{p}c", f"1.0+{len(s) - q}c")
        txt.insert(f"1.0+{p}c", new[p:len(new) - q])
        txt.edit_separator()
        txt.config(autoseparators=True)
        txt.tag_remove("sel", "1.0", "end")
        txt.tag_add("sel", f"1.0+{start}c", f"1.0+{end}c")
        txt.mark_set("insert", f"1.0+{end}c")
        txt.focus_set()
        self._render_italics(txt)

    # --- Field navigation and context menu ---
    def _focus_field(self, txt, step):
        """Tab / Shift+Tab: move to the next / previous field, its text selected."""
        widgets = [w for _, w, _ in self.field_widgets if w.winfo_exists()]
        if txt not in widgets:
            return "break"
        target = widgets[(widgets.index(txt) + step) % len(widgets)]
        target.focus_set()
        target.tag_remove("sel", "1.0", "end")
        target.tag_add("sel", "1.0", "end-1c")
        target.mark_set("insert", "end-1c")
        self._scroll_into_view(target)
        return "break"

    def _scroll_into_view(self, widget):
        """Scroll the JSON pane just enough for `widget` to be visible."""
        total = self.json_inner.winfo_height()
        if total <= 1:
            return
        top = widget.winfo_y()  # fields are gridded straight into json_inner
        bottom = top + widget.winfo_height()
        view_top = self.json_canvas.canvasy(0)
        view_h = self.json_canvas.winfo_height()
        margin = 30
        if top < view_top + margin:
            self.json_canvas.yview_moveto(max(0, top - margin) / total)
        elif bottom > view_top + view_h - margin:
            # a field taller than the pane is shown from its top
            y = top - margin if bottom - top > view_h - 2 * margin else bottom + margin - view_h
            self.json_canvas.yview_moveto(max(0, y) / total)

    def _show_context_menu(self, event, txt):
        txt.focus_set()
        has_sel = bool(txt.tag_ranges("sel"))
        if not has_sel:
            txt.mark_set("insert", f"@{event.x},{event.y}")
        sel_state = tk.NORMAL if has_sel else tk.DISABLED
        menu = tk.Menu(txt, tearoff=0)
        menu.add_command(label="Cut", accelerator="Cmd+X", state=sel_state,
                         command=lambda: txt.event_generate("<<Cut>>"))
        menu.add_command(label="Copy", accelerator="Cmd+C", state=sel_state,
                         command=lambda: txt.event_generate("<<Copy>>"))
        menu.add_command(label="Paste", accelerator="Cmd+V",
                         command=lambda: txt.event_generate("<<Paste>>"))
        menu.add_separator()
        menu.add_command(label="Italics", accelerator="Cmd+I", state=sel_state,
                         command=lambda: self._toggle_italic(txt))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _on_show_marks(self):
        for _, txt, _ in self.field_widgets:
            txt.tag_configure("mark", elide=not self.show_marks.get())

    def _open_in_editor(self):
        """Open the current JSON file in the default editor (VSCode / system default)."""
        if not hasattr(self, 'json_path') or not self.json_path:
            return
        try:
            subprocess.Popen(["code", str(self.json_path)])
        except FileNotFoundError:
            subprocess.Popen(["open", str(self.json_path)])

    def _open_png(self):
        """Reveal the current PNG source image in Finder."""
        img_path = find_source_image(self.book_path, self.page_num)
        if img_path is None or not img_path.exists():
            messagebox.showwarning("No Image", "No source image found for this page.")
            return
        try:
            subprocess.Popen(["open", "-R", str(img_path)])
        except Exception as e:
            messagebox.showerror("Error", f"Failed to reveal image:\n{e}")

    def _flag_for_review(self):
        """Copy the page's raw_json file and its scan to the modernization_error folder."""
        page_str = f"{self.page_num:04d}"
        raw_json_path = self.book_path / "raw_json" / "commentaire" / f"page_{page_str}.json"
        img_path = find_source_image(self.book_path, self.page_num)
        sources = [p for p in (raw_json_path, img_path) if p is not None and p.exists()]

        if not sources:
            messagebox.showwarning("Not Found", f"Neither the raw JSON nor the scan was found for page {self.page_num}.")
            return

        # Create modernization_error folder
        error_dir = self.book_path / "modernization_error"
        error_dir.mkdir(exist_ok=True)

        # Copy files (page_NNNN.json and page_NNNN.png side by side)
        try:
            copied = []
            for src in sources:
                dest_path = error_dir / f"page_{page_str}{src.suffix}"
                shutil.copy(src, dest_path)
                copied.append(dest_path.name)
            missing = [] if raw_json_path.exists() else ["raw JSON"]
            missing += [] if img_path is not None and img_path.exists() else ["scan"]
            note = f"\n\nNot found: {', '.join(missing)}" if missing else ""
            messagebox.showinfo("Flagged", f"Page {self.page_num} copied to:\n{error_dir}\n\n{', '.join(copied)}{note}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to copy file:\n{e}")

    # --- Save ---
    def _save(self):
        if self.data is None:
            return

        for json_path, widget, was_null in self.field_widgets:
            raw = widget.get("1.0", "end-1c").replace(LRM, "")

            if raw.strip() == "null" or (raw.strip() == "" and was_null):
                val = None
            else:
                field_name = json_path[-1]
                if field_name in ("verse_number", "commentary_id", "verse_ref", "chapter_number", "chapter"):
                    try:
                        val = int(raw.strip())
                    except ValueError:
                        val = None if raw.strip() == "null" else raw
                else:
                    val = raw

            obj = self.data
            for key in json_path[:-1]:
                obj = obj[key]
            obj[json_path[-1]] = val

        self.data = trim(clean_page(self.data))  # punctuation.py rules, then the ends trimmed
        try:
            with open(self.json_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            self.dirty = False
            self.dirty_label.config(text="saved", foreground=self.SAVE_COLOR)
        except Exception as e:
            messagebox.showerror("Save Error", str(e))

    # --- Navigation ---
    def _prev_page(self):
        if self.page_idx > 0:
            self._load_page(self.all_pages[self.page_idx - 1])

    def _next_page(self):
        if self.page_idx < len(self.all_pages) - 1:
            self._load_page(self.all_pages[self.page_idx + 1])

    def _jump_to_page(self, event=None):
        try:
            target = int(self.jump_var.get().strip())
        except ValueError:
            return
        if target in self.all_pages:
            self._load_page(target)
        else:
            messagebox.showwarning("Not found", f"Page {target} not in normalized directory.")

    def _on_close(self):
        if self.dirty:
            result = messagebox.askyesnocancel(
                "Unsaved changes",
                "You have unsaved changes. Do you want to save before closing?",
                icon='warning'
            )
            if result is None:  # Cancel
                return
            elif result:  # Yes - save
                self._save()
            # else: No - don't save, just close
        self.root.destroy()


class App:
    def __init__(self, root, book_dir=None, page_num=None):
        self.root = root
        self.root.title("Page Editor")

        if book_dir:
            book_path = DATA_DIR / book_dir
            if not book_path.is_dir():
                messagebox.showerror("Error", f"Book directory not found: {book_path}")
                sys.exit(1)
            norm_dir = book_path / "normalized"
            pages = sorted(
                int(re.search(r"page_(\d+)", f.name).group(1))
                for f in norm_dir.glob("page_*.json")
                if re.search(r"page_(\d+)", f.name)
            )
            if page_num and page_num in pages:
                self._start_editor(book_path, page_num, pages)
            elif pages:
                self._start_editor(book_path, pages[0], pages)
            else:
                messagebox.showerror("Error", "No normalized pages found.")
                sys.exit(1)
        else:
            FileSelector(self.root, self._start_editor)

    def _start_editor(self, book_path, page_num, all_pages):
        PageEditor(self.root, book_path, page_num, all_pages)


if __name__ == "__main__":
    resume = "--resume" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--resume"]

    book_dir = args[0] if len(args) > 0 else None
    page_num = int(args[1]) if len(args) > 1 else None

    if resume and not book_dir:
        saved_book, saved_page = load_state()
        if saved_book:
            book_dir = saved_book
            page_num = saved_page
            print(f"Resuming: {book_dir} page {page_num}")

    root = tk.Tk()
    app = App(root, book_dir, page_num)
    try:
        root.mainloop()
    except KeyboardInterrupt:  # Ctrl+C in the terminal: quit quietly
        pass
