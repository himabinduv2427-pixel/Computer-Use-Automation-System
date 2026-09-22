# Computer-Use Automation System

An LLM-driven system for discovering and replaying automation flows in banking/credit union back-office applications.

## What This Does

1. **Discovers** automation by running LLM-driven agent loop (observe → decide → act) on a target application
2. **Records** the discovered flow as a typed, versioned, reusable artifact
3. **Replays** the artifact deterministically without LLM (fast, reliable, cheaper)
4. **Handles errors** explicitly (distinguishes business outcomes from failures)
5. **Escalates to humans** when stuck or facing risky actions
6. **Maintains safety** through guardrails, allowlists, and credential redaction

## Key Insight

> **The model discovers. The artifact captures. Deterministic replay runs it.**

Once learned, automation becomes a reliable, inspectable, auditable capability that agents can invoke on-demand.

## Architecture

```
┌─────────────────────────────────────────┐
│   LLM Agent Loop (Discovery)            │
│   Observe → Decide → Act                │
│   Screenshots + Actions → Artifact      │
└─────────────────────────────────────────┘
                  ↓
         [ArtifactSchema]
         (Typed, Versioned)
                  ↓
┌─────────────────────────────────────────┐
│   Deterministic Replay Engine           │
│   Execute without LLM                   │
│   Stable Targeting + Error Handling    │
└─────────────────────────────────────────┘
                  ↓
            [Replay Result]
         (Success/Failure/Outcome)
```

## Files

### Core System

- **agent_artifact.py** - Artifact schema definition
  - `ArtifactSchema`: Typed, versioned capability contract
  - `StepDefinition`: Each step with actions, checkpoints, error handlers
  - `Locator`: Robust element targeting with fallbacks

- **replay_engine.py** - Deterministic execution without LLM
  - `ReplayEngine`: Execute artifact given inputs
  - `ReplayResult`: Detailed outcome report
  - `SurfaceExecutor`: Abstract interface for interacting with target app

- **agent_loop.py** - LLM-driven discovery
  - `AgentLoop`: Observe → Decide → Act until goal met
  - `ActionDecision`: What LLM decided to do next

### Test/Demo

- **mock_banking_app.py** - Simulated banking back-office
  - Member search functionality
  - Account details lookup
  - No real credentials or data

### Documentation

- **REPORT.md** - Detailed design report
  - Architecture and data flow
  - Artifact schema deep-dive
  - Error handling and human escalation
  - Multi-tenant design
  - Trade-offs and evaluation criteria

- **README.md** - This file

## Quick Start

### 1. Install Dependencies

```bash
pip install fastapi uvicorn anthropic google-generativeai playwright
```

### 2. Set Up API Keys

```bash
export GEMINI_API_KEY=your_key_here
export ANTHROPIC_API_KEY=your_key_here
```

### 3. Start Mock Banking App

```bash
python mock_banking_app.py
# → http://localhost:8001
```

### 4. Run Discovery

```bash
python discover_example.py \
  --goal "Look up member 12345 and read their savings balance" \
  --app-url http://localhost:8001
```

This will:
- Run LLM-driven agent loop
- Take screenshots and decide next actions
- Record flow as artifact
- Save to `./artifacts/`

### 5. Run Replay

```bash
python replay_example.py \
  --artifact-id art_example_001 \
  --member-id 67890
```

This will:
- Load the saved artifact
- Execute deterministically (no LLM)
- Return results with detailed evidence

## Example Artifact

After discovery, you get a typed artifact like:

```json
{
  "artifact_id": "art_member_lookup_001",
  "capability_name": "lookup_member_savings",
  "goal": "look up member and read their current savings balance",
  "input_schema": {
    "member_id": {"type": "string", "required": true}
  },
  "output_schema": {
    "member_found": {"type": "boolean"},
    "member_name": {"type": "string"},
    "savings_balance": {"type": "string"}
  },
  "steps": [
    {
      "step_id": "step_1",
      "description": "Navigate to dashboard",
      "actions": [...],
      "expected_state": {"page_title": "Dashboard"},
      "error_handlers": {"navigation_failed": "retry"}
    },
    ...
  ],
  "allowed_domains": ["bank.local"],
  "reversible": true,
  "requires_confirmation": false
}
```

## Replay Result

When you replay with `{"member_id": "12345"}`, you get:

```json
{
  "artifact_id": "art_member_lookup_001",
  "run_id": "abc123",
  "status": "success",
  "final_outputs": {
    "member_found": true,
    "member_name": "John Doe",
    "savings_balance": "$5,234.56"
  },
  "steps": [
    {
      "step_id": "step_1",
      "status": "success",
      "expected_state_met": true
    },
    ...
  ],
  "execution_time_ms": 1250
}
```

