#!/usr/bin/env python3
"""
Example: Run deterministic replay of a saved artifact.

This demonstrates:
1. Load saved artifact from disk
2. Apply input variables
3. Execute deterministically without LLM
4. Handle errors explicitly
5. Return structured result

Usage:
    python replay_example.py --artifact-id art_lookup_abc123 --member-id 67890
"""

import asyncio
import argparse
import json
from pathlib import Path
from typing import Optional

from agent_artifact import ArtifactSchema
from replay_engine import ReplayEngine, ReplayResult, SurfaceExecutor


class DemoSurfaceExecutor(SurfaceExecutor):
    """Mock surface executor for demo"""

    def __init__(self):
        self.state = {
            "current_url": "http://localhost:8001/",
            "page": "dashboard",
            "members": {
                "12345": {
                    "name": "John Doe",
                    "accounts": {
                        "savings": {"balance": "$5,234.56"}
                    }
                },
                "67890": {
                    "name": "Jane Smith",
                    "accounts": {
                        "savings": {"balance": "$12,890.00"}
                    }
                }
            }
        }

    async def navigate(self, url: str) -> bool:
        self.state["current_url"] = url
        self.state["page"] = "dashboard"
        return True

    async def find_and_click(self, locator_type: str, locator_value: str) -> bool:
        # Simulate clicking different elements
        if "search" in locator_value.lower():
            self.state["page"] = "search"
            return True
        elif "result" in locator_value.lower():
            self.state["page"] = "member_details"
            return True
        return True

    async def find_and_type(self, locator_type: str, locator_value: str, text: str) -> bool:
        self.state["typed_value"] = text
        return True

    async def find_and_read(self, locator_type: str, locator_value: str) -> Optional[str]:
        # Return balance based on entered member ID
        member_id = self.state.get("typed_value", "")
        if member_id in self.state["members"]:
            return self.state["members"][member_id]["accounts"]["savings"]["balance"]
        return None

    async def verify_state(self, expected_state: dict) -> bool:
        # Simple demo: always pass
        return True


def get_screenshot_demo() -> str:
    """Return a demo screenshot (base64 placeholder)"""
    return "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="


async def run_replay_demo(artifact_id: str, member_id: str):
    """Demo: Load artifact and replay it"""

    print("\n" + "="*70, flush=True)
    print("COMPUTER-USE AUTOMATION REPLAY DEMO", flush=True)
    print("="*70, flush=True)
    print(f"\nArtifact: {artifact_id}", flush=True)
    print(f"Member ID: {member_id}\n", flush=True)

    # Load artifact
    artifacts_dir = Path("artifacts")
    artifact_path = artifacts_dir / f"{artifact_id}.json"

    if not artifact_path.exists():
        print(f"Error: Artifact not found at {artifact_path}")
        print("\nTo create an artifact, run:")
        print("  python discover_example.py")
        return

    print(f"Step 1: Loading artifact from {artifact_path}...", flush=True)
    artifact_data = json.loads(artifact_path.read_text())
    artifact = ArtifactSchema.from_dict(artifact_data)
    print(f"  ✓ Loaded: {artifact.capability_name}\n", flush=True)

    # Initialize replay engine
    print("Step 2: Setting up replay engine...", flush=True)
    executor = DemoSurfaceExecutor()
    engine = ReplayEngine(
        surface_executor=executor,
        screenshot_provider=get_screenshot_demo,
        logger=lambda msg: print(f"    {msg}", flush=True)
    )
    print("  ✓ Engine ready\n", flush=True)

    # Prepare inputs
    print("Step 3: Preparing inputs...", flush=True)
    inputs = {"member_id": member_id}
    print(f"  Member ID: {member_id}\n", flush=True)

    # Run replay
    print("Step 4: Executing replay (deterministic, no LLM)...\n", flush=True)
    result = await engine.replay(artifact, inputs)

    # Report results
    print("\n" + "="*70, flush=True)
    print("REPLAY RESULT", flush=True)
    print("="*70, flush=True)
    print(f"\nStatus: {result.status.value}", flush=True)
    print(f"Execution Time: {result.execution_time_ms:.0f}ms", flush=True)
    print(f"Artifact: {result.artifact_id}", flush=True)
    print(f"Run ID: {result.run_id}\n", flush=True)

    if result.status.value == "success":
        print("✓ REPLAY SUCCESSFUL\n", flush=True)
    elif result.status.value == "business_outcome":
        print(f"⚠ BUSINESS OUTCOME: {result.business_outcome}\n", flush=True)
    else:
        print(f"✗ FAILED: {result.error_summary}\n", flush=True)

    # Step-by-step results
    print("Step Results:", flush=True)
    for step in result.steps:
        status_icon = "✓" if step.status == "success" else "✗"
        print(f"  {status_icon} {step.step_id}: {step.status}", flush=True)
        if step.error_message:
            print(f"     Error: {step.error_message}", flush=True)

    # Final outputs
    if result.final_outputs:
        print(f"\nFinal Outputs:", flush=True)
        for key, value in result.final_outputs.items():
            print(f"  {key}: {value}", flush=True)

    # Evidence
    if result.steps and result.steps[-1].actions:
        last_action = result.steps[-1].actions[-1]
        if last_action.output:
            print(f"\nExtracted Data:", flush=True)
            print(f"  Savings Balance: {last_action.output}", flush=True)

    print("\n" + "="*70, flush=True)

    # Human escalation if needed
    if result.human_intervention_needed:
        print("\n⚠ HUMAN INTERVENTION NEEDED", flush=True)
        print(f"Reason: {result.intervention_reason}", flush=True)
        print("\nSystem would now:", flush=True)
        print("  1. Pause automation", flush=True)
        print("  2. Route intervention request to human operator", flush=True)
        print("  3. Provide live session for manual control", flush=True)
        print("  4. Log human actions and resume", flush=True)
    else:
        print("\n✓ No human intervention needed", flush=True)

    print()


def main():
    parser = argparse.ArgumentParser(
        description="Replay a saved automation artifact deterministically"
    )
    parser.add_argument(
        "--artifact-id",
        help="ID of artifact to replay (e.g., art_lookup_abc123)"
    )
    parser.add_argument(
        "--member-id",
        default="67890",
        help="Member ID to look up"
    )

    args = parser.parse_args()

    if not args.artifact_id:
        # Try to find most recent artifact
        artifacts_dir = Path("artifacts")
        if artifacts_dir.exists():
            artifacts = list(artifacts_dir.glob("*.json"))
            if artifacts:
                artifact_file = sorted(artifacts)[-1]  # Most recent
                args.artifact_id = artifact_file.stem
                print(f"Using most recent artifact: {args.artifact_id}")
            else:
                print("No artifacts found. Run discover_example.py first.")
                return
        else:
            print("No artifacts directory found. Run discover_example.py first.")
            return

    asyncio.run(run_replay_demo(args.artifact_id, args.member_id))


if __name__ == "__main__":
    main()