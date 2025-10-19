# Contributing

We welcome contributions to Localargo! This document provides guidelines for contributing to the project.

## Development Setup

### Quick Setup with Mise (Recommended)

1. **Install Mise:**
   ```bash
   # macOS with Homebrew
   brew install mise

   # Or install manually
   curl https://mise.jdx.dev/install.sh | sh
   ```

2. **Clone and setup:**
   ```bash
   git clone https://github.com/William Born/localargo.git
   cd localargo

   # Install all development tools
   mise install

   # Create Hatch environment
   hatch env create
   ```

   This will automatically install and configure:
   - Python 3.12
   - KinD, kubectl, ArgoCD CLI
   - Hatch, mdBook
   - All other development tools

### Manual Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/William Born/localargo.git
   cd localargo
   ```

2. **Set up development environment:**
   ```bash
   # Install in development mode with dev dependencies
   pip install -e ".[dev]"
   ```

3. **Run tests:**
   ```bash
   # Run the test suite
   hatch run test
   ```

4. **Type checking:**
   ```bash
   # Run MyPy type checking
   hatch run types:check
   ```

## Code Style

This project follows these coding standards:

- **Black**: For code formatting
- **isort**: For import sorting
- **MyPy**: For static type checking
- **flake8**: For linting

## Project Structure

```text
src/localargo/
├── __about__.py      # Version information
├── __init__.py       # Package initialization
├── __main__.py       # Main entry point
└── cli/              # Command-line interface
    └── __init__.py   # CLI commands

tests/                # Test suite
docs/                 # Documentation (mdbook)
```

## Adding New Commands

Localargo uses Click for CLI commands. To add a new command:

1. Add the command function in `src/localargo/cli/__init__.py`
2. Decorate it with `@localargo.command()`
3. Update this documentation

Example:
```python
@localargo.command()
def new_command():
    """Description of the new command."""
    click.echo("New command executed!")
```

## Testing

LocalArgo follows a **mocked testing philosophy** where all tests are fully isolated and require no external dependencies.

### Development and Testing Loop

All developers must run the following before committing or opening a PR:

```bash
# 1. Format code and tests
hatch fmt

# 2. Type-check
hatch run typecheck

# 3. Run tests (unit only, mocked)
pytest -v

# 4. (Optional) Check coverage
pytest --cov=localargo --cov-report=term-missing
```

All tests are fully mocked—no Kubernetes, Docker, or Kind binaries are required.

### Writing Tests

- Write tests in the `tests/` directory
- Use pytest for testing framework
- Aim for good test coverage
- All subprocess calls must be mocked (see `tests/conftest.py`)
- Tests should verify command construction, not execution

## Documentation

- Update this mdbook documentation for any new features
- Keep README.md up to date
- Use clear, concise language

## Submitting Changes

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes
4. Run tests and type checking
5. Update documentation if needed
6. Commit your changes: `git commit -am 'Add my feature'`
7. Push to the branch: `git push origin feature/my-feature`
8. Submit a pull request

## License

By contributing to Localargo, you agree that your contributions will be licensed under the same MIT license that covers the project.