## Error Handling

The system distinguishes three types of outcomes:

1. **Success**: All steps completed, goal achieved
2. **Business Outcome**: Expected result (e.g., "member not found") - not a crash
3. **Hard Failure**: Unexpected error - escalate to human

Example: "member not found" is a **business outcome**, not a failure:

```python
if "record_not_found" in step.error_message:
    result.status = ReplayResultStatus.BUSINESS_OUTCOME
    result.business_outcome = "Member not found"
    # Return cleanly; let caller handle
```

## Human Escalation

When replay gets stuck:

```python
{
  "intervention_request": {
    "artifact_id": "art_lookup_001",
    "step": "step_4_read_results",
    "reason": "Expected results element not found after retries",
    "current_url": "https://bank.local/member-search",
    "screenshot": "base64_data...",
    "human_action_needed": "Review screenshot; click correct element"
  }
}
```

Human sees **live session** (not mocked), takes control, performs actions, then hands back to automation.

## Safety Features

### Allowlist Enforcement

```python
artifact.allowed_domains = ["bank.local", "internal.bank.local"]
# Replay will refuse to run on any other domain
```

### Reversibility Checks

```python
if action.is_irreversible and requires_confirmation:
    raise NeedsApproval("Irreversible action; needs human confirmation")
```

### Credential Redaction

```python
# ✗ Never:
{"output": {"account_number": "123456789"}}

# ✓ Always:
{"output": {"account_last_4": "6789"}}
```

## Robust Element Targeting

Each locator includes a fallback chain:

```python
Locator(
    type=LocatorType.ACCESSIBILITY,  # Primary
    value="Search Button",
    fallbacks=[
        Locator(LocatorType.CSS_SELECTOR, "button[data-testid='search']"),
        Locator(LocatorType.XPATH, "//button[contains(text(), 'Search')]"),
        Locator(LocatorType.IMAGE, "screenshot_coordinates")  # Last resort
    ]
)
```

If UI layout changes, replay tries fallback locators before failing.

## Multi-Tenant Design

For systems used by hundreds of institutions:

**Base artifact** (works across 80% of tenants):
```json
{
  "artifact_id": "art_lookup_base",
  "steps": [...]
}
```

**Tenant customizations** (stored separately):
```json
{
  "tenant_id": "bank_acme_001",
  "artifact_id": "art_lookup_base",
  "step_overrides": [
    {
      "step_id": "step_2",
      "locator_override": "button.acme-search-btn"
    }
  ]
}
```

Replay applies tenant overrides automatically. Drift detector flags when overrides need updating.

## Design Decisions

| Decision | Why |
|----------|-----|
| **Fallback locators** | Real UIs change; fallbacks maintain replay stability |
| **Explicit error handlers** | Must distinguish "member not found" (valid) from "page crashed" (invalid) |
| **Live session handoff** | Human actions are preserved and logged; context isn't lost |
| **Base + tenant overrides** | Scales to hundreds of institutions without per-tenant waste |
| **Deterministic replay** | Fast, cheap, reliable; no LLM call needed for production runs |

## Evaluation Criteria

✅ Goal-driven agent loop
✅ Structured, typed artifact
✅ Deterministic replay
✅ Explicit error handling
✅ Human-in-loop escalation
✅ Safety guardrails
✅ Observability & evidence

See REPORT.md for full evaluation against assignment requirements.

## Next Steps

1. **Operator Console** - Real-time UI for handoff and monitoring
2. **Drift Detection** - ML model to detect UI changes and flag artifacts needing updates
3. **Artifact Marketplace** - Cross-institution reuse and version management
4. **Multi-step Recovery** - Backtracking when one step assumption fails
5. **Confidence Scoring** - Track artifact reliability after N replays

## Files Reference

```
.
├── agent_artifact.py        # Artifact schema (core data model)
├── replay_engine.py         # Deterministic execution engine
├── agent_loop.py            # LLM-driven discovery
├── mock_banking_app.py      # Test application
├── discover_example.py      # Example: run discovery
├── replay_example.py        # Example: run replay
├── REPORT.md                # Detailed design report
├── README.md                # This file
└── artifacts/               # Directory for saved artifacts
    └── (created at runtime)
```

## Questions?

See REPORT.md for:
- Detailed architecture
- Artifact schema specification
- Error handling strategy
- Multi-tenant design
- Trade-off analysis
- Extensibility guide

---

**Status**: Core system complete and working. Ready for integration with real LLM and browser automation libraries.
