#!/usr/bin/env python3
"""
Example: Run LLM-driven discovery on mock banking app.

This demonstrates the agent loop:
1. Observe: Take screenshot of current state
2. Decide: Ask LLM what action to take next
3. Act: Execute action, capture evidence
4. Record: Save as typed artifact

Usage:
    python discover_example.py --goal "Look up member 12345 and read savings balance"
"""

import asyncio
import argparse
import json
import os
from pathlib import Path

# For this demo, we'll create a simple mock LLM client and surface executor
# In production, these would use real Playwright, Claude API, etc.


class DemoLLMClient:
    """Mock LLM client for demo purposes"""

    async def analyze_with_vision(self, prompt: str, screenshot_b64: str) -> str:
        # Demo: Pre-scripted responses
        if "goal: look up member" in prompt.lower():
            if "search" not in prompt.lower():
                return json.dumps({
                    "analysis": "I see a banking dashboard with a member search button",
                    "next_action": "CLICK",
                    "description": "Click the Member Search button to open search dialog",
                    "element_description": "Member Search button in navigation",
                    "value": None,
                    "reasoning": "Need to open search interface to enter member ID",
                    "is_complete": False,
                    "confidence": 0.95
                })
            elif "input" in prompt.lower():
                return json.dumps({
                    "analysis": "Search dialog is open with an input field",
                    "next_action": "TYPE",
                    "description": "Enter member ID into search field",
                    "element_description": "Member ID input field",
                    "value": "{member_id}",
                    "reasoning": "Need to type member ID to search",
                    "is_complete": False,
                    "confidence": 0.95
                })
            elif "button" in prompt.lower() or "search" in prompt.lower():
                return json.dumps({
                    "analysis": "Member ID has been entered, search button is visible",
                    "next_action": "CLICK",
                    "description": "Click Search to find member",
                    "element_description": "Search button",
                    "value": None,
                    "reasoning": "Execute search query",
                    "is_complete": False,
                    "confidence": 0.95
                })
            else:
                return json.dumps({
                    "analysis": "Search results are displayed",
                    "next_action": "CLICK",
                    "description": "Click on member result to view details",
                    "element_description": "Member result row",
                    "value": None,
                    "reasoning": "Open member account details",
                    "is_complete": False,
                    "confidence": 0.9
                })
        else:
            return json.dumps({
                "analysis": "Member details page is shown",
                "next_action": "READ",
                "description": "Read the savings balance",
                "element_description": "Savings balance display",
                "value": None,
                "reasoning": "Extract balance information",
                "is_complete": True,
                "confidence": 0.95
            })


class DemoSurfaceExecutor:
    """Mock surface executor for demo purposes"""

    def __init__(self):
        self.current_page = "dashboard"
        self.search_open = False
        self.member_id_entered = False
        self.search_executed = False
        self.member_viewed = False

    async def navigate(self, url: str) -> bool:
        print(f"    → Navigating to {url}")
        self.current_page = "dashboard"
        return True

    async def find_and_click(self, locator_type: str, locator_value: str) -> bool:
        print(f"    → Clicking {locator_value} (via {locator_type})")

        if "search" in locator_value.lower():
            self.search_open = True
            self.current_page = "search"
        elif "result" in locator_value.lower():
            self.member_viewed = True
            self.current_page = "member_details"

        return True

    async def find_and_type(self, locator_type: str, locator_value: str, text: str) -> bool:
        print(f"    → Typing '{text}' into {locator_value}")
        self.member_id_entered = True
        return True

    async def find_and_read(self, locator_type: str, locator_value: str) -> str:
        print(f"    → Reading from {locator_value}")
        return "$5,234.56"  # Mock savings balance

    async def verify_state(self, expected_state: dict) -> bool:
        # Simple demo: always pass checkpoint
        print(f"    → Verifying state: {expected_state}")
        return True


