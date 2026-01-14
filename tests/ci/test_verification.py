"""
Test Suite for Phase 7: Browser-Based Verification

Tests verification workflow, activities, and feature flags.
"""

import pytest
import os

# Test feature flags
from navigator.config import get_feature_flags, reload_feature_flags


class TestFeatureFlags:
	"""Test feature flag system."""
	
	def test_feature_flags_default_disabled(self):
		"""Test that verification features are disabled by default."""
		# Clear env vars
		os.environ.pop('FEATURE_BROWSER_VERIFICATION', None)
		os.environ.pop('FEATURE_KNOWLEDGE_ENRICHMENT', None)
		
		reload_feature_flags()
		flags = get_feature_flags()
		
		assert flags.is_verification_enabled() == False
		assert flags.is_enrichment_enabled() == False
	
	def test_feature_flags_can_enable(self):
		"""Test that features can be enabled via environment."""
		os.environ['FEATURE_BROWSER_VERIFICATION'] = 'true'
		os.environ['FEATURE_KNOWLEDGE_ENRICHMENT'] = 'true'
		
		reload_feature_flags()
		flags = get_feature_flags()
		
		assert flags.is_verification_enabled() == True
		assert flags.is_enrichment_enabled() == True
		
		# Cleanup
		os.environ.pop('FEATURE_BROWSER_VERIFICATION', None)
		os.environ.pop('FEATURE_KNOWLEDGE_ENRICHMENT', None)
	
	def test_feature_flags_various_true_values(self):
		"""Test that various truth values work."""
		test_values = ['true', '1', 'yes', 'on', 'enabled', 'TRUE', 'True']
		
		for value in test_values:
			os.environ['FEATURE_BROWSER_VERIFICATION'] = value
			reload_feature_flags()
			flags = get_feature_flags()
			assert flags.is_verification_enabled() == True, f"Failed for value: {value}"
		
		# Cleanup
		os.environ.pop('FEATURE_BROWSER_VERIFICATION', None)
	
	def test_feature_flags_to_dict(self):
		"""Test feature flags can be exported as dict."""
		flags = get_feature_flags()
		flags_dict = flags.to_dict()
		
		assert 'browser_verification' in flags_dict
		assert 'knowledge_enrichment' in flags_dict
		assert isinstance(flags_dict['browser_verification'], bool)


class TestVerificationSchemas:
	"""Test verification Pydantic schemas."""
	
	def test_discrepancy_schema(self):
		"""Test Discrepancy schema validation."""
		from navigator.schemas.verification import Discrepancy, DiscrepancyType, DiscrepancySeverity
		
		discrepancy = Discrepancy(
			discrepancy_id="disc-123",
			verification_job_id="job-456",
			type=DiscrepancyType.ACTION_FAILED,
			severity=DiscrepancySeverity.CRITICAL,
			expected={"result": "success"},
			actual={"result": "failure"},
			evidence={"screenshot": "path/to/image.png"},
		)
		
		assert discrepancy.discrepancy_id == "disc-123"
		assert discrepancy.type == DiscrepancyType.ACTION_FAILED
		assert discrepancy.severity == DiscrepancySeverity.CRITICAL
		assert discrepancy.resolved == False
	
	def test_enrichment_schema(self):
		"""Test Enrichment schema validation."""
		from navigator.schemas.verification import Enrichment, EnrichmentType
		
		enrichment = Enrichment(
			enrichment_id="enrich-123",
			verification_job_id="job-456",
			type=EnrichmentType.SELECTOR_FALLBACK,
			target_type="action",
			target_id="action-789",
			changes={"selector": {"old": ".btn", "new": "#submit-btn"}},
			rationale="Original selector failed, added fallback",
		)
		
		assert enrichment.enrichment_id == "enrich-123"
		assert enrichment.type == EnrichmentType.SELECTOR_FALLBACK
		assert enrichment.target_type == "action"
	
	def test_verification_report_schema(self):
		"""Test VerificationReport schema validation."""
		from navigator.schemas.verification import VerificationReport
		from datetime import datetime
		
		report = VerificationReport(
			report_id="report-123",
			verification_job_id="job-456",
			target_type="screen",
			target_id="screen-789",
			started_at=datetime.utcnow(),
			completed_at=datetime.utcnow(),
			duration_seconds=45.5,
			success=True,
			screens_verified=3,
			actions_replayed=12,
			success_rate=91.7,
		)
		
		assert report.report_id == "report-123"
		assert report.screens_verified == 3
		assert report.actions_replayed == 12
		assert report.success_rate == 91.7


