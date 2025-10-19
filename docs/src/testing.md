# Testing Philosophy

LocalArgo is an infrastructure-oriented system that orchestrates *real tools* — not a simulation of them.  
Our testing strategy reflects this reality: we test **intent, not side effects**.

---

## 🧭 Guiding Principles

### 1. No Real Dependencies
Our test suite must run **on any developer machine** and **in any CI environment** without installing:
- `kind`
- `k3s`
- `kubectl`
- Docker
- Kubernetes

Tests must pass using **only Python and pytest**.  
This guarantees reproducibility, simplicity, and safety.

---

### 2. Intent Verification, Not Execution
LocalArgo providers (`kind`, `k3s`, etc.) are orchestrators:  
they *compose and invoke commands* that manage clusters.

We don't need to prove the tools themselves work — we need to prove **we invoked them correctly**.

That means:
- ✅ Asserting that `subprocess.run` was called with the correct arguments.  
- ✅ Ensuring command flags, names, and environment variables match expectations.  
- 🚫 Not actually creating, deleting, or modifying clusters.

This is sometimes called **command-dispatch testing** or **mocked orchestration testing**.

---

### 3. Fully Mocked Execution
All command executions are replaced with mocks:

```python
from unittest.mock import patch

@patch("subprocess.run")
def test_kind_create_cluster(mock_run):
    mock_run.return_value.returncode = 0
    provider = KindProvider(name="demo")
    provider.create()
    mock_run.assert_called_with(
        ["kind", "create", "cluster", "--name", "demo"],
        check=True
    )
```

The above verifies *exactly what would have happened* — without invoking any external binaries.

---

### 4. Developer Feedback Loop
We value **fast feedback** and **low maintenance cost**.

To keep the loop tight:
```bash
# Format before commit
hatch fmt

# Check types
hatch run typecheck

# Run all tests
pytest -v
```

These commands should always pass on a fresh clone of the repository with no system dependencies.

---

### 5. Test Coverage vs. Risk Acceptance
We consciously accept a small amount of risk by not running real cluster operations in tests.  
Our confidence comes from:
- Verifying command structure and flow control.
- Strong typing and code review.
- Real-world user feedback for end-to-end validation.

The cost of full cluster simulation outweighs the marginal benefit for unit testing.  
Any real-world validation should live in **integration or smoke tests**, not in the main unit suite.

---

## 🧩 Unit Testing Scope

| Layer | Approach | Example |
|--------|-----------|----------|
| **Core (`localargo/core/`)** | Pure unit tests — no I/O | Test config loading or YAML parsing |
| **Providers (`kind`, `k3s`)** | Mocked subprocess calls | Assert command argument correctness |
| **CLI (`__main__.py`)** | Monkeypatch `sys.argv` | Validate flag parsing & routing |
| **Logging** | Use `caplog` | Verify expected log output |

---

## 🧱 Integration Tests (Future)
In later stages, we may introduce:
- "Smoke tests" that spin up a temporary Kind cluster in a separate CI stage.
- Optional end-to-end validation for providers (behind `pytest -m integration`).

These will **never** run in default test mode.

---

## ✅ Summary
> LocalArgo's tests are designed for clarity, speed, and safety — not illusionary realism.  
> We test *what we control*: command construction, argument parsing, and behavior flow.  
> External tools are trusted to perform their documented functions.

This keeps the project lightweight, CI-friendly, and developer-first — exactly the way LocalArgo should be.
