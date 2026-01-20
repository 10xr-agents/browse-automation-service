"""
Agent Communication API (Phase 3).

Provides schemas and services for general agents to communicate with browser-use agents.
"""

import logging
import re
from typing import Any

from pydantic import BaseModel, Field, field_validator

from navigator.knowledge.extract.browser_use_mapping import BrowserUseAction

logger = logging.getLogger(__name__)


# =============================================================================
# Agent Communication Schemas
# =============================================================================

class AgentInstruction(BaseModel):
	"""
	Instruction from general agent to browser-use agent.
	
	This schema represents a high-level instruction that needs to be
	translated into browser-use actions.
	"""
	instruction_type: str = Field(
		...,
		description="Instruction type: 'navigate_to_screen' | 'execute_task' | 'find_screen' | 'explore_website' | 'get_actions'"
	)
	target: str = Field(..., description="Screen ID, task ID, URL, or description")
	knowledge_id: str = Field(..., description="Knowledge ID to query")
	context: dict[str, Any] = Field(
		default_factory=dict,
		description="Additional context (current_url, current_screen_id, etc.)"
	)
	
	@field_validator('instruction_type')
	@classmethod
	def validate_instruction_type(cls, v: str) -> str:
		"""Validate instruction type."""
		valid_types = [
			'navigate_to_screen',
			'execute_task',
			'find_screen',
			'explore_website',
			'get_actions',
			'get_screen_context',
		]
		if v not in valid_types:
			raise ValueError(f"Invalid instruction_type: {v}. Must be one of {valid_types}")
		return v


class AgentResponse(BaseModel):
	"""
	Response from knowledge system to general agent.
	
	Contains browser-use actions ready for execution.
	"""
	success: bool = Field(..., description="Whether the query succeeded")
	actions: list[BrowserUseAction] = Field(
		default_factory=list,
		description="List of browser-use actions to execute"
	)
	expected_result: dict[str, Any] = Field(
		default_factory=dict,
		description="Expected result after executing actions (screen_id, verification criteria, etc.)"
	)
	error: str | None = Field(
		default=None,
		description="Error message if query failed"
	)
	metadata: dict[str, Any] = Field(
		default_factory=dict,
		description="Additional metadata (confidence, alternatives, etc.)"
	)


# =============================================================================
# Screen Recognition Service
# =============================================================================

