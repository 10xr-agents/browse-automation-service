#!/usr/bin/env python3
"""
Phase 2 Testing Summary Generator

Runs all Phase 2 tests and generates a summary report.
"""

import asyncio
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def run_pytest_tests():
	"""Run pytest tests and return results."""
	print("Running pytest tests...")
	result = subprocess.run(
		["uv", "run", "pytest", "tests/ci/knowledge/", "-v", "--tb=short"],
		capture_output=True,
		text=True,
	)
	
	# Parse results
	output = result.stdout + result.stderr
	passed = output.count("PASSED")
	failed = output.count("FAILED")
	errors = output.count("ERROR")
	total = passed + failed + errors
	
	return {
		"total": total,
		"passed": passed,
		"failed": failed,
		"errors": errors,
		"output": output,
		"exit_code": result.returncode,
	}


def run_manual_test():
	"""Run manual test script."""
	print("\nRunning manual test script...")
	result = subprocess.run(
		["uv", "run", "python", "scripts/test_phase2_manual.py"],
		capture_output=True,
		text=True,
	)
	
	return {
		"success": result.returncode == 0,
		"output": result.stdout + result.stderr,
		"exit_code": result.returncode,
	}


def main():
	"""Generate Phase 2 testing summary."""
	print("=" * 80)
	print("Phase 2 Testing Summary Generator")
	print("=" * 80)
	print(f"Timestamp: {datetime.now().isoformat()}\n")
	
	# Run pytest tests
	pytest_results = run_pytest_tests()
	
	# Run manual test
	manual_results = run_manual_test()
	
	# Generate summary
	print("\n" + "=" * 80)
	print("Testing Summary")
	print("=" * 80)
	
	print(f"\nPytest Tests:")
	print(f"  Total: {pytest_results['total']}")
	print(f"  Passed: {pytest_results['passed']}")
	print(f"  Failed: {pytest_results['failed']}")
	print(f"  Errors: {pytest_results['errors']}")
	print(f"  Success Rate: {(pytest_results['passed'] / pytest_results['total'] * 100) if pytest_results['total'] > 0 else 0:.1f}%")
	
	print(f"\nManual Test:")
	print(f"  Success: {manual_results['success']}")
	
	# Overall status
	overall_success = (
		pytest_results['exit_code'] == 0 and
		manual_results['success'] and
		pytest_results['failed'] == 0 and
		pytest_results['errors'] == 0
	)
	
	print(f"\nOverall Status: {'✓ SUCCESS' if overall_success else '✗ FAILED'}")
	print("=" * 80)
	
	# Save results
	results = {
		"timestamp": datetime.now().isoformat(),
		"pytest": pytest_results,
		"manual": manual_results,
		"overall_success": overall_success,
	}
	
	results_file = project_root / "phase2_test_results.json"
	with open(results_file, "w") as f:
		json.dump(results, f, indent=2)
	print(f"\nResults saved to: {results_file}")
	
	return 0 if overall_success else 1


if __name__ == "__main__":
	sys.exit(main())
