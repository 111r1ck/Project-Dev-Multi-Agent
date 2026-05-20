# Contributing

[中文文档](./CONTRIBUTING.zh-CN.md)

## Development Setup

1. Fork the repository and create a feature branch.
2. Install dependencies:

```bash
pip install -e .[dev]
```

3. Copy environment template:

```bash
cp .env.example .env
```

## Test

Run tests before opening a pull request:

```bash
pytest
```

## Pull Request Guidelines

1. Keep commits focused and atomic.
2. Add or update tests for behavior changes.
3. Update `README.md` when setup or public behavior changes.
4. Never commit secrets (`.env` must remain untracked).
