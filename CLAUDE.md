# CLAUDE.md

This file provides guidance for AI assistants working with the **test-firstattempt** repository.

## Repository Overview

This is a newly initialized repository (`schwh/test-firstattempt`). As the project evolves, this document should be updated to reflect the current state of the codebase.

## Project Structure

```
test-firstattempt/
├── CLAUDE.md          # AI assistant guidance (this file)
└── (project files)    # To be added as the project develops
```

## Development Workflow

### Git Conventions

- **Default branch**: `main` (or as configured by the repository owner)
- **Feature branches**: Use descriptive names prefixed with the purpose (e.g., `feature/`, `fix/`, `claude/`)
- Write clear, concise commit messages describing the "why" not just the "what"
- Keep commits atomic — one logical change per commit

### Getting Started

1. Clone the repository
2. Check the project's dependency file (e.g., `package.json`, `requirements.txt`) once added
3. Install dependencies using the appropriate package manager
4. Follow the build/test instructions documented below as they are added

## Code Style and Conventions

<!-- Update this section as linters, formatters, and style guides are configured -->

- Follow the project's configured linter and formatter rules
- Maintain consistency with existing code patterns
- Prefer clarity over cleverness

## Testing

<!-- Update this section when test frameworks are added -->

- Run the full test suite before pushing changes
- Add tests for new functionality
- Ensure existing tests pass after modifications

## Build and Run

<!-- Update this section when build tooling is configured -->

No build system has been configured yet. Update this section when one is added.

## CI/CD

<!-- Update this section when CI/CD pipelines are added -->

No CI/CD pipeline is configured yet. Update this section when one is added.

## Key Guidelines for AI Assistants

- **Read before writing**: Always read existing files before modifying them
- **Minimal changes**: Only make changes that are directly requested or clearly necessary
- **No over-engineering**: Keep solutions simple and focused on the task at hand
- **Security first**: Avoid introducing vulnerabilities (injection, XSS, etc.)
- **Update this file**: When adding significant tooling, dependencies, or conventions, update this CLAUDE.md to keep it current
