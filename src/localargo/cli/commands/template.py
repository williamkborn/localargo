# SPDX-FileCopyrightText: 2025-present U.N. Owen <void@some.where>
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

#
# SPDX-License-Identifier: MIT
import click
import yaml

from localargo.logging import logger


@click.group()
def template() -> None:
    """Create ArgoCD applications from templates."""


@template.command()
@click.argument("name")
@click.option(
    "--app-type",
    "-t",
    type=click.Choice(["web-app", "api", "worker", "database"]),
    default="web-app",
    help="Application type",
)
@click.option("--repo", "-r", help="Git repository URL")
@click.option("--path", "-p", default=".", help="Path within repository")
@click.option("--namespace", "-n", default="default", help="Target namespace")
@click.option("--image", "-i", help="Container image")
@click.option("--port", type=int, default=80, help="Service port")
@click.option("--env", multiple=True, help="Environment variables (KEY=VALUE)")
@click.option("--create-app", is_flag=True, help="Create the ArgoCD application immediately")
def create(
    name: str,
    app_type: str,
    repo: str | None,
    path: str,
    namespace: str,
    image: str | None,
    port: int,
    env: tuple[str, ...],
    *,
    create_app: bool,
) -> None:
    """Create an application from a template."""
    if not repo:
        logger.error("❌ Repository URL required (--repo)")
        return

    # Generate application configuration
    app_config = _generate_app_template(name, app_type, repo, path, namespace, image, port, env)

    # Show the generated config
    logger.info("Generated ArgoCD Application:")
    logger.info("=" * 50)
    logger.info(yaml.dump(app_config, default_flow_style=False))

    if create_app:
        # Save to temp file and create with argocd CLI
        import subprocess
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(app_config, f)
            temp_file = f.name

        try:
            argocd_path = shutil.which("argocd")
            if argocd_path is None:
                msg = "argocd not found in PATH. Please ensure argocd CLI is installed and available."
                raise RuntimeError(msg)
            subprocess.run([argocd_path, "app", "create", name, "--file", temp_file], check=True)
            logger.info(f"✅ ArgoCD application '{name}' created")
        except FileNotFoundError:
            logger.error("❌ argocd CLI not found")
        except subprocess.CalledProcessError as e:
            logger.info(f"❌ Error creating application: {e}")
        finally:
            Path(temp_file).unlink(missing_ok=True)
    else:
        logger.info("\nUse --create-app to create the application immediately")


@template.command()
def list_templates() -> None:
    """List available application templates."""
    templates = {
        "web-app": "Web application with service and ingress",
        "api": "REST API application",
        "worker": "Background worker/job application",
        "database": "Database deployment (PostgreSQL, MySQL, etc.)",
    }

    logger.info("Available templates:")
    for name, desc in templates.items():
        logger.info(f"  {name:<12} - {desc}")


@template.command()
@click.argument("template_type")
def show(template_type: str) -> None:
    """Show template details."""
    if template_type not in ["web-app", "api", "worker", "database"]:
        logger.error(f"❌ Unknown template type: {template_type}")
        return

    # Generate example config
    example_config = _generate_app_template(
        f"example-{template_type}",
        template_type,
        "https://github.com/example/example-repo",
        ".",
        "default",
        f"example/{template_type}:latest",
        80,
        (),
    )

    logger.info(f"Template: {template_type}")
    logger.info("=" * 30)
    logger.info(yaml.dump(example_config, default_flow_style=False))


def _generate_app_template(
    name: str,
    app_type: str,
    repo: str,
    path: str,
    namespace: str,
    image: str | None,
    port: int,
    env_vars: tuple[str, ...],
) -> dict[str, Any]:
    """Generate ArgoCD application configuration from template."""
    # Base application structure
    app: dict = {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "Application",
        "metadata": {"name": name, "namespace": "argocd"},
        "spec": {
            "project": "default",
            "source": {"repoURL": repo, "path": path, "targetRevision": "HEAD"},
            "destination": {"server": "https://kubernetes.default.svc", "namespace": namespace},
            "syncPolicy": {"automated": {"prune": True, "selfHeal": True}},
        },
    }

    # Customize based on application type
    if app_type == "web-app":
        app["spec"]["source"]["helm"] = {
            "parameters": [
                {"name": "image.repository", "value": image or f"{name}"},
                {"name": "image.tag", "value": "latest"},
                {"name": "service.port", "value": str(port)},
            ]
        }
        # Add environment variables
        if env_vars:
            env_params = []
            for env in env_vars:
                if "=" in env:
                    key, value = env.split("=", 1)
                    env_params.append({"name": f"env.{key}", "value": value})
            if "helm" in app["spec"]["source"] and "parameters" in app["spec"]["source"]["helm"]:
                app["spec"]["source"]["helm"]["parameters"].extend(env_params)

    elif app_type == "api":
        app["spec"]["source"]["helm"] = {
            "parameters": [
                {"name": "image.repository", "value": image or f"{name}-api"},
                {"name": "image.tag", "value": "latest"},
                {"name": "service.port", "value": str(port)},
                {"name": "ingress.enabled", "value": "true"},
            ]
        }

    elif app_type == "worker":
        app["spec"]["source"]["helm"] = {
            "parameters": [
                {"name": "image.repository", "value": image or f"{name}-worker"},
                {"name": "image.tag", "value": "latest"},
                {"name": "replicaCount", "value": "2"},
            ]
        }
        # Remove service-related config for workers
        if "syncPolicy" in app["spec"]:
            app["spec"]["syncPolicy"] = {"automated": {}}  # Simpler sync policy

    elif app_type == "database":
        app["spec"]["source"]["helm"] = {
            "parameters": [
                {"name": "image.repository", "value": image or "postgres"},
                {"name": "image.tag", "value": "13"},
                {"name": "persistence.enabled", "value": "true"},
                {"name": "persistence.size", "value": "10Gi"},
            ]
        }

    return app
