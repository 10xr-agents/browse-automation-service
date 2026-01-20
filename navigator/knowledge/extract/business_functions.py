"""
Business function extraction from video content.

Extracts business functions and operational aspects from video demonstrations
using LLM analysis of transcription, frame analysis, and action sequences.
"""

import json
import logging
import os
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from navigator.schemas import ContentChunk

logger = logging.getLogger(__name__)


class BusinessFunction(BaseModel):
	"""Business function definition."""
	business_function_id: str = Field(..., description="Unique identifier")
	name: str = Field(..., description="Business function name")
	category: str = Field(..., description="Category (User Management, Order Processing, etc.)")
	description: str = Field(..., description="Description of what this business function does")
	business_reasoning: str | None = Field(None, description="Why this function exists, what problem it solves, business rationale")
	business_impact: str | None = Field(None, description="Business value, impact, or outcomes of this function")
	business_requirements: list[str] = Field(default_factory=list, description="Explicit business requirements that led to this function")
	operational_aspects: list[str] = Field(default_factory=list, description="Operational aspects (technical requirements, validations, side effects)")
	workflow_steps: list[str] = Field(default_factory=list, description="High-level workflow steps")
	metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

	# Cross-reference fields (Phase 1: Schema Updates)
	related_user_flows: list[str] = Field(
		default_factory=list,
		description="User flow IDs that implement this business function"
	)
	related_screens: list[str] = Field(
		default_factory=list,
		description="Screen IDs used by this business function"
	)
	related_tasks: list[str] = Field(
		default_factory=list,
		description="Task IDs that support this business function"
	)
	related_workflows: list[str] = Field(
		default_factory=list,
		description="Workflow IDs that implement this business function"
	)
	related_actions: list[str] = Field(
		default_factory=list,
		description="Action IDs used in this business function"
	)


class BusinessFunctionExtractionResult(BaseModel):
	"""Result of business function extraction."""
	business_functions: list[BusinessFunction] = Field(default_factory=list)
	success: bool = True
	errors: list[str] = Field(default_factory=list)
	statistics: dict[str, Any] = Field(default_factory=dict)

	def calculate_statistics(self):
		"""Calculate extraction statistics."""
		self.statistics = {
			'total_functions': len(self.business_functions),
			'categories': list(set(bf.category for bf in self.business_functions)),
		}

	def add_error(self, error_type: str, error_message: str, error_context: dict[str, Any] | None = None):
		"""Add an error to the result."""
		error_str = f"{error_type}: {error_message}"
		if error_context:
			error_str += f" (Context: {error_context})"
		self.errors.append(error_str)
		self.success = False