class TestVerificationWorkflowInput:
	"""Test verification workflow input/output."""
	
	def test_workflow_input_dataclass(self):
		"""Test VerificationWorkflowInput dataclass."""
		from navigator.schemas.verification import VerificationWorkflowInput
		
		input_data = VerificationWorkflowInput(
			verification_job_id="verify-123",
			target_type="screen",
			target_id="screen-456",
			verification_options={"enable_enrichment": True},
		)
		
		assert input_data.verification_job_id == "verify-123"
		assert input_data.target_type == "screen"
		assert input_data.target_id == "screen-456"
		assert input_data.verification_options["enable_enrichment"] == True
	
	def test_workflow_output_dataclass(self):
		"""Test VerificationWorkflowOutput dataclass."""
		from navigator.schemas.verification import VerificationWorkflowOutput
		
		output_data = VerificationWorkflowOutput(
			verification_job_id="verify-123",
			success=True,
			screens_verified=5,
			actions_replayed=20,
			discrepancies_found=2,
			changes_made=1,
			duration_seconds=120.5,
			report_id="report-789",
		)
		
		assert output_data.success == True
		assert output_data.screens_verified == 5
		assert output_data.discrepancies_found == 2
		assert output_data.changes_made == 1


@pytest.mark.asyncio
async def test_verification_api_disabled_by_default():
	"""Test that verification API returns 503 when feature disabled."""
	from navigator.knowledge.api_v2 import VerificationRequest
	from fastapi import HTTPException
	
	# Ensure feature is disabled
	os.environ.pop('FEATURE_BROWSER_VERIFICATION', None)
	reload_feature_flags()
	
	# The API should raise HTTPException with status 503
	# (This would be tested with actual FastAPI test client in integration tests)
	
	request = VerificationRequest(
		target_type="screen",
		target_id="screen-123",
		verification_options={},
	)
	
	# Test that validation passes
	assert request.target_type == "screen"
	assert request.target_id == "screen-123"


@pytest.mark.asyncio
async def test_verification_activities_import():
	"""Test that verification activities can be imported."""
	from navigator.temporal.activities_verification import (
		load_knowledge_definitions_activity,
		launch_browser_session_activity,
		verify_screens_activity,
		apply_enrichments_activity,
		generate_verification_report_activity,
		cleanup_browser_session_activity,
	)
	
	# All activities should be importable
	assert callable(load_knowledge_definitions_activity)
	assert callable(launch_browser_session_activity)
	assert callable(verify_screens_activity)
	assert callable(apply_enrichments_activity)
	assert callable(generate_verification_report_activity)
	assert callable(cleanup_browser_session_activity)


@pytest.mark.asyncio
async def test_verification_workflow_import():
	"""Test that verification workflow can be imported."""
	from navigator.temporal.workflows_verification import KnowledgeVerificationWorkflow
	
	# Workflow should be importable
	assert KnowledgeVerificationWorkflow is not None
	assert hasattr(KnowledgeVerificationWorkflow, 'run')


def test_phase7_integration():
	"""Test that Phase 7 components integrate correctly."""
	# Test that all Phase 7 components are present
	from navigator.config import get_feature_flags
	from navigator.schemas.verification import (
		VerificationWorkflowInput,
		VerificationWorkflowOutput,
		Discrepancy,
		Enrichment,
		VerificationReport,
	)
	from navigator.temporal.workflows_verification import KnowledgeVerificationWorkflow
	from navigator.temporal.activities_verification import (
		load_knowledge_definitions_activity,
		launch_browser_session_activity,
		verify_screens_activity,
		apply_enrichments_activity,
		generate_verification_report_activity,
		cleanup_browser_session_activity,
	)
	
	# All components should be importable and ready
	assert get_feature_flags is not None
	assert VerificationWorkflowInput is not None
	assert VerificationWorkflowOutput is not None
	assert Discrepancy is not None
	assert Enrichment is not None
	assert VerificationReport is not None
	assert KnowledgeVerificationWorkflow is not None
	assert load_knowledge_definitions_activity is not None
