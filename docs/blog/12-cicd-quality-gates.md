# Adding AI Quality Gates to Your CI/CD Pipeline

*Published: December 2025*

---

Static analysis catches syntax errors. Unit tests catch logic bugs. Code review catches design problems.

What catches the things humans miss?

AI quality gates. Multiple models reviewing your code changes, reaching consensus, and blocking or approving deployments—automatically.

This post shows you how to add LLM Council's `council-gate` skill to your CI/CD pipeline.

## Why AI Quality Gates?

Traditional quality gates are rule-based:

- **Linters**: "Line too long", "Missing semicolon"
- **SAST**: "Potential SQL injection at line 42"
- **Coverage**: "Branch coverage below 80%"

These catch what they're programmed to catch. They miss:

- **Architectural violations**: "This service shouldn't call that database directly"
- **Semantic bugs**: "This function returns early before cleanup"
- **Security in context**: "This SQL is safe here but would be dangerous there"
- **Design smell**: "This abstraction will cause problems at scale"

AI models can reason about code in ways static tools can't. Multi-model consensus reduces individual model errors.

## The council-gate Skill

`council-gate` is a CI/CD-optimized verification skill with structured exit codes:

| Exit Code | Verdict | Pipeline Action |
|-----------|---------|-----------------|
| `0` | PASS | Continue deployment |
| `1` | FAIL | Block deployment |
| `2` | UNCLEAR | Require human review |

The `UNCLEAR` verdict is the key innovation. Instead of binary pass/fail, you get a third option: "the council couldn't reach confident consensus."

## GitHub Actions Integration

### Basic Setup

```yaml
# .github/workflows/council-gate.yml
name: Council Quality Gate

on:
  pull_request:
    branches: [main, master]

jobs:
  council-gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Full history for diff analysis

      - name: Install LLM Council
        run: pip install llm-council-core

      - name: Run Council Gate
        env:
          OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_API_KEY }}
        run: |
          llm-council gate \
            --snapshot ${{ github.sha }} \
            --confidence-threshold 0.8

      - name: Upload Transcript
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: council-transcript
          path: .council/logs/
```

### Handling All Three Verdicts

```yaml
jobs:
  council-gate:
    runs-on: ubuntu-latest
    outputs:
      verdict: ${{ steps.gate.outputs.verdict }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Install LLM Council
        run: pip install llm-council-core

      - name: Run Council Gate
        id: gate
        continue-on-error: true
        env:
          OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_API_KEY }}
        run: |
          set +e
          llm-council gate \
            --snapshot ${{ github.sha }} \
            --confidence-threshold 0.8 \
            --output-format json > verdict.json
          EXIT_CODE=$?
          echo "exit_code=$EXIT_CODE" >> $GITHUB_OUTPUT

          if [ $EXIT_CODE -eq 0 ]; then
            echo "verdict=PASS" >> $GITHUB_OUTPUT
          elif [ $EXIT_CODE -eq 1 ]; then
            echo "verdict=FAIL" >> $GITHUB_OUTPUT
          else
            echo "verdict=UNCLEAR" >> $GITHUB_OUTPUT
          fi

      - name: Handle PASS
        if: steps.gate.outputs.verdict == 'PASS'
        run: echo "Council approved changes"

      - name: Handle FAIL
        if: steps.gate.outputs.verdict == 'FAIL'
        run: |
          echo "Council found blocking issues"
          cat verdict.json | jq '.blocking_issues'
          exit 1

      - name: Handle UNCLEAR
        if: steps.gate.outputs.verdict == 'UNCLEAR'
        run: |
          echo "Council needs human review"
          gh pr comment ${{ github.event.number }} --body "$(cat <<'EOF'
          ## Council Quality Gate: Manual Review Required

          The LLM Council couldn't reach confident consensus on this PR.

          **Confidence**: $(cat verdict.json | jq -r '.confidence')
          **Threshold**: 0.8

          Please review the [council transcript](link-to-artifact) and approve manually.
          EOF
          )"
        env:
          GH_TOKEN: ${{ github.token }}

      - name: Upload Transcript
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: council-transcript
          path: .council/logs/
```

## GitLab CI Integration

