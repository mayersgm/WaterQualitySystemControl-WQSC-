# CLAUDE.md - OptionSteppers2026

## Project Overview


## What This Project Is

*

## Tech Stack

## Architecture


### Key Concepts


### Directory Structure


## Terminology Standards


## Safety Rules


### Security:
- NEVER commit `.env` files, `secrets.json`, or credential files
- NEVER expose API keys in logs or error messages

### Configuration:



## Testing
Autonomous Debug-and-Fix Against Test Suites

Read the handoff doc in MEMORY.md and identify all pending phase specs. For each independent phase, create a git worktree and launch a parallel subagent via the Task tool with instructions to: (1) implement the phase per spec, (2) run the full test suite until green, (3) commit and push to a phase-specific branch, (4) report back with branch name and test count. After all agents complete, summarize results and prepare PRs. Stop and confirm with me before spawning if any phases have dependencies.

## Commit Guidelines

- Format: `type(scope): brief description`
- Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`
- One logical change per commit
- Prefer multiple small commits over one large commit

## Branch Strategy


## Workflow

- Always commit AND push after completing work unless explicitly told otherwise. Confirm both actions were taken.

## Git Operations

- When working with worktrees, always verify the correct worktree path before editing files. Run `git worktree list` and confirm the active directory matches the intended branch.

## Debugging

- Fix the root cause before moving on. Do not assume the first hypothesis is correct — verify each fix actually resolves the issue before declaring it done. Common pitfalls: reading config from wrong source, editing wrong file, caching stale values.

## Session Continuity

- When user asks to continue from a previous session, FIRST check `.claude/` memory files and all MEMORY.md files in the repo before asking the user what to do.

## Code Quality

- Keep changes small and focused
- Don't over-engineer — only make changes that are directly needed
- Don't leave dead code
- After writing code, ask: "Would a senior engineer say this is overcomplicated?" If yes, simplify.
- Fight entropy. Leave the codebase better than you found it.
