"""
Distributed To-Do List — Desktop GUI Client
============================================
Python Tkinter-based desktop client that connects to the Flask server
and receives live updates via Server-Sent Events in a background thread.

Requirements:
    pip install requests

Run:
    python client_gui.py [--server http://localhost:5000]
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import threading
import requests
import json
import time
import argparse
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────
DEFAULT_SERVER = "http://localhost:5000"

# ── Color palette (dark theme) ────────────────────────────────────────────────
COLORS = {
    "bg":        "#0f0f1a",
    "surface":   "#1a1a2e",
    "surface2":  "#16213e",
    "border":    "#2d2d5e",
    "primary":   "#6366f1",
    "success":   "#10b981",
    "danger":    "#ef4444",
    "warn":      "#f59e0b",
    "text":      "#e2e8f0",
    "muted":     "#94a3b8",
    "low":       "#10b981",
    "medium":    "#f59e0b",
    "high":      "#ef4444",
}

PRIORITY_COLORS = {"low": COLORS["low"], "medium": COLORS["warn"], "high": COLORS["danger"]}


class ToDoApp(tk.Tk):
    def __init__(self, server_url):
        super().__init__()
        self.server = server_url.rstrip("/")
        self.title("Distributed To-Do List")
        self.geometry("1000x680")
        self.configure(bg=COLORS["bg"])
        self.minsize(750, 500)

        self.tasks = {}            # id → task dict
        self.filter_var = tk.StringVar(value="all")
        self.connected = False
        self._sse_thread = None
        self._stop_sse = threading.Event()

        self._build_ui()
        self._start_sse()

    # ── UI Construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        self._build_header()
        self._build_stats_bar()
        pane = tk.PanedWindow(self, orient=tk.HORIZONTAL, bg=COLORS["bg"],
                              sashwidth=4, sashrelief=tk.FLAT)
        pane.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        left = self._build_left_panel(pane)
        right = self._build_right_panel(pane)
        pane.add(left, minsize=280)
        pane.add(right, minsize=380)
        pane.paneconfig(left, width=310)

    def _build_header(self):
        hdr = tk.Frame(self, bg=COLORS["surface"], height=54)
        hdr.pack(fill=tk.X)
        hdr.pack_propagate(False)

        tk.Label(hdr, text="✅  Distributed To-Do List",
                 bg=COLORS["surface"], fg=COLORS["text"],
                 font=("Segoe UI", 14, "bold")).pack(side=tk.LEFT, padx=16, pady=12)

        right = tk.Frame(hdr, bg=COLORS["surface"])
        right.pack(side=tk.RIGHT, padx=16)
        self.status_dot = tk.Canvas(right, width=10, height=10, bg=COLORS["surface"],
                                    highlightthickness=0)
        self.status_dot.pack(side=tk.LEFT, padx=(0, 6), pady=14)
        self.status_label = tk.Label(right, text="Connecting…",
                                     bg=COLORS["surface"], fg=COLORS["muted"],
                                     font=("Segoe UI", 9))
        self.status_label.pack(side=tk.LEFT)
        self._draw_dot(False)

    def _draw_dot(self, connected):
        c = COLORS["success"] if connected else COLORS["danger"]
        self.status_dot.delete("all")
        self.status_dot.create_oval(1, 1, 9, 9, fill=c, outline=c)

    def _build_stats_bar(self):
        bar = tk.Frame(self, bg=COLORS["bg"])
        bar.pack(fill=tk.X, padx=10, pady=(10, 0))
        self.stat_vars = {}
        stats = [("Total", "total", COLORS["primary"]),
                 ("Pending", "pending", COLORS["warn"]),
                 ("Done", "done", COLORS["success"]),
                 ("High !", "high", COLORS["danger"])]
        for label, key, color in stats:
            card = tk.Frame(bar, bg=COLORS["surface"], relief=tk.FLAT,
                            highlightbackground=COLORS["border"], highlightthickness=1)
            card.pack(side=tk.LEFT, padx=(0, 8), pady=(0, 8))
            v = tk.StringVar(value="0")
            self.stat_vars[key] = v
            tk.Label(card, textvariable=v, font=("Segoe UI", 20, "bold"),
                     bg=COLORS["surface"], fg=color, width=4).pack(padx=16, pady=(8, 2))
            tk.Label(card, text=label, font=("Segoe UI", 8),
                     bg=COLORS["surface"], fg=COLORS["muted"]).pack(pady=(0, 8))

    def _build_left_panel(self, parent):
        frame = tk.Frame(parent, bg=COLORS["surface"],
                         highlightbackground=COLORS["border"], highlightthickness=1)

        # Filter buttons
        tk.Label(frame, text="FILTER", bg=COLORS["surface"], fg=COLORS["muted"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=14, pady=(12, 4))

        filters = [("All Tasks", "all"), ("Pending", "pending"), ("Completed", "completed"),
                   ("🔴 High Priority", "high"), ("🟡 Medium", "medium"), ("🟢 Low", "low")]
        self.filter_buttons = {}
        for lbl, val in filters:
            btn = tk.Button(frame, text=lbl, bg=COLORS["surface"], fg=COLORS["muted"],
                            font=("Segoe UI", 9), bd=0, relief=tk.FLAT, anchor="w",
                            padx=14, pady=6, activebackground=COLORS["primary"],
                            activeforeground="white", cursor="hand2",
                            command=lambda v=val: self._set_filter(v))
            btn.pack(fill=tk.X)
            self.filter_buttons[val] = btn
        self._highlight_filter("all")

        tk.Frame(frame, bg=COLORS["border"], height=1).pack(fill=tk.X, padx=10, pady=10)

        # Add Task Form
        tk.Label(frame, text="ADD TASK", bg=COLORS["surface"], fg=COLORS["muted"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=14, pady=(0, 6))

        self._lbl(frame, "Title *")
        self.new_title = self._entry(frame)
        self.new_title.bind("<Return>", lambda e: self._add_task())

        self._lbl(frame, "Description")
        self.new_desc = tk.Text(frame, height=3, bg=COLORS["bg"], fg=COLORS["text"],
                                insertbackground=COLORS["text"], relief=tk.FLAT,
                                font=("Segoe UI", 9), padx=6, pady=4)
        self.new_desc.pack(fill=tk.X, padx=14, pady=(0, 6))

        self._lbl(frame, "Priority")
        self.new_priority = ttk.Combobox(frame, values=["low", "medium", "high"],
                                         state="readonly", font=("Segoe UI", 9))
        self.new_priority.set("medium")
        self.new_priority.pack(fill=tk.X, padx=14, pady=(0, 6))
        self._style_combo(self.new_priority)

        self._lbl(frame, "Category")
        self.new_category = self._entry(frame, placeholder="General")

        btn = tk.Button(frame, text="➕  Add Task",
                        bg=COLORS["primary"], fg="white",
                        font=("Segoe UI", 10, "bold"), bd=0, relief=tk.FLAT,
                        padx=14, pady=8, cursor="hand2", command=self._add_task)
        btn.pack(fill=tk.X, padx=14, pady=(6, 14))

        return frame

    def _build_right_panel(self, parent):
        frame = tk.Frame(parent, bg=COLORS["bg"])

        # Toolbar
        toolbar = tk.Frame(frame, bg=COLORS["bg"])
        toolbar.pack(fill=tk.X, pady=(8, 4))
        tk.Label(toolbar, text="Tasks", bg=COLORS["bg"], fg=COLORS["text"],
                 font=("Segoe UI", 13, "bold")).pack(side=tk.LEFT)
        tk.Button(toolbar, text="🔄 Refresh", bg=COLORS["surface2"], fg=COLORS["muted"],
                  font=("Segoe UI", 8), bd=0, relief=tk.FLAT, padx=8, pady=4,
                  cursor="hand2", command=self._load_tasks).pack(side=tk.RIGHT)

        # Treeview
        cols = ("title", "priority", "category", "status", "updated")
        self.tree = ttk.Treeview(frame, columns=cols, show="headings", selectmode="browse")
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=scrollbar.set)

        # Column settings
        widths = {"title": 280, "priority": 80, "category": 110, "status": 90, "updated": 130}
        for col in cols:
            self.tree.heading(col, text=col.capitalize(),
                              command=lambda c=col: self._sort_by(c))
            self.tree.column(col, width=widths.get(col, 100))

        # Row tags
        self.tree.tag_configure("high", foreground=COLORS["high"])
        self.tree.tag_configure("medium", foreground=COLORS["warn"])
        self.tree.tag_configure("low", foreground=COLORS["low"])
        self.tree.tag_configure("done", foreground=COLORS["muted"])

        # Style
        style = ttk.Style()
        style.configure("Treeview",
                         background=COLORS["surface"],
                         fieldbackground=COLORS["surface"],
                         foreground=COLORS["text"],
                         rowheight=30,
                         font=("Segoe UI", 9))
        style.configure("Treeview.Heading",
                         background=COLORS["surface2"],
                         foreground=COLORS["muted"],
                         font=("Segoe UI", 9, "bold"))
        style.map("Treeview", background=[("selected", COLORS["primary"])])

        # Context / action buttons
        action_bar = tk.Frame(frame, bg=COLORS["bg"])
        action_bar.pack(fill=tk.X, pady=(8, 0))
        for lbl, color, cmd in [
            ("✏️ Edit", COLORS["primary"], self._edit_task),
            ("✅ Toggle Done", COLORS["success"], self._toggle_done),
            ("🗑️ Delete", COLORS["danger"], self._delete_task),
        ]:
            tk.Button(action_bar, text=lbl, bg=color, fg="white",
                      font=("Segoe UI", 9, "bold"), bd=0, relief=tk.FLAT,
                      padx=12, pady=6, cursor="hand2", command=cmd).pack(side=tk.LEFT, padx=(0, 8))

        self.tree.bind("<Double-1>", lambda e: self._edit_task())
        return frame

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _lbl(self, parent, text):
        tk.Label(parent, text=text, bg=COLORS["surface"], fg=COLORS["muted"],
                 font=("Segoe UI", 8)).pack(anchor="w", padx=14)

    def _entry(self, parent, placeholder=""):
        e = tk.Entry(parent, bg=COLORS["bg"], fg=COLORS["text"],
                     insertbackground=COLORS["text"], relief=tk.FLAT,
                     font=("Segoe UI", 9))
        e.pack(fill=tk.X, padx=14, pady=(0, 6), ipady=4)
        if placeholder:
            e.insert(0, placeholder)
        return e

    def _style_combo(self, combo):
        s = ttk.Style()
        s.configure("TCombobox", fieldbackground=COLORS["bg"], background=COLORS["bg"],
                    foreground=COLORS["text"])

    def _highlight_filter(self, value):
        for v, btn in self.filter_buttons.items():
            if v == value:
                btn.config(bg=COLORS["primary"], fg="white")
            else:
                btn.config(bg=COLORS["surface"], fg=COLORS["muted"])

    def _get_selected_id(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select a Task", "Please select a task first.")
            return None
        return self.tree.item(sel[0])["values"][0] if len(self.tree.item(sel[0])["values"]) > 5 else \
               self._iid_to_id.get(sel[0])

    # ── Data / API ─────────────────────────────────────────────────────────────

    def _api(self, method, path, **kwargs):
        try:
            resp = requests.request(method, self.server + path, timeout=8, **kwargs)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            self.after(0, lambda: self._toast(f"Error: {e}", error=True))
            return None

    def _load_tasks(self):
        data = self._api("GET", "/api/tasks")
        if data is not None:
            self.tasks = {t["id"]: t for t in data}
            self.after(0, self._refresh_view)

    def _add_task(self):
        title = self.new_title.get().strip()
        if not title:
            messagebox.showwarning("Missing Title", "Please enter a task title.")
            return
        body = {
            "title": title,
            "description": self.new_desc.get("1.0", tk.END).strip(),
            "priority": self.new_priority.get(),
            "category": self.new_category.get().strip() or "General",
        }
        t = self._api("POST", "/api/tasks", json=body)
        if t:
            self.new_title.delete(0, tk.END)
            self.new_desc.delete("1.0", tk.END)
            self._toast(f"Task added: {t['title']}")

    def _edit_task(self):
        task_id = self._selected_task_id()
        if not task_id:
            return
        task = self.tasks.get(task_id)
        if not task:
            return
        win = tk.Toplevel(self)
        win.title("Edit Task")
        win.configure(bg=COLORS["surface"])
        win.geometry("420x360")
        win.grab_set()

        def lbl(t): tk.Label(win, text=t, bg=COLORS["surface"], fg=COLORS["muted"],
                              font=("Segoe UI", 8)).pack(anchor="w", padx=16, pady=(6, 0))
        def ent():
            e = tk.Entry(win, bg=COLORS["bg"], fg=COLORS["text"],
                         insertbackground=COLORS["text"], relief=tk.FLAT, font=("Segoe UI", 9))
            e.pack(fill=tk.X, padx=16, ipady=4)
            return e

        lbl("Title")
        etitle = ent(); etitle.insert(0, task["title"])
        lbl("Description")
        edesc = tk.Text(win, height=3, bg=COLORS["bg"], fg=COLORS["text"],
                        insertbackground=COLORS["text"], relief=tk.FLAT, font=("Segoe UI", 9))
        edesc.pack(fill=tk.X, padx=16, pady=(0, 0))
        edesc.insert("1.0", task.get("description", ""))
        lbl("Priority")
        epri = ttk.Combobox(win, values=["low", "medium", "high"], state="readonly")
        epri.set(task["priority"]); epri.pack(fill=tk.X, padx=16)
        lbl("Category")
        ecat = ent(); ecat.insert(0, task.get("category", ""))

        def save():
            body = {
                "title": etitle.get().strip(),
                "description": edesc.get("1.0", tk.END).strip(),
                "priority": epri.get(),
                "category": ecat.get().strip() or "General",
            }
            updated = self._api("PUT", f"/api/tasks/{task_id}", json=body)
            if updated:
                win.destroy()
                self._toast("Task updated")

        btn_frame = tk.Frame(win, bg=COLORS["surface"])
        btn_frame.pack(fill=tk.X, padx=16, pady=12)
        tk.Button(btn_frame, text="Cancel", bg=COLORS["surface2"], fg=COLORS["muted"],
                  bd=0, relief=tk.FLAT, padx=10, pady=6, command=win.destroy).pack(side=tk.RIGHT, padx=(6, 0))
        tk.Button(btn_frame, text="Save Changes", bg=COLORS["primary"], fg="white",
                  bd=0, relief=tk.FLAT, padx=10, pady=6, command=save,
                  font=("Segoe UI", 9, "bold")).pack(side=tk.RIGHT)

    def _toggle_done(self):
        task_id = self._selected_task_id()
        if not task_id:
            return
        task = self.tasks.get(task_id)
        self._api("PUT", f"/api/tasks/{task_id}", json={"completed": not task["completed"]})

    def _delete_task(self):
        task_id = self._selected_task_id()
        if not task_id:
            return
        task = self.tasks.get(task_id)
        if not messagebox.askyesno("Delete Task", f"Delete \"{task['title']}\"?"):
            return
        self._api("DELETE", f"/api/tasks/{task_id}")

    def _selected_task_id(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("No Selection", "Please select a task.")
            return None
        return self._iid_to_id.get(sel[0])

    # ── View refresh ─────────────────────────────────────────────────────────

    def _set_filter(self, value):
        self.filter_var.set(value)
        self._highlight_filter(value)
        self._refresh_view()

    def _refresh_view(self):
        self.tree.delete(*self.tree.get_children())
        self._iid_to_id = {}
        filt = self.filter_var.get()

        tasks = list(self.tasks.values())
        if filt == "pending":
            tasks = [t for t in tasks if not t["completed"]]
        elif filt == "completed":
            tasks = [t for t in tasks if t["completed"]]
        elif filt in ("low", "medium", "high"):
            tasks = [t for t in tasks if t["priority"] == filt]
        tasks.sort(key=lambda t: t["created_at"], reverse=True)

        for t in tasks:
            status = "✅ Done" if t["completed"] else "⏳ Pending"
            updated = t["updated_at"][:10]
            tag = "done" if t["completed"] else t.get("priority", "medium")
            iid = self.tree.insert("", tk.END,
                values=(t["title"], t["priority"], t["category"], status, updated),
                tags=(tag,))
            self._iid_to_id[iid] = t["id"]

        self._update_stats()

    def _update_stats(self):
        all_t = list(self.tasks.values())
        self.stat_vars["total"].set(str(len(all_t)))
        self.stat_vars["pending"].set(str(sum(1 for t in all_t if not t["completed"])))
        self.stat_vars["done"].set(str(sum(1 for t in all_t if t["completed"])))
        self.stat_vars["high"].set(str(sum(1 for t in all_t if t["priority"] == "high")))

    def _sort_by(self, col):
        tasks = list(self.tasks.values())
        key_map = {"title": "title", "priority": "priority", "category": "category",
                   "status": "completed", "updated": "updated_at"}
        key = key_map.get(col, col)
        tasks.sort(key=lambda t: str(t.get(key, "")))
        self.tasks = {t["id"]: t for t in tasks}
        self._refresh_view()

    # ── SSE (real-time) ───────────────────────────────────────────────────────

    def _start_sse(self):
        self._stop_sse.clear()
        self._sse_thread = threading.Thread(target=self._sse_worker, daemon=True)
        self._sse_thread.start()

    def _sse_worker(self):
        while not self._stop_sse.is_set():
            try:
                with requests.get(self.server + "/api/stream", stream=True, timeout=60) as resp:
                    self.after(0, lambda: self._set_connected(True))
                    for line in resp.iter_lines():
                        if self._stop_sse.is_set():
                            break
                        if not line:
                            continue
                        if isinstance(line, bytes):
                            line = line.decode()
                        if line.startswith("data:"):
                            payload = line[5:].strip()
                            try:
                                msg = json.loads(payload)
                                self.after(0, lambda m=msg: self._handle_event(m))
                            except Exception:
                                pass
            except Exception as e:
                self.after(0, lambda: self._set_connected(False))
                time.sleep(3)

    def _handle_event(self, msg):
        evt = msg.get("event")
        data = msg.get("data")
        if evt == "snapshot":
            self.tasks = {t["id"]: t for t in data}
        elif evt == "task_created":
            self.tasks[data["id"]] = data
            self._toast(f"📝 New task: {data['title']}")
        elif evt == "task_updated":
            self.tasks[data["id"]] = data
        elif evt == "task_deleted":
            self.tasks.pop(data["id"], None)
            self._toast("🗑️ Task deleted")
        self._refresh_view()

    def _set_connected(self, ok):
        self.connected = ok
        self._draw_dot(ok)
        self.status_label.config(
            text="Live ✦ Connected" if ok else "Reconnecting…",
            fg=COLORS["success"] if ok else COLORS["danger"])

    # ── Toast notification ────────────────────────────────────────────────────

    def _toast(self, msg, error=False):
        toast = tk.Toplevel(self)
        toast.overrideredirect(True)
        toast.attributes("-topmost", True)
        color = COLORS["danger"] if error else COLORS["success"]
        frame = tk.Frame(toast, bg=COLORS["surface"],
                         highlightbackground=color, highlightthickness=2)
        frame.pack()
        tk.Label(frame, text=msg, bg=COLORS["surface"], fg=COLORS["text"],
                 font=("Segoe UI", 9), padx=16, pady=10).pack()
        x = self.winfo_x() + self.winfo_width() - 300
        y = self.winfo_y() + self.winfo_height() - 60
        toast.geometry(f"+{x}+{y}")
        self.after(3000, toast.destroy)


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Distributed To-Do GUI Client")
    parser.add_argument("--server", default=DEFAULT_SERVER,
                        help="Server URL (default: http://localhost:5000)")
    args = parser.parse_args()

    app = ToDoApp(args.server)
    app.mainloop()