# Usage

Localargo is a command-line tool that provides convenient utilities for ArgoCD local development workflows.

## Getting Started

After installation, you can run Localargo from the command line:

```bash
localargo --help
```

## Available Commands

### Cluster Management

#### Declarative Cluster Management (Recommended)

LocalArgo supports declarative cluster management using YAML manifests. Define your clusters in a `clusters.yaml` file:

```yaml
clusters:
  - name: dev-cluster
    provider: kind
  - name: staging-cluster
    provider: k3s
```

Then use these commands to manage your clusters:

```bash
# Create all clusters defined in clusters.yaml
localargo cluster apply

# Delete all clusters defined in clusters.yaml
localargo cluster delete

# Show status of all clusters defined in clusters.yaml
localargo cluster status

# Use a custom manifest file
localargo cluster apply my-clusters.yaml
localargo cluster status production-clusters.yaml
```

#### Imperative Cluster Management (Legacy)

For individual cluster operations:

```bash
# Check current cluster and ArgoCD status
localargo cluster status

# Initialize a local cluster with ArgoCD (kind or k3s, kind is default)
localargo cluster init  # Uses kind by default
localargo cluster init --provider k3s

# Switch to a different context
localargo cluster switch my-cluster

# List available contexts
localargo cluster list
```

### Application Management

Create, sync, and manage applications. You can deploy in two ways:

- Via ArgoCD CLI (default): create/update ArgoCD Applications and sync
- Via kubectl with a kubeconfig: apply one or more manifest files directly

```bash
# Create a new application (ArgoCD mode)
localargo app create my-app --repo https://github.com/myorg/myrepo

# Sync an application
localargo app sync my-app

# Check application status
localargo app status my-app

# Delete an application
localargo app delete my-app
```

#### Deploying via kubectl with a kubeconfig

Add `manifest_files` to your `localargo.yaml` app entries to apply YAMLs with kubectl:

```yaml
apps:
  - name: core-local
    manifest_files:
      - /path/to/apps/core/local/core-app.yaml
  - name: keycloak-local
    manifest_files:
      - /path/to/apps/keycloak/local/keycloak-app.yaml
```

Then deploy with an optional kubeconfig:

```bash
# Deploy only manifest-based apps in catalog (kubectl apply -f ...)
localargo app deploy --all --kubeconfig /path/to/kubeconfig

# Or a single app
localargo app deploy core-local --kubeconfig /path/to/kubeconfig
```

#### Deploying from flags (create/update ArgoCD app directly)

You can skip the catalog and deploy a single app by specifying repo details:

```bash
# Create/update and sync an ArgoCD app directly
localargo app deploy \
  --repo https://gitlab.com/govflows/platform/core.git \
  --app-name core-local \
  --repo-path infra/charts \
  --namespace core-local \
  --project default \
  --type helm \
  --helm-values ../environments/local/values-core.yaml

# Or apply one or more manifests directly without catalog
localargo app deploy -f /abs/path/to/app.yaml [-f another.yaml] --kubeconfig /path/to/kubeconfig
```

### Port Forwarding

Easily access services running in your applications:

```bash
# Start port forwarding for a service
localargo port-forward start my-service

# Port forward all services in an application
localargo port-forward app my-app

# List active port forwards
localargo port-forward list

# Stop all port forwards
localargo port-forward stop --all
```

### Secrets Management

Create and manage secrets for local development:

```bash
# Create a secret from key-value pairs
localargo secrets create my-secret --from-literal API_KEY=secret --from-literal DB_PASS=password

# Create a secret from files
localargo secrets create my-secret --from-file config=config.yaml

# Get and decode secret values
localargo secrets get my-secret

# Update a secret key
localargo secrets update my-secret --key API_KEY --value new-secret

# Delete a secret
localargo secrets delete my-secret
```

### Sync Operations

Sync applications and watch for changes:

```bash
# Sync all applications
localargo sync --all

# Sync a specific application
localargo sync my-app

# Sync and watch for changes (auto-sync on file changes)
localargo sync my-app --watch
```

### Application Templates

Quick-start applications from common templates:

```bash
# List available templates
localargo template list

# Create an application from a template
localargo template create my-web-app --type web-app --repo https://github.com/myorg/myrepo --image nginx:latest

# Show template details
localargo template show web-app
```

### Debug Tools

Comprehensive debugging and troubleshooting utilities:

```bash
# Check ArgoCD system health
localargo debug health

# Validate application configuration
localargo debug validate my-app --check-images --check-secrets

# Show application logs
localargo debug logs my-app

# Show Kubernetes events for an application
localargo debug events my-app
```

## Command Line Options

Localargo supports standard CLI options:

- `-h, --help`: Show help message and exit
- `-v, --verbose`: Enable verbose logging with rich formatting
- `--version`: Show version number and exit

## Configuration

### Cluster Manifests

Cluster manifests are YAML files that declaratively define the clusters you want to manage. The basic structure is:

```yaml
clusters:
  - name: cluster-name      # Required: unique cluster identifier
    provider: kind          # Required: provider type (kind, k3s)
    # Additional provider-specific options can be added here
```

#### Supported Providers

- **kind**: Kubernetes in Docker - lightweight clusters for development
- **k3s**: Lightweight Kubernetes - production-like clusters

#### Advanced Manifest Features

```yaml
clusters:
  # Multiple clusters of different providers
  - name: development
    provider: kind
    # Additional options can be provider-specific

  - name: staging
    provider: k3s
    # k3s-specific configuration options
    version: "v1.27.0+k3s1"

  # Environment-specific configurations
  - name: ci-cluster
    provider: kind
    nodes: 3  # Custom node configuration
```

#### Manifest Validation

You can validate a manifest file without applying it:

```bash
# This will check syntax and provider availability
python -c "from localargo.config.manifest import validate_manifest; validate_manifest('clusters.yaml')"
```

Localargo currently works with your existing kubectl and argocd CLI configurations. Future versions may support additional configuration options.

## Prerequisites

Localargo requires:

- **kubectl**: For Kubernetes cluster interaction
- **argocd CLI**: For ArgoCD operations (optional, some features work without it)
- **Python 3.8+**: For running Localargo

## Examples

### Complete Development Workflow

```bash
# 1. Set up local cluster
localargo cluster init --provider k3s

# 2. Create application from template
localargo template create my-api --type api --repo https://github.com/myorg/api --image myorg/api:latest

# 3. Create development secrets
localargo secrets create dev-secrets --from-literal DATABASE_URL=postgres://localhost --from-literal REDIS_URL=redis://localhost

# 4. Port forward services for local access
localargo port-forward start my-api-service

# 5. Sync and watch for changes during development
localargo sync my-api --watch

# 6. Debug issues if they arise
localargo debug logs my-api
localargo debug validate my-api
```

### Switching Between Environments

```bash
# Development environment
localargo cluster switch dev-cluster
localargo app sync --all

# Staging environment
localargo cluster switch staging-cluster
localargo app status --all

# Production environment
localargo cluster switch prod-cluster
localargo app diff my-app
```