```yaml
# .gitlab-ci.yml
stages:
  - test
  - council
  - deploy

council-gate:
  stage: council
  image: python:3.11-slim
  variables:
    OPENROUTER_API_KEY: $OPENROUTER_API_KEY
  before_script:
    - pip install llm-council-core
  script:
    - |
      llm-council gate \
        --snapshot $CI_COMMIT_SHA \
        --confidence-threshold 0.8
  allow_failure:
    exit_codes:
      - 2  # UNCLEAR triggers manual approval
  artifacts:
    paths:
      - .council/logs/
    when: always

deploy:
  stage: deploy
  needs: [council-gate]
  script:
    - echo "Deploying..."
  when: on_success
```

### Manual Approval for UNCLEAR

```yaml
council-gate:
  stage: council
  script:
    - llm-council gate --snapshot $CI_COMMIT_SHA
  allow_failure:
    exit_codes: [2]

manual-review:
  stage: council
  needs:
    - job: council-gate
      artifacts: true
  rules:
    - if: $CI_JOB_STATUS == "failed"
      when: manual
  script:
    - echo "Human approved after council UNCLEAR verdict"
```

## Azure DevOps Integration

```yaml
# azure-pipelines.yml
trigger:
  - main

pool:
  vmImage: 'ubuntu-latest'

stages:
  - stage: QualityGate
    jobs:
      - job: CouncilGate
        steps:
          - checkout: self
            fetchDepth: 0

          - task: UsePythonVersion@0
            inputs:
              versionSpec: '3.11'

          - script: pip install llm-council-core
            displayName: 'Install LLM Council'

          - script: |
              llm-council gate \
                --snapshot $(Build.SourceVersion) \
                --confidence-threshold 0.8
            displayName: 'Run Council Gate'
            env:
              OPENROUTER_API_KEY: $(OPENROUTER_API_KEY)
            continueOnError: true

          - publish: .council/logs
            artifact: council-transcript
            condition: always()
```

## Focus Areas: Security, Performance, Compliance

The `--rubric-focus` flag adjusts scoring weights:

### Security Focus

```bash
llm-council gate --snapshot $SHA --rubric-focus Security
```

Emphasizes:

- SQL injection, XSS, CSRF vulnerabilities
- Hardcoded secrets and credentials
- Authentication and authorization flaws
- Input validation gaps
- Dependency vulnerabilities

### Performance Focus

```bash
llm-council gate --snapshot $SHA --rubric-focus Performance
```

Emphasizes:

- Algorithm complexity (O(n²) where O(n) is possible)
- N+1 query patterns
- Memory leaks and resource exhaustion
- Blocking operations in async code
- Missing caching opportunities

### Compliance Focus

```bash
llm-council gate --snapshot $SHA --rubric-focus Compliance
```

Emphasizes:

- PII handling and data protection
- Audit logging completeness
- Access control implementation
- Regulatory requirements (GDPR, HIPAA, SOC2)
- Documentation for compliance audits

## Blocking Issues by Severity

Council verdicts include categorized issues:

```json
{
  "verdict": "fail",
  "confidence": 0.92,
  "exit_code": 1,
  "blocking_issues": [
    {
      "severity": "critical",
      "file": "src/auth.py",
      "line": 45,
      "message": "Password compared using == instead of constant-time comparison",
      "cwe": "CWE-208"
    }
  ],
  "suggestions": [
    {
      "severity": "minor",
      "file": "src/api.py",
      "line": 23,
      "message": "Consider adding rate limiting to this endpoint"
    }
  ]
}
```

### Severity Levels

| Severity | Definition | Pipeline Impact |
|----------|------------|-----------------|
| **Critical** | Security vulnerabilities, data loss, production crashes | Automatic FAIL |
| **Major** | Bugs in core functionality, missing error handling | Usually FAIL |
| **Minor** | Style issues, documentation gaps, improvements | Suggestions only |

## Cost and Latency Considerations

### Cost

Each council gate runs 3-5 model queries. At typical pricing:

| Tier | Models | Cost per Gate |
|------|--------|---------------|
| Quick | 3 small models | ~$0.01-0.05 |
| Balanced | 3 medium models | ~$0.05-0.20 |
| High | 3 large models | ~$0.20-1.00 |

For a team running 50 PRs/day with balanced tier: ~$2.50-10.00/day.

### Latency

Parallel model queries minimize latency:

