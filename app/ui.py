from __future__ import annotations

import base64
import csv
import os
import subprocess
import sys
import tkinter as tk
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any

from .config import APP_NAME, APP_VERSION, BACKUP_DIR, PROJECT_DIR, UPI_QR_IMAGE
from .db import backup_database, connect, init_db
from .importer import import_products
from .invoices import generate_invoice_pdf
from .insights import analyze_business
from .services import (
    add_expense, adjust_stock, authenticate, change_password, create_product,
    create_purchase, create_sale, create_user, dashboard_metrics, deactivate_product,
    list_expenses, list_low_stock, list_products, list_purchases, list_sales,
    list_users, profit_loss, refund_sale, report_data, sale_detail, settings,
    set_user_active, update_product, update_settings, money,
)

BG = "#F3F6FB"
NAV = "#14233B"
NAV_HOVER = "#203957"
PRIMARY = "#2563EB"
TEXT = "#1F2937"
MUTED = "#64748B"
WHITE = "#FFFFFF"
GREEN = "#15803D"
RED = "#B91C1C"
BORDER = "#DCE3ED"


def _float(text: str, label: str, default: float = 0.0) -> float:
    try:
        value = float(str(text).strip() or default)
    except ValueError as exc:
        raise ValueError(f"{label} must be a number.") from exc
    return value


def _tree(parent: tk.Widget, columns: list[tuple[str, str, int]], height: int = 12) -> ttk.Treeview:
    names = [c[0] for c in columns]
    frame = ttk.Frame(parent)
    frame.pack(fill="both", expand=True)
    tree = ttk.Treeview(frame, columns=names, show="headings", height=height)
    ybar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    xbar = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
    for key, title, width in columns:
        tree.heading(key, text=title)
        tree.column(key, width=width, minwidth=65, anchor="w")
    tree.grid(row=0, column=0, sticky="nsew")
    ybar.grid(row=0, column=1, sticky="ns")
    xbar.grid(row=1, column=0, sticky="ew")
    frame.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)
    return tree


def _clear_tree(tree: ttk.Treeview) -> None:
    tree.delete(*tree.get_children())


