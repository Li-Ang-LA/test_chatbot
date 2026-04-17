Implement GitHub issue #$ARGUMENTS.

## Workflow

1. **Read context**: Read `plan.md` from the project root to understand the overall plan. Then fetch the GitHub issue details to understand the exact requirements and acceptance criteria.

2. **Branch**: Switch to latest `main` (`git switch main && git pull`), then create a new branch following the naming convention: `<type>/<issue-number>-<short-description>`.

3. **Implement**: Complete the implementation for this single issue only. Follow the plan's spec, acceptance tests, and dependencies. Run lint, format, and tests after each change.

4. **Commit**: Make atomic commits as you go. Use the project's commit message format: `<type>(<scope>): <imperative subject>`. Use `Refs #N` on intermediate commits and `Closes #N` on the final commit.

5. **Push & PR**: Push the branch and create a PR with title format `<type>(<scope>)[#<issue-number>]: <subject>`. The PR body must include `Closes #N` and a test plan. At the end of the PR body, add a line `@claude review this PR` to trigger automated code review.

## Rules

- The branch and PR must be focused on this **single issue** — no mixing work across issues.
- If this issue depends on another issue that is not yet merged, ask the user how to proceed.
- Follow all conventions in `.claude/rules/git-project-mgmt.md`.
- Do not skip the research/plan phases if the issue requires design decisions not covered in the existing plan.
