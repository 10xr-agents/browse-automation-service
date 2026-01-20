"""
Operational workflow extraction from video content.

Extracts step-by-step operational workflows from video demonstrations
by combining transcription, action sequences, and frame analysis.
"""

import json
import logging
import os
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from navigator.schemas import ContentChunk

logger = logging.getLogger(__name__)


class WorkflowStep(BaseModel):
	"""Workflow step definition."""
	step_number: int = Field(..., description="Step number in sequence")
	action: str = Field(..., description="Action to perform")
	screen: str = Field(..., description="Screen where action occurs")
	precondition: str | None = Field(None, description="Precondition for this step")
	postcondition: str | None = Field(None, description="Expected result after step")
	error_handling: str | None = Field(None, description="Error handling instructions")


class OperationalWorkflow(BaseModel):
	"""Operational workflow definition."""
	workflow_id: str = Field(..., description="Unique identifier")
	name: str = Field(..., description="Workflow name")
	description: str = Field(..., description="Description of what this workflow does")
	business_function: str = Field(..., description="Associated business function (name)")
	business_reasoning: str | None = Field(None, description="Why this workflow exists, what problem it solves, business rationale")
	business_impact: str | None = Field(None, description="Business value, impact, or outcomes of this workflow")
	business_requirements: list[str] = Field(default_factory=list, description="Explicit business requirements that led to this workflow")
	steps: list[WorkflowStep] = Field(default_factory=list, description="Workflow steps")
	metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

	# Cross-reference fields (Phase 1: Schema Updates)
	business_function_id: str | None = Field(
		None,
		description="Business function ID this workflow implements (ID reference, not name)"
	)
	user_flow_ids: list[str] = Field(
		default_factory=list,
		description="User flow IDs that implement this workflow"
	)
	screen_ids: list[str] = Field(
		default_factory=list,
		description="Screen IDs used in this workflow"
	)
	task_ids: list[str] = Field(
		default_factory=list,
		description="Task IDs that are part of this workflow"
	)
	action_ids: list[str] = Field(
		default_factory=list,
		description="Action IDs used in this workflow"
	)
	transition_ids: list[str] = Field(
		default_factory=list,
		description="Transition IDs used in this workflow"
	)


class WorkflowExtractionResult(BaseModel):
	"""Result of workflow extraction."""
	workflows: list[OperationalWorkflow] = Field(default_factory=list)
	success: bool = True
	errors: list[str] = Field(default_factory=list)
	statistics: dict[str, Any] = Field(default_factory=dict)

	def calculate_statistics(self):
		"""Calculate extraction statistics."""
		self.statistics = {
			'total_workflows': len(self.workflows),
			'total_steps': sum(len(w.steps) for w in self.workflows),
			'average_steps_per_workflow': sum(len(w.steps) for w in self.workflows) / len(self.workflows) if self.workflows else 0,
		}

	def add_error(self, error_type: str, error_message: str, error_context: dict[str, Any] | None = None):
		"""Add an error to the result."""
		error_str = f"{error_type}: {error_message}"
		if error_context:
			error_str += f" (Context: {error_context})"
		self.errors.append(error_str)
		self.success = False


