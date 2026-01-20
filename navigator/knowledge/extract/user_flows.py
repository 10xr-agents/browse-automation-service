"""
User flow extraction and synthesis from all features.

Generates comprehensive user flows by combining:
- Screens (application states)
- Workflows (step-by-step procedures)
- Business Functions (business context)
- Transitions (navigation paths)
"""

import json
import logging
import os
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class FlowStep(BaseModel):
	"""User flow step definition."""
	step_number: int = Field(..., description="Step number in sequence")
	screen_name: str = Field(..., description="Screen name where this step occurs")
	screen_id: str | None = Field(None, description="Screen identifier")
	action: str = Field(..., description="Action performed in this step")
	action_id: str | None = Field(None, description="Action identifier")
	transition_id: str | None = Field(None, description="Transition identifier (if navigation occurs)")
	description: str = Field(..., description="Description of what happens in this step")
	user_goal: str | None = Field(None, description="User's goal in this step")
	business_function: str | None = Field(None, description="Associated business function")


class UserFlow(BaseModel):
	"""User flow definition synthesized from all features."""
	user_flow_id: str = Field(..., description="Unique identifier")
	name: str = Field(..., description="User flow name (e.g., 'User Registration', 'Checkout Process')")
	description: str = Field(..., description="Description of the complete user flow")
	website_id: str = Field(..., description="Website identifier")
	category: str = Field(default="general", description="Flow category (authentication, purchase, content_creation, etc.)")
	business_function: str | None = Field(None, description="Primary business function this flow supports (name)")

	# Flow structure
	entry_screen: str = Field(..., description="Entry screen name (where flow starts)")
	exit_screen: str = Field(..., description="Exit screen name (where flow ends)")
	steps: list[FlowStep] = Field(default_factory=list, description="Sequential flow steps")

	# Related entities (by ID) - Enhanced in Phase 1
	related_screens: list[str] = Field(default_factory=list, description="Screen IDs used in this flow")
	related_workflows: list[str] = Field(default_factory=list, description="Workflow IDs that compose this flow")
	related_business_functions: list[str] = Field(default_factory=list, description="Business function IDs related to this flow")
	related_transitions: list[str] = Field(default_factory=list, description="Transition IDs used in this flow")

	# NEW cross-reference fields (Phase 1: Schema Updates)
	related_tasks: list[str] = Field(
		default_factory=list,
		description="Task IDs that are part of this user flow"
	)
	related_actions: list[str] = Field(
		default_factory=list,
		description="Action IDs used in this user flow"
	)
	screen_sequence: list[dict[str, Any]] = Field(
		default_factory=list,
		description="Ordered sequence of screens with transitions: [{'screen_id': '...', 'transition_id': '...', 'order': 1}, ...]"
	)
	entry_actions: list[str] = Field(
		default_factory=list,
		description="Action IDs that can start this flow"
	)
	exit_actions: list[str] = Field(
		default_factory=list,
		description="Action IDs that complete this flow"
	)

	# Business context
	business_reasoning: str | None = Field(None, description="Why this user flow exists, business context")
	business_impact: str | None = Field(None, description="Business value and impact of this flow")
	business_requirements: list[str] = Field(default_factory=list, description="Business requirements addressed by this flow")

	# Flow metadata
	total_steps: int = Field(default=0, description="Total number of steps")
	estimated_duration: int = Field(default=0, description="Estimated duration in seconds")
	complexity: str = Field(default="medium", description="Flow complexity: low|medium|high")

	# Visualization
	mermaid_diagram: str | None = Field(None, description="Mermaid flowchart diagram representation")

	metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class UserFlowExtractionResult(BaseModel):
	"""Result of user flow extraction."""
	user_flows: list[UserFlow] = Field(default_factory=list)
	success: bool = True
	errors: list[str] = Field(default_factory=list)
	statistics: dict[str, Any] = Field(default_factory=dict)

	def calculate_statistics(self):
		"""Calculate extraction statistics."""
		self.statistics = {
			'total_flows': len(self.user_flows),
			'total_steps': sum(len(f.steps) for f in self.user_flows),
			'average_steps_per_flow': sum(len(f.steps) for f in self.user_flows) / len(self.user_flows) if self.user_flows else 0,
			'categories': list(set(f.category for f in self.user_flows)),
		}

	def add_error(self, error_type: str, error_message: str, error_context: dict[str, Any] | None = None):
		"""Add an error to the result."""
		error_str = f"{error_type}: {error_message}"
		if error_context:
			error_str += f" (Context: {error_context})"
		self.errors.append(error_str)
		self.success = False