class ScreenRecognitionService:
	"""
	Matches current browser state to known screens.
	
	Uses URL patterns and DOM indicators to identify which screen
	the browser is currently on.
	"""
	
	async def recognize_screen(
		self,
		current_url: str,
		dom_summary: str,
		knowledge_id: str
	) -> dict[str, Any]:
		"""
		Recognize which screen the browser is currently on.
		
		Args:
			current_url: Current browser URL
			dom_summary: DOM summary text from browser
			knowledge_id: Knowledge ID to query screens from
		
		Returns:
			Dict with:
			- screen_id: Matched screen ID (or None)
			- confidence: Confidence score (0-1)
			- matched_indicators: List of matched indicators
			- available_actions: Available actions on this screen
		"""
		try:
			from navigator.knowledge.persist.documents.screens import (
				query_screens_by_knowledge_id,
			)
			
			# Get all actionable screens for this knowledge
			screens = await query_screens_by_knowledge_id(
				knowledge_id,
				content_type="web_ui",
				actionable_only=True,
				limit=1000
			)
			
			if not screens:
				return {
					"screen_id": None,
					"confidence": 0.0,
					"message": "No actionable screens found for this knowledge"
				}
			
			best_match = None
			best_score = 0.0
			matched_indicators_list: list[dict[str, Any]] = []
			
			for screen in screens:
				score, matched = self._calculate_match_score(
					screen,
					current_url,
					dom_summary
				)
				
				if score > best_score:
					best_score = score
					best_match = screen
					matched_indicators_list = matched
			
			if best_match and best_score > 0.7:  # Confidence threshold
				# Get available actions for this screen
				available_actions = await self._get_available_actions(
					best_match.screen_id,
					knowledge_id
				)
				
				return {
					"screen_id": best_match.screen_id,
					"screen_name": best_match.name,
					"confidence": best_score,
					"matched_indicators": matched_indicators_list,
					"available_actions": available_actions
				}
			
			return {
				"screen_id": None,
				"confidence": best_score,
				"message": f"No matching screen found (best match: {best_score:.2f})",
				"best_candidate": best_match.screen_id if best_match else None
			}
		
		except Exception as e:
			logger.error(f"Failed to recognize screen: {e}", exc_info=True)
			return {
				"screen_id": None,
				"confidence": 0.0,
				"error": str(e)
			}
	
	def _calculate_match_score(
		self,
		screen: Any,  # ScreenDefinition
		current_url: str,
		dom_summary: str
	) -> tuple[float, list[dict[str, Any]]]:
		"""
		Calculate how well screen matches current state.
		
		Args:
			screen: Screen definition
			current_url: Current browser URL
			dom_summary: DOM summary text
		
		Returns:
			Tuple of (score, matched_indicators)
		"""
		score = 0.0
		matched_indicators: list[dict[str, Any]] = []
		
		# URL pattern matching (40% weight)
		url_match = False
		for pattern in screen.url_patterns:
			try:
				if re.match(pattern, current_url):
					url_match = True
					matched_indicators.append({
						"type": "url_matches",
						"pattern": pattern,
						"value": current_url
					})
					break
			except re.error:
				logger.warning(f"Invalid regex pattern: {pattern}")
				continue
		
		if url_match:
			score += 0.4
		
		# DOM indicator matching (60% weight)
		matched_count = 0
		total_indicators = len(screen.state_signature.required_indicators)
		
		if total_indicators > 0:
			dom_lower = dom_summary.lower()
			
			for indicator in screen.state_signature.required_indicators:
				matched = False
				
				if indicator.type == "dom_contains":
					if indicator.value and indicator.value.lower() in dom_lower:
						matched = True
						matched_indicators.append({
							"type": "dom_contains",
							"value": indicator.value,
							"selector": indicator.selector
						})
				
				elif indicator.type == "url_matches":
					if indicator.pattern:
						try:
							if re.match(indicator.pattern, current_url):
								matched = True
								matched_indicators.append({
									"type": "url_matches",
									"pattern": indicator.pattern
								})
						except re.error:
							pass
				
				elif indicator.type == "url_exact":
					if indicator.value and indicator.value == current_url:
						matched = True
						matched_indicators.append({
							"type": "url_exact",
							"value": indicator.value
						})
				
				if matched:
					matched_count += 1
			
			indicator_score = matched_count / total_indicators if total_indicators > 0 else 0.0
			score += indicator_score * 0.6
		
		return score, matched_indicators
	
	async def _get_available_actions(
		self,
		screen_id: str,
		knowledge_id: str
	) -> list[dict[str, Any]]:
		"""Get available actions for a screen."""
		try:
			from navigator.knowledge.persist.documents.actions import (
				query_actions_by_knowledge_id,
			)
			from navigator.knowledge.persist.documents.screens import get_screen
			
			# Get screen to find action_ids
			screen = await get_screen(screen_id)
			if not screen or not hasattr(screen, 'action_ids'):
				return []
			
			# Get all actions for this knowledge
			all_actions = await query_actions_by_knowledge_id(knowledge_id, limit=1000)
			
			# Filter to actions available on this screen
			screen_action_ids = set(screen.action_ids or [])
			available = [
				{
					"action_id": action.action_id,
					"action_type": action.action_type,
					"name": action.name,
					"target_selector": action.target_selector
				}
				for action in all_actions
				if action.action_id in screen_action_ids
			]
			
			return available
		
		except Exception as e:
			logger.error(f"Failed to get available actions: {e}")
			return []
