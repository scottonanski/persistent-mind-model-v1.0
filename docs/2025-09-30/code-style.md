# 🎨 Code Style Guide

PMM prefers clear, deterministic code. Use the tooling below before opening a pull request.

## 1. Ruff (lint + fix)

```bash
ruff check pmm tests
ruff format pmm tests
```

Ruff enforces import order, catches dead code, and can auto-fix many small issues.

## 2. Black (format)

```bash
black pmm tests
```

Black is idempotent; run it after larger refactors to ensure consistent formatting.

## 3. MyPy (types)

```bash
mypy pmm
```

Type hints help keep the autonomous systems deterministic. Focus on warnings in `pmm/runtime/` and `pmm/storage/` first.

## 4. Commit hygiene

- Keep commits focused and well-described.
- Run tests + linting locally before pushing.
- Avoid reformatting unrelated files in the same commit as logic changes.

## 5. Determinism matters

- Never introduce randomness without a deterministic seed saved in the event log.
- All new background systems must be idempotent and traceable.
- If you add a new event kind, update `docs/guide/observability.md` and the API docs.

Need a reference environment? See [development-setup.md](development-setup.md).
