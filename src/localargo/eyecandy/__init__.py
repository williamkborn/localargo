# SPDX-FileCopyrightText: 2025-present William Born <william.born.git@gmail.com>

#
# SPDX-License-Identifier: MIT

"""Eyecandy UI abstractions for LocalArgo CLI.

This module provides Rich-based UI abstractions for the LocalArgo CLI,
including table rendering, progress steps, and enhanced CLI styling.
"""

from localargo.eyecandy.progress_steps import StepLogger
from localargo.eyecandy.table_renderer import TableRenderer

__all__ = ["TableRenderer", "StepLogger"]
