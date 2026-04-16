---
name: git-project-mgmt
description: >
  GitHub project management with gh CLI and git. Trigger when user wants to: create/manage issues, branches, PRs, releases, labels, milestones, review code, check CI, manage GitHub Projects, or any gh/git workflow. Also trigger for: "open a PR", "file an issue", "create a release", "check CI", "review code", "push changes", "merge", "tag", "branch", or any reference to the team's git workflow conventions.
---


# Git Project Management

This skill manages the full GitHub workflow for a multi-person software team.
Always follow the conventions defined in the project's CLAUDE.md.

## Prerequisites

Before any operation, verify:

```bash
gh auth status
git config user.name && git config user.email
```

## Quick Reference

| Task | Action |
|------|--------|
| Start new work | Create Issue → Create branch → Develop → PR |
| Branch naming | `<type>/<issue#>-<description>` |
| Commit format | `<type>(<scope>): <subject>` |
| Issue title | `[Type] description` (Type capitalized) |
| PR title | `<type>(<scope>)[#N]: <subject>` (omit [#N] if no Issue) |
| Merge strategy | Squash merge, delete branch |

## Core Conventions

### Types

`feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `ci`, `perf`, `revert`

### Scopes

Use the module or area touched by the change. Common examples:
`api`, `ui`, `auth`, `db`, `config`, `ci`, `deps`, `build`, `infra`, `logging`, `docs`, `test`

Define a project-specific scope list in your repo's CLAUDE.md when helpful.

### Issue Title Format

```
[Type] description
```

Examples:
- `[Feat] Add SSO login`
- `[Bug] Crash when submitting empty form`
- `[Refactor] Split monolith auth module`

### Branch Naming

```
<type>/<issue-number>-<short-description>
```

Examples:
- `feat/12-sso-login`
- `fix/34-empty-form-crash`
- `refactor/56-auth-module`

### Commit Messages

```
<type>(<scope>): imperative subject ≤72 chars

Optional body explaining WHY.

Closes #<issue-number>
```

### PR Title

```
<type>(<scope>)[#<issue-number>]: <subject>
```

If no corresponding Issue, omit `[#N]`:

```
<type>(<scope>): <subject>
```

Examples:
- `feat(auth)[#12]: add SSO login flow`
- `chore(ci): add lint to CI pipeline`

## Workflows

For step-by-step command sequences, read `references/workflows.md`.

## Label Policy

Labels vary by operation type. Follow this strictly.

### Issue Labels

| Category | Required? | When |
|----------|-----------|------|
| `type:` × 1 | ✅ Required | Always |
| `priority:` × 1 | ✅ Required | Always |
| `scope:` × 1~2 | Recommended | When specific modules involved |
| `status:` | Dynamic | Add/remove as state changes |

### PR Labels

| Category | Required? | When |
|----------|-----------|------|
| `type:` × 1 | ✅ Required | Always (match Issue/branch) |
| `scope:` × 1~2 | Recommended | Match the Issue |
| `priority:` | ❌ Never | Belongs to Issue level |

### Release / Tag

No labels. Use SemVer tags (`v1.2.0`) and Milestones.

## Decision Guide

| User wants to... | Start with... |
|---|---|
| Work on a new feature | `references/workflows.md` § Feature Development |
| Fix a bug | `references/workflows.md` § Feature Development (same flow) |
| Do a release | `references/workflows.md` § Release |
| Set up a new repo | `references/workflows.md` § Repo Initialization |
| Review someone's PR | `references/workflows.md` § Code Review |
| Check project progress | `references/workflows.md` § Daily Operations |