| Stage | Typical Duration |
|-------|------------------|
| Stage 1 (responses) | 5-15 seconds |
| Stage 2 (peer review) | 10-20 seconds |
| Stage 3 (synthesis) | 3-8 seconds |
| **Total** | 20-45 seconds |

Compare to human code review: hours to days.

### Optimization Tips

1. **Run council-gate only on significant changes**:
   ```yaml
   on:
     pull_request:
       paths:
         - 'src/**'
         - '!src/**/*.md'
   ```

2. **Use quick tier for draft PRs, high tier for merge**:
   ```yaml
   - name: Determine Tier
     run: |
       if [ "${{ github.event.pull_request.draft }}" == "true" ]; then
         echo "TIER=quick" >> $GITHUB_ENV
       else
         echo "TIER=high" >> $GITHUB_ENV
       fi
   ```

3. **Cache the council installation**:
   ```yaml
   - uses: actions/cache@v4
     with:
       path: ~/.cache/pip
       key: ${{ runner.os }}-pip-llm-council
   ```

## When NOT to Use AI Quality Gates

AI gates complement, not replace, existing tools:

| Use Case | Better Tool |
|----------|-------------|
| Syntax errors | Linter |
| Type mismatches | Type checker |
| Known vulnerability patterns | SAST |
| Test coverage | Coverage tools |
| Code formatting | Formatter |

Use AI gates for:

- Semantic correctness
- Architectural decisions
- Security in context
- Design quality
- Complex logic review

## Monitoring and Alerting

Track gate metrics over time:

```yaml
- name: Record Metrics
  if: always()
  run: |
    curl -X POST ${{ secrets.METRICS_ENDPOINT }} \
      -d '{
        "pr": "${{ github.event.number }}",
        "verdict": "${{ steps.gate.outputs.verdict }}",
        "confidence": "${{ steps.gate.outputs.confidence }}",
        "duration_ms": "${{ steps.gate.outputs.duration }}",
        "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"
      }'
```

Alert on:

- **High UNCLEAR rate**: Models might be misconfigured
- **Latency spikes**: API issues or model degradation
- **Low confidence variance**: Possible model collusion

## Example: Full Production Setup

```yaml
# .github/workflows/quality-gates.yml
name: Quality Gates

on:
  pull_request:
    branches: [main]
    paths:
      - 'src/**'
      - 'tests/**'

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  # Traditional gates run in parallel
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm run lint

  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm test

  # AI gate runs after traditional gates pass
  council-gate:
    needs: [lint, test]
    runs-on: ubuntu-latest
    outputs:
      verdict: ${{ steps.gate.outputs.verdict }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Install LLM Council
        run: pip install llm-council-core

      - name: Run Council Gate
        id: gate
        continue-on-error: true
        env:
          OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_API_KEY }}
        run: |
          llm-council gate \
            --snapshot ${{ github.sha }} \
            --rubric-focus Security \
            --confidence-threshold 0.8 \
            --tier balanced

      - name: Comment on PR
        if: steps.gate.outputs.verdict != 'PASS'
        uses: actions/github-script@v7
        with:
          script: |
            const verdict = '${{ steps.gate.outputs.verdict }}';
            const body = verdict === 'FAIL'
              ? '## Council Gate: Changes Blocked\n\nSee artifacts for details.'
              : '## Council Gate: Manual Review Required\n\nConfidence below threshold.';
            github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
              body: body
            });

      - name: Upload Transcript
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: council-transcript
          path: .council/logs/

  # Require council approval for merge
  approve:
    needs: [council-gate]
    if: needs.council-gate.outputs.verdict == 'PASS'
    runs-on: ubuntu-latest
    steps:
      - run: echo "All quality gates passed"
```

## Getting Started

1. **Add API key to secrets**:
   ```bash
   gh secret set OPENROUTER_API_KEY
   ```

2. **Create workflow file**:
   Copy the [Basic Setup](#basic-setup) YAML above to `.github/workflows/council-gate.yml`

3. **Open a PR and watch**:
   The council will review your changes and post results.

---

*This post demonstrates CI/CD integration for [ADR-034: Agent Skills](../adr/ADR-034-agent-skills-verification.md).*

*LLM Council is open source: [github.com/amiable-dev/llm-council](https://github.com/amiable-dev/llm-council)*
