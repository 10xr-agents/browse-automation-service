"""
LLM-Based Action Extrapolation (Phase 5).

Uses Gemini LLM to infer missing screen actions and transitions between known actions.
"""

import json
import logging
import os
import re
from typing import Any

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


# =============================================================================
# Extrapolation Schemas
# =============================================================================

class ActionGap(BaseModel):
	"""Represents a gap between two known actions."""
	from_action_id: str = Field(..., description="Starting action ID")
	to_action_id: str = Field(..., description="Ending action ID")
	from_screen_id: str | None = Field(None, description="Starting screen ID")
	to_screen_id: str | None = Field(None, description="Ending screen ID")
	context: dict[str, Any] = Field(
		default_factory=dict,
		description="Additional context"
	)


class ExtrapolationRequest(BaseModel):
	"""Request for LLM-based action extrapolation."""
	gaps: list[ActionGap] = Field(..., description="List of action gaps to fill")
	knowledge_id: str = Field(..., description="Knowledge ID for context")
	website_id: str = Field(..., description="Website ID for context")
	include_screens: bool = Field(
		default=True,
		description="Whether to infer screen transitions"
	)
	max_intermediate_steps: int = Field(
		default=5,
		ge=1,
		le=10,
		description="Maximum intermediate steps to infer"
	)


class InferredAction(BaseModel):
	"""An action inferred by LLM."""
	action_type: str = Field(..., description="Action type (click, type, navigate, etc.)")
	target: str = Field(..., description="Target element or URL")
	description: str = Field(..., description="Human-readable description")
	confidence: float = Field(
		...,
		ge=0.0,
		le=1.0,
		description="Confidence score (0-1)"
	)
	reasoning: str = Field(..., description="LLM reasoning for this action")
	screen_id: str | None = Field(
		None,
		description="Screen ID where this action occurs"
	)


class ExtrapolationResult(BaseModel):
	"""Result of action extrapolation."""
	gaps_filled: int = Field(..., description="Number of gaps successfully filled")
	inferred_actions: list[InferredAction] = Field(
		...,
		description="Inferred actions"
	)
	inferred_transitions: list[dict[str, Any]] = Field(
		default_factory=list,
		description="Inferred screen transitions"
	)
	confidence_scores: dict[str, float] = Field(
		default_factory=dict,
		description="Confidence scores per gap"
	)
	errors: list[str] = Field(
		default_factory=list,
		description="Extrapolation errors"
	)


# =============================================================================
# Action Extrapolation Service
# =============================================================================