class BusinessFunctionExtractor:
	"""
	Extracts business functions from video content.
	
	Uses OpenAI or Gemini LLM to analyze:
	- Transcription for business keywords
	- Action sequences for workflows
	- Frame analysis for UI context
	"""

	def __init__(self, website_id: str = "unknown"):
		"""
		Initialize business function extractor.
		
		Args:
			website_id: Website identifier for extracted functions
		"""
		self.website_id = website_id

	def extract_business_functions(
		self,
		content_chunks: list[ContentChunk]
	) -> BusinessFunctionExtractionResult:
		"""
		Extract business functions from content chunks.
		
		Supports all source types:
		- Video: transcription, frame analysis, action chunks
		- Documentation: documentation chunks (MD, PDF, DOCX, HTML, TXT)
		- Website: webpage chunks (from Browser-Use crawling)
		- Crawl4AI: documentation chunks (from Crawl4AI crawling)
		- Exploration: exploration chunks (from page exploration)
		
		Args:
			content_chunks: Content chunks from any ingestion source
		
		Returns:
			BusinessFunctionExtractionResult with extracted functions
		"""
		result = BusinessFunctionExtractionResult()

		try:
			logger.info(f"Extracting business functions from {len(content_chunks)} content chunks")

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
				logger.warning("No relevant content found for business function extraction")
				return result

			# Extract business functions using LLM
			business_functions = self._extract_with_llm(
				combined_content,
				documentation_chunks=documentation_chunks,
				summary_chunks=summary_chunks
			)
			result.business_functions = business_functions

			# Calculate statistics
			result.calculate_statistics()

			logger.info(
				f"✅ Extracted {result.statistics['total_functions']} business functions "
				f"({len(result.statistics['categories'])} categories)"
			)

		except Exception as e:
			logger.error(f"❌ Error extracting business functions: {e}", exc_info=True)
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
		documentation_chunks: list[ContentChunk] | None = None,
		summary_chunks: list[ContentChunk] | None = None
	) -> list[BusinessFunction]:
		"""Extract business functions using OpenAI or Gemini LLM."""
		business_functions = []

		# Try OpenAI first
		openai_key = os.getenv('OPENAI_API_KEY')
		if openai_key:
			try:
				from openai import OpenAI
				client = OpenAI(api_key=openai_key)

				# Determine content type for better prompting
				has_docs = (documentation_chunks is not None and len(documentation_chunks) > 0) or (summary_chunks is not None and len(summary_chunks) > 0)
				content_type = "documentation" if has_docs else "video"

				# Use documentation_chunks and summary_chunks from method parameters
				doc_chunks = documentation_chunks if documentation_chunks is not None else []
				sum_chunks = summary_chunks if summary_chunks is not None else []

				prompt = f"""Analyze this {content_type} content and extract business functions and operational aspects.

Content:
{content[:12000]}  # Increased limit for documentation

Identify ALL business functions described or demonstrated:
1. Business functions (e.g., User Management, Order Processing, Content Management, Data Analysis, Reporting, Configuration, Authentication, Authorization, Payment Processing, Inventory Management, Customer Support, Analytics, Data Export/Import, System Administration, etc.)
2. Business reasoning (EXTENSIVE: why this function exists, what problem it solves, business rationale - provide detailed multi-paragraph explanation covering business context, problem statement, stakeholders affected, historical context if relevant)
3. Business impact (EXTENSIVE: business value, impact, or outcomes of this function - provide detailed analysis covering quantitative/qualitative benefits, ROI considerations, user experience impact, competitive advantages, long-term strategic value)
4. Business requirements (EXTENSIVE list: explicit requirements that led to this function - provide comprehensive list with detailed explanations for each requirement, regulatory/compliance needs, user needs, business objectives)
5. Operational aspects (technical requirements, validations, side effects, dependencies)
6. High-level workflow steps for each function
7. Business rules and constraints
8. Integration points and dependencies
9. Data models and entities
10. API endpoints and services
11. Security and access control requirements

IMPORTANT: For business_reasoning, business_impact, and business_requirements - provide EXTENSIVE, DETAILED explanations (multiple paragraphs, not just short statements). These should comprehensively explain the business context, value proposition, and requirements that justify the function's existence.

Be COMPREHENSIVE - extract ALL business functions mentioned in the content. Don't miss any function.

Return a JSON object with a "business_functions" key containing an array of business functions with this structure:
{{
  "business_functions": [
    {{
      "name": "Function Name",
      "category": "Category (User Management, Order Processing, etc.)",
      "description": "Description of what this function does",
      "business_reasoning": "EXTENSIVE multi-paragraph explanation: Why this function exists, what problem it solves, business rationale - include business context, problem statement, stakeholders, historical context",
      "business_impact": "EXTENSIVE multi-paragraph analysis: Business value, impact, outcomes - include quantitative/qualitative benefits, ROI, user experience impact, competitive advantages, strategic value",
      "business_requirements": ["Detailed requirement 1 with explanation", "Detailed requirement 2 with explanation", ...],
      "operational_aspects": ["aspect1", "aspect2"],
      "workflow_steps": ["step1", "step2", "step3"]
    }}
  ]
}}

Return ONLY valid JSON, no markdown formatting."""

				response = client.chat.completions.create(
					model="gpt-4o",
					messages=[
						{"role": "system", "content": f"You are an expert at analyzing business processes and extracting business functions from {content_type} content. Be comprehensive and don't miss any business functions."},
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
					functions_data = data
				elif isinstance(data, dict) and 'business_functions' in data:
					functions_data = data['business_functions']
				elif isinstance(data, dict):
					functions_data = [data]
				else:
					functions_data = []

				for func_data in functions_data:
					business_function = BusinessFunction(
						business_function_id=str(uuid4()),
						name=func_data.get('name', 'Unknown'),
						category=func_data.get('category', 'General'),
						description=func_data.get('description', ''),
						business_reasoning=func_data.get('business_reasoning'),
						business_impact=func_data.get('business_impact'),
						business_requirements=func_data.get('business_requirements', []),
						operational_aspects=func_data.get('operational_aspects', []),
						workflow_steps=func_data.get('workflow_steps', []),
						metadata={'extraction_method': 'openai', 'website_id': self.website_id}
					)
					business_functions.append(business_function)

				logger.info(f"✅ Extracted {len(business_functions)} business functions using OpenAI")
				return business_functions

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

				prompt = f"""Analyze this {content_type} content and extract business functions and operational aspects.

Content:
{content[:12000]}  # Increased limit for documentation

Identify ALL business functions described or demonstrated:
1. Business functions (e.g., User Management, Order Processing, Content Management, Data Analysis, Reporting, Configuration, Authentication, Authorization, Payment Processing, Inventory Management, Customer Support, Analytics, Data Export/Import, System Administration, etc.)
2. Business reasoning (EXTENSIVE: why this function exists, what problem it solves, business rationale - provide detailed multi-paragraph explanation covering business context, problem statement, stakeholders affected, historical context if relevant)
3. Business impact (EXTENSIVE: business value, impact, or outcomes of this function - provide detailed analysis covering quantitative/qualitative benefits, ROI considerations, user experience impact, competitive advantages, long-term strategic value)
4. Business requirements (EXTENSIVE list: explicit requirements that led to this function - provide comprehensive list with detailed explanations for each requirement, regulatory/compliance needs, user needs, business objectives)
5. Operational aspects (technical requirements, validations, side effects, dependencies)
6. High-level workflow steps for each function
7. Business rules and constraints
8. Integration points and dependencies
9. Data models and entities
10. API endpoints and services
11. Security and access control requirements

IMPORTANT: For business_reasoning, business_impact, and business_requirements - provide EXTENSIVE, DETAILED explanations (multiple paragraphs, not just short statements). These should comprehensively explain the business context, value proposition, and requirements that justify the function's existence.

Be COMPREHENSIVE - extract ALL business functions mentioned in the content. Don't miss any function.

Return a JSON array of business functions with this structure:
[
  {{
    "name": "Function Name",
    "category": "Category (User Management, Order Processing, etc.)",
    "description": "Description of what this function does",
    "business_reasoning": "EXTENSIVE multi-paragraph explanation: Why this function exists, what problem it solves, business rationale - include business context, problem statement, stakeholders, historical context",
    "business_impact": "EXTENSIVE multi-paragraph analysis: Business value, impact, outcomes - include quantitative/qualitative benefits, ROI, user experience impact, competitive advantages, strategic value",
    "business_requirements": ["Detailed requirement 1 with explanation", "Detailed requirement 2 with explanation", ...],
    "operational_aspects": ["aspect1", "aspect2"],
    "workflow_steps": ["step1", "step2", "step3"]
  }}
]

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
					functions_data = data
				elif isinstance(data, dict) and 'business_functions' in data:
					functions_data = data['business_functions']
				elif isinstance(data, dict):
					functions_data = [data]
				else:
					functions_data = []

				for func_data in functions_data:
					business_function = BusinessFunction(
						business_function_id=str(uuid4()),
						name=func_data.get('name', 'Unknown'),
						category=func_data.get('category', 'General'),
						description=func_data.get('description', ''),
						business_reasoning=func_data.get('business_reasoning'),
						business_impact=func_data.get('business_impact'),
						business_requirements=func_data.get('business_requirements', []),
						operational_aspects=func_data.get('operational_aspects', []),
						workflow_steps=func_data.get('workflow_steps', []),
						metadata={'extraction_method': 'gemini', 'website_id': self.website_id}
					)
					business_functions.append(business_function)

				logger.info(f"✅ Extracted {len(business_functions)} business functions using Gemini")
				return business_functions

			except Exception as e:
				logger.warning(f"Gemini extraction failed: {e}")

		# If both fail, return empty list
		logger.warning("No LLM available for business function extraction")
		return []
