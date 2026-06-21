"""CustomTkinter GUI for the Post-Change Validation Reviewer."""

from __future__ import annotations

import traceback
from pathlib import Path
from typing import List

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from src.post_change_validation_analysis import run_analysis
from src.post_change_validation_ios_log_signature import validate_ios_xe_log_signature
from src.post_change_validation_models import Finding
from src.post_change_validation_pdf import export_pdf, export_pdf_from_html_browser
from post_change_validation_report_shell import (
    APP_NAME,
    APP_VERSION,
    build_html_report,
    display_severity,
    overall_status,
    severity_counts,
)
from src.post_change_validation_gui_detail_formatting import format_detail_pane, format_detail_summary

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("dark-blue")

_PAD = 14
_CORNER = 8


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        # CTkFont requires a root window; create fonts after CTk init, not at import time.
        self._font_title = ctk.CTkFont(family="Segoe UI", size=17, weight="bold")
        self._font_subtitle = ctk.CTkFont(family="Segoe UI", size=10)
        self._font_summary = ctk.CTkFont(family="Segoe UI", size=11, weight="bold")
        self._font_section = ctk.CTkFont(family="Segoe UI", size=13, weight="bold")
        self._font_detail = ctk.CTkFont(family="Consolas", size=12)
        self.title(f"{APP_NAME} v{APP_VERSION} - created by William Munn")
        self.geometry("1220x800")
        self.minsize(980, 640)
        self.path_inputs: dict[str, tk.StringVar] = {
            "pre_log": tk.StringVar(),
            "post_log": tk.StringVar(),
            "port_map": tk.StringVar(),
        }
        self.findings: List[Finding] = []
        self._configure_tree_style()
        self._build_ui()

    def get_scaling(self) -> float:
        return ctk.ScalingTracker.get_widget_scaling(self)

    def _configure_tree_style(self) -> None:
        scale_factor = self.get_scaling()
        scaled_font_size = int(11 * scale_factor)
        scaled_row_height = int(30 * scale_factor)

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            "PCV.Treeview",
            background="#2b2b2b",
            foreground="#dce4ee",
            fieldbackground="#2b2b2b",
            borderwidth=0,
            rowheight=scaled_row_height,
            font=("Segoe UI", scaled_font_size),
        )
        style.configure(
            "PCV.Treeview.Heading",
            background="#1f538d",
            foreground="#ffffff",
            relief="flat",
            font=("Segoe UI", scaled_font_size, "bold"),
        )
        style.map(
            "PCV.Treeview",
            background=[("selected", "#144870")],
            foreground=[("selected", "#ffffff")],
        )

    def _build_ui(self) -> None:
        root = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        root.pack(fill="both", expand=True, padx=_PAD, pady=_PAD)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(4, weight=1)

        header = ctk.CTkFrame(root, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        ctk.CTkLabel(header, text=APP_NAME, font=self._font_title, anchor="w").pack(side="left")
        ctk.CTkLabel(
            header,
            text=f"v{APP_VERSION}",
            font=self._font_subtitle,
            text_color="#9aa5ad",
            anchor="w",
        ).pack(side="left", padx=(8, 0), pady=(6, 0))

        input_frame = ctk.CTkFrame(root, corner_radius=_CORNER)
        input_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        input_frame.columnconfigure(1, weight=1)
        ctk.CTkLabel(input_frame, text="Inputs", font=self._font_section, anchor="w").grid(
            row=0, column=0, columnspan=3, sticky="w", padx=12, pady=(10, 6)
        )

        for idx, (label, key, cmd) in enumerate(
            [
                ("Pre-change log", "pre_log", self.pick_pre),
                ("Post-change log", "post_log", self.pick_post),
                ("Port map CSV", "port_map", self.pick_map),
            ],
            start=1,
        ):
            var = self.path_inputs[key]
            ctk.CTkLabel(input_frame, text=label, anchor="w").grid(
                row=idx, column=0, sticky="w", padx=12, pady=6
            )
            ctk.CTkEntry(input_frame, textvariable=var, corner_radius=6).grid(
                row=idx, column=1, sticky="ew", padx=8, pady=6
            )
            ctk.CTkButton(
                input_frame,
                text="Browse",
                width=90,
                corner_radius=6,
                command=cmd,
            ).grid(row=idx, column=2, padx=(0, 12), pady=6)

        ctk.CTkLabel(
            input_frame,
            text="Leave Port map CSV blank to auto-detect from the post-change running-config.",
            text_color="#9aa5ad",
            anchor="w",
            wraplength=760,
        ).grid(row=4, column=1, sticky="w", padx=8, pady=(0, 12))

        btns = ctk.CTkFrame(root, fg_color="transparent")
        btns.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        ctk.CTkButton(
            btns,
            text="Run Validation",
            corner_radius=6,
            fg_color="#2fa572",
            hover_color="#248f5f",
            command=self.run_validation,
        ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            btns,
            text="Export HTML",
            corner_radius=6,
            fg_color="#1f538d",
            hover_color="#184a7a",
            command=self.save_html,
        ).pack(side="left", padx=6)
        ctk.CTkButton(
            btns,
            text="Export PDF",
            corner_radius=6,
            fg_color="#1f538d",
            hover_color="#184a7a",
            command=self.save_pdf,
        ).pack(side="left", padx=6)
        ctk.CTkButton(
            btns,
            text="Clear",
            corner_radius=6,
            fg_color="#4a4a4a",
            hover_color="#3a3a3a",
            command=self.clear,
        ).pack(side="left", padx=6)

        self.summary = ctk.CTkLabel(
            root,
            text="Load pre/post logs and run validation.",
            font=self._font_summary,
            anchor="w",
        )
        self.summary.grid(row=3, column=0, sticky="ew", pady=(0, 6))

        tree_frame = ctk.CTkFrame(root, corner_radius=_CORNER)
        tree_frame.grid(row=4, column=0, sticky="nsew", pady=(0, 10))
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        cols = ("severity", "category", "finding", "detail")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings", style="PCV.Treeview")
        for col, width in [("severity", 80), ("category", 160), ("finding", 360), ("detail", 520)]:
            self.tree.heading(col, text=col.title())
            self.tree.column(col, width=width, anchor="w")
        self.tree.tag_configure("FAIL", foreground="#ff8a8a", background="#3d1f1f")
        self.tree.tag_configure("WARN", foreground="#ffd166", background="#3d3520")
        self.tree.tag_configure("REVIEW", foreground="#c5d0d6", background="#2f3438")
        self.tree.tag_configure("PASS", foreground="#8ee99a", background="#1f3d24")
        self.tree.tag_configure("INFO", foreground="#b8c5cc", background="#2f3438")
        self.tree.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        self.tree.bind("<<TreeviewSelect>>", self.show_detail)

        detail_frame = ctk.CTkFrame(root, corner_radius=_CORNER)
        detail_frame.grid(row=5, column=0, sticky="ew")
        detail_frame.columnconfigure(0, weight=1)
        ctk.CTkLabel(detail_frame, text="Selected Finding Detail", font=self._font_section, anchor="w").grid(
            row=0, column=0, sticky="w", padx=12, pady=(10, 4)
        )
        self.detail_text = ctk.CTkTextbox(
            detail_frame,
            height=140,
            corner_radius=6,
            font=self._font_detail,
            wrap="word",
        )
        self.detail_text.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 12))

    def _pick_validated_log(self, *, title: str, var: tk.StringVar, log_label: str) -> None:
        path = filedialog.askopenfilename(
            title=title,
            filetypes=[("Text files", "*.txt *.log"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            log_text = Path(path).read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            messagebox.showerror("File read error", f"Could not read {log_label} log:\n{exc}")
            return
        ok, reason = validate_ios_xe_log_signature(log_text)
        if not ok:
            messagebox.showerror(
                "Unsupported log",
                f"{log_label} log rejected.\n\n{reason}",
            )
            return
        var.set(path)

    def pick_pre(self):
        self._pick_validated_log(
            title="Select pre-change log",
            var=self.path_inputs["pre_log"],
            log_label="Pre-change",
        )

    def pick_post(self):
        self._pick_validated_log(
            title="Select post-change log",
            var=self.path_inputs["post_log"],
            log_label="Post-change",
        )

    def pick_map(self):
        var = self.path_inputs["port_map"]
        var.set(filedialog.askopenfilename(title="Select port map CSV", filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]) or var.get())

    def run_validation(self):
        try:
            pre_path = self.path_inputs["pre_log"].get().strip()
            post_path = self.path_inputs["post_log"].get().strip()
            port_map_path = self.path_inputs["port_map"].get().strip()
            if not pre_path or not post_path:
                messagebox.showwarning("Missing files", "Select both pre-change and post-change log files.")
                return
            pre_text = Path(pre_path).read_text(encoding="utf-8", errors="ignore")
            post_text = Path(post_path).read_text(encoding="utf-8", errors="ignore")
            for log_label, log_text in (("Pre-change log", pre_text), ("Post-change log", post_text)):
                ok, reason = validate_ios_xe_log_signature(log_text)
                if not ok:
                    messagebox.showerror("Unsupported log", f"{log_label}:\n\n{reason}")
                    return
            self.findings = run_analysis(pre_text, post_text, port_map_path=port_map_path)
            self.populate()
        except Exception as e:
            messagebox.showerror("Validation error", f"{e}\n\n{traceback.format_exc()}")

    def populate(self):
        self.tree.delete(*self.tree.get_children())
        counts = severity_counts(self.findings)
        self.summary.configure(
            text=f"Overall Status: {overall_status(self.findings)}    FAIL: {counts['FAIL']}  WARN: {counts['WARN']}  PASS: {counts['PASS']}  INFO: {counts['INFO']}"
        )
        for idx, f in enumerate(self.findings):
            detail_preview = format_detail_summary(f)
            sev = display_severity(f)
            self.tree.insert("", "end", iid=str(idx), values=(sev, f.category, f.finding, detail_preview), tags=(sev,))

    def show_detail(self, _evt=None):
        sel = self.tree.selection()
        self.detail_text.delete("1.0", "end")
        if not sel:
            return
        f = self.findings[int(sel[0])]
        self.detail_text.insert(
            "end",
            f"{f.severity} - {f.category}\n{f.finding}\n\n{format_detail_pane(f)}",
        )

    def save_html(self):
        if not self.findings:
            messagebox.showwarning("Nothing to export", "Run validation first.")
            return
        path = filedialog.asksaveasfilename(title="Save HTML report", defaultextension=".html", filetypes=[("HTML", "*.html")])
        if not path:
            return
        Path(path).write_text(
            build_html_report(
                self.findings,
                self.path_inputs["pre_log"].get(),
                self.path_inputs["post_log"].get(),
                self.path_inputs["port_map"].get(),
            ),
            encoding="utf-8",
        )
        messagebox.showinfo("Saved", f"HTML report saved:\n{path}")

    def save_pdf(self):
        if not self.findings:
            messagebox.showwarning("Nothing to export", "Run validation first.")
            return
        path = filedialog.asksaveasfilename(title="Save PDF report", defaultextension=".pdf", filetypes=[("PDF", "*.pdf")])
        if not path:
            return
        try:
            browser_error = ""
            try:
                renderer = export_pdf_from_html_browser(
                    self.findings,
                    self.path_inputs["pre_log"].get(),
                    self.path_inputs["post_log"].get(),
                    self.path_inputs["port_map"].get(),
                    path,
                )
            except Exception as browser_exc:
                browser_error = str(browser_exc)
                export_pdf(
                    self.findings,
                    self.path_inputs["pre_log"].get(),
                    self.path_inputs["post_log"].get(),
                    self.path_inputs["port_map"].get(),
                    path,
                )
                renderer = "fallback ReportLab renderer"
            msg = f"PDF report saved:\n{path}\n\nRenderer: {renderer}"
            if browser_error:
                msg += f"\n\nBrowser renderer failed with:\n{browser_error[:1200]}"
            messagebox.showinfo("Saved", msg)
        except Exception as e:
            messagebox.showerror("PDF export error", str(e))

    def clear(self):
        self.findings = []
        self.tree.delete(*self.tree.get_children())
        self.detail_text.delete("1.0", "end")
        self.summary.configure(text="Load pre/post logs and run validation.")