class WorkflowExtractor:
	"""
	Extracts operational workflows from video content.
	
	Combines:
	- Transcription (step descriptions)
	- Action sequences (actual steps)
	- Frame analysis (screen states)
	"""

	def __init__(self, website_id: str = "unknown"):
		"""
		Initialize workflow extractor.
		
		Args:
			website_id: Website identifier for extracted workflows
		"""
		self.website_id = website_id

	def extract_workflows(
		self,
		content_chunks: list[ContentChunk],
		business_function: str | None = None
	) -> WorkflowExtractionResult:
		"""
		Extract operational workflows from content chunks.
		
		Supports all source types:
		- Video: transcription, frame analysis, action chunks
		- Documentation: documentation chunks (MD, PDF, DOCX, HTML, TXT)
		- Website: webpage chunks (from Browser-Use crawling)
		- Crawl4AI: documentation chunks (from Crawl4AI crawling)
		- Exploration: exploration chunks (from page exploration)
		
		Args:
			content_chunks: Content chunks from any ingestion source
			business_function: Optional business function to filter workflows
		
		Returns:
			WorkflowExtractionResult with extracted workflows
		"""
		result = WorkflowExtractionResult()

		try:
			logger.info(f"Extracting workflows from {len(content_chunks)} content chunks")

			# Separate chunks by type (support video, documentation, website, exploration)
			transcription_chunks = [c for c in content_chunks if c.chunk_type == "video_transcription"]
			frame_chunks = [c for c in content_chunks if c.chunk_type == "video_frame_analysis"]
			action_chunks = [c for c in content_chunks if c.chunk_type == "video_action"]
			documentation_chunks = [c for c in content_chunks if c.chunk_type in ["documentation", "webpage", "exploration"]]
			summary_chunks = [c for c in content_chunks if "summary" in c.chunk_type]

			# Store for use in _extract_with_llm
			self._documentation_chunks = documentation_chunks
			self._summary_chunks = summary_chunks

			# Combine all relevant content (video or documentation)
			combined_content = self._combine_content(
				transcription_chunks, frame_chunks, action_chunks,
				documentation_chunks, summary_chunks
			)

			if not combined_content:
				logger.warning("No relevant content found for workflow extraction")
				return result

			# Extract workflows using LLM
			workflows = self._extract_with_llm(
				combined_content,
				business_function,
				documentation_chunks=documentation_chunks,
				summary_chunks=summary_chunks
			)
			result.workflows = workflows

			# Calculate statistics
			result.calculate_statistics()

			logger.info(
				f"✅ Extracted {result.statistics['total_workflows']} workflows "
				f"({result.statistics['total_steps']} total steps)"
			)

		except Exception as e:
			logger.error(f"❌ Error extracting workflows: {e}", exc_info=True)
			result.add_error("ExtractionError", str(e), {"exception_type": type(e).__name__})

		return result

	def _combine_content(
		self,
		transcription_chunks: list[ContentChunk],
		frame_chunks: list[ContentChunk],
		action_chunks: list[ContentChunk],
		documentation_chunks: list[ContentChunk] | None = None,
		summary_chunks: list[ContentChunk] | None = None
	) -> str:
		"""
		Combine content chunks into a single text for LLM analysis.
		
		Supports both video content (transcription, frames, actions) and
		documentation content (text, tables, structure).
		"""
		content_parts = []

		# Add documentation content (if available)
		if documentation_chunks:
			content_parts.append("# Document Content\n")
			for chunk in documentation_chunks:
				if chunk.section_title:
					content_parts.append(f"\n## {chunk.section_title}\n")
				content_parts.append(chunk.content)
				content_parts.append("\n")
			content_parts.append("\n")

		# Add summary chunks (comprehensive summaries)
		if summary_chunks:
			content_parts.append("# Comprehensive Summaries\n")
			for chunk in summary_chunks:
				content_parts.append(chunk.content)
				content_parts.append("\n")
			content_parts.append("\n")

		# Add video transcription (if available)
		if transcription_chunks:
			content_parts.append("# Video Transcription\n")
			for chunk in transcription_chunks:
				content_parts.append(chunk.content)
			content_parts.append("\n")

		# Add frame analysis (if available)
		if frame_chunks:
			content_parts.append("# Frame Analysis\n")
			for chunk in frame_chunks[:10]:  # Limit to first 10 frames
				content_parts.append(chunk.content)
			content_parts.append("\n")

		# Add action sequence (if available)
		if action_chunks:
			content_parts.append("# Action Sequence\n")
			for chunk in action_chunks:
				content_parts.append(chunk.content)
			content_parts.append("\n")

		return "\n".join(content_parts)

	def _extract_with_llm(
		self,
		content: str,
		business_function: str | None = None,
		documentation_chunks: list[ContentChunk] | None = None,
		summary_chunks: list[ContentChunk] | None = None
	) -> list[OperationalWorkflow]:
		"""Extract workflows using OpenAI or Gemini LLM."""
		workflows = []

		# Try OpenAI first
		openai_key = os.getenv('OPENAI_API_KEY')
		if openai_key:
			try:
				from openai import OpenAI
				client = OpenAI(api_key=openai_key)

				# Determine content type
				has_docs = (documentation_chunks is not None and len(documentation_chunks) > 0) or (summary_chunks is not None and len(summary_chunks) > 0)
				content_type = "documentation" if has_docs else "video"

				prompt = f"""Analyze this {content_type} content and extract operational workflows.

Content:
{content[:12000]}  # Increased limit for documentation

{f"Focus on workflows related to: {business_function}" if business_function else ""}

Extract step-by-step operational workflows. For each workflow, identify:
1. Workflow name and description (what this workflow does)
2. Business reasoning (EXTENSIVE: why this workflow exists, what problem it solves, business rationale - provide detailed multi-paragraph explanation covering business context, problem statement, stakeholders affected, historical context if relevant)
3. Business impact (EXTENSIVE: business value, impact, or outcomes of this workflow - provide detailed analysis covering quantitative/qualitative benefits, ROI considerations, user experience impact, competitive advantages, long-term strategic value)
4. Business requirements (EXTENSIVE list: explicit requirements that led to this workflow - provide comprehensive list with detailed explanations for each requirement, regulatory/compliance needs, user needs, business objectives)
5. Associated business function
6. Sequential steps with:
   - Step number
   - Action to perform
   - Screen/page/section where action occurs (if applicable)
   - Preconditions (what must be true before this step)
   - Postconditions (expected result after step)
   - Error handling (what to do if step fails)
   - Dependencies (other workflows or functions this depends on)
   - Inputs and outputs (data required/produced)

Be COMPREHENSIVE - extract ALL workflows described in the content. Don't miss any workflow steps.

Return a JSON object with a "workflows" key containing an array of workflows with this structure:
{{
  "workflows": [
    {{
      "name": "Workflow Name",
    "description": "Description of what this workflow does",
    "business_function": "Associated business function",
    "business_reasoning": "EXTENSIVE multi-paragraph explanation: Why this workflow exists, what problem it solves, business rationale - include business context, problem statement, stakeholders, historical context",
    "business_impact": "EXTENSIVE multi-paragraph analysis: Business value, impact, outcomes - include quantitative/qualitative benefits, ROI, user experience impact, competitive advantages, strategic value",
    "business_requirements": ["Detailed requirement 1 with explanation", "Detailed requirement 2 with explanation", ...],
    "steps": [
      {{
        "step_number": 1,
        "action": "Action to perform",
        "screen": "Screen name",
        "precondition": "What must be true before this step",
        "postcondition": "Expected result",
        "error_handling": "What to do if this fails"
      }}
    ]
    }}
  ]
}}

Return ONLY valid JSON, no markdown formatting."""

				response = client.chat.completions.create(
					model="gpt-4o",
					messages=[
						{"role": "system", "content": "You are an expert at analyzing operational workflows and extracting step-by-step procedures from video demonstrations."},
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
					workflows_data = data
				elif isinstance(data, dict) and 'workflows' in data:
					workflows_data = data['workflows']
				elif isinstance(data, dict):
					workflows_data = [data]
				else:
					workflows_data = []

				for wf_data in workflows_data:
					steps = []
					for step_data in wf_data.get('steps', []):
						step = WorkflowStep(
							step_number=step_data.get('step_number', 0),
							action=step_data.get('action', ''),
							screen=step_data.get('screen', 'Unknown'),
							precondition=step_data.get('precondition'),
							postcondition=step_data.get('postcondition'),
							error_handling=step_data.get('error_handling'),
						)
						steps.append(step)

					workflow = OperationalWorkflow(
						workflow_id=str(uuid4()),
						name=wf_data.get('name', 'Unknown Workflow'),
						description=wf_data.get('description', ''),
						business_function=wf_data.get('business_function', business_function or 'General'),
						business_reasoning=wf_data.get('business_reasoning'),
						business_impact=wf_data.get('business_impact'),
						business_requirements=wf_data.get('business_requirements', []),
						steps=steps,
						metadata={'extraction_method': 'openai', 'website_id': self.website_id}
					)
					workflows.append(workflow)

				logger.info(f"✅ Extracted {len(workflows)} workflows using OpenAI")
				return workflows

			except Exception as e:
				logger.warning(f"OpenAI extraction failed: {e}")

		# Fallback to Gemini (using new google.genai SDK)
		google_key = os.getenv('GOOGLE_API_KEY')
		if google_key:
			try:
				from google import genai

				# Create client with API key (new SDK pattern)
				client = genai.Client(api_key=google_key)

				# Determine content type
				has_docs = (documentation_chunks is not None and len(documentation_chunks) > 0) or (summary_chunks is not None and len(summary_chunks) > 0)
				content_type = "documentation" if has_docs else "video"

				prompt = f"""Analyze this {content_type} content and extract operational workflows.

Content:
{content[:12000]}  # Increased limit for documentation

{f"Focus on workflows related to: {business_function}" if business_function else ""}

Extract step-by-step operational workflows. For each workflow, identify:
1. Workflow name and description (what this workflow does)
2. Business reasoning (EXTENSIVE: why this workflow exists, what problem it solves, business rationale - provide detailed multi-paragraph explanation covering business context, problem statement, stakeholders affected, historical context if relevant)
3. Business impact (EXTENSIVE: business value, impact, or outcomes of this workflow - provide detailed analysis covering quantitative/qualitative benefits, ROI considerations, user experience impact, competitive advantages, long-term strategic value)
4. Business requirements (EXTENSIVE list: explicit requirements that led to this workflow - provide comprehensive list with detailed explanations for each requirement, regulatory/compliance needs, user needs, business objectives)
5. Associated business function
6. Sequential steps with:
   - Step number
   - Action to perform
   - Screen/page/section where action occurs (if applicable)
   - Preconditions (what must be true before this step)
   - Postconditions (expected result after step)
   - Error handling (what to do if step fails)
   - Dependencies (other workflows or functions this depends on)
   - Inputs and outputs (data required/produced)

Be COMPREHENSIVE - extract ALL workflows described in the content. Don't miss any workflow steps.

Return a JSON object with a "workflows" key containing an array of workflows with this structure:
{{
  "workflows": [
    {{
      "name": "Workflow Name",
    "description": "Description of what this workflow does",
    "business_function": "Associated business function",
    "business_reasoning": "EXTENSIVE multi-paragraph explanation: Why this workflow exists, what problem it solves, business rationale - include business context, problem statement, stakeholders, historical context",
    "business_impact": "EXTENSIVE multi-paragraph analysis: Business value, impact, outcomes - include quantitative/qualitative benefits, ROI, user experience impact, competitive advantages, strategic value",
    "business_requirements": ["Detailed requirement 1 with explanation", "Detailed requirement 2 with explanation", ...],
    "steps": [
      {{
        "step_number": 1,
        "action": "Action to perform",
        "screen": "Screen name",
        "precondition": "What must be true before this step",
        "postcondition": "Expected result",
        "error_handling": "What to do if this fails"
      }}
    ]
    }}
  ]
}}

Return ONLY valid JSON, no markdown formatting."""

				response = client.models.generate_content(
					model="gemini-2.5-flash",  # Updated to newer model
					contents=prompt
				)
				content_text = response.text

				# Try to extract JSON
				try:
					data = json.loads(content_text)
				except json.JSONDecodeError:
					import re
					json_match = re.search(r'```json\s*(.*?)\s*```', content_text, re.DOTALL)
					if json_match:
						data = json.loads(json_match.group(1))
					else:
						logger.warning("Could not parse Gemini response as JSON")
						return []

				# Handle both direct array and wrapped in object
				if isinstance(data, list):
					workflows_data = data
				elif isinstance(data, dict) and 'workflows' in data:
					workflows_data = data['workflows']
				elif isinstance(data, dict):
					workflows_data = [data]
				else:
					workflows_data = []

				for wf_data in workflows_data:
					steps = []
					for step_data in wf_data.get('steps', []):
						step = WorkflowStep(
							step_number=step_data.get('step_number', 0),
							action=step_data.get('action', ''),
							screen=step_data.get('screen', 'Unknown'),
							precondition=step_data.get('precondition'),
							postcondition=step_data.get('postcondition'),
							error_handling=step_data.get('error_handling'),
						)
						steps.append(step)

					workflow = OperationalWorkflow(
						workflow_id=str(uuid4()),
						name=wf_data.get('name', 'Unknown Workflow'),
						description=wf_data.get('description', ''),
						business_function=wf_data.get('business_function', business_function or 'General'),
						business_reasoning=wf_data.get('business_reasoning'),
						business_impact=wf_data.get('business_impact'),
						business_requirements=wf_data.get('business_requirements', []),
						steps=steps,
						metadata={'extraction_method': 'gemini', 'website_id': self.website_id}
					)
					workflows.append(workflow)

				logger.info(f"✅ Extracted {len(workflows)} workflows using Gemini")
				return workflows

			except Exception as e:
				logger.warning(f"Gemini extraction failed: {e}")

		# If both fail, return empty list
		logger.warning("No LLM available for workflow extraction")
		return []