class ActionExtrapolationService:
	"""
	Uses Gemini LLM to infer missing actions and transitions.
	
	When we have knowledge about two actions (e.g., "Action A" and "Action C"),
	this service infers what intermediate actions or screen transitions occurred
	between them based on:
	- Known start and end actions
	- Screen context
	- Website structure
	- Common UI patterns
	"""
	
	def __init__(self):
		"""Initialize extrapolation service."""
		self._client_cache: dict[str, Any] = {}
	
	def _get_gemini_client(self) -> Any:
		"""Get or create cached Gemini client."""
		google_key = os.getenv('GOOGLE_API_KEY')
		if not google_key:
			raise ValueError("GOOGLE_API_KEY environment variable not set")
		
		if google_key not in self._client_cache:
			from google import genai
			self._client_cache[google_key] = genai.Client(api_key=google_key)
		
		return self._client_cache[google_key]
	
	async def extrapolate_actions(
		self,
		request: ExtrapolationRequest
	) -> ExtrapolationResult:
		"""
		Infer missing actions between known actions.
		
		Example scenario:
		- Known: Action A (click "Login") on Screen 1
		- Known: Action C (type "username") on Screen 2
		- Missing: What happened between A and C?
		- Inferred: Action B (navigate to login page, wait for page load)
		
		Args:
			request: Extrapolation request with gaps to fill
		
		Returns:
			ExtrapolationResult with inferred actions and transitions
		"""
		result = ExtrapolationResult(gaps_filled=0, inferred_actions=[])
		
		# Get Gemini client
		try:
			client = self._get_gemini_client()
		except ValueError as e:
			result.errors.append(f"Failed to initialize Gemini client: {str(e)}")
			return result
		
		# Get context for each gap
		for gap in request.gaps:
			try:
				# Get known actions
				from navigator.knowledge.persist.documents.actions import get_action
				from navigator.knowledge.persist.documents.screens import get_screen
				from navigator.knowledge.persist.documents.screens import (
					query_screens_by_website,
				)
				
				from_action = await get_action(gap.from_action_id)
				to_action = await get_action(gap.to_action_id)
				
				if not from_action or not to_action:
					result.errors.append(
						f"Action not found: from={gap.from_action_id}, to={gap.to_action_id}"
					)
					continue
				
				# Get screen context if available
				from_screen = await get_screen(gap.from_screen_id) if gap.from_screen_id else None
				to_screen = await get_screen(gap.to_screen_id) if gap.to_screen_id else None
				
				# Get website structure for context
				website_screens = await query_screens_by_website(
					request.website_id,
					actionable_only=True,
					limit=20  # Limit to avoid too much context
				)
				
				# Build prompt for Gemini
				prompt = self._build_extrapolation_prompt(
					from_action=from_action,
					to_action=to_action,
					from_screen=from_screen,
					to_screen=to_screen,
					website_screens=website_screens,
					max_steps=request.max_intermediate_steps
				)
				
				# Call Gemini LLM
				response = client.models.generate_content(
					model="gemini-2.0-flash-exp",
					contents=prompt
				)
				
				# Parse LLM response
				inferred = self._parse_extrapolation_response(response.text)
				
				# Validate and add to result
				if inferred:
					# Convert to InferredAction objects
					for action_data in inferred.get('actions', []):
						try:
							inferred_action = InferredAction(
								action_type=action_data.get('action_type', 'click'),
								target=action_data.get('target', ''),
								description=action_data.get('description', ''),
								confidence=float(action_data.get('confidence', 0.7)),
								reasoning=action_data.get('reasoning', ''),
								screen_id=action_data.get('screen_id')
							)
							result.inferred_actions.append(inferred_action)
						except Exception as e:
							logger.warning(f"Failed to parse inferred action: {e}")
							continue
					
					if request.include_screens and inferred.get('transitions'):
						result.inferred_transitions.extend(inferred['transitions'])
					
					result.gaps_filled += 1
					result.confidence_scores[gap.from_action_id] = float(
						inferred.get('confidence', 0.7)
					)
				else:
					result.errors.append(
						f"Failed to parse LLM response for gap {gap.from_action_id} -> {gap.to_action_id}"
					)
			
			except Exception as e:
				logger.error(
					f"Failed to extrapolate actions for gap {gap.from_action_id} -> {gap.to_action_id}: {e}",
					exc_info=True
				)
				result.errors.append(
					f"Gap {gap.from_action_id} -> {gap.to_action_id}: {str(e)}"
				)
		
		return result
	
	def _build_extrapolation_prompt(
		self,
		from_action: Any,  # ActionDefinition
		to_action: Any,  # ActionDefinition
		from_screen: Any | None,  # ScreenDefinition
		to_screen: Any | None,  # ScreenDefinition
		website_screens: list[Any],  # list[ScreenDefinition]
		max_steps: int
	) -> str:
		"""Build prompt for Gemini to infer missing actions."""
		
		# Format screen names
		from_screen_name = from_screen.name if from_screen else 'Unknown'
		to_screen_name = to_screen.name if to_screen else 'Unknown'
		
		# Format available screens
		available_screens = ', '.join([s.name for s in website_screens[:10]])
		
		prompt = f"""You are analyzing a website automation workflow. You need to infer what actions occurred between two known actions.

KNOWN START ACTION:
- Action ID: {from_action.action_id}
- Action Type: {from_action.action_type}
- Action Name: {from_action.name}
- Target: {from_action.target_selector or 'N/A'}
- Screen: {from_screen_name}

KNOWN END ACTION:
- Action ID: {to_action.action_id}
- Action Type: {to_action.action_type}
- Action Name: {to_action.name}
- Target: {to_action.target_selector or 'N/A'}
- Screen: {to_screen_name}

WEBSITE CONTEXT:
Available screens: {available_screens}

TASK:
Infer the most likely sequence of actions that occurred between the start and end actions.
Consider:
1. Common UI patterns (navigation, form filling, waiting for page loads)
2. Screen transitions (if screens are different)
3. Required intermediate steps (e.g., page navigation, element waiting, scrolling)
4. Browser automation best practices

OUTPUT FORMAT (JSON):
{{
  "actions": [
    {{
      "action_type": "navigate|click|type|wait|scroll|...",
      "target": "element selector, URL, or description",
      "description": "Human-readable description",
      "confidence": 0.0-1.0,
      "reasoning": "Why this action is likely",
      "screen_id": "screen_id if known, null otherwise"
    }}
  ],
  "transitions": [
    {{
      "from_screen_id": "...",
      "to_screen_id": "...",
      "trigger_action": "action description"
    }}
  ],
  "confidence": 0.0-1.0,
  "reasoning": "Overall reasoning for the inferred sequence"
}}

Limit to maximum {max_steps} intermediate actions.
Return ONLY valid JSON, no markdown formatting."""
		
		return prompt
	
	def _parse_extrapolation_response(self, response_text: str) -> dict[str, Any] | None:
		"""Parse Gemini LLM response into structured format."""
		try:
			# Extract JSON from response (handle markdown code blocks)
			text = response_text.strip()
			
			# Try direct JSON parsing first
			try:
				return json.loads(text)
			except json.JSONDecodeError:
				pass
			
			# Try to extract JSON from markdown code blocks
			json_match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
			if not json_match:
				json_match = re.search(r'```\s*(\{.*?\})\s*```', text, re.DOTALL)
			
			if json_match:
				return json.loads(json_match.group(1))
			
			# Try to find JSON object in text
			json_match = re.search(r'\{.*\}', text, re.DOTALL)
			if json_match:
				return json.loads(json_match.group(0))
			
			logger.warning("Could not parse JSON from LLM response")
			return None
		
		except Exception as e:
			logger.error(f"Failed to parse extrapolation response: {e}")
			return None
