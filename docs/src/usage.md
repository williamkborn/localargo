# Usage

Localargo is a command-line tool that provides convenient utilities for ArgoCD local development workflows.

## Getting Started

After installation, you can run Localargo from the command line:

```bash
localargo --help
```

## Available Commands

### Cluster Management

Manage Kubernetes clusters for ArgoCD development:

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

Create, sync, and manage ArgoCD applications:

```bash
# Create a new application
localargo app create my-app --repo https://github.com/myorg/myrepo

# Sync an application
localargo app sync my-app

# Check application status
localargo app status my-app

# Show diff between desired and live state
localargo app diff my-app

# Delete an application
localargo app delete my-app
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
