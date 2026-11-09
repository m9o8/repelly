# repelly - https://github.com/m9o8/repelly
# Copyright (C) 2026 Moritz Peist
# SPDX-License-Identifier: GPL-3.0-or-later
# This program comes with ABSOLUTELY NO WARRANTY. It is free software: you can
# redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or later. See <https://www.gnu.org/licenses/>.

"""Repelling, non-overlapping text labels for Plotly figures."""

from repelly._api import add_label_repel, add_text_repel
from repelly._figure import RepelFigure, as_repel_figure
from repelly._static import bake

__version__ = "0.1.0"

__all__ = [
    "RepelFigure",
    "__version__",
    "add_label_repel",
    "add_text_repel",
    "as_repel_figure",
    "bake",
]
