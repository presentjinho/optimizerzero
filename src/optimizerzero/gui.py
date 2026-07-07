from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
import os
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .core import Goal, OptimizeOptions, OptimizeResult, analyze_files, discover_files, format_bytes, merge_goal_options, optimize_many, parse_size, write_report


def default_workers() -> int:
    cpu_count = os.cpu_count() or 2
    return max(1, min(4, cpu_count - 1 if cpu_count > 1 else 1))


def format_duration(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    if seconds < 60:
        return f"{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {seconds}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"


class OptimizerZeroApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("OptimizerZero")
        self.geometry("1080x700")
        self.minsize(1080, 700)
        self.files: list[Path] = []
        self.results: list[OptimizeResult] = []
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.run_started_at: float = 0.0
        self.run_total: int = 0
        self.run_completed: int = 0
        self._build_ui()

    def _build_ui(self) -> None:
        self.configure(bg="#101418")
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TButton", padding=8)
        style.configure("Treeview", rowheight=26)
        header = tk.Frame(self, bg="#101418")
        header.pack(fill="x", padx=18, pady=(16, 8))
        tk.Label(header, text="OptimizerZero", fg="#f4f7fb", bg="#101418", font=("Segoe UI", 22, "bold")).pack(anchor="w")
        tk.Label(header, text="Smart local compression. Files stay on this PC.", fg="#9fb0c0", bg="#101418").pack(anchor="w")
        actions = tk.Frame(self, bg="#101418")
        actions.pack(fill="x", padx=18, pady=8)
        self.add_files_button = ttk.Button(actions, text="Add Files", command=self.add_files)
        self.add_files_button.pack(side="left", padx=(0, 8))
        self.add_folder_button = ttk.Button(actions, text="Add Folder", command=self.add_folder)
        self.add_folder_button.pack(side="left", padx=(0, 8))
        self.analyze_button = ttk.Button(actions, text="Analyze", command=self.analyze)
        self.analyze_button.pack(side="left", padx=(0, 8))
        self.clear_button = ttk.Button(actions, text="Clear", command=self.clear)
        self.clear_button.pack(side="left", padx=(0, 8))
        self.report_button = ttk.Button(actions, text="Save Report", command=self.save_report)
        self.report_button.pack(side="left", padx=(0, 18))
        tk.Label(actions, text="Goal", fg="#d7dee7", bg="#101418").pack(side="left")
        self.goal_var = tk.StringVar(value=Goal.SMART.value)
        ttk.Combobox(actions, textvariable=self.goal_var, values=[goal.value for goal in Goal], width=10, state="readonly").pack(side="left", padx=8)
        self.recursive_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(actions, text="Recursive", variable=self.recursive_var).pack(side="left", padx=8)
        self.dry_run_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(actions, text="Dry Run", variable=self.dry_run_var).pack(side="left", padx=8)
        self.run_button = ttk.Button(actions, text="Run", command=self.run)
        self.run_button.pack(side="right")
        limits = tk.Frame(self, bg="#101418")
        limits.pack(fill="x", padx=18, pady=(0, 8))
        self.min_savings_var = self._entry(limits, "Min savings %", "0", 8)
        self.max_size_var = self._entry(limits, "Max size", "", 10)
        self.target_size_var = self._entry(limits, "Target", "", 10)
        self.max_dimension_var = self._entry(limits, "Max dimension px", "", 8)
        self.workers_var = self._entry(limits, f"CPU threads (auto={default_workers()})", "auto", 8)
        self.summary_var = tk.StringVar(value="0 files / 0 B saved")
        tk.Label(limits, textvariable=self.summary_var, fg="#9fb0c0", bg="#101418").pack(side="right")
        progress = tk.Frame(self, bg="#101418")
        progress.pack(fill="x", padx=18, pady=(0, 8))
        self.progress_var = tk.StringVar(value="")
        tk.Label(progress, textvariable=self.progress_var, fg="#9fb0c0", bg="#101418").pack(side="left")
        table_frame = tk.Frame(self)
        table_frame.pack(fill="both", expand=True, padx=18, pady=8)
        cols = ("file", "type", "size", "status", "saved")
        self.table = ttk.Treeview(table_frame, columns=cols, show="headings")
        for col, label, width in [("file", "File", 380), ("type", "Type", 70), ("size", "Size", 100), ("status", "Status", 360), ("saved", "Saved", 100)]:
            self.table.heading(col, text=label)
            self.table.column(col, width=width, anchor="w")
        table_xscroll = ttk.Scrollbar(table_frame, orient="horizontal", command=self.table.xview)
        self.table.configure(xscrollcommand=table_xscroll.set)
        self.table.pack(side="top", fill="both", expand=True)
        table_xscroll.pack(side="bottom", fill="x")
        self.log = tk.Text(self, height=8, bg="#0b0f13", fg="#dbe7f3", insertbackground="#dbe7f3", relief="flat", wrap="word")
        self.log.pack(fill="x", padx=18, pady=(8, 16))
        self.log_line("Ready.")

    def _entry(self, parent: tk.Frame, label: str, value: str, width: int) -> tk.StringVar:
        tk.Label(parent, text=label, fg="#d7dee7", bg="#101418").pack(side="left")
        var = tk.StringVar(value=value)
        ttk.Entry(parent, textvariable=var, width=width).pack(side="left", padx=(8, 18))
        return var

    def _eta_text(self) -> str:
        if self.run_completed <= 0 or self.run_completed >= self.run_total:
            return "estimating…"
        elapsed = time.time() - self.run_started_at
        avg_per_file = elapsed / self.run_completed
        remaining = self.run_total - self.run_completed
        return f"ETA {format_duration(avg_per_file * remaining)}"

    def log_line(self, text: str) -> None:
        self.log.insert("end", text + "\n")
        self.log.see("end")

    def refresh(self) -> None:
        self.table.delete(*self.table.get_children())
        for path in self.files:
            self.table.insert("", "end", iid=str(path), values=(path.name, path.suffix.lower(), format_bytes(path.stat().st_size), "pending", "-"))

    def add_files(self) -> None:
        selected = filedialog.askopenfilenames(title="Add files")
        self.files.extend(Path(path) for path in selected)
        self.files = discover_files(self.files, recursive=False)
        self.refresh()

    def add_folder(self) -> None:
        folder = filedialog.askdirectory(title="Add folder")
        if folder:
            self.files = discover_files([Path(folder)], recursive=self.recursive_var.get())
            self.refresh()
            self.log_line(f"Found {len(self.files)} supported files.")

    def clear(self) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("Running", "Wait for the current optimization to finish before clearing.")
            return
        self.files = []
        self.results = []
        self.refresh()
        self.summary_var.set("0 files / 0 B saved")
        self.progress_var.set("")

    def set_running(self, running: bool) -> None:
        state = "disabled" if running else "normal"
        for button in (self.add_files_button, self.add_folder_button, self.analyze_button, self.clear_button, self.run_button):
            button.configure(state=state)

    def analyze(self) -> None:
        if not self.files:
            messagebox.showinfo("No files", "Add files or a folder first.")
            return
        by_kind: dict[str, list] = {}
        for item in analyze_files(self.files, recursive=False):
            by_kind.setdefault(item.kind, []).append(item)
        self.log_line("Analysis:")
        for kind in sorted(by_kind):
            items = by_kind[kind]
            self.log_line(f"  {kind}: {len(items)} files / {format_bytes(sum(item.size for item in items))}")

    def run(self) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("Running", "Optimization is already running.")
            return
        if not self.files:
            messagebox.showinfo("No files", "Add files or a folder first.")
            return
        try:
            min_savings = float(self.min_savings_var.get() or "0")
            max_size = parse_size(self.max_size_var.get())
            target_size = parse_size(self.target_size_var.get())
            max_dimension_text = self.max_dimension_var.get().strip()
            max_dimension = int(max_dimension_text) if max_dimension_text else None
            workers_text = self.workers_var.get().strip().lower()
            workers = default_workers() if workers_text in {"", "auto"} else int(workers_text)
        except ValueError:
            messagebox.showerror("Invalid limit", "Use a number, auto, 75MB, or 2GB.")
            return
        options = merge_goal_options(
            Goal(self.goal_var.get()),
            recursive=self.recursive_var.get(),
            dry_run=self.dry_run_var.get(),
            min_savings_percent=min_savings,
            max_size_bytes=max_size,
            target_size_bytes=target_size,
            max_dimension=max_dimension,
            workers=workers,
        )
        files_snapshot = list(self.files)
        self.results = []
        self.run_started_at = time.time()
        self.run_total = len(files_snapshot)
        self.run_completed = 0
        self.progress_var.set(f"0 / {self.run_total}")
        self.set_running(True)
        self.worker = threading.Thread(target=self._run_worker, args=(files_snapshot, options), daemon=True)
        self.worker.start()
        self.after(100, self._pump_events)

    def _run_worker(self, files: list[Path], options: OptimizeOptions) -> None:
        for path in files:
            self.events.put(("status", (path, "running", "-")))
        for result in optimize_many(files, options):
            path = Path(result.source)
            self.events.put(("status", (path, result.message, format_bytes(max(0, result.saved_bytes)))))
            self.events.put(("log", f"{result.status}: {path.name} | {result.message}"))
            self.events.put(("result", result))
        self.events.put(("done", None))

    def _pump_events(self) -> None:
        while True:
            try:
                event, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if event == "status":
                path, status, saved = payload
                if self.table.exists(str(path)):
                    self.table.set(str(path), "status", status)
                    self.table.set(str(path), "saved", saved)
            elif event == "log":
                self.log_line(str(payload))
            elif event == "result":
                self.results.append(payload)
                self.run_completed += 1
                self.progress_var.set(f"{self.run_completed} / {self.run_total} · {self._eta_text()}")
            elif event == "done":
                saved_total = sum(max(0, result.saved_bytes) for result in self.results)
                optimized = sum(1 for result in self.results if result.status == "optimized")
                errors = sum(1 for result in self.results if result.status == "error")
                self.summary_var.set(f"{optimized} optimized / {format_bytes(saved_total)} saved / {errors} errors")
                elapsed = time.time() - self.run_started_at
                self.progress_var.set(f"{self.run_completed} / {self.run_total} · done in {format_duration(elapsed)}")
                self.log_line("Done.")
                self.set_running(False)
                return
        self.after(100, self._pump_events)

    def save_report(self) -> None:
        if not self.results:
            messagebox.showinfo("No report", "Run an optimization or dry run first.")
            return
        target = filedialog.asksaveasfilename(title="Save JSON report", defaultextension=".json", filetypes=[("JSON report", "*.json"), ("All files", "*.*")])
        if target:
            write_report(Path(target), self.results)
            self.log_line(f"Report saved: {target}")


def main() -> int:
    app = OptimizerZeroApp()
    app.mainloop()
    return 0
