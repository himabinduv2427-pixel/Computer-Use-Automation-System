"""
Deterministic replay engine.
Re-executes saved artifacts without LLM, using stable element targeting.
Handles errors explicitly and reports success/failure clearly.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Callable, Tuple
from enum import Enum
import asyncio
from datetime import datetime
import json

from agent_artifact import ArtifactSchema, ActionType, LocatorType, StepDefinition, Action


class ReplayResultStatus(Enum):
    """Outcome of a replay execution"""
    SUCCESS = "success"
    BUSINESS_OUTCOME = "business_outcome"  # "member not found" - legit result, not crash
    RECOVERABLE_ERROR = "recoverable_error"  # Transient; could retry
    HARD_FAILURE = "hard_failure"  # Cannot proceed
    STUCK = "stuck"  # Human intervention needed


@dataclass
class ActionResult:
    """Result of executing a single action"""
    action_id: str
    action_type: ActionType
    status: str  # success, error, skipped
    error_message: Optional[str] = None
    output: Optional[Any] = None  # For READ actions
    screenshot: Optional[str] = None  # Base64 for evidence
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class StepResult:
    """Result of executing a step"""
    step_id: str
    status: str = "pending"  # success, error, skipped
    actions: List[ActionResult] = field(default_factory=list)
    expected_state_met: bool = False
    outputs: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None
    recovery_attempted: bool = False
    recovery_action: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class ReplayResult:
    """Complete replay execution report"""
    artifact_id: str
    run_id: str
    status: ReplayResultStatus
    steps: List[StepResult] = field(default_factory=list)
    final_outputs: Dict[str, Any] = field(default_factory=dict)
    error_summary: Optional[str] = None
    success_reason: Optional[str] = None
    business_outcome: Optional[str] = None  # "member not found", "permission denied", etc
    human_intervention_needed: bool = False
    intervention_reason: Optional[str] = None
    execution_time_ms: float = 0.0
    started_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "run_id": self.run_id,
            "status": self.status.value,
            "steps": [
                {
                    "step_id": s.step_id,
                    "status": s.status,
                    "actions": [
                        {
                            "action_id": a.action_id,
                            "action_type": a.action_type.value,
                            "status": a.status,
                            "error_message": a.error_message,
                            "output": a.output,
                            "timestamp": a.timestamp
                        } for a in s.actions
                    ],
                    "expected_state_met": s.expected_state_met,
                    "outputs": s.outputs,
                    "error_message": s.error_message,
                    "recovery_attempted": s.recovery_attempted,
                    "recovery_action": s.recovery_action,
                    "timestamp": s.timestamp
                } for s in self.steps
            ],
            "final_outputs": self.final_outputs,
            "error_summary": self.error_summary,
            "success_reason": self.success_reason,
            "business_outcome": self.business_outcome,
            "human_intervention_needed": self.human_intervention_needed,
            "intervention_reason": self.intervention_reason,
            "execution_time_ms": self.execution_time_ms,
            "started_at": self.started_at
        }


class ReplayEngine:
    """
    Executes automation artifacts deterministically.

    Key responsibilities:
    - Apply template variables (e.g., {member_id})
    - Execute actions with robust element targeting (fallback chain)
    - Verify checkpoints (expected_state)
    - Detect and handle errors explicitly
    - Distinguish business outcomes from failures
    - Provide detailed evidence/logging
    """

    def __init__(
        self,
        surface_executor: 'SurfaceExecutor',  # Pluggable interface to interact with app
        screenshot_provider: Callable[[], str],  # Returns base64 screenshot
        logger: Optional[Callable[[str], None]] = None
    ):
        """
        Args:
            surface_executor: Handles actual clicks, reads, etc. on the target surface
            screenshot_provider: Callable that returns base64-encoded screenshot
            logger: Optional logging function
        """
        self.surface_executor = surface_executor
        self.screenshot_provider = screenshot_provider
        self.logger = logger or print

    async def replay(
        self,
        artifact: ArtifactSchema,
        inputs: Dict[str, Any]
    ) -> ReplayResult:
        """
        Execute a saved artifact deterministically.

        Args:
            artifact: The saved automation capability
            inputs: Typed inputs matching artifact.input_schema

        Returns:
            Structured result with success/failure details
        """
        import uuid
        start_time = datetime.utcnow()
        run_id = str(uuid.uuid4())[:8]

        result = ReplayResult(
            artifact_id=artifact.artifact_id,
            run_id=run_id,
            status=ReplayResultStatus.SUCCESS
        )

        self.logger(f"[{run_id}] Starting replay of {artifact.artifact_id}")
        self.logger(f"[{run_id}] Inputs: {inputs}")

        try:
            # Validate inputs against schema
            self._validate_inputs(inputs, artifact.input_schema)

            # Execute each step
            for step in artifact.steps:
                step_result = await self._execute_step(step, inputs, artifact)
                result.steps.append(step_result)

                if step_result.status == "error":
                    # Try recovery if handlers defined
                    if not step_result.recovery_attempted and step.error_handlers:
                        self.logger(f"[{run_id}] Step {step.step_id} failed. Attempting recovery...")
                        # Recovery logic here (could retry, skip, escalate)
                        step_result.recovery_attempted = True
                        step_result.recovery_action = "retry"
                        # For now, re-execute step
                        step_result = await self._execute_step(step, inputs, artifact)
                        result.steps[-1] = step_result

                    if step_result.status == "error":
                        # Hard failure
                        result.status = ReplayResultStatus.HARD_FAILURE
                        result.error_summary = f"Step {step.step_id} failed: {step_result.error_message}"
                        result.human_intervention_needed = True
                        result.intervention_reason = f"Automation stuck at step {step.step_id}: {step_result.error_message}"
                        self.logger(f"[{run_id}] {result.error_summary}")
                        break

                # Collect outputs from this step
                if step_result.outputs:
                    result.final_outputs.update(step_result.outputs)

            # Determine final status
            if result.status == ReplayResultStatus.SUCCESS:
                # Check if all steps succeeded
                if all(s.status == "success" for s in result.steps):
                    result.success_reason = "All steps completed successfully"
                    self.logger(f"[{run_id}] Replay succeeded")
                else:
                    # Check for business outcome (not a crash)
                    if any("not_found" in s.error_message or "not exist" in s.error_message.lower()
                           for s in result.steps if s.error_message):
                        result.status = ReplayResultStatus.BUSINESS_OUTCOME
                        result.business_outcome = "Member not found"
                        self.logger(f"[{run_id}] Business outcome: {result.business_outcome}")
                    else:
                        result.status = ReplayResultStatus.HARD_FAILURE
                        self.logger(f"[{run_id}] Replay failed")

        except Exception as e:
            result.status = ReplayResultStatus.HARD_FAILURE
            result.error_summary = f"Replay execution error: {str(e)}"
            result.human_intervention_needed = True
            result.intervention_reason = str(e)
            self.logger(f"[{run_id}] Exception: {e}")

        # Calculate execution time
        result.execution_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

        return result

    async def _execute_step(
        self,
        step: StepDefinition,
        inputs: Dict[str, Any],
        artifact: ArtifactSchema
    ) -> StepResult:
        """Execute a single step"""
        result = StepResult(step_id=step.step_id, status="pending")

        self.logger(f"  Executing step: {step.step_id} - {step.description}")

        try:
            # Execute actions in sequence
            for i, action in enumerate(step.actions):
                action_id = f"{step.step_id}_action_{i}"
                action_result = await self._execute_action(action, inputs)
                action_result.action_id = action_id
                result.actions.append(action_result)

                if action_result.status == "error":
                    result.status = "error"
                    result.error_message = action_result.error_message
                    return result

            # Verify checkpoint (expected state)
            if step.expected_state:
                state_verified = await self._verify_state(step.expected_state)
                result.expected_state_met = state_verified

                if not state_verified:
                    result.status = "error"
                    result.error_message = f"Expected state not met: {step.expected_state}"
                    return result

            # Extract outputs if defined
            if step.expected_outputs:
                for output_key, output_spec in step.expected_outputs.items():
                    # This would use the last READ action's output
                    if result.actions and result.actions[-1].action_type == ActionType.READ:
                        result.outputs[output_key] = result.actions[-1].output

            result.status = "success"

        except Exception as e:
            result.status = "error"
            result.error_message = str(e)

        return result

    async def _execute_action(self, action: Action, inputs: Dict[str, Any]) -> ActionResult:
        """Execute a single action"""
        result = ActionResult(
            action_id="",
            action_type=action.action_type,
            status="pending"
        )

        try:
            # Apply template variables
            value = action.value
            if value and "{" in value:
                for key, val in inputs.items():
                    value = value.replace(f"{{{key}}}", str(val))

            if action.action_type == ActionType.CLICK:
                success = await self._find_and_click(action.locator, inputs)
                result.status = "success" if success else "error"
                if not success:
                    result.error_message = f"Failed to find and click element: {action.locator}"

            elif action.action_type == ActionType.TYPE:
                success = await self._find_and_type(action.locator, value, inputs)
                result.status = "success" if success else "error"
                if not success:
                    result.error_message = f"Failed to type in element: {action.locator}"

            elif action.action_type == ActionType.READ:
                text = await self._find_and_read(action.locator, inputs)
                if text is not None:
                    result.status = "success"
                    result.output = text
                else:
                    result.status = "error"
                    result.error_message = f"Failed to read element: {action.locator}"

            elif action.action_type == ActionType.NAVIGATE:
                success = await self.surface_executor.navigate(value)
                result.status = "success" if success else "error"
                if not success:
                    result.error_message = f"Failed to navigate to {value}"

            elif action.action_type == ActionType.WAIT:
                # Wait for condition
                await asyncio.sleep(2)  # Simple implementation
                result.status = "success"

            # Capture screenshot for evidence
            try:
                result.screenshot = self.screenshot_provider()
            except:
                pass

        except Exception as e:
            result.status = "error"
            result.error_message = str(e)

        return result

    async def _find_and_click(self, locator, inputs: Dict[str, Any]) -> bool:
        """Find element and click it, using fallback chain if needed"""
        if not locator:
            return False

        # Try primary locator
        found = await self.surface_executor.find_and_click(
            locator.type.value,
            locator.value
        )

        if found:
            return True

        # Try fallbacks
        for fallback in locator.fallbacks:
            found = await self.surface_executor.find_and_click(
                fallback.type.value,
                fallback.value
            )
            if found:
                self.logger(f"    Used fallback locator: {fallback.value}")
                return True

        return False

    async def _find_and_type(self, locator, value: str, inputs: Dict[str, Any]) -> bool:
        """Find element and type in it"""
        if not locator or not value:
            return False

        found = await self.surface_executor.find_and_type(
            locator.type.value,
            locator.value,
            value
        )

        if found:
            return True

        for fallback in locator.fallbacks:
            found = await self.surface_executor.find_and_type(
                fallback.type.value,
                fallback.value,
                value
            )
            if found:
                return True

        return False

    async def _find_and_read(self, locator, inputs: Dict[str, Any]) -> Optional[str]:
        """Find element and read its text"""
        if not locator:
            return None

        text = await self.surface_executor.find_and_read(
            locator.type.value,
            locator.value
        )

        if text:
            return text

        for fallback in locator.fallbacks:
            text = await self.surface_executor.find_and_read(
                fallback.type.value,
                fallback.value
            )
            if text:
                return text

        return None

    async def _verify_state(self, expected_state: Dict[str, Any]) -> bool:
        """Verify that expected state is met"""
        # This would use the surface executor to check visibility, values, etc.
        # For now, simplified implementation
        return await self.surface_executor.verify_state(expected_state)

    def _validate_inputs(self, inputs: Dict[str, Any], schema: Dict[str, Any]):
        """Validate inputs match schema"""
        for key, spec in schema.items():
            if spec.get("required", False) and key not in inputs:
                raise ValueError(f"Missing required input: {key}")


class SurfaceExecutor:
    """
    Abstract interface for interacting with the target surface.
    Implementations handle web browsers, desktop apps, etc.
    """

    async def navigate(self, url: str) -> bool:
        """Navigate to URL"""
        raise NotImplementedError

    async def find_and_click(self, locator_type: str, locator_value: str) -> bool:
        """Find element and click"""
        raise NotImplementedError

    async def find_and_type(self, locator_type: str, locator_value: str, text: str) -> bool:
        """Find element and type text"""
        raise NotImplementedError

    async def find_and_read(self, locator_type: str, locator_value: str) -> Optional[str]:
        """Find element and read its text"""
        raise NotImplementedError

    async def verify_state(self, expected_state: Dict[str, Any]) -> bool:
        """Verify expected state is met"""
        raise NotImplementedError