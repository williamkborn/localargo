# Localargo Documentation

This directory contains the documentation for Localargo, built using [mdBook](https://rust-lang.github.io/mdBook/).

## Building the Documentation

### Prerequisites

Install mdBook:

```bash
# Using cargo (recommended)
cargo install mdbook

# Or download pre-built binaries from:
# https://github.com/rust-lang/mdBook/releases
```

### Build

```bash
# From the docs directory
./build.sh

# Or manually
mdbook build
```

### Serve Locally

To serve the documentation with live reloading during development:

```bash
mdbook serve
```

Then open http://localhost:3000 in your browser.

## Documentation Structure

- `book.toml`: mdBook configuration
- `src/`: Markdown source files
  - `SUMMARY.md`: Table of contents
  - `introduction.md`: Project introduction
  - `installation.md`: Installation instructions
  - `usage.md`: Usage guide
  - `contributing.md`: Contributing guidelines
- `build.sh`: Build script

## Output

Built documentation will be available in the `book/` directory.
