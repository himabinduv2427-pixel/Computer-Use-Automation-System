"""
Structured artifact schema for reusable automation capabilities.
Captures the flow from discovery run and enables deterministic replay.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional, Literal
from enum import Enum
import json
from datetime import datetime


class ActionType(Enum):
    """Supported automation actions"""
    CLICK = "click"
    TYPE = "type"
    NAVIGATE = "navigate"
    READ = "read"
    WAIT = "wait"
    SCROLL = "scroll"


class LocatorType(Enum):
    """How we identify elements for robust replay"""
    CSS_SELECTOR = "css_selector"
    XPATH = "xpath"
    ACCESSIBILITY = "accessibility"  # accessibility tree / ARIA label
    IMAGE = "image"  # screenshot-based coordinate
    TEST_ID = "test_id"  # data-testid attribute


@dataclass
class Locator:
    """Element identification strategy for deterministic replay"""
    type: LocatorType
    value: str
    # Robustness metadata
    fallbacks: List['Locator'] = field(default_factory=list)
    description: str = ""  # Why we chose this locator

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type.value,
            "value": self.value,
            "fallbacks": [f.to_dict() for f in self.fallbacks],
            "description": self.description
        }


@dataclass
class Action:
    """Atomic action in the automation flow"""
    action_type: ActionType
    locator: Optional[Locator] = None
    value: Optional[str] = None  # For TYPE actions
    wait_condition: Optional[str] = None  # For WAIT actions
    reasoning: str = ""  # Why we took this action

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_type": self.action_type.value,
            "locator": self.locator.to_dict() if self.locator else None,
            "value": self.value,
            "wait_condition": self.wait_condition,
            "reasoning": self.reasoning
        }


@dataclass
class StepDefinition:
    """One step in the automation flow with expected outcomes"""
    step_id: str
    description: str
    actions: List[Action]
    expected_state: Dict[str, Any]  # Checkpoint: what should be visible/true
    expected_outputs: Optional[Dict[str, Any]] = None  # Data to extract
    error_handlers: Dict[str, str] = field(default_factory=dict)  # Error type -> recovery action

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "description": self.description,
            "actions": [a.to_dict() for a in self.actions],
            "expected_state": self.expected_state,
            "expected_outputs": self.expected_outputs,
            "error_handlers": self.error_handlers
        }


@dataclass
class ArtifactSchema:
    """
    Reusable automation capability artifact.
    Captured from a successful discovery run, replayed deterministically.
    """
    # Metadata
    artifact_id: str
    capability_name: str
    capability_description: str
    goal: str  # Natural language goal this capability fulfills

    # Contract
    input_schema: Dict[str, Any]  # Typed inputs (e.g., {"member_id": str, "action": str})
    output_schema: Dict[str, Any]  # What caller gets back

    # The flow
    steps: List[StepDefinition] = field(default_factory=list)

    # Metadata
    version: str = "1.0.0"
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    tenant_id: str = ""
    tags: List[str] = field(default_factory=list)

    # Safety & scope
    allowed_domains: List[str] = field(default_factory=list)  # Where this can operate
    reversible: bool = True  # Can we undo this?
    requires_confirmation: bool = False  # Human approval needed?

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to JSON"""
        return {
            "artifact_id": self.artifact_id,
            "capability_name": self.capability_name,
            "capability_description": self.capability_description,
            "goal": self.goal,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "steps": [s.to_dict() for s in self.steps],
            "version": self.version,
            "created_at": self.created_at,
            "tenant_id": self.tenant_id,
            "tags": self.tags,
            "allowed_domains": self.allowed_domains,
            "reversible": self.reversible,
            "requires_confirmation": self.requires_confirmation
        }

    def to_json(self) -> str:
        """Export as JSON"""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ArtifactSchema':
        """Deserialize from dict"""
        steps = [
            StepDefinition(
                step_id=s["step_id"],
                description=s["description"],
                actions=[
                    Action(
                        action_type=ActionType(a["action_type"]),
                        locator=Locator(
                            type=LocatorType(a["locator"]["type"]),
                            value=a["locator"]["value"],
                            description=a["locator"].get("description", "")
                        ) if a.get("locator") else None,
                        value=a.get("value"),
                        wait_condition=a.get("wait_condition"),
                        reasoning=a.get("reasoning", "")
                    ) for a in s["actions"]
                ],
                expected_state=s["expected_state"],
                expected_outputs=s.get("expected_outputs"),
                error_handlers=s.get("error_handlers", {})
            ) for s in data.get("steps", [])
        ]

        return cls(
            artifact_id=data["artifact_id"],
            capability_name=data["capability_name"],
            capability_description=data["capability_description"],
            goal=data["goal"],
            input_schema=data["input_schema"],
            output_schema=data["output_schema"],
            steps=steps,
            version=data.get("version", "1.0.0"),
            created_at=data.get("created_at", ""),
            tenant_id=data.get("tenant_id", ""),
            tags=data.get("tags", []),
            allowed_domains=data.get("allowed_domains", []),
            reversible=data.get("reversible", True),
            requires_confirmation=data.get("requires_confirmation", False)
        )


