# localargo

[![PyPI - Version](https://img.shields.io/pypi/v/localargo.svg)](https://pypi.org/project/localargo)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/localargo.svg)](https://pypi.org/project/localargo)

**Convenient ArgoCD local development tool**

Localargo is a command-line tool that makes ArgoCD development workflows faster and more convenient. It provides streamlined commands for managing local clusters, applications, secrets, port forwarding, and debugging - all designed specifically for ArgoCD development.

## Features

- 🚀 **Cluster Management**: Set up and switch between local/remote Kubernetes clusters
- 📦 **Application Management**: Create, sync, and manage ArgoCD applications
- 🌐 **Port Forwarding**: Easily access services running in your applications
- 🔐 **Secrets Management**: Create and manage secrets for local development
- 🔄 **Sync Operations**: Sync applications with watch mode for continuous development
- 📋 **Templates**: Quick-start applications from common templates
- 🔍 **Debug Tools**: Comprehensive debugging and troubleshooting utilities

## Quick Start

```bash
# Install localargo
pip install localargo

# Initialize a local cluster with ArgoCD (uses KinD by default)
localargo cluster init

# Create an application from a template
localargo template create my-app --repo https://github.com/myorg/myrepo

# Port forward services for easy access
localargo port-forward start my-service

# Sync and watch for changes
localargo sync my-app --watch
```

## Table of Contents

- [Installation](#installation)
- [Documentation](#documentation)
- [License](#license)

## Installation

```console
pip install localargo
```

### Development Setup

For contributors and development, we recommend using [Mise](https://mise.jdx.dev/) to set up the complete development environment:

```bash
# Install Mise (macOS with Homebrew)
brew install mise

# Install all development tools
mise install

# Create Hatch environment
hatch env create

# All tools will be automatically available
```

### 🧩 Git Hook Setup

To ensure code quality before every commit, enable the mise-managed pre-commit hook:

```bash
mise generate git-pre-commit --write --task=precommit
```

This creates `.git/hooks/pre-commit`, which automatically runs:

- `hatch fmt`
- `hatch run typecheck`
- `hatch run test`

If any step fails, the commit will be blocked until fixed.

You can also run it manually at any time:

```bash
mise run precommit
```

### Optional Dependencies

For file watching functionality:
```console
pip install localargo[watch]
```

## Documentation

📖 Full documentation is available at [docs/](docs/) and can be built locally using mdBook.

To build the documentation:

```console
# Install mdBook (if not already installed)
cargo install mdbook

# Build the docs
cd docs && mdbook build

# Or using Hatch
hatch run docs:build
```

## License

`localargo` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.
# Test comment for precommit hook
