"""
LLM-driven agent loop for discovery.
Takes a natural language goal and learns a reusable artifact.
"""

import asyncio
import uuid
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime

from agent_artifact import (
    ArtifactSchema, StepDefinition, Action, Locator, ActionType, LocatorType
)


@dataclass
class DiscoveryContext:
    """Context maintained during discovery run"""
    goal: str
    app_url: str
    current_url: str = ""
    current_screenshot: str = ""
    steps_taken: List[str] = field(default_factory=list)
    discovered_elements: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    outputs_collected: Dict[str, Any] = field(default_factory=dict)


class AgentLoop:
    """
    LLM-driven observe → decide → act loop for automation discovery.

    Workflow:
    1. Observe: Take screenshot, analyze state
    2. Decide: Ask LLM "what action should we take next?"
    3. Act: Execute action, capture evidence
    4. Repeat until goal met
    5. Record as reusable artifact
    """

    def __init__(
        self,
        llm_client,  # LLM with vision (Claude, GPT-4, Gemini, etc)
        surface_executor,  # Browser/app interaction
        screenshot_provider,
        logger=None
    ):
        self.llm = llm_client
        self.surface_executor = surface_executor
        self.screenshot_provider = screenshot_provider
        self.logger = logger or print

    async def discover(
        self,
        goal: str,
        app_url: str,
        max_steps: int = 20,
        tenant_id: str = ""
    ) -> ArtifactSchema:
        """
        Run discovery loop: observe → decide → act until goal is met.

        Returns:
            Captured artifact with reusable automation capability
        """
        run_id = str(uuid.uuid4())[:8]
        context = DiscoveryContext(goal=goal, app_url=app_url)

        self.logger(f"\n[{run_id}] Starting discovery for goal: {goal}")
        self.logger(f"[{run_id}] Target app: {app_url}\n")

        # Step 0: Navigate to app
        await self.surface_executor.navigate(app_url)
        context.current_url = app_url

        step_count = 0
        artifact_steps = []

        while step_count < max_steps:
            step_count += 1

            # OBSERVE: Take screenshot
            try:
                context.current_screenshot = self.screenshot_provider()
            except Exception as e:
                self.logger(f"  [ERROR] Failed to capture screenshot: {e}")
                break

            # DECIDE: Ask LLM what to do
            decision = await self._ask_llm_for_next_action(context)

            if decision.is_complete:
                self.logger(f"\n[{run_id}] Goal achieved!")
                self.logger(f"[{run_id}] Steps taken: {step_count}")
                break

            if decision.action_type == "skip" or not decision.action_type:
                self.logger(f"  Step {step_count}: Agent decided to stop (uncertain)")
                break

            # ACT: Execute action
            self.logger(f"  Step {step_count}: {decision.action_type}")
            if decision.reasoning:
                self.logger(f"           Reasoning: {decision.reasoning}")

            action = Action(
                action_type=ActionType[decision.action_type.upper()],
                locator=decision.locator,
                value=decision.value,
                reasoning=decision.reasoning
            )

            success = await self._execute_action(action, context)

            if success:
                context.steps_taken.append(f"Step {step_count}: {decision.action_type}")
                artifact_steps.append(
                    StepDefinition(
                        step_id=f"step_{step_count}",
                        description=decision.action_description or f"{decision.action_type}",
                        actions=[action],
                        expected_state={
                            "step": step_count,
                            "action": decision.action_type
                        }
                    )
                )
            else:
                self.logger(f"    [ERROR] Action failed")

        # Record artifact
        self.logger(f"\n[{run_id}] Recording artifact from {step_count} steps...")

        artifact = ArtifactSchema(
            artifact_id=f"art_{run_id}",
            capability_name=f"auto_capability_{run_id}",
            capability_description=f"Learned automation: {goal}",
            goal=goal,
            input_schema={"user_input": {"type": "string"}},
            output_schema={"result": {"type": "string"}},
            steps=artifact_steps,
            version="1.0.0",
            tenant_id=tenant_id,
            tags=["auto-discovered"]
        )

        self.logger(f"[{run_id}] Artifact created: {artifact.artifact_id}")
        self.logger(f"[{run_id}] Capability: {artifact.capability_name}")

        return artifact

    async def _ask_llm_for_next_action(self, context: DiscoveryContext) -> 'ActionDecision':
        """Ask LLM what action to take next"""

        prompt = f"""
You are an expert automation engineer. Your job is to analyze the current state of a banking application
and decide what action to take to accomplish this goal:

GOAL: {context.goal}

Current state: Screenshot attached below.

Respond with ONLY valid JSON (no markdown, no extra text):
{{
  "analysis": "What you see in the screenshot and current state",
  "next_action": "CLICK|TYPE|NAVIGATE|READ|WAIT|SCROLL|NONE",
  "description": "Brief description of what we're trying to accomplish with this action",
  "element_description": "Which element/area to interact with",
  "value": "Value to type or URL to navigate to (or null)",
  "reasoning": "Why this action gets us closer to the goal",
  "is_complete": false,
  "confidence": 0.0-1.0
}}

If the goal is already accomplished, set is_complete to true.
If you're unsure what to do, respond with next_action: "SKIP" and explain why.
"""

        # Call LLM with screenshot
        response_text = await self.llm.analyze_with_vision(
            prompt,
            context.current_screenshot
        )

        # Parse response
        import json
        import re

        try:
            decision_data = json.loads(response_text)
        except json.JSONDecodeError:
            # Try to extract JSON from response
            match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if match:
                decision_data = json.loads(match.group())
            else:
                decision_data = {
                    "next_action": "SKIP",
                    "is_complete": False,
                    "reasoning": "Failed to parse LLM response"
                }

        return ActionDecision.from_dict(decision_data)

    async def _execute_action(self, action: Action, context: DiscoveryContext) -> bool:
        """Execute an action on the surface"""
        try:
            if action.action_type == ActionType.CLICK:
                # Simple demo: would use actual locator in production
                return await self.surface_executor.find_and_click(
                    action.locator.type.value if action.locator else "css",
                    "button"  # Placeholder
                )

            elif action.action_type == ActionType.TYPE:
                return await self.surface_executor.find_and_type(
                    action.locator.type.value if action.locator else "css",
                    "input",
                    action.value or ""
                )

            elif action.action_type == ActionType.NAVIGATE:
                return await self.surface_executor.navigate(action.value or "")

            elif action.action_type == ActionType.READ:
                text = await self.surface_executor.find_and_read(
                    action.locator.type.value if action.locator else "css",
                    "div"
                )
                if text:
                    context.outputs_collected["result"] = text
                    return True
                return False

            elif action.action_type == ActionType.WAIT:
                await asyncio.sleep(2)
                return True

            return True

        except Exception as e:
            self.logger(f"    [ERROR] {str(e)}")
            return False


@dataclass
class ActionDecision:
    """What the LLM decided to do"""
    action_type: str
    action_description: str
    element_description: str
    value: Optional[str]
    reasoning: str
    is_complete: bool
    confidence: float
    locator: Optional[Locator] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ActionDecision':
        return cls(
            action_type=data.get("next_action", "SKIP").upper(),
            action_description=data.get("description", ""),
            element_description=data.get("element_description", ""),
            value=data.get("value"),
            reasoning=data.get("reasoning", ""),
            is_complete=data.get("is_complete", False),
            confidence=data.get("confidence", 0.5),
            locator=None  # Would be parsed from data if present
        )
