# Git Workflows Reference

All command sequences for the team's GitHub workflow.

## Table of Contents

1. [Repo Initialization](#repo-initialization)
2. [Branch Protection](#branch-protection)
3. [Feature Development (End-to-End)](#feature-development)
4. [Code Review](#code-review)
5. [Conflict Resolution](#conflict-resolution)
6. [Release](#release)
7. [Hotfix](#hotfix)
8. [Daily Operations](#daily-operations)
9. [Maintenance](#maintenance)

---

## Repo Initialization

First-time setup for a new team member:

```bash
gh repo clone <owner>/<repo>
cd <repo>
git config user.name "Your Name"
git config user.email "your@email.com"

# Verify
gh auth status
git log --oneline -3
```

For the Maintainer — initial repo config:

```bash
# Enable useful repo settings
gh api repos/{owner}/{repo} -X PATCH \
  -f has_issues=true \
  -f has_wiki=false \
  -f allow_squash_merge=true \
  -f allow_merge_commit=false \
  -f allow_rebase_merge=false \
  -f delete_branch_on_merge=true \
  -f squash_merge_commit_title=PR_TITLE \
  -f squash_merge_commit_message=PR_BODY
```

This ensures:
- Only squash merge is allowed (enforces clean history)
- Branches auto-delete after merge
- Squash commit uses PR title + body (preserves issue references)

---

## Branch Protection

Maintainer sets up `main` branch protection:

```bash
gh api repos/{owner}/{repo}/branches/main/protection -X PUT \
  --input - <<'EOF'
{
  "required_status_checks": {
    "strict": true,
    "contexts": ["ci"]
  },
  "enforce_admins": false,
  "required_pull_request_reviews": {
    "required_approving_review_count": 1,
    "dismiss_stale_reviews": true
  },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false
}
EOF
```

---

## Feature Development

Complete flow from Issue to merge. Works for `feat`, `fix`, `refactor`, etc.

### Step 1: Create Issue

Labels: `type:` (required) + `priority:` (required) + `scope:` (recommended)

```bash
# Feature — required: type + priority, recommended: scope
gh issue create \
  --title "[Feat] Add SSO login flow" \
  --body "## Motivation
Current login only supports email/password. Enterprise customers need SSO.

## Proposed Approach
- Integrate OIDC provider (Okta/Auth0)
- Add \`/auth/sso/callback\` route
- Store provider claims in session

## Acceptance Criteria
- [ ] Users can log in via configured OIDC provider
- [ ] Existing email/password flow unchanged
- [ ] Session TTL configurable
- [ ] Logs capture provider + subject for audit" \
  --label "type:feat,priority:high,scope:auth"

# Bug — required: type + priority, recommended: scope
gh issue create \
  --title "[Bug] Crash when submitting empty signup form" \
  --body "## Environment
- App version: 1.4.2
- Browser: Chrome 123 / Safari 17

## Steps to Reproduce
1. Open /signup
2. Click Submit without filling any field

## Expected vs Actual
Expected: inline validation errors.
Actual: 500 response, client shows generic error banner.

## Hypothesis
Server-side validator likely throws on \`undefined\` email before schema check." \
  --label "type:bug,priority:critical,scope:api,scope:ui"
```

### Step 2: Create Branch

```bash
# Assuming Issue #12 was created
git switch main && git pull origin main
git switch -c feat/12-sso-login
```

### Step 3: Develop and Commit

One commit = one atomic, describable change. Each commit should pass lint independently.
Do NOT mix unrelated changes (e.g. bugfix + rename + docs) into one commit.
Prefer finer granularity on feature branches — squash merge cleans up the history.

```bash
# Each commit is one focused logical unit
git add src/auth/oidc.ts
git commit -m "feat(auth): add OIDC client and token verifier"

git add src/routes/auth.ts
git commit -m "feat(api): add /auth/sso/callback route"

git add tests/auth/sso.test.ts
git commit -m "test(auth): cover SSO callback happy path and errors"

# Keep in sync with main
git fetch origin && git rebase origin/main
```

### Step 4: Push and Create PR

```bash
git push -u origin feat/12-sso-login

gh pr create \
  --title "feat(auth)[#12]: add SSO login flow" \
  --body "## What
Adds OIDC-based SSO login.

## Why
Enterprise customer requirement (see #12).

## Changes
- \`src/auth/oidc.ts\`: OIDC client, JWKS fetch, token verifier
- \`src/routes/auth.ts\`: \`/auth/sso/callback\` route
- \`src/session.ts\`: store provider + subject in session

## Testing
- [x] Unit tests for token verifier (valid, expired, bad signature)
- [x] Integration test for callback route
- [x] Manually tested against staging Auth0 tenant

Closes #12" \
  --reviewer teammate1 \
  --label "type:feat,scope:auth" \
  --milestone "v1.2"
```

### Step 5: After Review — Merge

```bash
gh pr merge --squash --delete-branch

# Local cleanup
git switch main && git pull
git branch -d feat/12-sso-login
```

---

## Code Review

```bash
# See PRs waiting for my review
gh pr list --search "review-requested:@me"

# View PR
gh pr view 42
gh pr diff 42

# Checkout locally and test
gh pr checkout 42
# run the project's lint + test suite

# Approve
gh pr review 42 --approve --body "Tested locally, looks good ✅"

# Request changes
gh pr review 42 --request-changes --body "Issues to address:
1. \`API_BASE_URL\` is hardcoded in line 45 — move to env config
2. Missing input validation on public handler
3. No test for the error-path branch"

# Comment only
gh pr review 42 --comment --body "Suggestion: consider extracting the retry logic into a shared util"
```

### Review checklist

When reviewing, check:
- No hardcoded secrets, URLs, or environment-specific values
- Inputs validated at trust boundaries
- Error paths handled (not just the happy path)
- No regressions in existing behavior
- Tests cover at least the happy path + one meaningful error case
- Logs useful for debugging, no sensitive data leaked
- Public functions have clear types / interfaces
- No dead code, commented-out blocks, or debug residue

---

## Conflict Resolution

```bash
# On your feature branch
git fetch origin
git rebase origin/main

# If conflicts occur:
# 1. Edit conflicting files
# 2. git add <resolved-files>
# 3. git rebase --continue
# 4. Force push (rebase rewrites history)
git push --force-with-lease
```

`--force-with-lease` is safer than `--force`: it fails if someone else pushed to your branch.

---

## Release

### Prepare Release

```bash
# 1. Ensure main is clean
git switch main && git pull

# 2. Check milestone completeness
gh api repos/{owner}/{repo}/milestones \
  --jq '.[] | select(.title=="v1.2") | "Open: \(.open_issues), Closed: \(.closed_issues)"'

# 3. Tag
git tag -a v1.2.0 -m "Release v1.2.0: SSO login, audit logging"
git push origin v1.2.0

# 4. Create release with auto-generated notes
gh release create v1.2.0 \
  --title "v1.2.0 — SSO Login & Audit Logging" \
  --generate-notes

# 5. Close milestone
MILESTONE_NUM=$(gh api repos/{owner}/{repo}/milestones \
  --jq '.[] | select(.title=="v1.2") | .number')
gh api repos/{owner}/{repo}/milestones/$MILESTONE_NUM -X PATCH -f state=closed
```

### Version Convention (SemVer)

```
MAJOR.MINOR.PATCH

v1.0.0 → v1.0.1  patch: bug fix, no API change
       → v1.1.0  minor: new feature, backward compatible
       → v2.0.0  major: breaking change (API signature, config format, data migration)
```

---

## Hotfix

```bash
git switch main && git pull
git switch -c hotfix/78-session-leak

# Fix the issue
git add -A
git commit -m "fix(auth): clear session store on logout to prevent leak

Closes #78"

git push -u origin hotfix/78-session-leak

gh pr create \
  --title "fix(auth)[#78]: clear session store on logout" \
  --body "Sessions were not being evicted on logout, causing stale entries
to accumulate in Redis.

Closes #78" \
  --reviewer teammate1 \
  --label "type:bug,scope:auth"

# After approval
gh pr merge --squash --delete-branch
```

---

## Daily Operations

### Morning Check

```bash
# My open issues
gh issue list --assignee @me --state open

# PRs waiting for my review
gh pr list --search "review-requested:@me"

# My PR status (CI, reviews)
gh pr status

# Recent CI runs
gh run list --limit 5
```

### Project Overview

```bash
# All open issues by priority
gh issue list --state open --label "priority:critical"
gh issue list --state open --label "priority:high"

# Milestone progress
gh api repos/{owner}/{repo}/milestones \
  --jq '.[] | select(.state=="open") | "\(.title): \(.closed_issues)/\(.closed_issues + .open_issues) done"'

# Team PR activity
gh pr list --state all --limit 10 --json number,title,state,author \
  --jq '.[] | "#\(.number) [\(.state)] \(.title) (@\(.author.login))"'
```

### Search

```bash
# Find issues about a topic
gh search issues "session leak" --repo {owner}/{repo}

# Find code
gh search code "getSessionToken" --repo {owner}/{repo}
```

---

## Maintenance

### Stale Branch Cleanup

```bash
# List merged branches on remote
git branch -r --merged origin/main | grep -v main | sed 's/origin\///'

# Delete them
git branch -r --merged origin/main | grep -v main | sed 's/origin\///' | \
  xargs -I{} git push origin --delete {}
```

### Bulk Close Stale Issues

```bash
gh issue list --state open --label "status:wontfix" --json number --jq '.[].number' | \
  xargs -I{} gh issue close {} --reason "not planned"
```

### Check Rate Limit

```bash
gh api rate_limit --jq '{
  core: "\(.resources.core.remaining)/\(.resources.core.limit)",
  graphql: "\(.resources.graphql.remaining)/\(.resources.graphql.limit)"
}'
```
