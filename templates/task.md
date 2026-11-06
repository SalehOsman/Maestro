# Task {{ID}}: {{TITLE}}

- Feature id: `{{FEATURE}}`
- Project root: `{{PROJECT}}`
- Methodology: `{{METHODOLOGY}}` (rules: `.maestro/EXECUTOR_RULES.md`)
- Kind: feature | fix (review round N) | setup

## Behaviour
{{What the feature must do, from the user's point of view}}

## Acceptance criteria
- [ ] {{Measurable criterion}}
- [ ] {{Error path that must be handled}}
- [ ] Verify command passes: `{{from .maestro/config.json}}`

## Constraints
- In scope: {{areas or files the feature may touch}}
- Out of scope: {{what must not change}}
- Do NOT run git commands that merge, rebase or push.

## Review depth
{{quick | full}}, because {{reason}}.

## Context the executor needs
{{Only what it cannot find in the repository: decisions already made, links, examples}}

## When done
Follow the two stop points in `.maestro/EXECUTOR_RULES.md`: the plan checkpoint, then the report
`.maestro/reports/task-{{ID}}.done.md` (template `.maestro/report-template.md`), written LAST.
