# SPDX-FileCopyrightText: 2025-present William Born <william.born.git@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Template management for ArgoCD applications.

This module provides commands for creating ArgoCD applications from templates.
"""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import click
import yaml

from localargo.logging import logger
from localargo.utils.cli import check_cli_availability


@dataclass
class TemplateConfig:  # pylint: disable=too-many-instance-attributes
    """Configuration for application template generation."""

    name: str
    app_type: str
    repo: str
    path: str
    namespace: str
    image: str | None
    port: int
    env_vars: tuple[str, ...]


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
def create(  # pylint: disable=too-many-arguments
    name: str,
    app_type: str,
    *,
    repo: str | None,
    path: str,
    namespace: str,
    image: str | None,
    port: int,
    env: tuple[str, ...],
    create_app: bool,
) -> None:
    """Create an application from a template."""
    if not repo:
        logger.error("❌ Repository URL required (--repo)")
        return

    config = _build_template_config(
        name=name,
        app_type=app_type,
        repo=repo,
        path=path,
        namespace=namespace,
        image=image,
        port=port,
        env_vars=env,
    )
    app_config = _generate_app_template(config)

    _display_generated_config(app_config)

    if create_app:
        _create_argocd_app(name, app_config)
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
        logger.info("  %-12s - %s", name, desc)


@template.command()
@click.argument("template_type")
def show(template_type: str) -> None:
    """Show template details."""
    if template_type not in ["web-app", "api", "worker", "database"]:
        logger.error("❌ Unknown template type: %s", template_type)
        return

    # Generate example config
    example_config = _generate_app_template(
        TemplateConfig(
            name=f"example-{template_type}",
            app_type=template_type,
            repo="https://github.com/example/example-repo",
            path=".",
            namespace="default",
            image=f"example/{template_type}:latest",
            port=80,
            env_vars=(),
        )
    )

    logger.info("Template: %s", template_type)
    logger.info("=" * 30)
    logger.info(yaml.dump(example_config, default_flow_style=False))


def _build_template_config(  # pylint: disable=too-many-arguments
    name: str,
    app_type: str,
    *,
    repo: str,
    path: str,
    namespace: str,
    image: str | None,
    port: int,
    env_vars: tuple[str, ...],
) -> TemplateConfig:
    """Build a TemplateConfig object from parameters."""
    return TemplateConfig(
        name=name,
        app_type=app_type,
        repo=repo,
        path=path,
        namespace=namespace,
        image=image,
        port=port,
        env_vars=env_vars,
    )


def _display_generated_config(app_config: dict[str, Any]) -> None:
    """Display the generated application configuration."""
    logger.info("Generated ArgoCD Application:")
    logger.info("=" * 50)
    logger.info(yaml.dump(app_config, default_flow_style=False))


def _create_argocd_app(name: str, app_config: dict[str, Any]) -> None:
    """Create an ArgoCD application from the configuration."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(app_config, f)
        temp_file = f.name

    try:
        argocd_path = check_cli_availability("argocd")
        if argocd_path is None:
            msg = "argocd not found in PATH. Please ensure argocd CLI is installed."
            raise RuntimeError(msg)
        subprocess.run([argocd_path, "app", "create", name, "--file", temp_file], check=True)
        logger.info("✅ ArgoCD application '%s' created", name)
    except FileNotFoundError:
        logger.error("❌ argocd CLI not found")
    except subprocess.CalledProcessError as e:
        logger.info("❌ Error creating application: %s", e)
    finally:
        Path(temp_file).unlink(missing_ok=True)


def _generate_app_template(config: TemplateConfig) -> dict[str, Any]:
    """Generate ArgoCD application configuration from template."""
    app = _create_base_application(config)
    _customize_application_for_type(app, config)
    return app


def _create_base_application(config: TemplateConfig) -> dict[str, Any]:
    """Create the base ArgoCD application structure."""
    return {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "Application",
        "metadata": {"name": config.name, "namespace": "argocd"},
        "spec": {
            "project": "default",
            "source": {"repoURL": config.repo, "path": config.path, "targetRevision": "HEAD"},
            "destination": {
                "server": "https://kubernetes.default.svc",
                "namespace": config.namespace,
            },
            "syncPolicy": {"automated": {"prune": True, "selfHeal": True}},
        },
    }


def _customize_application_for_type(app: dict[str, Any], config: TemplateConfig) -> None:
    """Customize the application based on its type."""
    if config.app_type == "web-app":
        _configure_web_app(app, config)
    elif config.app_type == "api":
        _configure_api_app(app, config)
    elif config.app_type == "worker":
        _configure_worker_app(app, config)
    elif config.app_type == "database":
        _configure_database_app(app, config)


def _configure_web_app(app: dict[str, Any], config: TemplateConfig) -> None:
    """Configure a web application."""
    app["spec"]["source"]["helm"] = {
        "parameters": [
            {"name": "image.repository", "value": config.image or f"{config.name}"},
            {"name": "image.tag", "value": "latest"},
            {"name": "service.port", "value": str(config.port)},
        ]
    }

    if config.env_vars:
        env_params = _build_env_parameters(config.env_vars)
        if "helm" in app["spec"]["source"] and "parameters" in app["spec"]["source"]["helm"]:
            app["spec"]["source"]["helm"]["parameters"].extend(env_params)


def _configure_api_app(app: dict[str, Any], config: TemplateConfig) -> None:
    """Configure an API application."""
    app["spec"]["source"]["helm"] = {
        "parameters": [
            {"name": "image.repository", "value": config.image or f"{config.name}-api"},
            {"name": "image.tag", "value": "latest"},
            {"name": "service.port", "value": str(config.port)},
            {"name": "ingress.enabled", "value": "true"},
        ]
    }


def _configure_worker_app(app: dict[str, Any], config: TemplateConfig) -> None:
    """Configure a worker application."""
    app["spec"]["source"]["helm"] = {
        "parameters": [
            {"name": "image.repository", "value": config.image or f"{config.name}-worker"},
            {"name": "image.tag", "value": "latest"},
            {"name": "replicaCount", "value": "2"},
        ]
    }
    # Remove service-related config for workers
    if "syncPolicy" in app["spec"]:
        app["spec"]["syncPolicy"] = {"automated": {}}  # Simpler sync policy


def _configure_database_app(app: dict[str, Any], config: TemplateConfig) -> None:
    """Configure a database application."""
    app["spec"]["source"]["helm"] = {
        "parameters": [
            {"name": "image.repository", "value": config.image or "postgres"},
            {"name": "image.tag", "value": "13"},
            {"name": "persistence.enabled", "value": "true"},
            {"name": "persistence.size", "value": "10Gi"},
        ]
    }


def _build_env_parameters(env_vars: tuple[str, ...]) -> list[dict[str, str]]:
    """Build environment variable parameters for helm."""
    env_params = []
    for env in env_vars:
        if "=" in env:
            key, value = env.split("=", 1)
            env_params.append({"name": f"env.{key}", "value": value})
    return env_params
