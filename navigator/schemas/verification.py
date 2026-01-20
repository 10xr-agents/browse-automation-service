"""
Verification Workflow Schemas

Pydantic models for Phase 7: Browser-Based Verification
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

# =============================================================================
# Verification Input/Output Schemas
# =============================================================================

@dataclass
class VerificationWorkflowInput:
	"""Input for verification workflow."""
	verification_job_id: str
	target_type: str  # "job", "screen", "task"
	target_id: str
	verification_options: dict[str, Any]


@dataclass
class VerificationWorkflowOutput:
	"""Output from verification workflow."""
	verification_job_id: str
	success: bool
	screens_verified: int
	actions_replayed: int
	discrepancies_found: int
	changes_made: int
	duration_seconds: float
	report_id: str


# =============================================================================
# Discrepancy Schemas
# =============================================================================

class DiscrepancySeverity(str, Enum):
	"""Severity levels for discrepancies."""
	CRITICAL = "critical"  # Action failed completely
	MAJOR = "major"  # Wrong outcome achieved
	MINOR = "minor"  # Small deviation
	INFO = "info"  # Informational only


class DiscrepancyType(str, Enum):
	"""Types of discrepancies."""
	ACTION_FAILED = "action_failed"
	WRONG_SCREEN = "wrong_screen"
	ELEMENT_NOT_FOUND = "element_not_found"
	SELECTOR_MISMATCH = "selector_mismatch"
	TIMING_ISSUE = "timing_issue"
	STATE_MISMATCH = "state_mismatch"


class Discrepancy(BaseModel):
	"""Discrepancy detected during verification."""
	discrepancy_id: str = Field(..., description="Unique discrepancy ID")
	verification_job_id: str = Field(..., description="Parent verification job")
	type: DiscrepancyType = Field(..., description="Discrepancy type")
	severity: DiscrepancySeverity = Field(..., description="Severity level")
	screen_id: str | None = Field(None, description="Screen where discrepancy occurred")
	action_id: str | None = Field(None, description="Action where discrepancy occurred")
	expected: dict[str, Any] = Field(default_factory=dict, description="Expected outcome")
	actual: dict[str, Any] = Field(default_factory=dict, description="Actual outcome")
	evidence: dict[str, Any] = Field(default_factory=dict, description="Evidence (screenshots, logs)")
	timestamp: datetime = Field(default_factory=datetime.utcnow, description="When detected")
	resolved: bool = Field(False, description="Whether resolved by enrichment")
	resolution: str | None = Field(None, description="How it was resolved")


# =============================================================================
# Enrichment Schemas
# =============================================================================

class EnrichmentType(str, Enum):
	"""Types of enrichments."""
	SELECTOR_FALLBACK = "selector_fallback"
	TIMING_ADJUSTMENT = "timing_adjustment"
	TRANSITION_CORRECTION = "transition_correction"
	ELEMENT_ADDITION = "element_addition"
	RELIABILITY_UPDATE = "reliability_update"


class Enrichment(BaseModel):
	"""Knowledge enrichment applied during verification."""
	enrichment_id: str = Field(..., description="Unique enrichment ID")
	verification_job_id: str = Field(..., description="Parent verification job")
	type: EnrichmentType = Field(..., description="Enrichment type")
	target_type: str = Field(..., description="What was enriched (screen/task/action)")
	target_id: str = Field(..., description="Target ID")
	changes: dict[str, Any] = Field(default_factory=dict, description="Changes made")
	rationale: str = Field(..., description="Why enrichment was applied")
	timestamp: datetime = Field(default_factory=datetime.utcnow, description="When applied")


# =============================================================================
# Verification Report Schema
# =============================================================================

class VerificationReport(BaseModel):
	"""Verification report generated after workflow completion."""
	report_id: str = Field(..., description="Unique report ID")
	verification_job_id: str = Field(..., description="Verification job ID")
	target_type: str = Field(..., description="What was verified")
	target_id: str = Field(..., description="Target ID")
	started_at: datetime = Field(..., description="Verification start time")
	completed_at: datetime = Field(..., description="Verification completion time")
	duration_seconds: float = Field(..., description="Total duration")
	success: bool = Field(..., description="Overall success")
	screens_verified: int = Field(0, description="Number of screens verified")
	actions_replayed: int = Field(0, description="Number of actions replayed")
	discrepancies: list[Discrepancy] = Field(default_factory=list, description="Discrepancies found")
	enrichments: list[Enrichment] = Field(default_factory=list, description="Enrichments applied")
	success_rate: float = Field(0.0, description="Percentage of successful replays")
	metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
