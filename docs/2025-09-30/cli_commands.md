# PMM Command Line Interface (CLI) Guide

This document provides a comprehensive guide to the Persistent Mind Model (PMM) Command Line Interface (CLI) tools. These tools allow you to interact with and manage your PMM instance.

## Table of Contents
- [Basic Usage](#basic-usage)
- [Available Commands](#available-commands)
  - [chat](#chat)
  - [introspect](#introspect)
  - [backlog](#backlog)
  - [canaries](#canaries)
  - [invariants](#invariants)
  - [model_select](#model_select)
- [Common Options](#common-options)
- [Troubleshooting](#troubleshooting)

## Basic Usage

All PMM CLI commands follow this basic pattern:

```bash
python -m pmm.cli.COMMAND [OPTIONS]
```

## Available Commands

### `chat`

Starts an interactive chat session with the PMM instance.

**Usage:**
```bash
python -m pmm.cli.chat --db .data/pmm.db
```

**Options:**
- `--db PATH`: Path to the SQLite database file (required)
- `--model MODEL`: Specify which model to use for responses
- `--verbose`: Enable verbose output

**Description:**
The chat interface allows you to have interactive conversations with PMM. The system maintains context between messages and can perform actions based on your inputs.

---

### `introspect`

Runs introspection and self-analysis on the PMM instance.

**Usage:**
```bash
python -m pmm.cli.introspect --db .data/pmm.db
```

**Options:**
- `--db PATH`: Path to the SQLite database file (required)
- `--window N`: Number of recent events to analyze (default: 100)
- `--full`: Perform a full system introspection (may take longer)

**Description:**
This command triggers PMM's self-introspection capabilities, analyzing recent events, commitment patterns, and trait evolution. It can help identify patterns in PMM's behavior and development.

---

### `backlog`

Manages the processing backlog of the PMM system.

**Usage:**
```bash
python -m pmm.cli.backlog --db .data/pmm.db process
```

**Subcommands:**
- `process`: Processes pending items in the backlog
- `status`: Shows current backlog status
- `clear`: Clears the backlog (use with caution)

**Description:**
The backlog system manages deferred processing tasks in PMM, ensuring that all operations are eventually processed even if they can't be handled immediately.

---

### `canaries`

Runs canary tests to verify system health.

**Usage:**
```bash
python -m pmm.cli.canaries --db .data/pmm.db
```

**Options:**
- `--db PATH`: Path to the SQLite database file (required)
- `--quick`: Run only critical canary tests
- `--verbose`: Show detailed test output

**Description:**
Canary tests are lightweight health checks that verify the basic functionality of the PMM system. They're designed to detect issues before they become critical.

---

### `invariants`

Verifies system invariants and consistency checks.

**Usage:**
```bash
python -m pmm.cli.invariants --db .data/pmm.db
```

**Options:**
- `--db PATH`: Path to the SQLite database file (required)
- `--fix`: Attempt to automatically fix any issues found
- `--strict`: Treat all warnings as errors

**Description:**
This command checks the internal consistency of the PMM system, ensuring that all data structures and relationships are valid. It's particularly useful after system upgrades or migrations.

---

### `model_select`

Manages and selects between different model configurations.

**Usage:**
```bash
python -m pmm.cli.model_select --db .data/pmm.db list
```

**Subcommands:**
- `list`: List available models
- `set MODEL`: Set the active model
- `info MODEL`: Show detailed information about a model

**Description:**
This command allows you to manage different model configurations and switch between them as needed. Different models may be optimized for different types of tasks or interactions.

## Common Options

Most commands support these common options:

- `--help`: Show help message and exit
- `--version`: Show version information
- `--log-level LEVEL`: Set the logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

## Troubleshooting

### "No module named pmm.cli.MODULE"
If you encounter this error, it typically means:
1. The PMM package is not installed in your current environment
2. You're running the command from the wrong directory
3. There's a typo in the module name

### Database Connection Issues
If you see database-related errors:
1. Verify the database file exists at the specified path
2. Ensure the application has read/write permissions for the database file
3. Check if another process has locked the database

### Getting Help
For additional help, you can use the `--help` flag with any command:

```bash
python -m pmm.cli.chat --help
```
