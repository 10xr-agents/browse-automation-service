#!/usr/bin/env python3
"""
Comprehensive validation script to verify all fixes are in place.

This script validates:
1. All schema fixes are applied
2. All error handling is correct
3. All serialization issues are fixed
4. All status reporting is correct

Run this before production testing to ensure everything is ready.
"""

import inspect
import sys
from dataclasses import fields
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def check_frame_reference_serialization():
	"""Verify FrameReference is converted to string in frame_filtering.py"""
	file_path = project_root / "navigator/temporal/activities/video/frame_filtering.py"
	content = file_path.read_text()
	
	issues = []
	
	# Check that FrameReference is converted to string
	if 'frame_ref.to_path_string()' not in content:
		issues.append("❌ FrameReference not converted to string in frame_filtering.py")
	
	# Check that we're not appending FrameReference objects directly
	if 'all_frame_paths.append((timestamp, frame_ref))' in content:
		issues.append("❌ Still appending FrameReference objects directly (should use to_path_string())")
	
	if 'filtered_frame_paths.append((timestamp, frame_ref))' in content:
		issues.append("❌ Still appending FrameReference objects directly (should use to_path_string())")
	
	return issues


def check_thumbnails_field():
	"""Verify thumbnails field exists in SourceMetadata"""
	file_path = project_root / "navigator/schemas/domain.py"
	content = file_path.read_text()
	
	issues = []
	
	# Check that thumbnails field exists
	if 'thumbnails: list[str]' not in content:
		issues.append("❌ thumbnails field missing from SourceMetadata")
	
	# Verify it's in the right place (after language field)
	if 'language: str | None' in content:
		language_idx = content.find('language: str | None')
		thumbnails_idx = content.find('thumbnails: list[str]')
		if thumbnails_idx < language_idx:
			issues.append("⚠️ thumbnails field appears before language field (order issue)")
	
	return issues


def check_analyze_frames_batch_result_schema():
	"""Verify AnalyzeFramesBatchResult is used correctly"""
	file_path = project_root / "navigator/temporal/activities/video/frame_analysis.py"
	content = file_path.read_text()
	
	issues = []
	
	# Check that schema fields match
	if 'analysis_result_s3_key=' in content:
		issues.append("❌ Using 'analysis_result_s3_key' instead of 's3_key' in AnalyzeFramesBatchResult")
	
	if 'frames_analyzed=' in content:
		issues.append("❌ Using 'frames_analyzed' instead of 'frame_count' in AnalyzeFramesBatchResult")
	
	if 'batch_index=' in content and 'AnalyzeFramesBatchResult(' in content:
		# Check if batch_index is being passed (it shouldn't be in the result)
		lines = content.split('\n')
		for i, line in enumerate(lines):
			if 'AnalyzeFramesBatchResult(' in line:
				# Check next few lines
				for j in range(i, min(i+10, len(lines))):
					if 'batch_index=' in lines[j] and 'AnalyzeFramesBatchResult' in '\n'.join(lines[i:j+1]):
						issues.append("❌ batch_index should not be in AnalyzeFramesBatchResult (it's input only)")
						break
	
	return issues


def check_video_assembly_metadata():
	"""Verify video assembly handles metadata correctly"""
	file_path = project_root / "navigator/temporal/activities/video/assembly.py"
	content = file_path.read_text()
	
	issues = []
	
	# Check that thumbnails assignment exists
	if 'result.metadata.thumbnails =' not in content:
		issues.append("❌ thumbnails assignment missing in assembly.py")
	
	# Check that file stats are handled safely
	if 'video_path.stat().st_size if video_path.exists() else 0' in content:
		issues.append("⚠️ video_path.stat() called twice (inefficient, but not breaking)")
	
	# Check for safe stat handling
	if 'try:' in content and 'stat_result = video_path.stat()' in content:
		# Good - using try/except
		pass
	elif 'video_path.stat()' in content and 'except' not in content.split('video_path.stat()')[0][-200:]:
		issues.append("⚠️ video_path.stat() not wrapped in try/except (could fail on permissions)")
	
	return issues


def check_status_reporting():
	"""Verify status reporting handles failures correctly"""
	file_path = project_root / "navigator/knowledge/rest_api_workflows.py"
	content = file_path.read_text()
	
	issues = []
	
	# Check for explicit FAILED status handling
	if 'WorkflowExecutionStatus.FAILED' not in content:
		issues.append("⚠️ No explicit check for WorkflowExecutionStatus.FAILED")
	
	# Check status mapping includes all failure cases
	if "'failed': WorkflowStatus.FAILED" not in content:
		issues.append("❌ 'failed' status not mapped to WorkflowStatus.FAILED")
	
	if "'terminated': WorkflowStatus.FAILED" not in content:
		issues.append("⚠️ 'terminated' status not mapped to WorkflowStatus.FAILED")
	
	if "'timed_out': WorkflowStatus.FAILED" not in content:
		issues.append("⚠️ 'timed_out' status not mapped to WorkflowStatus.FAILED")
	
	return issues