class UserFlowExtractor:
	"""
	Extracts and synthesizes user flows from all features.
	
	Combines:
	- Screens (application states)
	- Workflows (step-by-step procedures)
	- Business Functions (business context)
	- Transitions (navigation paths)
	
	Uses LLM to synthesize comprehensive user flows that show how users
	navigate through the application to complete tasks.
	"""

	def __init__(self, website_id: str = "unknown"):
		"""
		Initialize user flow extractor.
		
		Args:
			website_id: Website identifier for extracted flows
		"""
		self.website_id = website_id

	async def extract_user_flows(
		self,
		screens: list[Any],  # ScreenDefinition
		workflows: list[Any],  # OperationalWorkflow
		business_functions: list[Any],  # BusinessFunction
		transitions: list[Any],  # TransitionDefinition
	) -> UserFlowExtractionResult:
		"""
		Extract user flows by synthesizing screens, workflows, business functions, and transitions.
		
		Args:
			screens: List of screen definitions
			workflows: List of operational workflows
			business_functions: List of business functions
			transitions: List of transition definitions
		
		Returns:
			UserFlowExtractionResult with synthesized user flows
		"""
		result = UserFlowExtractionResult()

		try:
			if not screens and not workflows:
				logger.warning("No screens or workflows provided for user flow extraction")
				return result

			# Combine all knowledge into a single context for LLM
			combined_context = self._combine_knowledge(
				screens, workflows, business_functions, transitions
			)

			if not combined_context:
				logger.warning("No relevant knowledge found for user flow extraction")
				return result

			# Extract user flows using LLM
			user_flows = await self._extract_with_llm(
				combined_context,
				screens, workflows, business_functions, transitions
			)
			result.user_flows = user_flows

			# Generate Mermaid diagrams for each flow
			for flow in result.user_flows:
				flow.mermaid_diagram = self._generate_mermaid_diagram(flow)

			# Calculate statistics
			result.calculate_statistics()

			logger.info(
				f"✅ Extracted {result.statistics['total_flows']} user flows "
				f"({result.statistics['total_steps']} total steps, "
				f"{len(result.statistics['categories'])} categories)"
			)

		except Exception as e:
			logger.error(f"❌ Error extracting user flows: {e}", exc_info=True)
			result.add_error("ExtractionError", str(e), {"exception_type": type(e).__name__})

		return result

	def _combine_knowledge(
		self,
		screens: list[Any],
		workflows: list[Any],
		business_functions: list[Any],
		transitions: list[Any],
	) -> str:
		"""
		Combine all knowledge entities into a single text for LLM synthesis.
		
		Args:
			screens: Screen definitions
			workflows: Operational workflows
			business_functions: Business functions
			transitions: Transition definitions
		
		Returns:
			Combined knowledge context as string
		"""
		content_parts = []

		# Add business functions context
		if business_functions:
			content_parts.append("# Business Functions\n")
			for bf in business_functions:
				content_parts.append(f"\n## {bf.name} ({bf.category})")
				content_parts.append(f"Description: {bf.description}")
				if bf.business_reasoning:
					content_parts.append(f"Business Reasoning: {bf.business_reasoning}")
				if bf.business_impact:
					content_parts.append(f"Business Impact: {bf.business_impact}")
				content_parts.append("")
			content_parts.append("\n")

		# Add workflows context
		if workflows:
			content_parts.append("# Operational Workflows\n")
			for wf in workflows:
				content_parts.append(f"\n## {wf.name}")
				content_parts.append(f"Description: {wf.description}")
				content_parts.append(f"Business Function: {wf.business_function}")
				content_parts.append("Steps:")
				for step in wf.steps:
					content_parts.append(f"  {step.step_number}. [{step.screen}] {step.action}")
				content_parts.append("")
			content_parts.append("\n")

		# Add screens context
		if screens:
			content_parts.append("# Application Screens\n")
			for screen in screens[:50]:  # Limit to first 50 screens
				content_parts.append(f"\n## {screen.name} (ID: {screen.screen_id})")
				content_parts.append(f"URL Patterns: {', '.join(screen.url_patterns[:3])}")
				content_parts.append(f"UI Elements: {len(screen.ui_elements)} elements")
				content_parts.append("")
			content_parts.append("\n")

		# Add transitions context
		if transitions:
			content_parts.append("# Screen Transitions\n")
			for trans in transitions[:50]:  # Limit to first 50 transitions
				# Handle both TransitionDefinition objects and dicts
				if hasattr(trans, 'from_screen_id'):
					from_screen_id = trans.from_screen_id
					to_screen_id = trans.to_screen_id
					trigger_action = trans.triggered_by.action_type if trans.triggered_by else "unknown"
					reliability = trans.reliability_score if hasattr(trans, 'reliability_score') else 0.95
				else:
					from_screen_id = trans.get('from_screen_id', trans.get('from_screen', 'unknown'))
					to_screen_id = trans.get('to_screen_id', trans.get('to_screen', 'unknown'))
					trigger_action = trans.get('trigger_action', trans.get('triggered_by', {}).get('action_type', 'unknown'))
					reliability = trans.get('reliability', trans.get('reliability_score', 0.95))

				content_parts.append(f"\n## {from_screen_id} → {to_screen_id}")
				content_parts.append(f"Trigger Action: {trigger_action}")
				content_parts.append(f"Reliability: {reliability}")
				content_parts.append("")
			content_parts.append("\n")

		return "\n".join(content_parts)

	async def _extract_with_llm(
		self,
		combined_context: str,
		screens: list[Any],
		workflows: list[Any],
		business_functions: list[Any],
		transitions: list[Any],
	) -> list[UserFlow]:
		"""Extract user flows using OpenAI or Gemini LLM."""
		user_flows = []

		# Try OpenAI first
		openai_key = os.getenv('OPENAI_API_KEY')
		if openai_key:
			try:
				from openai import OpenAI
				client = OpenAI(api_key=openai_key)

				prompt = f"""Analyze the application knowledge base and synthesize comprehensive user flows.

Knowledge Base Context:
{combined_context[:20000]}  # Large limit for comprehensive context

Your task is to synthesize user flows that show how users navigate through the application to complete tasks.
A user flow should:
1. Start from an entry screen (e.g., landing page, login page)
2. Navigate through multiple screens via transitions
3. Perform actions at each screen (from workflows)
4. Support specific business functions
5. End at an exit screen (e.g., confirmation page, dashboard)

For each user flow, identify:
1. Flow name and description (e.g., "User Registration", "Product Purchase", "Content Creation")
2. Entry screen (where the flow starts)
3. Exit screen (where the flow ends)
4. Sequential steps combining:
   - Screen names (from Screens section)
   - Actions (from Workflows section)
   - Transitions (from Transitions section)
   - Business functions (from Business Functions section)
5. Business context (why this flow exists, business impact)
6. Category (authentication, purchase, content_creation, configuration, etc.)

Be COMPREHENSIVE - synthesize ALL major user flows that can be identified from the knowledge base.
Don't create duplicate flows for the same task.
Focus on end-to-end user journeys, not just individual screens or workflows.

Return a JSON object with a "user_flows" key containing an array of user flows with this structure:
{{
  "user_flows": [
    {{
      "name": "User Flow Name",
      "description": "Description of the complete user flow",
      "category": "Category (authentication, purchase, content_creation, etc.)",
      "business_function": "Primary business function this flow supports",
      "entry_screen": "Entry screen name",
      "exit_screen": "Exit screen name",
      "steps": [
        {{
          "step_number": 1,
          "screen_name": "Screen name",
          "action": "Action performed",
          "description": "Description of what happens in this step",
          "user_goal": "User's goal in this step",
          "business_function": "Associated business function"
        }}
      ],
      "business_reasoning": "Why this user flow exists, business context",
      "business_impact": "Business value and impact of this flow",
      "business_requirements": ["requirement1", "requirement2"],
      "total_steps": 5,
      "estimated_duration": 120,
      "complexity": "medium"
    }}
  ]
}}

Return ONLY valid JSON, no markdown formatting."""

				response = client.chat.completions.create(
					model="gpt-4o",
					messages=[
						{"role": "system", "content": "You are an expert at synthesizing user flows from application knowledge bases. Create comprehensive, end-to-end user journeys that combine screens, workflows, and business functions."},
						{"role": "user", "content": prompt}
					],
					response_format={"type": "json_object"},
				)

				content_text = response.choices[0].message.content

				# Log response for debugging (first 500 chars)
				if len(content_text) > 500:
					logger.debug(f"OpenAI response (first 500 chars): {content_text[:500]}...")
				else:
					logger.debug(f"OpenAI response: {content_text}")

				# Try to parse JSON, with fallback for markdown code blocks
				try:
					data = json.loads(content_text)
				except json.JSONDecodeError as e:
					# Try to extract JSON from markdown code blocks
					import re
					json_match = re.search(r'```(?:json)?\s*(\{.*\})\s*```', content_text, re.DOTALL)
					if json_match:
						data = json.loads(json_match.group(1))
					else:
						# Try to find JSON object in the text
						json_match = re.search(r'\{.*\}', content_text, re.DOTALL)
						if json_match:
							data = json.loads(json_match.group(0))
						else:
							logger.error(f"Failed to parse JSON. Response length: {len(content_text)}, Error: {e}")
							logger.error(f"Response content: {content_text[:1000]}")
							raise

				# Handle both direct array and wrapped in object
				if isinstance(data, list):
					flows_data = data
				elif isinstance(data, dict) and 'user_flows' in data:
					flows_data = data['user_flows']
				elif isinstance(data, dict):
					flows_data = [data]
				else:
					flows_data = []

				# Match screens, workflows, transitions by name to get IDs
				screen_map = {s.name: s.screen_id for s in screens}
				workflow_map = {w.name: w.workflow_id for w in workflows}
				business_function_map = {bf.name: bf.business_function_id for bf in business_functions}
				transition_map = {}  # Would need more sophisticated matching

				for flow_data in flows_data:
					# Resolve screen IDs and workflow IDs from names
					steps = []
					for step_data in flow_data.get('steps', []):
						screen_id = screen_map.get(step_data.get('screen_name'))
						flow_step = FlowStep(
							step_number=step_data.get('step_number', 0),
							screen_name=step_data.get('screen_name', ''),
							screen_id=screen_id,
							action=step_data.get('action', ''),
							action_id=None,  # Would need action name mapping
							transition_id=None,
							description=step_data.get('description', ''),
							user_goal=step_data.get('user_goal'),
							business_function=step_data.get('business_function'),
						)
						steps.append(flow_step)

					# Collect related entity IDs
					related_screens = [s.screen_id for s in screens if s.name in [step.screen_name for step in steps]]
					related_workflows = [w.workflow_id for w in workflows if w.name == flow_data.get('business_function') or any(step.business_function == w.name for step in steps)]
					related_business_functions = [bf.business_function_id for bf in business_functions if bf.name == flow_data.get('business_function')]

					# Build screen_sequence with transitions (Phase 4 enhancement)
					screen_sequence = []
					related_transitions = []
					related_actions = []
					entry_actions = []
					exit_actions = []

					# Map transitions by from/to screen IDs
					transition_map = {}
					for trans in transitions:
						key = (trans.from_screen_id, trans.to_screen_id)
						if key not in transition_map:
							transition_map[key] = []
						transition_map[key].append(trans)

					# Build sequence from steps
					for i, step in enumerate(steps):
						if step.screen_id:
							# Find transition to next screen
							transition_id = None
							if i < len(steps) - 1 and steps[i + 1].screen_id:
								next_screen_id = steps[i + 1].screen_id
								transitions_for_step = transition_map.get((step.screen_id, next_screen_id), [])
								if transitions_for_step:
									transition_id = transitions_for_step[0].transition_id
									related_transitions.append(transition_id)
									# Get action from transition
									if transitions_for_step[0].action_id:
										related_actions.append(transitions_for_step[0].action_id)
									elif transitions_for_step[0].triggered_by and transitions_for_step[0].triggered_by.element_id:
										related_actions.append(transitions_for_step[0].triggered_by.element_id)

							screen_sequence.append({
								'screen_id': step.screen_id,
								'screen_name': step.screen_name,
								'transition_id': transition_id,
								'order': step.step_number
							})

							# Track entry/exit actions
							if i == 0 and transition_id:
								entry_actions.append(transition_id)
							if i == len(steps) - 1 and transition_id:
								exit_actions.append(transition_id)

					# Get entry and exit screen IDs
					entry_screen_id = screen_map.get(flow_data.get('entry_screen', ''))
					exit_screen_id = screen_map.get(flow_data.get('exit_screen', ''))

					user_flow = UserFlow(
						user_flow_id=str(uuid4()),
						name=flow_data.get('name', 'Unknown Flow'),
						description=flow_data.get('description', ''),
						website_id=self.website_id,
						category=flow_data.get('category', 'general'),
						business_function=flow_data.get('business_function'),
						entry_screen=flow_data.get('entry_screen', ''),
						exit_screen=flow_data.get('exit_screen', ''),
						steps=steps,
						related_screens=related_screens,
						related_workflows=related_workflows,
						related_business_functions=related_business_functions,
						related_transitions=list(set(related_transitions)),  # Deduplicate
						# Phase 4: Enhanced cross-references
						related_tasks=[],  # Will be populated from task extraction
						related_actions=list(set(related_actions)),  # Deduplicate
						screen_sequence=screen_sequence,
						entry_actions=list(set(entry_actions)),
						exit_actions=list(set(exit_actions)),
						business_reasoning=flow_data.get('business_reasoning'),
						business_impact=flow_data.get('business_impact'),
						business_requirements=flow_data.get('business_requirements', []),
						total_steps=flow_data.get('total_steps', len(steps)),
						estimated_duration=flow_data.get('estimated_duration', 0),
						complexity=flow_data.get('complexity', 'medium'),
						metadata={'extraction_method': 'openai', 'website_id': self.website_id}
					)
					user_flows.append(user_flow)

				logger.info(f"✅ Extracted {len(user_flows)} user flows using OpenAI")
				return user_flows

			except Exception as e:
				logger.warning(f"OpenAI extraction failed: {e}")

		# Fallback to empty list (Gemini implementation would go here)
		logger.warning("No LLM available for user flow extraction")
		return []

	def _generate_mermaid_diagram(self, flow: UserFlow) -> str:
		"""
		Generate Mermaid flowchart diagram for a user flow.
		
		Args:
			flow: UserFlow to generate diagram for
		
		Returns:
			Mermaid diagram string
		"""
		lines = ["flowchart TD"]
		lines.append(f"    Start([{flow.entry_screen}])")

		# Add steps
		for i, step in enumerate(flow.steps):
			node_id = f"step_{i}"
			node_label = f"{step.step_number}. {step.action}"
			lines.append(f"    {node_id}[{node_label}]")

			# Connect to previous step
			if i == 0:
				lines.append(f"    Start --> {node_id}")
			else:
				prev_id = f"step_{i-1}"
				lines.append(f"    {prev_id} --> {node_id}")

		# Add exit
		lines.append(f"    End([{flow.exit_screen}])")
		if flow.steps:
			last_step_id = f"step_{len(flow.steps)-1}"
			lines.append(f"    {last_step_id} --> End")
		else:
			lines.append("    Start --> End")

		return "\n".join(lines)
