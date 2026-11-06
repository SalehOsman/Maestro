# Contributing to Maestro

Thank you for contributing to Maestro.

## Setup

Maestro has zero third-party dependencies and relies entirely on Python's standard library:

1. Clone the repository:
   ```bash
   git clone https://github.com/SalehOsman/Maestro.git
   cd Maestro
   ```
2. Ensure you have **Python 3.9 or newer** installed (`python` on Windows, `python3` on macOS and Linux).

No virtual environment or package installation is required.

## Testing and Verification

Before submitting changes, run the test suite and language separation check:

1. **Run the test suite:**
   ```bash
   python -m unittest discover -s tests -v
   ```
2. **Run the language check:**
   ```bash
   python scripts/check_lang.py
   ```

Both must exit with status code 0.

## Development Rules

### Language Rule
- All code, documentation, templates, metadata, and agent files must be in **English**.
- **Arabic** is reserved exclusively for `README.ar.md` and files inside `docs/ar/`.
- Run `python scripts/check_lang.py` to verify that no unauthorized cross-language text is present.

### Test Isolation Rule
- Any test that inspects or mutates configuration, caches, logs, or user data must isolate `HOME`, `USERPROFILE`, `LOCALAPPDATA`, `MAESTRO_HELDOUT_HOME`, and `MAESTRO_MCP_LOG` in a temporary folder at the process level.
- Tests must never touch real user paths (`~/.claude/`, `~/.gemini/`, `~/.maestro/`).
- Tests must never invoke the real `agy` executable; test harness mocks or synthetic scripts must be used instead.

## Pull Request Process

1. Keep pull requests focused on a single task or improvement.
2. GitHub Actions CI must pass on all three supported operating systems (**Windows**, **Linux**, and **macOS**) across both **Python 3.9** and **Python 3.12**.
