# SPDX-FileCopyrightText: 2025-present William Born <william.born.git@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Main entry point for localargo CLI."""

import sys

if __name__ == "__main__":
    from localargo.cli import localargo

    sys.exit(localargo(verbose=False))