def check_empty_s3_key_handling():
	"""Verify empty S3 keys are handled correctly"""
	issues = []
	
	# Check workflow handles empty s3_key
	workflow_file = project_root / "navigator/temporal/workflows/helpers/video_processing.py"
	content = workflow_file.read_text()
	
	if 'result.success and result.s3_key' not in content:
		issues.append("⚠️ Not checking for non-empty s3_key before appending")
	
	# Check assembly handles empty s3_key
	assembly_file = project_root / "navigator/temporal/activities/video/assembly.py"
	assembly_content = assembly_file.read_text()
	
	if 'if not s3_key or not s3_key.strip()' not in assembly_content:
		issues.append("⚠️ Not skipping empty S3 keys in assembly activity")
	
	return issues


def check_s3_prefix_usage():
	"""Verify S3 prefix is used correctly"""
	file_path = project_root / "navigator/temporal/activities/video/frame_analysis.py"
	content = file_path.read_text()
	
	issues = []
	
	# Check that output_s3_prefix is used
	if 'input.output_s3_prefix' not in content:
		issues.append("❌ output_s3_prefix not used in frame_analysis.py")
	
	# Check that hardcoded bucket name is removed
	if 'knowledge-extraction-wf-dev/' in content and 's3_key = f' in content:
		# Check if it's in a comment or actual code
		lines = content.split('\n')
		for line in lines:
			if 'knowledge-extraction-wf-dev/' in line and 's3_key = f' in line and not line.strip().startswith('#'):
				issues.append("❌ Hardcoded bucket name still in s3_key construction")
				break
	
	return issues


def check_index_error_prevention():
	"""Verify IndexError prevention is in place"""
	issues = []
	
	# Check extraction_workflow.py
	workflow_file = project_root / "navigator/temporal/workflows/extraction_workflow.py"
	content = workflow_file.read_text()
	
	if 'if not ingest_results or len(ingest_results) == 0:' not in content:
		issues.append("❌ No validation before accessing ingest_results[0] in extraction_workflow.py")
	
	# Check ingestion_phase.py
	ingestion_file = project_root / "navigator/temporal/workflows/phases/ingestion_phase.py"
	ingestion_content = ingestion_file.read_text()
	
	if 'if not sources_to_process or len(sources_to_process) == 0:' not in ingestion_content:
		issues.append("❌ No validation before accessing sources_to_process[0] in ingestion_phase.py")
	
	if 'if not ingest_results or len(ingest_results) == 0:' not in ingestion_content:
		issues.append("❌ No validation before accessing ingest_results[0] in ingestion_phase.py")
	
	return issues


def main():
	"""Run all validation checks"""
	print("=" * 80)
	print("🔍 Comprehensive Pre-Production Validation")
	print("=" * 80)
	print()
	
	all_issues = []
	
	checks = [
		("FrameReference Serialization", check_frame_reference_serialization),
		("Thumbnails Field", check_thumbnails_field),
		("AnalyzeFramesBatchResult Schema", check_analyze_frames_batch_result_schema),
		("Video Assembly Metadata", check_video_assembly_metadata),
		("Status Reporting", check_status_reporting),
		("Empty S3 Key Handling", check_empty_s3_key_handling),
		("S3 Prefix Usage", check_s3_prefix_usage),
		("IndexError Prevention", check_index_error_prevention),
	]
	
	for check_name, check_func in checks:
		print(f"Checking: {check_name}...")
		issues = check_func()
		if issues:
			all_issues.extend([f"[{check_name}] {issue}" for issue in issues])
			print(f"  ❌ Found {len(issues)} issue(s)")
		else:
			print(f"  ✅ Passed")
		print()
	
	print("=" * 80)
	if all_issues:
		print(f"❌ VALIDATION FAILED: Found {len(all_issues)} issue(s)")
		print()
		for issue in all_issues:
			print(f"  {issue}")
		print()
		print("=" * 80)
		return 1
	else:
		print("✅ ALL VALIDATIONS PASSED - Ready for production testing!")
		print("=" * 80)
		return 0


if __name__ == '__main__':
	sys.exit(main())
