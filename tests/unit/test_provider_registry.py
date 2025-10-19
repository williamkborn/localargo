"""Tests for provider registry functionality."""

# SPDX-FileCopyrightText: 2025-present William Born <william.born.git@gmail.com>
#
# SPDX-License-Identifier: MIT

import pytest

from localargo.providers.k3s import K3sProvider
from localargo.providers.kind import KindProvider
from localargo.providers.registry import PROVIDERS, get_provider, list_available_providers


class TestProviderRegistry:
    """Test suite for provider registry."""

    def test_get_provider_kind(self):
        """Test getting kind provider."""
        provider_class = get_provider("kind")

        assert provider_class == KindProvider

    def test_get_provider_k3s(self):
        """Test getting k3s provider."""
        provider_class = get_provider("k3s")

        assert provider_class == K3sProvider

    def test_get_provider_unknown_raises_error(self):
        """Test getting unknown provider raises ValueError."""
        with pytest.raises(
            ValueError, match="Unknown provider: unknown. Available providers: kind, k3s"
        ):
            get_provider("unknown")

    def test_list_available_providers(self):
        """Test listing available providers."""
        providers = list_available_providers()
        assert providers == ["kind", "k3s"]

    def test_get_provider_case_sensitive(self):
        """Test provider names are case sensitive."""
        # Should work for lowercase
        provider_class = get_provider("kind")
        assert provider_class is not None

        # Should fail for uppercase
        with pytest.raises(ValueError, match="Unknown provider"):
            get_provider("KIND")

    def test_registry_imports(self):
        """Test that registry imports work correctly."""
        # This test ensures our imports in registry.py work
        assert "kind" in PROVIDERS
        assert "k3s" in PROVIDERS

        assert PROVIDERS["kind"] == KindProvider
        assert PROVIDERS["k3s"] == K3sProvider