class RetailWizardApp:
    def __init__(self, root: tk.Tk, db_path: str | Path | None = None):
        self.root = root
        self.db_path = db_path
        init_db(db_path)
        self.current_user: dict[str, Any] | None = None
        self.cart: dict[int, dict[str, Any]] = {}
        self.purchase_cart: dict[int, dict[str, Any]] = {}
        self.active_page = "Dashboard"
        # Dashboard timers are cancelled whenever the user leaves the dashboard.
        self._dashboard_clock_after_id: str | None = None
        self._dashboard_refresh_after_id: str | None = None
        self._dashboard_clock_label: tk.Label | None = None
        self._dashboard_last_updated_label: tk.Label | None = None
        self._dashboard_metric_labels: dict[str, tk.Label] = {}
        self._dashboard_recent_tree: ttk.Treeview | None = None
        self.style = ttk.Style()
        self._configure_style()
        self.root.title(f"{APP_NAME} | Retail Management")
        self.root.geometry("1440x820")
        self.root.minsize(1120, 680)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)
        self.show_entry_screen()

    def _configure_style(self) -> None:
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass
        self.style.configure("Treeview", background=WHITE, fieldbackground=WHITE, foreground=TEXT,
                             rowheight=30, bordercolor=BORDER, font=("Segoe UI", 9))
        self.style.configure("Treeview.Heading", background="#E9EEF6", foreground=TEXT,
                             font=("Segoe UI", 9, "bold"), padding=(8, 8))
        self.style.map("Treeview", background=[("selected", "#DCEAFE")], foreground=[("selected", TEXT)])
        self.style.configure("TCombobox", padding=6)
        self.style.configure("TEntry", padding=6)
        self.style.configure("TButton", padding=(11, 8), font=("Segoe UI", 9))
        self.style.configure("Secondary.TButton", padding=(10, 8), font=("Segoe UI", 9))
        self.style.configure("Accent.TButton", background="#0F766E", foreground=WHITE, font=("Segoe UI", 9, "bold"), padding=(12, 9))
        self.style.map("Accent.TButton", background=[("active", "#115E59")])
        self.style.configure("Primary.TButton", background=PRIMARY, foreground=WHITE, font=("Segoe UI", 9, "bold"))
        self.style.map("Primary.TButton", background=[("active", "#1D4ED8")])

    def show_entry_screen(self) -> None:
        """Show a clear welcome page with separate Register and Login paths."""
        self._cancel_dashboard_timers()
        self.active_page = "Welcome"
        for child in self.root.winfo_children():
            child.destroy()
        self.root.title(f"{APP_NAME} | Welcome")
        self._show_welcome()

    def _show_welcome(self) -> None:
        for child in self.root.winfo_children():
            child.destroy()
        shell = tk.Frame(self.root, bg="#EAF0F8")
        shell.pack(fill="both", expand=True)
        hero = tk.Frame(shell, bg=NAV, height=205)
        hero.pack(fill="x")
        hero.pack_propagate(False)
        tk.Label(hero, text="RETAIL WIZARD", bg=NAV, fg=WHITE,
                 font=("Segoe UI", 27, "bold")).pack(anchor="center", pady=(36, 6))
        tk.Label(hero, text="A smarter workspace for your store", bg=NAV, fg="#C7D5E7",
                 font=("Segoe UI", 11)).pack(anchor="center")

        panel = tk.Frame(shell, bg="#EAF0F8")
        panel.pack(fill="both", expand=True, padx=30, pady=26)
        tk.Label(panel, text="Welcome", bg="#EAF0F8", fg=TEXT,
                 font=("Segoe UI", 22, "bold")).pack(pady=(8, 4))
        tk.Label(panel, text="Choose how you would like to continue.", bg="#EAF0F8", fg=MUTED,
                 font=("Segoe UI", 10)).pack(pady=(0, 22))

        cards = tk.Frame(panel, bg="#EAF0F8")
        cards.pack()
        for col in range(2):
            cards.columnconfigure(col, weight=1, minsize=285)

        register_card = tk.Frame(cards, bg=WHITE, highlightbackground=BORDER, highlightthickness=1, width=300, height=255)
        register_card.grid(row=0, column=0, padx=12, sticky="nsew")
        register_card.pack_propagate(False)
        tk.Label(register_card, text="＋", bg="#E8F0FF", fg=PRIMARY, font=("Segoe UI", 25, "bold"),
                 width=3, height=1).pack(pady=(24, 10))
        tk.Label(register_card, text="Create an account", bg=WHITE, fg=TEXT,
                 font=("Segoe UI", 14, "bold")).pack(pady=3)
        tk.Label(register_card, text="Register the store owner on first setup,\nor join as a cashier afterwards.",
                 bg=WHITE, fg=MUTED, font=("Segoe UI", 9), justify="center").pack(pady=(3, 17))
        ttk.Button(register_card, text="Register", style="Primary.TButton",
                   command=self._show_registration).pack(fill="x", padx=25)

        login_card = tk.Frame(cards, bg=WHITE, highlightbackground=BORDER, highlightthickness=1, width=300, height=255)
        login_card.grid(row=0, column=1, padx=12, sticky="nsew")
        login_card.pack_propagate(False)
        tk.Label(login_card, text="↪", bg="#E5F7F1", fg=GREEN, font=("Segoe UI", 25, "bold"),
                 width=3, height=1).pack(pady=(24, 10))
        tk.Label(login_card, text="Sign in", bg=WHITE, fg=TEXT,
                 font=("Segoe UI", 14, "bold")).pack(pady=3)
        tk.Label(login_card, text="Access your dashboard, inventory,\npoint of sale and store reports.",
                 bg=WHITE, fg=MUTED, font=("Segoe UI", 9), justify="center").pack(pady=(3, 17))
        ttk.Button(login_card, text="Login", style="Accent.TButton",
                   command=self._show_login).pack(fill="x", padx=25)
        tk.Label(panel, text="Your store data stays in the local SQLite database on this device.",
                 bg="#EAF0F8", fg=MUTED, font=("Segoe UI", 8)).pack(side="bottom", pady=3)

    def _auth_shell(self, title: str, subtitle: str) -> tk.Frame:
        for child in self.root.winfo_children():
            child.destroy()
        shell = tk.Frame(self.root, bg="#EAF0F8")
        shell.pack(fill="both", expand=True)
        card = tk.Frame(shell, bg=WHITE, highlightbackground=BORDER, highlightthickness=1)
        card.place(relx=0.5, rely=0.5, anchor="center", width=490)
        tk.Label(card, text="RETAIL WIZARD", bg=WHITE, fg=PRIMARY,
                 font=("Segoe UI", 11, "bold")).pack(pady=(25, 6))
        tk.Label(card, text=title, bg=WHITE, fg=TEXT,
                 font=("Segoe UI", 21, "bold")).pack(pady=(0, 4))
        tk.Label(card, text=subtitle, bg=WHITE, fg=MUTED,
                 font=("Segoe UI", 9), wraplength=380).pack(pady=(0, 18))
        return card

    def _show_registration(self) -> None:
        """Register the first account as admin; later public registrations are cashiers."""
        card = self._auth_shell("Create your account", "Complete the form. Your account will be ready for sign in.")
        existing_users = list_users(self.db_path)
        assigned_role = "admin" if not existing_users else "cashier"
        role_label = "Store administrator" if assigned_role == "admin" else "Cashier account"
        tk.Label(card, text=f"Account type: {role_label}", bg=WHITE, fg=GREEN,
                 font=("Segoe UI", 9, "bold")).pack(pady=(0, 10))
        fields: dict[str, ttk.Entry] = {}
        for key, label, secret in [
            ("name", "Full name", False), ("username", "Username", False),
            ("password", "Password (at least 8 characters)", True),
            ("confirm", "Confirm password", True),
        ]:
            tk.Label(card, text=label, bg=WHITE, fg=TEXT, anchor="w",
                     font=("Segoe UI", 9, "bold")).pack(fill="x", padx=42)
            entry = ttk.Entry(card, show="•" if secret else "")
            entry.pack(fill="x", padx=42, pady=(4, 11), ipady=4)
            fields[key] = entry
        status = tk.Label(card, text="", bg=WHITE, fg=RED, font=("Segoe UI", 9), wraplength=380)
        status.pack(pady=(0, 5))

        def register() -> None:
            if fields["password"].get() != fields["confirm"].get():
                status.config(text="Passwords do not match.")
                return
            try:
                create_user(fields["name"].get(), fields["username"].get(),
                            fields["password"].get(), assigned_role, self.db_path)
            except Exception as exc:
                status.config(text=str(exc))
                return
            messagebox.showinfo("Registration complete", "Your account has been created. Please sign in.", parent=self.root)
            self._show_login(prefill_username=fields["username"].get().strip())

        ttk.Button(card, text="Create account", style="Primary.TButton", command=register).pack(fill="x", padx=42, pady=(5, 8))
        ttk.Button(card, text="Back to welcome", command=self._show_welcome).pack(fill="x", padx=42, pady=(0, 22))
        fields["confirm"].bind("<Return>", lambda _e: register())
        fields["name"].focus_set()

    def _show_login(self, prefill_username: str = "") -> None:
        card = self._auth_shell("Welcome back", "Sign in to open your Retail Wizard workspace.")
        tk.Label(card, text="Username", bg=WHITE, fg=TEXT, anchor="w",
                 font=("Segoe UI", 9, "bold")).pack(fill="x", padx=42)
        username = ttk.Entry(card)
        username.pack(fill="x", padx=42, pady=(4, 14), ipady=4)
        username.insert(0, prefill_username)
        tk.Label(card, text="Password", bg=WHITE, fg=TEXT, anchor="w",
                 font=("Segoe UI", 9, "bold")).pack(fill="x", padx=42)
        password = ttk.Entry(card, show="•")
        password.pack(fill="x", padx=42, pady=(4, 8), ipady=4)
        status = tk.Label(card, text="", bg=WHITE, fg=RED, font=("Segoe UI", 9))
        status.pack(pady=(0, 8))

        def sign_in(_event: Any = None) -> None:
            user = authenticate(username.get(), password.get(), self.db_path)
            if not user:
                status.config(text="Invalid username or password, or account is inactive.")
                password.delete(0, tk.END)
                return
            self.current_user = user
            self._show_main_shell()

        ttk.Button(card, text="Sign in", style="Primary.TButton", command=sign_in).pack(fill="x", padx=42, pady=(3, 8))
        ttk.Button(card, text="Back to welcome", command=self._show_welcome).pack(fill="x", padx=42, pady=(0, 22))
        password.bind("<Return>", sign_in)
        username.focus_set()

    def _show_main_shell(self) -> None:
        for child in self.root.winfo_children():
            child.destroy()
        user = self.current_user or {}
        self.root.title(f"{APP_NAME} | {user.get('full_name', '')}")
        shell = tk.Frame(self.root, bg=BG)
        shell.pack(fill="both", expand=True)
        self.sidebar = tk.Frame(shell, bg=NAV, width=218)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        tk.Label(self.sidebar, text="RETAIL\nWIZARD", bg=NAV, fg=WHITE,
                 font=("Segoe UI", 19, "bold"), justify="left").pack(anchor="w", padx=24, pady=(25, 4))
        tk.Label(self.sidebar, text=f"v{APP_VERSION}", bg=NAV, fg="#A9B9CE",
                 font=("Segoe UI", 8)).pack(anchor="w", padx=25, pady=(0, 20))
        self.nav_buttons: dict[str, tk.Button] = {}
        self.content = tk.Frame(shell, bg=BG)
        self.content.pack(side="left", fill="both", expand=True)
        nav_items = ["Dashboard", "Point of Sale", "Products", "Sales History", "Purchases", "Expenses", "Reports", "AI Insights", "Users & Settings"]
        if user.get("role") != "admin":
            nav_items = ["Dashboard", "Point of Sale", "Products", "Sales History"]
        for item in nav_items:
            button = tk.Button(self.sidebar, text=f"  {item}", anchor="w", bg=NAV, fg="#D8E3F0",
                               activebackground=NAV_HOVER, activeforeground=WHITE, relief="flat",
                               font=("Segoe UI", 10), padx=18, pady=10,
                               command=lambda page=item: self.navigate(page))
            button.pack(fill="x", padx=9, pady=2)
            self.nav_buttons[item] = button
        tk.Frame(self.sidebar, bg="#34465F", height=1).pack(fill="x", padx=18, pady=(20, 12))
        tk.Label(self.sidebar, text=user.get("full_name", ""), bg=NAV, fg=WHITE,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=24)
        tk.Label(self.sidebar, text=user.get("role", "").title(), bg=NAV, fg="#A9B9CE",
                 font=("Segoe UI", 8)).pack(anchor="w", padx=24, pady=(2, 9))
        tk.Button(self.sidebar, text="  Sign out", anchor="w", bg=NAV, fg="#FCA5A5",
                  activebackground=NAV_HOVER, activeforeground=WHITE, relief="flat",
                  font=("Segoe UI", 9), padx=18, pady=9, command=self.logout).pack(fill="x", padx=9, side="bottom", pady=16)
        self.navigate("Dashboard")

    def _cancel_dashboard_timers(self) -> None:
        """Stop dashboard callbacks before its widgets are destroyed."""
        for attr in ("_dashboard_clock_after_id", "_dashboard_refresh_after_id"):
            after_id = getattr(self, attr, None)
            if after_id:
                try:
                    self.root.after_cancel(after_id)
                except tk.TclError:
                    pass
                setattr(self, attr, None)

    def navigate(self, page: str) -> None:
        self._cancel_dashboard_timers()
        self.active_page = page
        for name, button in self.nav_buttons.items():
            button.configure(bg=NAV_HOVER if name == page else NAV,
                             fg=WHITE if name == page else "#D8E3F0")
        for child in self.content.winfo_children():
            child.destroy()
        page_builders = {
            "Dashboard": self._page_dashboard,
            "Point of Sale": self._page_pos,
            "Products": self._page_products,
            "Sales History": self._page_sales,
            "Purchases": self._page_purchases,
            "Expenses": self._page_expenses,
            "Reports": self._page_reports,
            "Users & Settings": self._page_settings,
            "AI Insights": self._page_ai_insights,
        }
        page_builders[page]()

    def _page_header(self, title: str, subtitle: str) -> tk.Frame:
        header = tk.Frame(self.content, bg=BG)
        header.pack(fill="x", padx=28, pady=(24, 18))
        tk.Label(header, text=title, bg=BG, fg=TEXT, font=("Segoe UI", 21, "bold")).pack(anchor="w")
        tk.Label(header, text=subtitle, bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(3, 0))
        return header

    def _card(self, parent: tk.Widget, title: str, value: str, accent: str = PRIMARY) -> tk.Frame:
        card = tk.Frame(parent, bg=WHITE, highlightbackground=BORDER, highlightthickness=1)
        tk.Frame(card, bg=accent, height=4).pack(fill="x")
        tk.Label(card, text=title.upper(), bg=WHITE, fg=MUTED, font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=16, pady=(13, 5))
        tk.Label(card, text=value, bg=WHITE, fg=TEXT, font=("Segoe UI", 19, "bold")).pack(anchor="w", padx=16, pady=(0, 15))
        return card

    def _format_local_sale_time(self, value: Any) -> str:
        """Display SQLite CURRENT_TIMESTAMP values in the computer's local timezone."""
        raw = str(value or "").strip()
        if not raw:
            return "-"
        try:
            parsed = datetime.fromisoformat(raw)
            # SQLite CURRENT_TIMESTAMP is UTC and has no timezone suffix.
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone().strftime("%d %b %Y, %I:%M:%S %p")
        except (TypeError, ValueError, OverflowError):
            return raw

    def _update_dashboard_clock(self) -> None:
        """Update the dashboard clock every second using Windows/local system time."""
        if self.active_page != "Dashboard" or self._dashboard_clock_label is None:
            self._dashboard_clock_after_id = None
            return
        try:
            now = datetime.now().astimezone()
            self._dashboard_clock_label.configure(
                text=now.strftime("%A, %d %B %Y  |  %I:%M:%S %p")
            )
            self._dashboard_clock_after_id = self.root.after(1000, self._update_dashboard_clock)
        except tk.TclError:
            self._dashboard_clock_after_id = None

    def _refresh_dashboard_data(self) -> None:
        """Refresh dashboard KPIs and recent sales without rebuilding the page."""
        if self.active_page != "Dashboard":
            self._dashboard_refresh_after_id = None
            return

        # A manual refresh replaces the pending automatic refresh instead of
        # creating multiple recurring callback loops.
        if self._dashboard_refresh_after_id:
            try:
                self.root.after_cancel(self._dashboard_refresh_after_id)
            except tk.TclError:
                pass
            self._dashboard_refresh_after_id = None

        try:
            metrics = dashboard_metrics(self.db_path)
            values = {
                "sales_today": f"₹{metrics['sales_today']:,.2f}",
                "transactions_today": str(metrics["transactions_today"]),
                "products": str(metrics["products"]),
                "low_stock": str(metrics["low_stock"]),
            }
            for key, value in values.items():
                label = self._dashboard_metric_labels.get(key)
                if label is not None and label.winfo_exists():
                    label.configure(text=value)

            tree = self._dashboard_recent_tree
            if tree is not None and tree.winfo_exists():
                _clear_tree(tree)
                for sale in list_sales(limit=10, db_path=self.db_path):
                    tree.insert(
                        "", "end", iid=str(sale["id"]),
                        values=(
                            sale["invoice_no"],
                            sale["customer_name"],
                            self._format_local_sale_time(sale["sold_at"]),
                            f"₹{sale['total'] - sale['refunded_total']:.2f}",
                            sale["payment_method"],
                        ),
                    )

            if self._dashboard_last_updated_label is not None and self._dashboard_last_updated_label.winfo_exists():
                self._dashboard_last_updated_label.configure(
                    text=f"Last refreshed: {datetime.now().astimezone().strftime('%I:%M:%S %p')}"
                )
        except Exception as exc:
            # Keep the dashboard usable if the database is temporarily busy.
            if self._dashboard_last_updated_label is not None:
                try:
                    self._dashboard_last_updated_label.configure(text=f"Refresh issue: {exc}")
                except tk.TclError:
                    pass
        finally:
            if self.active_page == "Dashboard":
                try:
                    self._dashboard_refresh_after_id = self.root.after(15000, self._refresh_dashboard_data)
                except tk.TclError:
                    self._dashboard_refresh_after_id = None

    def _page_dashboard(self) -> None:
        header = tk.Frame(self.content, bg=BG)
        header.pack(fill="x", padx=28, pady=(24, 18))
        header_left = tk.Frame(header, bg=BG)
        header_left.pack(side="left", fill="x", expand=True)
        tk.Label(header_left, text="Dashboard", bg=BG, fg=TEXT,
                 font=("Segoe UI", 21, "bold")).pack(anchor="w")
        tk.Label(header_left, text=f"Good day, {self.current_user['full_name']}. Here is your store overview.",
                 bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(3, 0))
        header_right = tk.Frame(header, bg=BG)
        header_right.pack(side="right", anchor="ne")
        self._dashboard_clock_label = tk.Label(
            header_right, text="", bg=BG, fg=PRIMARY,
            font=("Segoe UI", 10, "bold"), anchor="e"
        )
        self._dashboard_clock_label.pack(anchor="e")
        self._dashboard_last_updated_label = tk.Label(
            header_right, text="", bg=BG, fg=MUTED, font=("Segoe UI", 8), anchor="e"
        )
        self._dashboard_last_updated_label.pack(anchor="e", pady=(3, 0))
        self._update_dashboard_clock()

        metrics = dashboard_metrics(self.db_path)
        cards = tk.Frame(self.content, bg=BG)
        cards.pack(fill="x", padx=28)
        self._dashboard_metric_labels = {}
        specs = [
            ("sales_today", "Sales today", f"₹{metrics['sales_today']:,.2f}", PRIMARY),
            ("transactions_today", "Transactions today", str(metrics["transactions_today"]), "#0D9488"),
            ("products", "Active products", str(metrics["products"]), "#7C3AED"),
            ("low_stock", "Low-stock items", str(metrics["low_stock"]), RED),
        ]
        for i, (key, title, value, color) in enumerate(specs):
            widget = self._card(cards, title, value, color)
            widget.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 10, 0))
            cards.columnconfigure(i, weight=1)
            children = widget.winfo_children()
            if len(children) >= 3:
                self._dashboard_metric_labels[key] = children[2]

        lower = tk.Frame(self.content, bg=BG)
        lower.pack(fill="both", expand=True, padx=28, pady=20)
        left = tk.Frame(lower, bg=WHITE, highlightbackground=BORDER, highlightthickness=1)
        left.pack(side="left", fill="both", expand=True, padx=(0, 10))
        recent_header = tk.Frame(left, bg=WHITE)
        recent_header.pack(fill="x", padx=16, pady=(10, 6))
        tk.Label(recent_header, text="Recent transactions", bg=WHITE, fg=TEXT,
                 font=("Segoe UI", 12, "bold")).pack(side="left")
        ttk.Button(recent_header, text="Refresh", command=self._refresh_dashboard_data).pack(side="right", padx=(8, 0))
        tree = _tree(left, [("invoice", "Invoice", 185), ("customer", "Customer", 160),
                            ("date", "Date / time (local)", 185), ("total", "Net total", 110), ("payment", "Payment", 90)], 9)
        self._dashboard_recent_tree = tree
        for sale in list_sales(limit=10, db_path=self.db_path):
            tree.insert("", "end", iid=str(sale["id"]), values=(sale["invoice_no"], sale["customer_name"],
                self._format_local_sale_time(sale["sold_at"]), f"₹{sale['total']-sale['refunded_total']:.2f}", sale["payment_method"]))

        ttk.Button(recent_header, text="View details", style="Primary.TButton",
                   command=lambda: self._view_selected_sale(tree)).pack(side="right")
        tree.bind("<Double-1>", lambda _event: self._view_selected_sale(tree))
        tree.bind("<Return>", lambda _event: self._view_selected_sale(tree))
        right = tk.Frame(lower, bg=WHITE, highlightbackground=BORDER, highlightthickness=1, width=360)
        right.pack(side="left", fill="both", padx=(10, 0))
        right.pack_propagate(False)
        tk.Label(right, text="Stock alerts", bg=WHITE, fg=TEXT, font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=16, pady=13)
        low_items = list_low_stock(self.db_path)
        if not low_items:
            tk.Label(right, text="All active products are above their reorder levels.", bg=WHITE,
                     fg=GREEN, font=("Segoe UI", 9), wraplength=300).pack(anchor="w", padx=16, pady=12)
        else:
            alert_tree = _tree(right, [("sku", "SKU", 90), ("name", "Product", 155), ("stock", "Stock", 55)], 9)
            for product in low_items[:50]:
                alert_tree.insert("", "end", values=(product["sku"], product["name"], product["stock_qty"]))
        footer = tk.Frame(self.content, bg=BG)
        footer.pack(fill="x", padx=28, pady=(0, 18))
        ttk.Button(footer, text="New sale", style="Primary.TButton", command=lambda: self.navigate("Point of Sale")).pack(side="left")
        ttk.Button(footer, text="Manage products", command=lambda: self.navigate("Products")).pack(side="left", padx=8)
        ttk.Button(footer, text="Backup database", command=self._backup_database).pack(side="right")
        self._refresh_dashboard_data()

    def _page_products(self) -> None:
        self._page_header("Product catalogue", "Manage SKUs, selling price, tax, discounts, stock and expiry details.")
        toolbar = tk.Frame(self.content, bg=BG)
        toolbar.pack(fill="x", padx=28, pady=(0, 12))
        search = ttk.Entry(toolbar, width=34)
        search.pack(side="left", ipady=4)
        ttk.Button(toolbar, text="Search", command=lambda: refresh()).pack(side="left", padx=6)
        ttk.Button(toolbar, text="Add product", style="Primary.TButton", command=self._product_dialog).pack(side="right", padx=4)
        ttk.Button(toolbar, text="Import Excel / CSV", command=self._import_products).pack(side="right", padx=4)
        ttk.Button(toolbar, text="Export CSV", command=lambda: self._export_tree(tree, "products.csv")).pack(side="right", padx=4)
        ttk.Button(toolbar, text="Adjust stock", command=lambda: self._adjust_product_stock(tree)).pack(side="right", padx=4)
        ttk.Button(toolbar, text="Edit selected", command=lambda: self._edit_product(tree)).pack(side="right", padx=4)
        ttk.Button(toolbar, text="Deactivate", command=lambda: self._deactivate_product(tree)).pack(side="right", padx=4)
        frame = tk.Frame(self.content, bg=WHITE, highlightbackground=BORDER, highlightthickness=1)
        frame.pack(fill="both", expand=True, padx=28, pady=(0, 26))
        columns = [("id", "ID", 48), ("sku", "SKU", 105), ("name", "Product", 220), ("category", "Category", 120),
                   ("brand", "Brand", 110), ("price", "Price", 85), ("cost", "Cost", 85), ("discount", "Disc %", 65),
                   ("tax", "Tax %", 65), ("stock", "Stock", 75), ("reorder", "Reorder", 75), ("expiry", "Expiry", 95)]
        tree = _tree(frame, columns, 18)

        def refresh() -> None:
            term = search.get()
            _clear_tree(tree)
            for product in list_products(term, db_path=self.db_path):
                tree.insert("", "end", iid=str(product["id"]), values=(product["id"], product["sku"], product["name"],
                    product["category"], product["brand"], f"₹{product['price']:.2f}", f"₹{product['cost_price']:.2f}",
                    f"{product['discount_percent']:g}", f"{product['tax_percent']:g}", f"{product['stock_qty']:g}",
                    f"{product['reorder_level']:g}", product["expiry_date"] or "-"))
        self._products_refresh = refresh
        refresh()
        search.bind("<Return>", lambda _e: refresh())

    def _product_dialog(self, product: dict[str, Any] | None = None) -> None:
        """Scrollable product form with a permanently visible Save button."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Edit product" if product else "Add product")
        dialog.configure(bg=BG)
        dialog.geometry("720x690")
        dialog.minsize(600, 520)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.update_idletasks()
        x = max(0, (dialog.winfo_screenwidth() - 720) // 2)
        y = max(0, (dialog.winfo_screenheight() - 690) // 2)
        dialog.geometry(f"720x690+{x}+{y}")

        heading = tk.Frame(dialog, bg=BG)
        heading.pack(fill="x", padx=22, pady=(17, 10))
        tk.Label(heading, text="Product details", bg=BG, fg=TEXT,
                 font=("Segoe UI", 18, "bold")).pack(anchor="w")
        tk.Label(heading, text="Fields marked optional may be left blank.", bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(3, 0))

        body = tk.Frame(dialog, bg=WHITE, highlightbackground=BORDER, highlightthickness=1)
        body.pack(fill="both", expand=True, padx=20, pady=(0, 10))
        canvas = tk.Canvas(body, bg=WHITE, highlightthickness=0)
        scrollbar = ttk.Scrollbar(body, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        form = tk.Frame(canvas, bg=WHITE)
        window_id = canvas.create_window((0, 0), window=form, anchor="nw")
        form.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window_id, width=e.width))
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))
        default_tax = settings(self.db_path).get("default_tax_percent", "0")
        fields = [
            ("sku", "SKU / Product code", ""), ("barcode", "Barcode (optional)", ""),
            ("name", "Product name", ""), ("category", "Category", "General"),
            ("brand", "Brand", ""), ("unit", "Unit (pcs, kg, litre...)", "pcs"),
            ("price", "Selling price (₹)", "0"), ("cost_price", "Purchase cost (₹)", "0"),
            ("discount_percent", "Discount (%)", "0"), ("tax_percent", "Tax (%)", default_tax),
            ("stock_qty", "Opening / current stock", "0"), ("reorder_level", "Low-stock alert at", "5"),
            ("expiry_date", "Expiry date (YYYY-MM-DD, optional)", ""),
        ]
        variables: dict[str, tk.StringVar] = {}
        for index, (key, label, default) in enumerate(fields):
            row, col = divmod(index, 2)
            cell = tk.Frame(form, bg=WHITE)
            cell.grid(row=row, column=col, sticky="ew", padx=14, pady=9)
            tk.Label(cell, text=label, bg=WHITE, fg=MUTED,
                     font=("Segoe UI", 8, "bold")).pack(anchor="w")
            var = tk.StringVar(value=str(product.get(key, default) if product else default))
            field_entry = ttk.Entry(cell, textvariable=var)
            field_entry.pack(fill="x", pady=(5, 0), ipady=3)
            if key in {"price", "cost_price", "discount_percent", "tax_percent", "stock_qty", "reorder_level"}:
                field_entry.bind("<FocusIn>", lambda event: event.widget.after_idle(
                    lambda widget=event.widget: widget.select_range(0, tk.END)))
            if product and key == "stock_qty":
                field_entry.configure(state="disabled")
            variables[key] = var
        form.columnconfigure(0, weight=1)
        form.columnconfigure(1, weight=1)
        footer = tk.Frame(dialog, bg=BG)
        footer.pack(fill="x", padx=20, pady=(0, 15))
        status = tk.Label(footer, text="", bg=BG, fg=RED, font=("Segoe UI", 9), anchor="w")
        status.pack(side="left", fill="x", expand=True)

        def save() -> None:
            data = {key: var.get().strip() for key, var in variables.items()}
            try:
                for key in ("price", "cost_price", "discount_percent", "tax_percent", "stock_qty", "reorder_level"):
                    data[key] = _float(data[key], key)
                if product:
                    update_product(int(product["id"]), data, self.current_user["id"], self.db_path)
                else:
                    create_product(data, self.current_user["id"], self.db_path)
            except Exception as exc:
                status.config(text=str(exc))
                return
            canvas.unbind_all("<MouseWheel>")
            dialog.destroy()
            if hasattr(self, "_products_refresh"):
                self._products_refresh()
            messagebox.showinfo("Saved", "Product details saved successfully.", parent=self.root)

        ttk.Button(footer, text="Cancel", command=lambda: (canvas.unbind_all("<MouseWheel>"), dialog.destroy())).pack(side="right")
        ttk.Button(footer, text="Save product", style="Primary.TButton", command=save).pack(side="right", padx=8)
        dialog.bind("<Escape>", lambda _e: (canvas.unbind_all("<MouseWheel>"), dialog.destroy()))
        fields_focus = form.winfo_children()[0].winfo_children()[-1]
        fields_focus.focus_set()

    def _selected_product(self, tree: ttk.Treeview) -> dict[str, Any] | None:
        selected = tree.selection()
        if not selected:
            messagebox.showwarning("Select product", "Choose a product row first.", parent=self.root)
            return None
        product_id = int(selected[0])
        return next((p for p in list_products(include_inactive=True, db_path=self.db_path) if p["id"] == product_id), None)

    def _edit_product(self, tree: ttk.Treeview) -> None:
        product = self._selected_product(tree)
        if product: self._product_dialog(product)

    def _deactivate_product(self, tree: ttk.Treeview) -> None:
        product = self._selected_product(tree)
        if not product: return
        if messagebox.askyesno("Deactivate product", f"Deactivate {product['name']}? It will no longer appear in POS.", parent=self.root):
            try:
                deactivate_product(product["id"], self.current_user["id"], self.db_path)
                self._products_refresh()
            except Exception as exc: messagebox.showerror("Could not deactivate", str(exc), parent=self.root)

    def _adjust_product_stock(self, tree: ttk.Treeview) -> None:
        product = self._selected_product(tree)
        if not product: return
        qty = simpledialog.askfloat("Stock adjustment", f"Current stock: {product['stock_qty']:g}\nEnter change (+ to add, - to remove):", parent=self.root)
        if qty is None: return
        reason = simpledialog.askstring("Reason", "Why is stock being adjusted?", parent=self.root) or "Manual correction"
        try:
            adjust_stock(product["id"], qty, reason, self.current_user["id"], self.db_path)
            self._products_refresh()
        except Exception as exc: messagebox.showerror("Stock adjustment failed", str(exc), parent=self.root)

    def _import_products(self) -> None:
        path = filedialog.askopenfilename(parent=self.root, filetypes=[("Excel / CSV", "*.xlsx *.xlsm *.csv")])
        if not path: return
        try:
            result = import_products(path, self.current_user["id"], self.db_path)
        except Exception as exc:
            messagebox.showerror("Import failed", str(exc), parent=self.root)
            return
        detail = f"Imported: {result['imported']}\nSkipped: {result['skipped']}"
        if result["errors"]:
            detail += "\n\nFirst issues:\n" + "\n".join(result["errors"][:8])
        messagebox.showinfo("Import result", detail, parent=self.root)
        if hasattr(self, "_products_refresh"): self._products_refresh()

    def _page_pos(self) -> None:
        self._page_header("Point of sale", "Find products, build your cart and complete cash or UPI checkout.")
        body = tk.Frame(self.content, bg=BG)
        body.pack(fill="both", expand=True, padx=28, pady=(0, 24))
        left = tk.Frame(body, bg=WHITE, highlightbackground=BORDER, highlightthickness=1)
        left.pack(side="left", fill="both", expand=True, padx=(0, 10))
        right = tk.Frame(body, bg=WHITE, highlightbackground=BORDER, highlightthickness=1, width=510)
        right.pack(side="left", fill="both", padx=(10, 0))
        right.pack_propagate(False)

        # Reserve a permanent footer before packing the expanding cart table.
        # This keeps the checkout action visible even on smaller laptop screens.
        checkout_footer = tk.Frame(right, bg=WHITE)
        checkout_footer.pack(side="bottom", fill="x", padx=15, pady=(0, 12))
        ttk.Separator(checkout_footer).pack(fill="x", pady=(0, 8))
        checkout_hint = tk.Label(
            checkout_footer,
            text="Cash: verify the amount received, then complete the sale.",
            bg=WHITE, fg=MUTED, font=("Segoe UI", 8), wraplength=455,
            justify="left", anchor="w"
        )
        checkout_hint.pack(fill="x", pady=(0, 6))
        checkout_button = ttk.Button(
            checkout_footer,
            text="Complete cash sale & generate invoice",
            style="Primary.TButton",
            command=lambda: complete_sale()
        )
        checkout_button.pack(fill="x", ipady=5)

        tk.Label(left, text="Find products", bg=WHITE, fg=TEXT,
                 font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=15, pady=(13, 7))
        searchbar = tk.Frame(left, bg=WHITE)
        searchbar.pack(fill="x", padx=15, pady=(0, 9))
        search = ttk.Entry(searchbar)
        search.pack(side="left", fill="x", expand=True, ipady=4)
        qty_var = tk.StringVar(value="1")
        ttk.Label(searchbar, text="Qty").pack(side="left", padx=(8, 3))
        qty_spin = ttk.Spinbox(searchbar, from_=0.01, to=999999, increment=1, textvariable=qty_var, width=6)
        qty_spin.pack(side="left")

        products = list_products(db_path=self.db_path)
        product_map = {p["id"]: p for p in products}
        tree = _tree(left, [("id", "ID", 42), ("sku", "SKU", 100), ("name", "Product", 210),
                            ("price", "Price", 90), ("stock", "Available", 85)], 14)

        def refresh_products() -> None:
            _clear_tree(tree)
            for item in list_products(search.get().strip(), db_path=self.db_path):
                product_map[item["id"]] = item
                if item["stock_qty"] <= 0:
                    continue
                tree.insert("", "end", iid=str(item["id"]), values=(item["id"], item["sku"], item["name"],
                    f"₹{item['price']:.2f}", f"{item['stock_qty']:g}"))

        ttk.Button(searchbar, text="Search", command=refresh_products).pack(side="left", padx=5)
        ttk.Button(searchbar, text="＋ Add to cart", style="Primary.TButton", command=lambda: add_selected()).pack(side="left", padx=(5, 0))
        search.bind("<Return>", lambda _e: refresh_products())
        tk.Label(left, text="Select a product, set quantity, then use Add to cart.", bg=WHITE,
                 fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w", padx=15, pady=(0, 8))

        tk.Label(right, text="Current cart", bg=WHITE, fg=TEXT,
                 font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=15, pady=(13, 7))
        cart_tree = _tree(right, [("sku", "SKU", 82), ("name", "Product", 150), ("qty", "Qty", 52),
                                  ("price", "Unit", 68), ("total", "Line", 82)], 4)
        cart_total_label = tk.Label(right, text="Estimated total: ₹0.00", bg=WHITE, fg=TEXT,
                                    font=("Segoe UI", 15, "bold"))
        cart_total_label.pack(anchor="e", padx=15, pady=(8, 3))
        action_row = tk.Frame(right, bg=WHITE)
        action_row.pack(fill="x", padx=15, pady=(0, 8))

        def redraw_cart() -> float:
            """Render the same per-line Decimal rounding used by the sale service."""
            _clear_tree(cart_tree)
            prepared = []
            pre_order_total = Decimal("0.00")
            try:
                order_discount_pct = Decimal(str(max(0.0, min(100.0, float(self.pos_discount.get() or 0)))))
            except (ValueError, ArithmeticError):
                order_discount_pct = Decimal("0")

            for product_id, item in self.cart.items():
                product = product_map.get(product_id) or next(
                    (x for x in list_products(db_path=self.db_path) if x["id"] == product_id), None)
                if not product:
                    continue
                qty = Decimal(str(item["quantity"]))
                gross = money(Decimal(str(product["price"])) * qty)
                item_discount = money(gross * Decimal(str(product["discount_percent"])) / Decimal("100"))
                discounted = gross - item_discount
                pre_order_total += discounted
                prepared.append((product_id, item, product, qty, gross, item_discount, discounted))

            pre_order_total = money(pre_order_total)
            order_discount_total = money(pre_order_total * order_discount_pct / Decimal("100"))
            discount_remaining = order_discount_total
            total = Decimal("0.00")
            for index, (product_id, item, product, qty, gross, item_discount, discounted) in enumerate(prepared):
                if not pre_order_total or not order_discount_total:
                    allocated_order_discount = Decimal("0.00")
                elif index == len(prepared) - 1:
                    allocated_order_discount = discount_remaining
                else:
                    allocated_order_discount = min(
                        money(order_discount_total * discounted / pre_order_total), discounted)
                    discount_remaining = money(discount_remaining - allocated_order_discount)
                taxable = money(gross - item_discount - allocated_order_discount)
                tax = money(taxable * Decimal(str(product["tax_percent"])) / Decimal("100"))
                line_total = money(taxable + tax)
                total += line_total
                cart_tree.insert("", "end", iid=str(product_id), values=(product["sku"], product["name"],
                    f"{item['quantity']:g}", f"₹{product['price']:.2f}", f"₹{float(line_total):.2f}"))

            total = money(total)
            total_float = float(total)
            cart_total_label.config(text=f"Estimated total: ₹{total_float:.2f}")
            if self.pos_method.get() == "Cash" and not getattr(self, "_pos_cash_manual", False):
                self._pos_cash_updating = True
                self.pos_cash.set(f"{total_float:.2f}")
                self._pos_cash_updating = False
            return total_float

        def add_selected() -> None:
            selection = tree.selection()
            if not selection:
                messagebox.showwarning("Select product", "Select a product from the catalogue first.", parent=self.root)
                return
            product = product_map[int(selection[0])]
            try:
                qty = _float(qty_var.get(), "Quantity")
                if qty <= 0:
                    raise ValueError("Quantity must be greater than zero.")
                existing_qty = float(self.cart.get(product["id"], {}).get("quantity", 0))
                if existing_qty + qty > float(product["stock_qty"]):
                    raise ValueError(f"Only {float(product['stock_qty']) - existing_qty:g} more unit(s) are available.")
            except Exception as exc:
                messagebox.showwarning("Invalid quantity", str(exc), parent=self.root)
                return
            self.cart[product["id"]] = {"product_id": product["id"], "quantity": existing_qty + qty}
            qty_var.set("1")
            redraw_cart()
            cart_tree.selection_set(str(product["id"]))

        def remove_cart_line() -> None:
            selection = cart_tree.selection()
            if not selection:
                messagebox.showinfo("Select cart item", "Choose a cart row to remove.", parent=self.root)
                return
            self.cart.pop(int(selection[0]), None)
            redraw_cart()

        def change_cart_qty(delta: float) -> None:
            selection = cart_tree.selection()
            if not selection:
                messagebox.showinfo("Select cart item", "Choose a cart row first.", parent=self.root)
                return
            product_id = int(selection[0])
            current = float(self.cart[product_id]["quantity"])
            new_qty = current + delta
            product = product_map.get(product_id)
            if new_qty <= 0:
                self.cart.pop(product_id, None)
            elif product and new_qty <= float(product["stock_qty"]):
                self.cart[product_id]["quantity"] = new_qty
            else:
                messagebox.showwarning("Stock limit", f"Available stock is {product['stock_qty']:g}.", parent=self.root)
            redraw_cart()

        ttk.Button(action_row, text="− Qty", command=lambda: change_cart_qty(-1)).pack(side="left")
        ttk.Button(action_row, text="＋ Qty", command=lambda: change_cart_qty(1)).pack(side="left", padx=5)
        ttk.Button(action_row, text="Remove", command=remove_cart_line).pack(side="left")
        ttk.Button(action_row, text="Clear cart", command=lambda: (self.cart.clear(), redraw_cart())).pack(side="right")
        ttk.Separator(right).pack(fill="x", padx=15, pady=7)

        fields = tk.Frame(right, bg=WHITE)
        fields.pack(fill="x", padx=15)
        self.pos_name = tk.StringVar()
        self.pos_phone = tk.StringVar()
        self.pos_discount = tk.StringVar(value="0")
        self.pos_method = tk.StringVar(value="Cash")
        self.pos_cash = tk.StringVar(value="0.00")
        self._pos_cash_manual = False
        self._pos_cash_updating = False
        self._field(fields, "Customer name", self.pos_name, 0)
        self._field(fields, "Phone (optional)", self.pos_phone, 1)
        self._field(fields, "Additional order discount (%)", self.pos_discount, 2)
        method_row = tk.Frame(fields, bg=WHITE)
        method_row.grid(row=2, column=0, columnspan=2, sticky="ew", pady=4)
        tk.Label(method_row, text="Payment method", bg=WHITE, fg=MUTED,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        method = ttk.Combobox(method_row, textvariable=self.pos_method, values=["Cash", "UPI"], state="readonly")
        method.pack(fill="x", pady=(3, 0))
        cash_entry = self._field(fields, "Cash received (₹)", self.pos_cash, 6)
        upi_note = tk.Label(fields, text="UPI checkout opens a separate payment page and displays your own merchant QR image.",
                            bg=WHITE, fg=MUTED, font=("Segoe UI", 8), wraplength=455, justify="left")
        upi_note.grid(row=4, column=0, columnspan=2, sticky="w", pady=(5, 0))
        configured_vpa = settings(self.db_path).get("upi_vpa", "").strip()
        if configured_vpa:
            tk.Label(fields, text=f"UPI ID reference (verify against QR): {configured_vpa}", bg=WHITE, fg=GREEN,
                     font=("Segoe UI", 8, "bold")).grid(row=5, column=0, columnspan=2, sticky="w", pady=(2, 0))

        def cash_changed(*_args: Any) -> None:
            if not getattr(self, "_pos_cash_updating", False):
                self._pos_cash_manual = True
        self.pos_cash.trace_add("write", cash_changed)

        def payment_fields(*_args: Any) -> None:
            is_cash = self.pos_method.get() == "Cash"
            self._set_entry_state(cash_entry, is_cash)
            if is_cash:
                self._pos_cash_manual = False
                checkout_button.configure(text="Complete cash sale & generate invoice")
                checkout_hint.configure(
                    text="Cash: the received amount is prefilled with the total due. Edit it when the customer pays more."
                )
                redraw_cart()
            else:
                self._set_entry_state(cash_entry, False)
                checkout_button.configure(text="Open UPI payment & show merchant QR")
                checkout_hint.configure(
                    text="UPI: open the payment page, scan the store QR, verify receipt in your UPI app, then confirm to generate the invoice."
                )
        method.bind("<<ComboboxSelected>>", payment_fields)
        self.pos_discount.trace_add("write", lambda *_args: redraw_cart())

        def finalize_sale(payment_method: str, tendered: float = 0.0, reference: str = "", confirmed: bool = False) -> bool:
            try:
                discount = _float(self.pos_discount.get(), "Discount")
                sale = create_sale(list(self.cart.values()), self.pos_name.get(), self.pos_phone.get(),
                    self.current_user["id"], payment_method, amount_tendered=tendered,
                    payment_reference=reference, order_discount_percent=discount,
                    upi_confirmed=confirmed, db_path=self.db_path)
            except Exception as exc:
                messagebox.showerror("Checkout failed", str(exc), parent=self.root)
                return False
            detail = sale_detail(sale["id"], self.db_path)
            invoice_path = PROJECT_DIR / "invoices" / f"{sale['invoice_no']}.pdf"
            invoice_generated = False
            try:
                generate_invoice_pdf(detail, invoice_path, settings(self.db_path))
                invoice_status = f"Invoice PDF saved to:\n{invoice_path}"
                invoice_generated = True
            except Exception as exc:
                invoice_status = f"Sale recorded, but PDF generation failed:\n{exc}"

            # Speak only after create_sale has committed successfully. For UPI,
            # this point is reached only after the cashier manually verifies payment.
            self._announce_payment_success(
                payment_method=payment_method,
                amount=float(sale["total"]),
                invoice_no=str(sale["invoice_no"]),
                invoice_generated=invoice_generated,
            )
            self.cart.clear()
            self.pos_name.set("")
            self.pos_phone.set("")
            self.pos_discount.set("0")
            self.pos_method.set("Cash")
            self._pos_cash_manual = False
            self._pos_cash_updating = True
            self.pos_cash.set("0.00")
            self._pos_cash_updating = False
            payment_fields()
            redraw_cart()
            refresh_products()
            messagebox.showinfo("Sale completed", f"Invoice: {sale['invoice_no']}\n"
                f"Total: ₹{sale['total']:.2f}\nChange: ₹{sale['change_due']:.2f}\n\n{invoice_status}", parent=self.root)
            return True

        def open_upi_checkout(total: float) -> None:
            """Show the store-owned static QR and collect manual payment verification."""
            payment = tk.Toplevel(self.root)
            payment.title("UPI payment")
            payment.configure(bg=BG)
            payment.geometry("560x720")
            payment.minsize(500, 650)
            payment.transient(self.root)
            payment.grab_set()
            payment.resizable(True, True)

            # Reserve the action bar first so Confirm/Cancel never scroll below
            # the visible area on a small display.
            footer = tk.Frame(payment, bg=BG)
            footer.pack(side="bottom", fill="x", padx=24, pady=(5, 16))

            tk.Label(payment, text="Complete UPI payment", bg=BG, fg=TEXT,
                     font=("Segoe UI", 20, "bold")).pack(anchor="w", padx=24, pady=(18, 3))
            tk.Label(payment,
                     text="Scan the store's own QR code. Confirm the payment in your UPI/bank app before completing this sale.",
                     bg=BG, fg=MUTED, font=("Segoe UI", 9), wraplength=500,
                     justify="left").pack(anchor="w", padx=24, pady=(0, 10))

            amount_card = tk.Frame(payment, bg=WHITE, highlightbackground=BORDER, highlightthickness=1)
            amount_card.pack(fill="x", padx=24, pady=(0, 8))
            tk.Label(amount_card, text="AMOUNT TO PAY", bg=WHITE, fg=MUTED,
                     font=("Segoe UI", 8, "bold")).pack(pady=(9, 1))
            tk.Label(amount_card, text=f"₹{total:,.2f}", bg=WHITE, fg=PRIMARY,
                     font=("Segoe UI", 24, "bold")).pack(pady=(0, 9))

            qr_holder = tk.Frame(payment, bg=WHITE, highlightbackground=BORDER, highlightthickness=1)
            qr_holder.pack(padx=24, pady=5)
            qr_label = tk.Label(
                qr_holder,
                text=("Store QR image not found.\n\n"
                      "Add your own QR image at:\nassets/store_upi_qr.jpeg"),
                bg=WHITE, fg=MUTED, width=36, height=12, justify="center",
                font=("Segoe UI", 9), padx=12, pady=12
            )
            qr_label.pack(padx=8, pady=8)
            qr_loaded = False
            try:
                if not UPI_QR_IMAGE.is_file():
                    raise FileNotFoundError(
                        f"QR image not found: {UPI_QR_IMAGE}\n"
                        "Copy your merchant QR image to assets/store_upi_qr.jpeg."
                    )
                from PIL import Image, ImageTk
                with Image.open(UPI_QR_IMAGE) as source_image:
                    qr_image = source_image.convert("RGB")
                    resampling = getattr(Image, "Resampling", Image).LANCZOS
                    qr_image.thumbnail((250, 250), resampling)
                    qr_photo = ImageTk.PhotoImage(qr_image)
                qr_label.configure(image=qr_photo, text="", width=250, height=250)
                qr_label.image = qr_photo  # Keep a strong reference or Tk removes the image.
                qr_loaded = True
            except Exception as exc:
                qr_label.configure(
                    text=("Could not load the store QR image.\n\n"
                          "Expected: assets/store_upi_qr.jpeg\n\n"
                          f"Details: {exc}"),
                    image="", width=38, height=10
                )

            path_label = tk.Label(
                payment,
                text=f"QR image: {UPI_QR_IMAGE.relative_to(PROJECT_DIR).as_posix()}",
                bg=BG, fg=MUTED, font=("Segoe UI", 8)
            )
            path_label.pack(pady=(2, 4))
            configured_vpa = settings(self.db_path).get("upi_vpa", "").strip()
            if configured_vpa:
                tk.Label(payment, text=f"UPI ID reference: {configured_vpa}", bg=BG, fg=GREEN,
                         font=("Segoe UI", 8, "bold")).pack(pady=(0, 4))

            tk.Label(payment,
                     text="For a static QR, enter the amount shown above in your UPI app. Verify the payee and amount before paying.",
                     bg=BG, fg="#92400E", font=("Segoe UI", 8), wraplength=500,
                     justify="left").pack(anchor="w", padx=24, pady=(2, 8))

            ref_var = tk.StringVar()
            tk.Label(payment, text="UPI transaction reference / UTR", bg=BG, fg=TEXT,
                     font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=24)
            ref_entry = ttk.Entry(payment, textvariable=ref_var)
            ref_entry.pack(fill="x", padx=24, pady=(4, 8))
            confirmed_var = tk.BooleanVar(value=False)
            ttk.Checkbutton(payment, text="I verified the successful payment in the UPI/bank app.",
                            variable=confirmed_var).pack(anchor="w", padx=24, pady=(0, 8))
            tk.Label(payment,
                     text="Retail Wizard records the cashier's confirmation only. It cannot verify transfers or move money automatically.",
                     bg=BG, fg=MUTED, font=("Segoe UI", 8), wraplength=500,
                     justify="left").pack(anchor="w", padx=24, pady=(0, 8))

            def confirm_payment() -> None:
                if not qr_loaded:
                    messagebox.showwarning(
                        "Store QR unavailable",
                        "Add a valid merchant QR image at assets/store_upi_qr.jpeg before accepting a UPI sale.",
                        parent=payment
                    )
                    return
                if not ref_var.get().strip():
                    messagebox.showwarning("Reference required", "Enter the UPI transaction reference / UTR.", parent=payment)
                    ref_entry.focus_set()
                    return
                if not confirmed_var.get():
                    messagebox.showwarning(
                        "Payment not confirmed",
                        "Verify the money was received in the UPI/bank app and tick the confirmation box.",
                        parent=payment
                    )
                    return
                # Keep the payment window open if the database rejects the sale,
                # so the cashier can correct the issue without losing the reference.
                if finalize_sale("UPI", reference=ref_var.get().strip(), confirmed=True):
                    payment.destroy()

            ttk.Button(footer, text="Cancel", command=payment.destroy).pack(side="right")
            confirm_button = ttk.Button(
                footer, text="Confirm payment & generate invoice", style="Primary.TButton",
                command=confirm_payment
            )
            confirm_button.pack(side="right", padx=8)
            if not qr_loaded:
                confirm_button.configure(state="disabled")
                tk.Label(footer, text="Add your merchant QR image to enable UPI checkout.",
                         bg=BG, fg=RED, font=("Segoe UI", 8)).pack(side="left")
            payment.bind("<Escape>", lambda _event: payment.destroy())

        def complete_sale() -> None:
            if not self.cart:
                messagebox.showwarning("Empty cart", "Add products before checkout.", parent=self.root)
                return
            try:
                discount = _float(self.pos_discount.get(), "Discount")
                if not 0 <= discount <= 100:
                    raise ValueError("Discount must be between 0 and 100 percent.")
            except Exception as exc:
                messagebox.showwarning("Invalid discount", str(exc), parent=self.root)
                return
            total = redraw_cart()
            if self.pos_method.get() == "UPI":
                open_upi_checkout(total)
                return
            try:
                tendered = _float(self.pos_cash.get(), "Cash received")
            except Exception as exc:
                messagebox.showwarning("Invalid cash amount", str(exc), parent=self.root)
                return
            finalize_sale("Cash", tendered=tendered)

        payment_fields()
        refresh_products()
        redraw_cart()

    def _field(self, parent: tk.Widget, label: str, variable: tk.StringVar, row: int) -> ttk.Entry:
        col = row % 2
        grid_row = row // 2
        cell = tk.Frame(parent, bg=WHITE)
        cell.grid(row=grid_row, column=col, sticky="ew", padx=(0, 8) if col == 0 else (8, 0), pady=5)
        tk.Label(cell, text=label, bg=WHITE, fg=MUTED, font=("Segoe UI", 8, "bold")).pack(anchor="w")
        entry = ttk.Entry(cell, textvariable=variable)
        entry.pack(fill="x", pady=(3, 0))
        parent.columnconfigure(0, weight=1); parent.columnconfigure(1, weight=1)
        return entry

    def _find_entry(self, parent: tk.Widget, variable: tk.StringVar) -> ttk.Entry:
        for cell in parent.winfo_children():
            for child in cell.winfo_children():
                if isinstance(child, ttk.Entry) and str(child.cget("textvariable")) == str(variable):
                    return child
        return ttk.Entry(parent)

    def _set_entry_state(self, entry: ttk.Entry, enabled: bool) -> None:
        entry.configure(state="normal" if enabled else "disabled")

    def _page_sales(self) -> None:
        self._page_header("Sales history", "Review completed transactions, retrieve invoices and record partial or full refunds.")
        toolbar = tk.Frame(self.content, bg=BG)
        toolbar.pack(fill="x", padx=28, pady=(0, 12))
        search = ttk.Entry(toolbar, width=36)
        search.pack(side="left", ipady=4)
        tree = _tree(self.content, [("id", "ID", 45), ("invoice", "Invoice", 190), ("date", "Date", 155),
            ("customer", "Customer", 155), ("phone", "Phone", 110), ("payment", "Payment", 80),
            ("total", "Total", 95), ("refunded", "Refunded", 90), ("status", "Status", 125)], 18)

        def refresh() -> None:
            term = search.get()
            _clear_tree(tree)
            for sale in list_sales(term, db_path=self.db_path):
                tree.insert("", "end", iid=str(sale["id"]), values=(sale["id"], sale["invoice_no"], sale["sold_at"],
                    sale["customer_name"], sale["customer_phone"] or "-", sale["payment_method"],
                    f"₹{sale['total']:.2f}", f"₹{sale['refunded_total']:.2f}", sale["status"]))
        ttk.Button(toolbar, text="Search", command=refresh).pack(side="left", padx=6)
        search.bind("<Return>", lambda _e: refresh())
        ttk.Button(toolbar, text="View details / invoice", style="Primary.TButton",
                   command=lambda: self._view_selected_sale(tree)).pack(side="right", padx=4)
        ttk.Button(toolbar, text="Refund selected", command=lambda: self._refund_selected_sale(tree, refresh)).pack(side="right", padx=4)
        tree.bind("<Double-1>", lambda _event: self._view_selected_sale(tree))
        tree.bind("<Return>", lambda _event: self._view_selected_sale(tree))
        refresh()

    def _announce_payment_success(
        self,
        payment_method: str,
        amount: float,
        invoice_no: str,
        invoice_generated: bool,
    ) -> None:
        """Announce a saved sale using Windows SAPI; fail silently if unavailable.

        A static UPI QR is not payment verification. This method is called only
        after create_sale succeeds, and the UPI flow requires cashier confirmation.
        """
        if payment_method.upper() == "UPI":
            payment_text = "UPI payment confirmed by the cashier"
        else:
            payment_text = "Cash payment received"

        invoice_text = "Invoice generated" if invoice_generated else "Sale saved; invoice PDF could not be generated"
        speech = f"{payment_text}. Rupees {amount:.2f}. {invoice_text}. Invoice number {invoice_no}. Thank you."

        try:
            if sys.platform.startswith("win"):
                # PowerShell -EncodedCommand expects UTF-16LE Base64. This avoids
                # quoting/injection issues for invoice numbers and spoken text.
                import base64
                escaped = speech.replace("'", "''")
                script = (
                    "Add-Type -AssemblyName System.Speech; "
                    "$voice = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                    "$voice.Rate = 0; "
                    f"$voice.Speak('{escaped}'); "
                    "$voice.Dispose()"
                )
                encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
                creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                subprocess.Popen(
                    ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=creation_flags,
                )
            else:
                # Optional cross-platform fallback; Windows does not need this package.
                try:
                    import pyttsx3  # type: ignore
                    engine = pyttsx3.init()
                    engine.say(speech)
                    engine.runAndWait()
                except Exception:
                    pass
        except Exception:
            # Audio failure must never undo or block a completed sale.
            pass

    def _speak_transaction_details(self, sale: dict[str, Any], total_cost: Decimal, gross_profit: Decimal) -> None:
        """Speak the selected transaction summary on demand (Windows SAPI)."""
        invoice_no = str(sale.get("invoice_no", ""))
        customer = str(sale.get("customer_name") or "Walk-in customer")
        payment = str(sale.get("payment_method") or "unknown payment method")
        total = Decimal(str(sale.get("total", 0) or 0))
        items = sale.get("items", [])

        item_parts = []
        for item in items:
            name = str(item.get("product_name") or "Product")
            quantity = Decimal(str(item.get("quantity", 0) or 0))
            item_parts.append(f"{name}, quantity {quantity:g}")
        item_summary = "; ".join(item_parts) if item_parts else "No product line items found"

        speech = (
            f"Transaction details for invoice {invoice_no}. Customer {customer}. "
            f"Products purchased: {item_summary}. Total paid, {total:.2f} rupees. "
            f"Payment method, {payment}. Purchase cost, {total_cost:.2f} rupees. "
            f"Gross profit before refunds, {gross_profit:.2f} rupees."
        )

        try:
            if sys.platform.startswith("win"):
                escaped = speech.replace("'", "''")
                script = (
                    "Add-Type -AssemblyName System.Speech; "
                    "$voice = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                    "$voice.Rate = 0; "
                    f"$voice.Speak('{escaped}'); "
                    "$voice.Dispose()"
                )
                encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
                creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                subprocess.Popen(
                    ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=creation_flags,
                )
            else:
                try:
                    import pyttsx3  # type: ignore
                    engine = pyttsx3.init()
                    engine.say(speech)
                    engine.runAndWait()
                except Exception as exc:
                    messagebox.showwarning("Voice unavailable", str(exc), parent=self.root)
        except Exception as exc:
            messagebox.showwarning("Voice unavailable", str(exc), parent=self.root)

    def _view_selected_sale(self, tree: ttk.Treeview) -> None:
        selected = tree.selection()
        if not selected:
            messagebox.showwarning("Select sale", "Choose a sale first.", parent=self.root)
            return

        sale = sale_detail(int(selected[0]), self.db_path)
        if not sale:
            messagebox.showerror("Sale not found", "The selected transaction could not be loaded.", parent=self.root)
            return

        dialog = tk.Toplevel(self.root)
        dialog.title(f"Transaction details - {sale['invoice_no']}")
        dialog.geometry("1320x760")
        dialog.minsize(1050, 620)
        dialog.configure(bg=BG)
        dialog.transient(self.root)

        # Use a grid-based layout so the action footer stays visible even when
        # the product table contains many rows or Windows uses display scaling.
        content = tk.Frame(dialog, bg=BG)
        content.pack(fill="both", expand=True, padx=18, pady=12)
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(2, weight=1)

        tk.Label(
            content,
            text="Transaction details",
            bg=BG,
            fg=TEXT,
            font=("Segoe UI", 18, "bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))

        customer_name = sale.get("customer_name") or "Walk-in customer"
        customer_phone = sale.get("customer_phone") or "-"
        local_sold_at = self._format_local_sale_time(sale.get("sold_at"))
        tk.Label(
            content,
            text=(
                f"Invoice: {sale['invoice_no']}   |   Customer: {customer_name}   |   "
                f"Phone: {customer_phone}   |   Date: {local_sold_at}"
            ),
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 9),
        ).grid(row=1, column=0, sticky="w", pady=(0, 10))

        columns = [
            ("sku", "SKU", 105),
            ("name", "Product", 180),
            ("qty", "Sold qty", 75),
            ("returned", "Returned", 80),
            ("price", "Selling / unit", 105),
            ("cost", "Purchase / unit", 110),
            ("cost_total", "Total cost", 105),
            ("discount", "Discount", 95),
            ("tax", "Tax", 85),
            ("total", "Line total", 105),
            ("profit", "Gross profit", 110),
        ]
        table_holder = tk.Frame(content, bg=BG)
        table_holder.grid(row=2, column=0, sticky="nsew")
        items_tree = _tree(table_holder, columns, 11)

        total_cost = Decimal("0.00")
        total_line_profit = Decimal("0.00")
        for item in sale.get("items", []):
            quantity = Decimal(str(item.get("quantity", 0) or 0))
            unit_price = Decimal(str(item.get("unit_price", 0) or 0))
            unit_cost = Decimal(str(item.get("unit_cost", item.get("cost_price", 0)) or 0))
            discount_amount = Decimal(str(item.get("discount_amount", 0) or 0))
            tax_amount = Decimal(str(item.get("tax_amount", 0) or 0))
            line_total = Decimal(str(item.get("line_total", 0) or 0))
            returned_qty = Decimal(str(item.get("refunded_qty", 0) or 0))

            line_cost = money(quantity * unit_cost)
            # Tax is excluded from revenue when calculating gross margin.
            line_profit = money(line_total - tax_amount - line_cost)
            total_cost += line_cost
            total_line_profit += line_profit

            items_tree.insert(
                "",
                "end",
                iid=str(item["id"]),
                values=(
                    item.get("sku", ""),
                    item.get("product_name", ""),
                    f"{quantity:g}",
                    f"{returned_qty:g}",
                    f"₹{unit_price:.2f}",
                    f"₹{unit_cost:.2f}",
                    f"₹{line_cost:.2f}",
                    f"₹{discount_amount:.2f}",
                    f"₹{tax_amount:.2f}",
                    f"₹{line_total:.2f}",
                    f"₹{line_profit:.2f}",
                ),
            )

        subtotal = Decimal(str(sale.get("subtotal", 0) or 0))
        discount_total = Decimal(str(sale.get("discount_total", 0) or 0))
        tax_total = Decimal(str(sale.get("tax_total", 0) or 0))
        grand_total = Decimal(str(sale.get("total", 0) or 0))
        refunded_total = Decimal(str(sale.get("refunded_total", 0) or 0))
        net_sales_before_tax = money(subtotal - discount_total)
        gross_profit = money(net_sales_before_tax - total_cost)

        summary = tk.Frame(content, bg=WHITE, highlightbackground=BORDER, highlightthickness=1)
        summary.grid(row=3, column=0, sticky="ew", pady=(10, 8))
        tk.Label(summary, text="FINANCIAL SUMMARY", bg=WHITE, fg=TEXT,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=12, pady=(8, 4))
        summary_text = (
            f"Subtotal: ₹{subtotal:.2f}     Discount: ₹{discount_total:.2f}     "
            f"GST / tax: ₹{tax_total:.2f}     Invoice total: ₹{grand_total:.2f}\n"
            f"Purchase cost (COGS): ₹{total_cost:.2f}     "
            f"Net sales before tax: ₹{net_sales_before_tax:.2f}     "
            f"Gross profit before refunds: ₹{gross_profit:.2f}\n"
            f"Refunded amount: ₹{refunded_total:.2f}     "
            f"Payment method: {sale.get('payment_method', '-')}     Status: {sale.get('status', '-')}"
        )
        tk.Label(summary, text=summary_text, bg=WHITE, fg=TEXT,
                 font=("Segoe UI", 9), justify="left", anchor="w").pack(fill="x", padx=12, pady=(0, 8))

        tk.Label(
            content,
            text=(
                "Internal report: purchase cost and profit are not printed on the customer invoice. "
                "Profit shown here is before refunds. If a historical sale has no saved unit cost, "
                "its cost and profit may display as zero."
            ),
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 8),
            wraplength=1250,
            justify="left",
        ).grid(row=4, column=0, sticky="w", pady=(0, 5))

        footer = tk.Frame(content, bg=BG)
        footer.grid(row=5, column=0, sticky="ew", pady=(4, 0))

        def build_invoice_pdf(path: Path) -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            # The PDF receives the same local timestamp shown in this detail view.
            invoice_data = dict(sale)
            invoice_data["sold_at"] = local_sold_at
            generate_invoice_pdf(invoice_data, path, settings(self.db_path))

        def save_pdf() -> None:
            invoices_dir = PROJECT_DIR / "invoices"
            invoices_dir.mkdir(parents=True, exist_ok=True)
            selected_path = filedialog.asksaveasfilename(
                parent=dialog,
                title="Download customer invoice",
                initialdir=str(invoices_dir),
                initialfile=f"{sale['invoice_no']}.pdf",
                defaultextension=".pdf",
                filetypes=[("PDF invoice", "*.pdf")],
            )
            if not selected_path:
                return
            path = Path(selected_path)
            try:
                build_invoice_pdf(path)
                messagebox.showinfo(
                    "Invoice downloaded",
                    f"Customer invoice saved to:\n{path}",
                    parent=dialog,
                )
            except Exception as exc:
                messagebox.showerror(
                    "PDF error", f"Could not create the invoice PDF:\n{exc}", parent=dialog
                )

        def print_invoice() -> None:
            path = PROJECT_DIR / "invoices" / f"{sale['invoice_no']}.pdf"
            try:
                build_invoice_pdf(path)
                if sys.platform.startswith("win"):
                    try:
                        # Use the default PDF application's print verb when available.
                        os.startfile(str(path), "print")  # type: ignore[attr-defined]
                        messagebox.showinfo(
                            "Print request sent",
                            "The invoice PDF was sent to the default print action. Check your printer queue.",
                            parent=dialog,
                        )
                    except OSError:
                        # Some PDF viewers do not register a Windows print verb.
                        os.startfile(str(path))  # type: ignore[attr-defined]
                        messagebox.showinfo(
                            "Invoice opened",
                            "The invoice is open in your PDF viewer. Press Ctrl+P to print it.",
                            parent=dialog,
                        )
                else:
                    opener = ["open", str(path)] if sys.platform == "darwin" else ["xdg-open", str(path)]
                    subprocess.Popen(opener)
                    messagebox.showinfo(
                        "Invoice opened",
                        "The invoice is open in your PDF viewer. Use its Print option to print it.",
                        parent=dialog,
                    )
            except Exception as exc:
                messagebox.showerror(
                    "Print error", f"Could not prepare or open the invoice PDF:\n{exc}", parent=dialog
                )

        ttk.Button(footer, text="Close", command=dialog.destroy).pack(side="right")
        ttk.Button(footer, text="Download invoice (PDF)", style="Primary.TButton",
                   command=save_pdf).pack(side="right", padx=8)
        ttk.Button(footer, text="Print invoice", command=print_invoice).pack(side="right", padx=8)
        ttk.Button(
            footer,
            text="🔊 Generate voice summary",
            command=lambda: self._speak_transaction_details(sale, total_cost, gross_profit),
        ).pack(side="left")

    def _refund_selected_sale(self, tree: ttk.Treeview, refresh: Any) -> None:
        selected = tree.selection()
        if not selected:
            messagebox.showwarning("Select sale", "Choose a sale to refund.", parent=self.root)
            return

        sale = sale_detail(int(selected[0]), self.db_path)
        if not sale:
            messagebox.showerror("Refund unavailable", "The selected transaction could not be loaded.", parent=self.root)
            return

        # Keep the action controls in a fixed footer. The previous pack/expand
        # layout allowed the Treeview to consume the entire dialog and push the
        # refund button below the visible window.
        dialog = tk.Toplevel(self.root)
        dialog.title("Record refund")
        dialog.geometry("820x570")
        dialog.minsize(700, 480)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=1)

        tk.Label(
            dialog,
            text=f"Refund items from {sale['invoice_no']}",
            font=("Segoe UI", 14, "bold"),
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 10))

        table_frame = ttk.Frame(dialog)
        table_frame.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 8))
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        columns = ("id", "name", "sold", "returned", "available")
        item_tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=10, selectmode="browse")
        headings = (("id", "Item ID", 80), ("name", "Product", 300),
                    ("sold", "Sold qty", 100), ("returned", "Returned", 100),
                    ("available", "Refundable", 110))
        for key, label, width in headings:
            item_tree.heading(key, text=label)
            item_tree.column(key, width=width, minwidth=65, anchor="w")
        ybar = ttk.Scrollbar(table_frame, orient="vertical", command=item_tree.yview)
        xbar = ttk.Scrollbar(table_frame, orient="horizontal", command=item_tree.xview)
        item_tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        item_tree.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")

        for item in sale["items"]:
            remaining = max(0.0, float(item["quantity"]) - float(item["refunded_qty"]))
            item_tree.insert(
                "", "end", iid=str(item["id"]),
                values=(item["id"], item["product_name"], item["quantity"], item["refunded_qty"], remaining),
            )

        footer = ttk.Frame(dialog, padding=(16, 8, 16, 14))
        footer.grid(row=2, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        reason_var = tk.StringVar(value="Customer return")
        ttk.Label(footer, text="Refund reason").grid(row=0, column=0, sticky="w")
        ttk.Entry(footer, textvariable=reason_var).grid(row=1, column=0, sticky="ew", pady=(3, 8))
        restock_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            footer, text="Return item to available stock", variable=restock_var,
        ).grid(row=2, column=0, sticky="w", pady=(0, 6))
        ttk.Label(
            footer,
            text="Refunds are recorded for accounting; this app does not initiate an external bank/UPI transfer.",
            foreground=MUTED, wraplength=760,
        ).grid(row=3, column=0, sticky="w", pady=(0, 10))

        def record() -> None:
            row = item_tree.selection()
            if not row:
                messagebox.showwarning("Select item", "Select an item to refund.", parent=dialog)
                return
            item = next((r for r in sale["items"] if int(r["id"]) == int(row[0])), None)
            if item is None:
                messagebox.showerror("Refund failed", "The selected item could not be found.", parent=dialog)
                return
            max_qty = max(0.0, float(item["quantity"]) - float(item["refunded_qty"]))
            if max_qty <= 0:
                messagebox.showinfo("Already refunded", "There is no refundable quantity remaining for this item.", parent=dialog)
                return
            qty = simpledialog.askfloat(
                "Refund quantity",
                f"Refund quantity for {item['product_name']} (maximum {max_qty:g})",
                minvalue=0.01, maxvalue=max_qty, parent=dialog,
            )
            if qty is None:
                return
            try:
                result = refund_sale(
                    sale["id"], {item["id"]: qty}, reason_var.get().strip() or "Customer return",
                    self.current_user["id"], restock=restock_var.get(), db_path=self.db_path,
                )
            except Exception as exc:
                messagebox.showerror("Refund failed", str(exc), parent=dialog)
                return

            # Show the actual amount returned by the service, then refresh the
            # sales list so its Refunded and Status columns update immediately.
            amount = float(result.get("amount", 0) or 0)
            refund_no = result.get("refund_no", "")
            dialog.destroy()
            refresh()
            messagebox.showinfo(
                "Refund recorded",
                f"Refund recorded successfully.\n\nRefund number: {refund_no}\nRefund amount: ₹{amount:.2f}",
                parent=self.root,
            )

        actions = ttk.Frame(footer)
        actions.grid(row=4, column=0, sticky="ew")
        ttk.Button(actions, text="Close", command=dialog.destroy).pack(side="right")
        ttk.Button(
            actions, text="Record refund", style="Primary.TButton", command=record,
        ).pack(side="right", padx=(0, 8))

    def _page_purchases(self) -> None:
        self._page_header("Purchases & suppliers", "Record supplier purchases and automatically increase on-hand inventory.")
        body = tk.Frame(self.content, bg=BG); body.pack(fill="both", expand=True, padx=28, pady=(0, 24))
        form = tk.Frame(body, bg=WHITE, highlightbackground=BORDER, highlightthickness=1)
        form.pack(fill="x", pady=(0, 12))
        tk.Label(form, text="New purchase entry", bg=WHITE, fg=TEXT, font=("Segoe UI", 12, "bold")).grid(row=0, column=0, columnspan=6, sticky="w", padx=14, pady=10)
        supplier = tk.StringVar(); product_var = tk.StringVar(); qty_var = tk.StringVar(value="1"); cost_var = tk.StringVar(value="0")
        products = list_products(db_path=self.db_path); options = [f"{p['id']} | {p['sku']} | {p['name']}" for p in products]
        product_by_option = {options[i]: products[i] for i in range(len(options))}
        ttk.Label(form, text="Supplier", background=WHITE).grid(row=1, column=0, padx=10, sticky="w")
        ttk.Entry(form, textvariable=supplier, width=22).grid(row=2, column=0, padx=10, pady=(3, 12))
        ttk.Label(form, text="Product", background=WHITE).grid(row=1, column=1, padx=10, sticky="w")
        product_combo = ttk.Combobox(form, textvariable=product_var, values=options, width=32, state="readonly")
        product_combo.grid(row=2, column=1, padx=10, pady=(3, 12))
        product_combo.bind("<<ComboboxSelected>>", lambda _e: cost_var.set(str(product_by_option[product_var.get()]["cost_price"])))
        ttk.Label(form, text="Quantity", background=WHITE).grid(row=1, column=2, padx=10, sticky="w")
        ttk.Entry(form, textvariable=qty_var, width=10).grid(row=2, column=2, padx=10, pady=(3, 12))
        ttk.Label(form, text="Unit cost (₹)", background=WHITE).grid(row=1, column=3, padx=10, sticky="w")
        ttk.Entry(form, textvariable=cost_var, width=12).grid(row=2, column=3, padx=10, pady=(3, 12))
        cart_container = tk.Frame(form, bg=WHITE)
        cart_container.grid(row=3, column=0, columnspan=6, sticky="nsew", padx=12, pady=8)
        cart_tree = _tree(cart_container, [("sku", "SKU", 100), ("name", "Product", 200), ("qty", "Qty", 70), ("cost", "Unit cost", 100)], 4)
        form.columnconfigure(5, weight=1)
        def add_purchase_line() -> None:
            p = product_by_option.get(product_var.get())
            if not p: messagebox.showwarning("Choose product", "Select a product.", parent=self.root); return
            try:
                qty = _float(qty_var.get(), "Quantity"); cost = _float(cost_var.get(), "Unit cost")
                if qty <= 0 or cost < 0: raise ValueError("Quantity must be positive and cost cannot be negative.")
            except Exception as exc: messagebox.showerror("Invalid item", str(exc), parent=self.root); return
            self.purchase_cart[p["id"]] = {"product_id": p["id"], "quantity": qty, "unit_cost": cost}
            _clear_tree(cart_tree)
            for pid, line in self.purchase_cart.items():
                product = next(x for x in products if x["id"] == pid)
                cart_tree.insert("", "end", iid=str(pid), values=(product["sku"], product["name"], line["quantity"], f"₹{line['unit_cost']:.2f}"))
        def save_purchase() -> None:
            try:
                result = create_purchase(supplier.get(), list(self.purchase_cart.values()), self.current_user["id"], db_path=self.db_path)
            except Exception as exc: messagebox.showerror("Purchase failed", str(exc), parent=self.root); return
            self.purchase_cart.clear(); _clear_tree(cart_tree); supplier.set("")
            refresh_history()
            messagebox.showinfo("Purchase recorded", f"{result['purchase_no']}\nTotal: ₹{result['total']:.2f}", parent=self.root)
        ttk.Button(form, text="Add item", command=add_purchase_line).grid(row=2, column=4, padx=8)
        ttk.Button(form, text="Record purchase", style="Primary.TButton", command=save_purchase).grid(row=4, column=4, padx=8, pady=10)
        history = tk.Frame(body, bg=WHITE, highlightbackground=BORDER, highlightthickness=1); history.pack(fill="both", expand=True)
        tk.Label(history, text="Purchase history", bg=WHITE, fg=TEXT, font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=14, pady=10)
        history_tree = _tree(history, [("no", "Purchase no.", 190), ("date", "Date", 160), ("supplier", "Supplier", 200),
            ("subtotal", "Subtotal", 105), ("tax", "Tax", 90), ("total", "Total", 110)], 8)
        def refresh_history() -> None:
            _clear_tree(history_tree)
            for p in list_purchases(self.db_path):
                history_tree.insert("", "end", values=(p["purchase_no"], p["purchased_at"], p["supplier_name"],
                    f"₹{p['subtotal']:.2f}", f"₹{p['tax_total']:.2f}", f"₹{p['total']:.2f}"))
        refresh_history()

    def _page_expenses(self) -> None:
        self._page_header("Operating expenses", "Track rent, wages, utilities and other business expenses for profit & loss reporting.")
        form = tk.Frame(self.content, bg=WHITE, highlightbackground=BORDER, highlightthickness=1)
        form.pack(fill="x", padx=28, pady=(0, 14))
        values = {k: tk.StringVar(value=v) for k, v in {"category": "Utilities", "description": "", "amount": "", "date": date.today().isoformat()}.items()}
        labels = [("category", "Category"), ("description", "Description"), ("amount", "Amount (₹)"), ("date", "Date (YYYY-MM-DD)")]
        for i, (key, label) in enumerate(labels):
            cell = tk.Frame(form, bg=WHITE); cell.grid(row=0, column=i, padx=12, pady=12, sticky="ew")
            tk.Label(cell, text=label, bg=WHITE, fg=MUTED, font=("Segoe UI", 8, "bold")).pack(anchor="w")
            if key == "category":
                widget = ttk.Combobox(cell, textvariable=values[key], values=["Rent", "Wages", "Utilities", "Marketing", "Maintenance", "Transport", "Subscription", "Other"], width=18)
            else: widget = ttk.Entry(cell, textvariable=values[key], width=22)
            widget.pack(pady=(4, 0))
            form.columnconfigure(i, weight=1)
        tree = _tree(self.content, [("date", "Date", 120), ("category", "Category", 140), ("description", "Description", 280),
            ("amount", "Amount", 110), ("by", "Recorded by", 150)], 15)
        def refresh() -> None:
            _clear_tree(tree)
            for item in list_expenses(db_path=self.db_path):
                tree.insert("", "end", values=(item["expense_date"], item["category"], item["description"], f"₹{item['amount']:.2f}", item["created_by_name"]))
        def save() -> None:
            try:
                add_expense(values["category"].get(), values["description"].get(), values["amount"].get(), values["date"].get(), self.current_user["id"], self.db_path)
            except Exception as exc: messagebox.showerror("Expense not saved", str(exc), parent=self.root); return
            values["description"].set(""); values["amount"].set(""); refresh()
        ttk.Button(form, text="Add expense", style="Primary.TButton", command=save).grid(row=1, column=3, sticky="e", padx=14, pady=(0, 12))
        refresh()

    def _page_reports(self) -> None:
        self._page_header("Business reports", "Generate sales, inventory, purchasing and best-seller reports for a selected date range.")
        toolbar = tk.Frame(self.content, bg=BG); toolbar.pack(fill="x", padx=28, pady=(0, 12))
        report_type = tk.StringVar(value="Sales")
        start = tk.StringVar(); end = tk.StringVar()
        ttk.Label(toolbar, text="Report").pack(side="left")
        combo = ttk.Combobox(toolbar, textvariable=report_type, values=["Sales", "Stock", "Transactions", "Purchases", "Best sellers", "Profit & Loss"], state="readonly", width=18)
        combo.pack(side="left", padx=6)
        ttk.Label(toolbar, text="From (YYYY-MM-DD)").pack(side="left", padx=(14, 4)); ttk.Entry(toolbar, textvariable=start, width=13).pack(side="left")
        ttk.Label(toolbar, text="To").pack(side="left", padx=(10, 4)); ttk.Entry(toolbar, textvariable=end, width=13).pack(side="left")
        report_frame = tk.Frame(self.content, bg=WHITE, highlightbackground=BORDER, highlightthickness=1); report_frame.pack(fill="both", expand=True, padx=28, pady=(0, 24))
        summary = tk.Label(report_frame, text="", bg=WHITE, fg=TEXT, font=("Segoe UI", 10, "bold")); summary.pack(anchor="w", padx=14, pady=10)
        current_rows: list[dict[str, Any]] = []
        current_tree: ttk.Treeview | None = None
        def generate() -> None:
            nonlocal current_rows, current_tree
            if current_tree: current_tree.master.destroy(); current_tree = None
            summary.config(text="")
            try:
                if start.get(): date.fromisoformat(start.get())
                if end.get(): date.fromisoformat(end.get())
                if start.get() and end.get() and start.get() > end.get(): raise ValueError("Start date must not be after end date.")
            except ValueError as exc: messagebox.showerror("Invalid date", str(exc), parent=self.root); return
            kind = report_type.get()
            if kind == "Profit & Loss":
                result = profit_loss(start.get() or None, end.get() or None, self.db_path)
                summary.config(text="   |   ".join(f"{k.replace('_',' ').title()}: ₹{v:,.2f}" for k, v in result.items()))
                current_rows = [result]
                return
            key = {"Sales": "sales", "Stock": "stock", "Transactions": "transactions", "Purchases": "purchases", "Best sellers": "best_sellers"}[kind]
            current_rows = report_data(key, start.get() or None, end.get() or None, self.db_path)
            if not current_rows:
                summary.config(text="No records found for this selection.")
                return
            summary.config(text=f"{len(current_rows)} record(s)")
            colnames = list(current_rows[0].keys())
            current_tree = _tree(report_frame, [(c, c.replace("_", " ").title(), max(95, min(180, len(c)*11))) for c in colnames], 16)
            for row in current_rows:
                values = [f"₹{v:.2f}" if isinstance(v, float) and any(x in k for x in ("total", "amount", "revenue", "price", "cost", "sales", "profit", "expense", "refund")) else v for k, v in row.items()]
                current_tree.insert("", "end", values=values)
        def export() -> None:
            if not current_rows:
                messagebox.showwarning("No report", "Generate a report first.", parent=self.root); return
            path = filedialog.asksaveasfilename(parent=self.root, defaultextension=".csv", filetypes=[("CSV", "*.csv")])
            if not path: return
            with open(path, "w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(current_rows[0].keys())); writer.writeheader(); writer.writerows(current_rows)
            messagebox.showinfo("Export complete", f"Saved report to:\n{path}", parent=self.root)
        ttk.Button(toolbar, text="Generate", style="Primary.TButton", command=generate).pack(side="left", padx=12)
        ttk.Button(toolbar, text="Export CSV", command=export).pack(side="right")
        generate()

    def _page_ai_insights(self) -> None:
        """Local, explainable AI-assisted retail analysis. No customer data leaves this device."""
        self._page_header("AI business insights", "Explainable local analysis of inventory, sales, margin, refunds and operating costs.")
        toolbar = tk.Frame(self.content, bg=BG)
        toolbar.pack(fill="x", padx=28, pady=(0, 12))
        summary_area = tk.Frame(self.content, bg=BG)
        summary_area.pack(fill="x", padx=28, pady=(0, 12))
        # Scrollable analysis area keeps charts and all recommendations accessible
        # on smaller laptop screens and at high Windows display scaling.
        result_outer = tk.Frame(self.content, bg=BG)
        result_outer.pack(fill="both", expand=True, padx=28, pady=(0, 22))
        result_canvas = tk.Canvas(result_outer, bg=BG, highlightthickness=0, bd=0)
        result_scrollbar = ttk.Scrollbar(result_outer, orient="vertical", command=result_canvas.yview)
        result_canvas.configure(yscrollcommand=result_scrollbar.set)
        result_scrollbar.pack(side="right", fill="y")
        result_canvas.pack(side="left", fill="both", expand=True)
        result_area = tk.Frame(result_canvas, bg=BG)
        result_window = result_canvas.create_window((0, 0), window=result_area, anchor="nw")
        result_area.bind("<Configure>", lambda _event: result_canvas.configure(
            scrollregion=result_canvas.bbox("all")))
        result_canvas.bind("<Configure>", lambda event: result_canvas.itemconfigure(
            result_window, width=event.width))
        current_result: dict[str, Any] = {}

        def render() -> None:
            nonlocal current_result
            current_result = analyze_business(self.db_path)
            for widget in summary_area.winfo_children() + result_area.winfo_children():
                widget.destroy()
            metrics = current_result["metrics"]
            cards = [
                ("Net sales (30 days)", f"₹{metrics['net_sales']:,.2f}", PRIMARY),
                ("Net profit (30 days)", f"₹{metrics['net_profit']:,.2f}", GREEN if metrics["net_profit"] >= 0 else RED),
                ("Low-stock items", str(metrics["low_stock_count"]), RED),
                ("Products analysed", str(metrics["products_count"]), "#7C3AED"),
            ]
            for i, (title, value, color) in enumerate(cards):
                card = self._card(summary_area, title, value, color)
                card.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 9, 0))
                summary_area.columnconfigure(i, weight=1)
            top = tk.Frame(result_area, bg=BG)
            top.pack(fill="x", pady=(0, 8))
            tk.Label(top, text=f"{len(current_result['insights'])} recommendation(s)", bg=BG, fg=TEXT,
                     font=("Segoe UI", 12, "bold")).pack(side="left")
            tk.Label(top, text="Analysis window: last 30 days  •  Local rule-based engine  •  No cloud/API calls",
                     bg=BG, fg=MUTED, font=("Segoe UI", 8)).pack(side="right")

            # Visual summary: a donut for net sales/refunds and a signed bar chart
            # for the main profit-and-loss figures. These use the existing metrics
            # returned by app/insights.py; no third-party chart library is needed.
            charts = tk.Frame(result_area, bg=BG)
            charts.pack(fill="x", pady=(0, 12))
            charts.columnconfigure(0, weight=1, uniform="insight_charts")
            charts.columnconfigure(1, weight=1, uniform="insight_charts")

            donut_card = tk.Frame(charts, bg=WHITE, highlightbackground=BORDER, highlightthickness=1)
            donut_card.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
            tk.Label(donut_card, text="Sales & refunds", bg=WHITE, fg=TEXT,
                     font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=14, pady=(12, 0))
            tk.Label(donut_card, text="Share of recorded gross sales · last 30 days", bg=WHITE, fg=MUTED,
                     font=("Segoe UI", 8)).pack(anchor="w", padx=14, pady=(2, 0))
            donut_body = tk.Frame(donut_card, bg=WHITE)
            donut_body.pack(fill="both", expand=True, padx=8, pady=7)
            donut = tk.Canvas(donut_body, width=190, height=175, bg=WHITE, highlightthickness=0)
            donut.pack(side="left", padx=(4, 0))
            net_sales_value = max(0.0, float(metrics.get("net_sales", 0) or 0))
            refunds_value = max(0.0, float(metrics.get("refunds", 0) or 0))
            donut_total = net_sales_value + refunds_value
            cx1, cy1, cx2, cy2 = 18, 8, 166, 156
            if donut_total > 0:
                net_extent = 360.0 * net_sales_value / donut_total
                if net_sales_value > 0:
                    donut.create_arc(cx1, cy1, cx2, cy2, start=90, extent=net_extent,
                                     style="pieslice", fill=PRIMARY, outline=WHITE, width=2)
                if refunds_value > 0:
                    donut.create_arc(cx1, cy1, cx2, cy2, start=90 + net_extent,
                                     extent=360.0 * refunds_value / donut_total,
                                     style="pieslice", fill="#F59E0B", outline=WHITE, width=2)
                donut.create_oval(49, 39, 135, 125, fill=WHITE, outline=WHITE)
                donut.create_text(92, 72, text="NET SALES", fill=MUTED,
                                  font=("Segoe UI", 7, "bold"))
                center_value = f"₹{net_sales_value:,.0f}"
                donut.create_text(92, 94, text=center_value, fill=TEXT,
                                  font=("Segoe UI", 10, "bold"))
            else:
                donut.create_oval(cx1, cy1, cx2, cy2, fill="#E8EDF5", outline="#E8EDF5")
                donut.create_oval(49, 39, 135, 125, fill=WHITE, outline=WHITE)
                donut.create_text(92, 82, text="NO SALES", fill=MUTED,
                                  font=("Segoe UI", 8, "bold"))
            legend = tk.Frame(donut_body, bg=WHITE)
            legend.pack(side="left", fill="both", expand=True, padx=(8, 3))
            for label, amount, color in (("Net sales", net_sales_value, PRIMARY),
                                         ("Refunds", refunds_value, "#F59E0B")):
                line = tk.Frame(legend, bg=WHITE)
                line.pack(fill="x", pady=(20 if label == "Net sales" else 7, 3))
                swatch = tk.Canvas(line, width=12, height=12, bg=WHITE, highlightthickness=0)
                swatch.pack(side="left", padx=(0, 6))
                swatch.create_rectangle(1, 1, 11, 11, fill=color, outline=color)
                tk.Label(line, text=label, bg=WHITE, fg=TEXT,
                         font=("Segoe UI", 8, "bold")).pack(side="left")
                share = (amount / donut_total * 100) if donut_total else 0.0
                tk.Label(legend, text=f"₹{amount:,.2f}  ·  {share:.1f}%", bg=WHITE, fg=MUTED,
                         font=("Segoe UI", 8)).pack(anchor="w", padx=(18, 0))
            if float(metrics.get("net_sales", 0) or 0) < 0:
                tk.Label(donut_card, text="Refunds exceed gross sales in this period.", bg=WHITE,
                         fg=RED, font=("Segoe UI", 8)).pack(anchor="w", padx=14, pady=(0, 8))

            finance_card = tk.Frame(charts, bg=WHITE, highlightbackground=BORDER, highlightthickness=1)
            finance_card.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
            tk.Label(finance_card, text="Financial performance", bg=WHITE, fg=TEXT,
                     font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=14, pady=(12, 0))
            tk.Label(finance_card, text="Positive and negative values · last 30 days", bg=WHITE, fg=MUTED,
                     font=("Segoe UI", 8)).pack(anchor="w", padx=14, pady=(2, 0))
            bar_chart = tk.Canvas(finance_card, width=600, height=190, bg=WHITE, highlightthickness=0)
            bar_chart.pack(fill="x", expand=True, padx=8, pady=(4, 8))
            finance_rows = [
                ("Net sales", float(metrics.get("net_sales", 0) or 0), PRIMARY),
                ("Cost of goods", max(0.0, float(metrics.get("net_sales", 0) or 0) -
                 float(metrics.get("gross_profit", 0) or 0)), "#64748B"),
                ("Gross profit", float(metrics.get("gross_profit", 0) or 0), GREEN if float(metrics.get("gross_profit", 0) or 0) >= 0 else RED),
                ("Operating expenses", float(metrics.get("operating_expenses", 0) or 0), "#D97706"),
                ("Net profit", float(metrics.get("net_profit", 0) or 0), GREEN if float(metrics.get("net_profit", 0) or 0) >= 0 else RED),
            ]
            max_value = max([abs(value) for _, value, _ in finance_rows] + [1.0])
            baseline = 176
            bar_max_width = 325
            bar_chart.create_line(baseline, 13, baseline, 179, fill="#94A3B8", dash=(3, 3))
            for row_index, (label, value, color) in enumerate(finance_rows):
                y = 24 + row_index * 33
                bar_chart.create_text(8, y + 7, text=label, anchor="w", fill=TEXT,
                                      font=("Segoe UI", 8))
                width = abs(value) / max_value * bar_max_width
                if value >= 0:
                    x2 = baseline + width
                    bar_chart.create_rectangle(baseline, y, x2, y + 14, fill=color, outline=color)
                    value_x = min(590, x2 + 6)
                    anchor = "w"
                else:
                    x1 = baseline - width
                    bar_chart.create_rectangle(x1, y, baseline, y + 14, fill=color, outline=color)
                    value_x = max(130, x1 - 6)
                    anchor = "e"
                bar_chart.create_text(value_x, y + 7, text=f"{'-' if value < 0 else ''}₹{abs(value):,.0f}",
                                      anchor=anchor, fill=TEXT, font=("Segoe UI", 8, "bold"))

            if not current_result["insights"]:
                empty = tk.Frame(result_area, bg=WHITE, highlightbackground=BORDER, highlightthickness=1)
                empty.pack(fill="x", pady=5)
                tk.Label(empty, text="No critical issues detected", bg=WHITE, fg=GREEN,
                         font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=18, pady=(16, 4))
                tk.Label(empty, text="Keep recording purchases, sales and expenses to improve the quality of future analysis.",
                         bg=WHITE, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", padx=18, pady=(0, 16))
            for item in current_result["insights"]:
                card = tk.Frame(result_area, bg=WHITE, highlightbackground=BORDER, highlightthickness=1)
                card.pack(fill="x", pady=5)
                band = {"High": RED, "Medium": "#D97706", "Info": PRIMARY}.get(item["priority"], MUTED)
                line = tk.Frame(card, bg=band, width=5)
                line.pack(side="left", fill="y")
                content = tk.Frame(card, bg=WHITE)
                content.pack(side="left", fill="both", expand=True, padx=14, pady=11)
                head = tk.Frame(content, bg=WHITE)
                head.pack(fill="x")
                tk.Label(head, text=item["title"], bg=WHITE, fg=TEXT,
                         font=("Segoe UI", 10, "bold")).pack(side="left")
                tk.Label(head, text=item["priority"].upper(), bg=WHITE, fg=band,
                         font=("Segoe UI", 8, "bold")).pack(side="right")
                tk.Label(content, text=item["detail"], bg=WHITE, fg=MUTED,
                         font=("Segoe UI", 9), wraplength=1050, justify="left").pack(anchor="w", pady=(5, 4))
                tk.Label(content, text=f"Recommended action: {item['action']}", bg=WHITE, fg=TEXT,
                         font=("Segoe UI", 9, "bold"), wraplength=1050, justify="left").pack(anchor="w")

        def export() -> None:
            if not current_result:
                messagebox.showwarning("No analysis", "Run the analysis first.", parent=self.root)
                return
            path = filedialog.asksaveasfilename(parent=self.root, defaultextension=".csv",
                initialfile="retail_wizard_ai_insights.csv", filetypes=[("CSV", "*.csv")])
            if not path:
                return
            with open(path, "w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.DictWriter(handle, fieldnames=["priority", "title", "detail", "action"])
                writer.writeheader()
                writer.writerows(current_result["insights"])
            messagebox.showinfo("Export complete", f"Recommendations exported to:\n{path}", parent=self.root)

        ttk.Button(toolbar, text="↻ Run analysis", style="Primary.TButton", command=render).pack(side="left")
        ttk.Button(toolbar, text="Export recommendations", command=export).pack(side="left", padx=8)
        render()

    def _page_settings(self) -> None:
        self._page_header("Users, settings & backup", "Manage staff access, store identity, low-stock alerts and database backups.")
        body = tk.Frame(self.content, bg=BG); body.pack(fill="both", expand=True, padx=28, pady=(0, 24))
        left = tk.Frame(body, bg=WHITE, highlightbackground=BORDER, highlightthickness=1); left.pack(side="left", fill="both", expand=True, padx=(0, 10))
        right = tk.Frame(body, bg=WHITE, highlightbackground=BORDER, highlightthickness=1, width=425); right.pack(side="left", fill="both", expand=True, padx=(10, 0))
        right.pack_propagate(False)
        tk.Label(left, text="Store configuration", bg=WHITE, fg=TEXT, font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=16, pady=14)
        prefs = settings(self.db_path)
        vars_ = {k: tk.StringVar(value=prefs.get(k, "")) for k in ["store_name", "store_address", "store_phone", "store_email", "low_stock_threshold", "default_tax_percent", "upi_vpa"]}
        for key, label in [("store_name", "Store name"), ("store_address", "Address"), ("store_phone", "Phone"),
                           ("store_email", "Email"), ("low_stock_threshold", "Default low-stock threshold"),
                           ("default_tax_percent", "Default tax (%)"), ("upi_vpa", "UPI VPA (display/reference only)")]:
            cell = tk.Frame(left, bg=WHITE); cell.pack(fill="x", padx=16, pady=5)
            tk.Label(cell, text=label, bg=WHITE, fg=MUTED, font=("Segoe UI", 8, "bold")).pack(anchor="w")
            ttk.Entry(cell, textvariable=vars_[key]).pack(fill="x", pady=(3, 0))
        def save_settings() -> None:
            try: update_settings({k: v.get() for k, v in vars_.items()}, self.current_user["id"], self.db_path)
            except Exception as exc: messagebox.showerror("Settings not saved", str(exc), parent=self.root); return
            messagebox.showinfo("Saved", "Store settings updated.", parent=self.root)
        ttk.Button(left, text="Save settings", style="Primary.TButton", command=save_settings).pack(anchor="e", padx=16, pady=14)
        tk.Label(right, text="Staff accounts", bg=WHITE, fg=TEXT, font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=16, pady=14)
        user_tree = _tree(right, [("name", "Name", 115), ("username", "Username", 100), ("role", "Role", 70), ("status", "Active", 55)], 7)
        def refresh_users() -> None:
            _clear_tree(user_tree)
            for user in list_users(self.db_path):
                user_tree.insert("", "end", iid=str(user["id"]), values=(user["full_name"], user["username"], user["role"], "Yes" if user["is_active"] else "No"))
        refresh_users()
        controls = tk.Frame(right, bg=WHITE); controls.pack(fill="x", padx=16, pady=7)
        def add_staff() -> None:
            dialog = tk.Toplevel(self.root); dialog.title("Create staff account"); dialog.geometry("380x390"); dialog.transient(self.root); dialog.grab_set()
            data = {k: tk.StringVar() for k in ["name", "username", "password"]}; role = tk.StringVar(value="cashier")
            for key, label in [("name", "Full name"), ("username", "Username"), ("password", "Temporary password (8+ characters)")]:
                self._simple_dialog_field(dialog, label, data[key], secret=(key == "password"))
            tk.Label(dialog, text="Role", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=20, pady=(8, 2))
            ttk.Combobox(dialog, textvariable=role, values=["cashier", "admin"], state="readonly").pack(fill="x", padx=20)
            status = tk.Label(dialog, text="", fg=RED); status.pack()
            def save() -> None:
                try: create_user(data["name"].get(), data["username"].get(), data["password"].get(), role.get(), self.db_path)
                except Exception as exc: status.config(text=str(exc)); return
                dialog.destroy(); refresh_users()
            ttk.Button(dialog, text="Create account", style="Primary.TButton", command=save).pack(fill="x", padx=20, pady=18)
        def toggle_user() -> None:
            row = user_tree.selection()
            if not row: messagebox.showwarning("Select user", "Select a user account.", parent=self.root); return
            uid = int(row[0]); user = next(u for u in list_users(self.db_path) if u["id"] == uid)
            try: set_user_active(uid, not bool(user["is_active"]), self.current_user["id"], self.db_path)
            except Exception as exc: messagebox.showerror("User update failed", str(exc), parent=self.root); return
            refresh_users()
        ttk.Button(controls, text="Create staff user", command=add_staff).pack(side="left")
        ttk.Button(controls, text="Activate / deactivate", command=toggle_user).pack(side="right")
        ttk.Separator(right).pack(fill="x", padx=16, pady=10)
        ttk.Button(right, text="Change my password", command=self._change_my_password).pack(fill="x", padx=16, pady=5)
        ttk.Button(right, text="Create database backup", style="Primary.TButton", command=self._backup_database).pack(fill="x", padx=16, pady=5)
        ttk.Button(right, text="Open backup folder", command=lambda: self._open_folder(BACKUP_DIR)).pack(fill="x", padx=16, pady=5)
        tk.Label(right, text="Backups contain customer, product and financial records. Store them securely.",
                 bg=WHITE, fg=MUTED, font=("Segoe UI", 8), wraplength=370, justify="left").pack(anchor="w", padx=16, pady=8)

    def _simple_dialog_field(self, parent: tk.Widget, label: str, variable: tk.StringVar, secret: bool = False) -> None:
        tk.Label(parent, text=label, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=20, pady=(10, 2))
        ttk.Entry(parent, textvariable=variable, show="•" if secret else "").pack(fill="x", padx=20, ipady=3)

    def _change_my_password(self) -> None:
        dialog = tk.Toplevel(self.root); dialog.title("Change password"); dialog.geometry("380x300"); dialog.transient(self.root); dialog.grab_set()
        current, new, confirm = tk.StringVar(), tk.StringVar(), tk.StringVar()
        for label, var in [("Current password", current), ("New password", new), ("Confirm new password", confirm)]: self._simple_dialog_field(dialog, label, var, True)
        status = tk.Label(dialog, text="", fg=RED); status.pack(pady=6)
        def save() -> None:
            if new.get() != confirm.get(): status.config(text="New passwords do not match."); return
            try: change_password(self.current_user["id"], current.get(), new.get(), self.db_path)
            except Exception as exc: status.config(text=str(exc)); return
            dialog.destroy(); messagebox.showinfo("Password changed", "Your password was updated.", parent=self.root)
        ttk.Button(dialog, text="Update password", style="Primary.TButton", command=save).pack(fill="x", padx=20, pady=12)

    def _backup_database(self) -> None:
        from datetime import datetime
        target = BACKUP_DIR / f"retail_wizard_backup_{datetime.now():%Y%m%d_%H%M%S}.db"
        try: backup_database(target, self.db_path)
        except Exception as exc: messagebox.showerror("Backup failed", str(exc), parent=self.root); return
        messagebox.showinfo("Backup created", f"Database backup saved to:\n{target}", parent=self.root)

    def _export_tree(self, tree: ttk.Treeview, default_name: str) -> None:
        rows = [tree.item(item, "values") for item in tree.get_children()]
        if not rows:
            messagebox.showwarning("No data", "There are no rows to export.", parent=self.root); return
        path = filedialog.asksaveasfilename(parent=self.root, defaultextension=".csv", initialfile=default_name, filetypes=[("CSV", "*.csv")])
        if not path: return
        headers = [tree.heading(col, "text") for col in tree["columns"]]
        with open(path, "w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle); writer.writerow(headers); writer.writerows(rows)
        messagebox.showinfo("Export complete", f"Saved to:\n{path}", parent=self.root)

    @staticmethod
    def _open_folder(path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform.startswith("win"): os.startfile(str(path))  # type: ignore[attr-defined]
            elif sys.platform == "darwin": subprocess.Popen(["open", str(path)])
            else: subprocess.Popen(["xdg-open", str(path)])
        except Exception:
            pass

    def logout(self) -> None:
        self.current_user = None
        self.cart.clear(); self.purchase_cart.clear()
        self.show_entry_screen()


def launch() -> None:
    root = tk.Tk()
    RetailWizardApp(root)
    root.mainloop()
