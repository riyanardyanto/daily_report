from __future__ import annotations

import flet as ft

# ─────────────────────────────────────────────────────────────────────────────
# Premium curated palette — HSL-tuned, vibrant but not garish.
# ─────────────────────────────────────────────────────────────────────────────

# Interactive / action colors
PRIMARY   = "#2563EB"   # Indigo-Blue (modern SaaS blue)
SECONDARY = "#475569"   # Slate-600
SUCCESS   = "#059669"   # Emerald-600
DANGER    = "#DC2626"   # Red-600
INFO      = "#7C3AED"   # Violet-600
WARNING   = "#D97706"   # Amber-600

# Text on colored backgrounds
ON_COLOR = ft.Colors.WHITE

# ─── Dark sidebar palette ────────────────────────────────────────────────────
SIDEBAR_BG     = "#1E293B"   # Slate-800 — main sidebar background
SIDEBAR_SURFACE= "#0F172A"   # Slate-900 — darker inset / active item
SIDEBAR_BORDER = "#334155"   # Slate-700 — dividers inside sidebar
SIDEBAR_TEXT   = "#E2E8F0"   # Slate-200 — primary text in sidebar
SIDEBAR_MUTED  = "#94A3B8"   # Slate-400 — secondary / muted text
SIDEBAR_ACCENT = PRIMARY     # highlighted / active item accent

# ─── Content area palette ────────────────────────────────────────────────────
BG_PAGE        = "#F1F5F9"   # Slate-100 — page background
SURFACE        = "#FFFFFF"   # pure white cards / panels
SURFACE_ALT    = "#F8FAFC"   # Slate-50  — subtle alternate surface
BORDER_SUBTLE  = "#E2E8F0"   # Slate-200 — card borders
BORDER_DEFAULT = "#CBD5E1"   # Slate-300 — stronger borders

# ─── Text colors ─────────────────────────────────────────────────────────────
TEXT_PRIMARY   = "#0F172A"   # Slate-900 — headlines
TEXT_SECONDARY = "#334155"   # Slate-700 — body text
TEXT_MUTED     = "#64748B"   # Slate-500 — captions / meta

# ─── Table header ────────────────────────────────────────────────────────────
TABLE_HEADER_BG   = "#1E293B"   # dark (matches sidebar)
TABLE_HEADER_TEXT = "#F1F5F9"   # near-white

# ─── Issue-card accent strip palette (left border per card index) ─────────────
CARD_COLORS = [
    "#6366F1",   # Indigo
    "#8B5CF6",   # Violet
    "#EC4899",   # Pink
    "#EF4444",   # Red
    "#F97316",   # Orange
    "#EAB308",   # Yellow
    "#22C55E",   # Green
    "#14B8A6",   # Teal
    "#3B82F6",   # Blue
    "#A855F7",   # Purple
]

# Kept for backward-compat (some older imports may use SWITCH_ACTIVE)
SWITCH_ACTIVE = PRIMARY
