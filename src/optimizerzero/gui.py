from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .core import LossBudget, OptimizeOptions, OptimizeResult, Profile, analyze_files, discover_files, format_bytes, optimize_one, parse_size, write_report


class OptimizerZeroApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("OptimizerZero")
        self.geometry("1080x700")
        self.files: list[Path] = []
        self.results: list[OptimizeResult] = []
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker: threading.Thread | None = None
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
        tk.Label(header, text="Choose how much size to save and how much quality to trade.", fg="#9fb0c0", bg="#101418").pack(anchor="w")
        actions = tk.Frame(self, bg="#101418")
        actions.pack(fill="x", padx=18, pady=8)
        ttk.Button(actions, text="Add Files", command=self.add_files).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Add Folder", command=self.add_folder).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Analyze", command=self.analyze).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Clear", command=self.clear).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Save Report", command=self.save_report).pack(side="left", padx=(0, 18))
        tk.Label(actions, text="Profile", fg="#d7dee7", bg="#101418").pack(side="left")
        self.profile_var = tk.StringVar(value=Profile.SAFE.value)
        ttk.Combobox(actions, textvariable=self.profile_var, values=[p.value for p in Profile], width=10, state="readonly").pack(side="left", padx=8)
        tk.Label(actions, text="Loss", fg="#d7dee7", bg="#101418").pack(side="left")
        self.loss_budget_var = tk.StringVar(value="")
        ttk.Combobox(actions, textvariable=self.loss_budget_var, values=[""] + [budget.value for budget in LossBudget], width=8, state="readonly").pack(side="left", padx=8)
        self.recursive_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(actions, text="Recursive", variable=self.recursive_var).pack(side="left", padx=8)
        self.dry_run_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(actions, text="Dry Run", variable=self.dry_run_var).pack(side="left", padx=8)
        ttk.Button(actions, text="Run", command=self.run).pack(side="right")
        limits = tk.Frame(self, bg="#101418")
        limits.pack(fill="x", padx=18, pady=(0, 8))
        self.min_savings_var = self._entry(limits, "Min savings %", "0", 8)
        self.max_size_var = self._entry(limits, "Max size", "", 10)
        self.quality_var = self._entry(limits, "Quality", "", 6)
        self.target_size_var = self._entry(limits, "Target", "", 10)
        self.summary_var = tk.StringVar(value="0 files / 0 B saved")
        tk.Label(limits, textvariable=self.summary_var, fg="#9fb0c0", bg="#101418").pack(side="right")
        cols = ("file", "type", "size", "status", "saved")
        self.table = ttk.Treeview(self, columns=cols, show="headings")
        for col, label, width in [("file", "File", 430), ("type", "Type", 70), ("size", "Size", 110), ("status", "Status", 300), ("saved", "Saved", 100)]:
            self.table.heading(col, text=label)
            self.table.column(col, width=width, anchor="w")
        self.table.pack(fill="both", expand=True, padx=18, pady=8)
        self.log = tk.Text(self, height=8, bg="#0b0f13", fg="#dbe7f3", insertbackground="#dbe7f3", relief="flat")
        self.log.pack(fill="x", padx=18, pady=(8, 16))
        self.log_line("Ready.")

    def _entry(self, parent: tk.Frame, label: str, value: str, width: int) -> tk.StringVar:
        tk.Label(parent, text=label, fg="#d7dee7", bg="#101418").pack(side="left")
        var = tk.StringVar(value=value)
        ttk.Entry(parent, textvariable=var, width=width).pack(side="left", padx=(8, 18))
        return var

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
        self.files = []
        self.results = []
        self.refresh()
        self.summary_var.set("0 files / 0 B saved")

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
            quality = int(self.quality_var.get()) if self.quality_var.get().strip() else None
            target_size = parse_size(self.target_size_var.get())
        except ValueError:
            messagebox.showerror("Invalid limit", "Use a number, quality 1-100, 75MB, or 2GB.")
            return
        options = OptimizeOptions(
            profile=Profile(self.profile_var.get()),
            recursive=self.recursive_var.get(),
            dry_run=self.dry_run_var.get(),
            min_savings_percent=min_savings,
            max_size_bytes=max_size,
            loss_budget=LossBudget(self.loss_budget_var.get()) if self.loss_budget_var.get() else None,
            image_quality=quality,
            target_size_bytes=target_size,
        )
        self.results = []
        self.worker = threading.Thread(target=self._run_worker, args=(options,), daemon=True)
        self.worker.start()
        self.after(100, self._pump_events)

    def _run_worker(self, options: OptimizeOptions) -> None:
        for path in self.files:
            self.events.put(("status", (path, "running", "-")))
            result = optimize_one(path, options)
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
            elif event == "done":
                saved_total = sum(max(0, result.saved_bytes) for result in self.results)
                optimized = sum(1 for result in self.results if result.status == "optimized")
                errors = sum(1 for result in self.results if result.status == "error")
                self.summary_var.set(f"{optimized} optimized / {format_bytes(saved_total)} saved / {errors} errors")
                self.log_line("Done.")
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