# Example artifact: Look up member and read savings balance
EXAMPLE_MEMBER_LOOKUP_ARTIFACT = ArtifactSchema(
    artifact_id="art_member_lookup_001",
    capability_name="lookup_member_savings",
    capability_description="Search for a member by ID and read their current savings balance",
    goal="look up member 12345 and read their current savings balance",

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
            "description": "Whether member exists"
        },
        "member_name": {
            "type": "string",
            "description": "Member's name"
        },
        "savings_balance": {
            "type": "string",
            "description": "Current savings balance with currency"
        }
    },

    steps=[
        StepDefinition(
            step_id="step_1_navigate_home",
            description="Navigate to member search page",
            actions=[
                Action(
                    action_type=ActionType.NAVIGATE,
                    value="https://bank.local/dashboard",
                    reasoning="Start from dashboard to access member search"
                )
            ],
            expected_state={
                "page_title": "Dashboard",
                "elements_visible": ["member_search_button", "navigation_menu"]
            }
        ),

        StepDefinition(
            step_id="step_2_open_search",
            description="Click on Member Search",
            actions=[
                Action(
                    action_type=ActionType.CLICK,
                    locator=Locator(
                        type=LocatorType.ACCESSIBILITY,
                        value="Member Search",
                        fallbacks=[
                            Locator(LocatorType.CSS_SELECTOR, "button[data-testid='member-search']")
                        ],
                        description="Using accessibility label; fallback to test ID"
                    ),
                    reasoning="Click member search button to open lookup modal"
                )
            ],
            expected_state={
                "modal_open": True,
                "elements_visible": ["search_input_field", "search_button"]
            }
        ),

        StepDefinition(
            step_id="step_3_enter_member_id",
            description="Enter member ID in search field",
            actions=[
                Action(
                    action_type=ActionType.TYPE,
                    locator=Locator(
                        type=LocatorType.CSS_SELECTOR,
                        value="input[placeholder='Enter Member ID']",
                        fallbacks=[
                            Locator(LocatorType.XPATH, "//input[@data-testid='member-id-input']")
                        ],
                        description="Target search input field"
                    ),
                    value="{member_id}",  # Template variable
                    reasoning="Type member ID to search"
                )
            ],
            expected_state={
                "input_field_focused": True,
                "input_value": "{member_id}"
            }
        ),

        StepDefinition(
            step_id="step_4_search",
            description="Click Search button",
            actions=[
                Action(
                    action_type=ActionType.CLICK,
                    locator=Locator(
                        type=LocatorType.CSS_SELECTOR,
                        value="button:contains('Search')",
                        fallbacks=[
                            Locator(LocatorType.XPATH, "//button[text()='Search']")
                        ],
                        description="Search button"
                    ),
                    reasoning="Execute search query"
                ),
                Action(
                    action_type=ActionType.WAIT,
                    wait_condition="results_loaded",
                    reasoning="Wait for search results to load"
                )
            ],
            expected_state={
                "results_visible": True,
                "member_data_loaded": True
            },
            expected_outputs={
                "member_found": True,
                "member_name": "string"
            },
            error_handlers={
                "member_not_found": "Return false with error message",
                "search_timeout": "Retry search up to 2 times"
            }
        ),

        StepDefinition(
            step_id="step_5_view_account",
            description="Click on member result to view account details",
            actions=[
                Action(
                    action_type=ActionType.CLICK,
                    locator=Locator(
                        type=LocatorType.CSS_SELECTOR,
                        value="[data-testid='member-result-row']",
                        fallbacks=[
                            Locator(LocatorType.ACCESSIBILITY, "{member_name}")
                        ],
                        description="Member result row"
                    ),
                    reasoning="Open member account details"
                )
            ],
            expected_state={
                "account_detail_page_loaded": True,
                "elements_visible": ["account_summary", "balance_display"]
            }
        ),

        StepDefinition(
            step_id="step_6_read_savings",
            description="Extract savings balance from account page",
            actions=[
                Action(
                    action_type=ActionType.READ,
                    locator=Locator(
                        type=LocatorType.CSS_SELECTOR,
                        value="[data-account-type='savings'] .balance-amount",
                        fallbacks=[
                            Locator(LocatorType.XPATH, "//span[contains(@class, 'savings-balance')]")
                        ],
                        description="Savings account balance display"
                    ),
                    reasoning="Extract current savings balance for output"
                )
            ],
            expected_state={
                "balance_visible": True
            },
            expected_outputs={
                "savings_balance": "string"
            }
        )
    ],

    allowed_domains=["bank.local"],
    reversible=True,
    requires_confirmation=False,
    tags=["member-lookup", "read-only", "savings-account"]
)
