# Test Suite Documentation

## Overview

Comprehensive testing suite for the Blitz3 CNC system covering unit tests, integration tests, and performance tests.

## Test Structure

```
tests/
├── conftest.py                          # Pytest configuration and fixtures
├── mocks/
│   ├── __init__.py
│   └── mock_machine.py                  # Mock machine objects for testing
├── widgets/
│   ├── __init__.py
│   ├── test_status_panel.py            # StatusPanel widget tests
│   └── test_collapsible_section.py     # CollapsibleSection widget tests
├── logic/
│   ├── __init__.py
│   ├── test_mode_detector.py           # Mode detection logic tests
│   └── test_mode_config.py             # Mode configuration tests
├── integration/
│   ├── __init__.py
│   └── test_semi_auto_workflow.py      # Integration tests
├── performance/
│   ├── __init__.py
│   └── test_mode_detection_performance.py  # Performance tests
└── README.md                            # This file
```

## Installation

Install test dependencies:

```bash
pip install -r requirements-test.txt
pip install -r requirements-qt6.txt
```

## Running Tests

### Run all tests

```bash
QT_QPA_PLATFORM=offscreen pytest
```

### Run specific test suites

```bash
# Widget tests only
QT_QPA_PLATFORM=offscreen pytest tests/widgets/

# Logic tests only
QT_QPA_PLATFORM=offscreen pytest tests/logic/

# Integration tests only
QT_QPA_PLATFORM=offscreen pytest tests/integration/ -m integration

# Performance tests only
QT_QPA_PLATFORM=offscreen pytest tests/performance/ -m performance
```

### Run with coverage

```bash
QT_QPA_PLATFORM=offscreen pytest --cov --cov-report=html --cov-report=term-missing
```

View coverage report:
```bash
# HTML report
open htmlcov/index.html

# Or for Linux
xdg-open htmlcov/index.html
```

### Run specific tests

```bash
# Single test file
QT_QPA_PLATFORM=offscreen pytest tests/widgets/test_status_panel.py

# Single test function
QT_QPA_PLATFORM=offscreen pytest tests/widgets/test_status_panel.py::test_status_panel_initialization
```

### Verbose output

```bash
QT_QPA_PLATFORM=offscreen pytest -v
```

### Show print statements

```bash
QT_QPA_PLATFORM=offscreen pytest -s
```

## Test Markers

Tests are marked with custom markers for selective execution:

- `@pytest.mark.integration` - Integration tests (slower, require full setup)
- `@pytest.mark.performance` - Performance tests (check speed/memory)
- `@pytest.mark.hardware` - Hardware tests (require physical machine)
- `@pytest.mark.slow` - Slow tests (>1s runtime)

Run tests by marker:
```bash
QT_QPA_PLATFORM=offscreen pytest -m integration
QT_QPA_PLATFORM=offscreen pytest -m "not slow"
```

## Fixtures

Available pytest fixtures (see `conftest.py`):

- `qapp` - Qt Application instance (session-scoped)
- `mock_machine` - Mock machine for testing without hardware
- `mock_machine_adapter` - Mock machine adapter
- `temp_dir` - Temporary directory for test files
- `sample_cutlist` - Sample cutlist data
- `sample_profile` - Sample profile data
- `sample_mode_config` - Sample mode configuration

## Coverage Targets

- **Current Coverage**: 20.45%
- **Target Coverage**: 60%+ (to be achieved incrementally)

High coverage areas:
- `mode_config.py`: 96.61%
- `mode_detector.py`: 93.48%
- `collapsible_section.py`: 85.86%
- `status_panel.py`: 83.08%

## CI/CD

Tests are automatically run on:
- Push to `main` or `develop` branches
- Pull requests to `main` or `develop` branches

See `.github/workflows/tests.yml` for CI configuration.

## Writing Tests

### Unit Test Example

```python
def test_my_widget(qapp, mock_machine):
    """Test my widget initialization."""
    widget = MyWidget(mock_machine)
    assert widget is not None
```

### Integration Test Example

```python
@pytest.mark.integration
def test_workflow(qapp, mock_machine):
    """Test complete workflow."""
    # Test multiple components working together
    pass
```

### Performance Test Example

```python
@pytest.mark.performance
def test_speed():
    """Test operation completes quickly."""
    import time
    start = time.time()
    # ... perform operation
    elapsed = time.time() - start
    assert elapsed < 1.0
```

## Troubleshooting

### Qt Platform Plugin Error

If you see `qt.qpa.plugin: Could not load the Qt platform plugin "xcb"`:

```bash
export QT_QPA_PLATFORM=offscreen
```

### Import Errors

Ensure you're running pytest from the repository root:

```bash
cd /path/to/blitz
pytest
```

### Coverage Not Working

Ensure pytest-cov is installed:

```bash
pip install pytest-cov
```

## Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [pytest-qt Documentation](https://pytest-qt.readthedocs.io/)
- [Coverage.py Documentation](https://coverage.readthedocs.io/)
