## Agent skills

### Issue tracker

Track issues and specs in GitHub Issues. Read `docs/agents/issue-tracker.md`
before issue-tracker operations.

### Triage labels

Use the five canonical triage labels. Read `docs/agents/triage-labels.md`
when assigning triage roles.

### Domain docs

Use a single-context layout. Read `docs/agents/domain.md` before exploring
the codebase.

### Qualification and release work

Read `docs/agents/qualification.md` before preparing or restoring guides, resuming
a qualification campaign, reconciling evidence, or monitoring release CI.

### Development Principles
Test-Driven Development: Write or update tests first. Do not claim completion unless tests run and pass, or explicitly state why they could not be run.

Small, Reversible, Observable Changes: Prefer small diffs and scoped changes. Implement user-testable and visible changes before backend changes wherever feasible. Keep changes reversible where possible. Maintain separation of concerns; avoid mixing orchestration, domain logic, and IO unless trivial.

Fail Fast, No Silent Fallbacks: Validate inputs at boundaries. Surface errors early and explicitly. Assume dependencies may fail. No silent fallbacks or hidden degradation. Any fallback must be explicit, tested, and observable.

Minimize Complexity (YAGNI, No Premature Optimization): Implement the simplest solution that meets current requirements and tests. Do not design for speculative future use cases. Optimize only with evidence.

Deliberate Trade-offs: Reusability vs. Fit (DRY with Restraint): Apply DRY only to real, stable duplication. Avoid abstractions that increase cognitive load without clear benefit. Prefer fit-for-purpose code unless a second use case is concrete.

Don't Assume—Ask for Clarification: If requirements are ambiguous or multiple interpretations exist, ask. If proceeding is necessary, state assumptions explicitly and keep changes localized and reversible.

Confidence-Gated Autonomy: Proceed end-to-end only when confidence is high. Narrow scope and increase checks when confidence is medium. Stop and ask when confidence is low.

Security-by-Default: Treat all external input as untrusted. Use safe defaults and least privilege. Do not weaken auth, authz, crypto, or injection defenses without explicit instruction. Never introduce secrets into code. NEVER modify user credentials, password hashes, auth tokens, or security-sensitive database rows unless the user explicitly instructs you to do so. When testing requires authentication, check scripts/ and documentation for test credentials first, then ask the user.

Don't Break Contracts: Preserve existing public APIs, schemas, and behavioral contracts unless explicitly instructed otherwise. If breaking changes are required, provide migration steps and compatibility tests.

Risk-Scaled Rigor: Scale rigor with impact: (1) Low risk — unit tests, lint/format. (2) Medium risk — integration tests, edge cases, rollback awareness. (3) High risk (security, auth, money, data loss, core flows) — explicit approval before destructive actions, targeted tests, minimal refactoring.