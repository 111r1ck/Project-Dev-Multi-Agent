# Contributing

Thanks for your interest in contributing.

## Development Setup

1. Fork the repository and create a feature branch.
2. Install dependencies:

```bash
pip install -e .[dev]
```

3. Copy env template:

```bash
cp .env.example .env
```

## Test

Run tests before submitting a pull request:

```bash
pytest
```

## Pull Request Guidelines

1. Keep commits focused and atomic.
2. Add or update tests for behavior changes.
3. Update `README.md` if public behavior or setup changes.
4. Ensure no secrets are committed (`.env` must never be tracked).