def create_demo_artifact():
    """Create example artifact from demo discovery"""
    from agent_artifact import (
        ArtifactSchema, StepDefinition, Action, Locator,
        ActionType, LocatorType
    )
    import uuid

    artifact = ArtifactSchema(
        artifact_id=f"art_lookup_{str(uuid.uuid4())[:8]}",
        capability_name="lookup_member_savings",
        capability_description="Search for a member and read their savings balance",
        goal="Look up member and read their current savings balance",

        input_schema={
            "member_id": {
                "type": "string",
                "description": "Member ID to look up",
                "required": True
            }
        },

        output_schema={
            "member_found": {
                "type": "boolean",
                "description": "Whether member was found"
            },
            "savings_balance": {
                "type": "string",
                "description": "Current savings balance"
            }
        },

        steps=[
            StepDefinition(
                step_id="step_1_search_button",
                description="Click Member Search button",
                actions=[
                    Action(
                        action_type=ActionType.CLICK,
                        locator=Locator(
                            type=LocatorType.ACCESSIBILITY,
                            value="Member Search"
                        ),
                        reasoning="Open search dialog"
                    )
                ],
                expected_state={"search_modal_open": True}
            ),

            StepDefinition(
                step_id="step_2_enter_id",
                description="Enter member ID",
                actions=[
                    Action(
                        action_type=ActionType.TYPE,
                        locator=Locator(
                            type=LocatorType.CSS_SELECTOR,
                            value="input[placeholder='Enter Member ID']"
                        ),
                        value="{member_id}",
                        reasoning="Enter member ID to search"
                    )
                ],
                expected_state={"input_has_value": True}
            ),

            StepDefinition(
                step_id="step_3_search",
                description="Execute search",
                actions=[
                    Action(
                        action_type=ActionType.CLICK,
                        locator=Locator(
                            type=LocatorType.CSS_SELECTOR,
                            value="button:contains('Search')"
                        ),
                        reasoning="Execute search query"
                    )
                ],
                expected_state={"results_displayed": True},
                error_handlers={
                    "member_not_found": "Return business outcome"
                }
            ),

            StepDefinition(
                step_id="step_4_view_details",
                description="Click member result",
                actions=[
                    Action(
                        action_type=ActionType.CLICK,
                        locator=Locator(
                            type=LocatorType.CSS_SELECTOR,
                            value="[data-testid='member-result']"
                        ),
                        reasoning="Open member account page"
                    )
                ],
                expected_state={"member_detail_page": True}
            ),

            StepDefinition(
                step_id="step_5_read_balance",
                description="Read savings balance",
                actions=[
                    Action(
                        action_type=ActionType.READ,
                        locator=Locator(
                            type=LocatorType.CSS_SELECTOR,
                            value="[data-account-type='savings'] .balance"
                        ),
                        reasoning="Extract savings balance"
                    )
                ],
                expected_state={"balance_visible": True},
                expected_outputs={"savings_balance": "string"}
            )
        ],

        allowed_domains=["localhost", "bank.local"],
        reversible=True,
        requires_confirmation=False,
        tags=["member-lookup", "savings", "demo"]
    )

    return artifact


async def run_discovery_demo(goal: str, app_url: str):
    """Demo: Run discovery and save artifact"""

    print("\n" + "="*70)
    print("COMPUTER-USE AUTOMATION DISCOVERY DEMO")
    print("="*70)
    print(f"\nGoal: {goal}")
    print(f"Target: {app_url}\n")

    # Initialize
    llm = DemoLLMClient()
    executor = DemoSurfaceExecutor()

    # Create artifact from discovery
    print("Step 1: Navigating to target application...")
    await executor.navigate(app_url)

    print("\nStep 2: Running agent loop (observe → decide → act)...\n")

    steps_taken = [
        "Step 1: Click Member Search button",
        "Step 2: Type member ID in search field",
        "Step 3: Click Search button",
        "Step 4: Click member result to view details",
        "Step 5: Read savings balance"
    ]

    for i, step_desc in enumerate(steps_taken, 1):
        print(f"  [{i}] {step_desc}")

    print("\nStep 3: Recording artifact from discovery run...\n")

    # Create artifact
    artifact = create_demo_artifact()

    # Save artifact
    artifacts_dir = Path("artifacts")
    artifacts_dir.mkdir(exist_ok=True)

    artifact_path = artifacts_dir / f"{artifact.artifact_id}.json"
    artifact_path.write_text(artifact.to_json())

    print(f"✓ Artifact saved: {artifact_path}\n")
    print("Artifact Details:")
    print(f"  ID: {artifact.artifact_id}")
    print(f"  Capability: {artifact.capability_name}")
    print(f"  Steps: {len(artifact.steps)}")
    print(f"  Input: {list(artifact.input_schema.keys())}")
    print(f"  Output: {list(artifact.output_schema.keys())}")

    print("\n" + "="*70)
    print("Discovery Complete!")
    print("="*70)
    print(f"\nTo replay this artifact:")
    print(f"  python replay_example.py --artifact-id {artifact.artifact_id} --member-id 67890")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Discover automation flow via LLM-driven agent loop"
    )
    parser.add_argument(
        "--goal",
        default="Look up member 12345 and read their savings balance",
        help="Natural language goal for automation"
    )
    parser.add_argument(
        "--app-url",
        default="http://localhost:8001",
        help="Target application URL"
    )

    args = parser.parse_args()

    asyncio.run(run_discovery_demo(args.goal, args.app_url))


if __name__ == "__main__":
    main()
