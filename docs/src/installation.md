# Installation

Localargo can be installed using pip from PyPI or built from source.

## From PyPI

The recommended way to install Localargo is using pip:

```bash
pip install localargo
```

## From Source

If you want to install from source or contribute to development:

```bash
# Clone the repository
git clone https://github.com/William Born/localargo.git
cd localargo

# Install in development mode
pip install -e .
```

## Requirements

- Python 3.8 or later
- pip for package installation

## Development Environment Setup

### Using Mise (Recommended)

[Mise](https://mise.jdx.dev/) is a tool version manager that can set up your entire development environment automatically. This project includes a `mise.toml` configuration that installs all required tools.

1. **Install Mise:**
   ```bash
   # macOS with Homebrew
   brew install mise

   # Or install manually
   curl https://mise.jdx.dev/install.sh | sh
   ```

2. **Set up the development environment:**
   ```bash
   # Install all tools and create environment
   mise install
   hatch env create
   ```

3. **Activate the environment:**
   ```bash
   # Auto-activation (if enabled)
   cd /path/to/localargo

   # Or manually activate
   mise activate
   ```

The `mise.toml` configuration includes:
- Python 3.12
- KinD (Kubernetes in Docker)
- kubectl
- ArgoCD CLI
- Hatch
- mdBook
- Docker
- Git

### Manual Installation

If you prefer manual installation, install the following tools:

- **KinD** (Kubernetes in Docker) - Recommended for local development
  ```bash
  # macOS with Homebrew
  brew install kind

  # Or download from: https://kind.sigs.k8s.io/
  ```

- **k3s** - Lightweight Kubernetes distribution
  ```bash
  # Install k3s
  curl -sfL https://get.k3s.io | sh -
  ```

- **kubectl** - Required for cluster interaction
  ```bash
  # macOS with Homebrew
  brew install kubectl
  ```

- **argocd CLI** (optional) - For advanced ArgoCD operations
  ```bash
  # Install argocd CLI
  brew install argocd
  ```

- **Hatch** - Python project management
  ```bash
  pip install hatch
  ```

- **mdBook** - Documentation generation
  ```bash
  # macOS with Homebrew
  brew install mdbook
  ```

## Verification

After installation, verify that Localargo is working:

```bash
localargo --version
```

You should see the current version number displayed.
