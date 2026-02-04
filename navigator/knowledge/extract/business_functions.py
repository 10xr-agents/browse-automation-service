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
		Phase 5.3: Combine content chunks into a single text for LLM analysis.
		
		Enhanced to prioritize documentation content and extract business context.
		
		Supports both video content (transcription, frames, actions) and
		documentation content (text, tables, structure).
		"""
		content_parts = []

		# Phase 5.3: Prioritize documentation content for business context extraction
		if documentation_chunks:
			content_parts.append("# Document Content (Primary Source for Business Context)\n")
			content_parts.append("IMPORTANT: This documentation contains business functions, features, requirements, and reasoning.\n")
			content_parts.append("Extract ALL business context including:\n")
			content_parts.append("- Business functions and their purposes\n")
			content_parts.append("- Business features and capabilities\n")
			content_parts.append("- Business requirements (regulatory, user needs, business objectives)\n")
			content_parts.append("- Business reasoning (why features exist, problems they solve)\n")
			content_parts.append("- Links to web UI screens (screens mentioned in documentation)\n\n")
			
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

				# Phase 3.4: Enhanced prompt for comprehensive business details extraction
				prompt = f"""Analyze this {content_type} content and extract business functions and operational aspects.

Content:
{content[:12000]}  # Increased limit for documentation

Identify ALL business functions described or demonstrated:
1. Business functions (e.g., User Management, Order Processing, Content Management, Data Analysis, Reporting, Configuration, Authentication, Authorization, Payment Processing, Inventory Management, Customer Support, Analytics, Data Export/Import, System Administration, etc.)
2. Business reasoning (EXTENSIVE: why this function exists, what problem it solves, business rationale - provide detailed multi-paragraph explanation covering business context, problem statement, stakeholders affected, historical context if relevant, market conditions, competitive landscape, business drivers)
3. Business impact (EXTENSIVE: business value, impact, or outcomes of this function - provide detailed analysis covering quantitative/qualitative benefits, ROI considerations, user experience impact, competitive advantages, long-term strategic value, revenue impact, cost savings, efficiency gains, customer satisfaction metrics)
4. Business requirements (EXTENSIVE list: explicit requirements that led to this function - provide comprehensive list with detailed explanations for each requirement, regulatory/compliance needs, user needs, business objectives, legal requirements, industry standards, scalability needs, security requirements)
5. Operational aspects (COMPREHENSIVE: technical requirements, validations, side effects, dependencies, performance requirements, error handling, monitoring needs, integration requirements, data flow, security controls, access patterns)
6. High-level workflow steps for each function
7. Business rules and constraints
8. Integration points and dependencies
9. Data models and entities
10. API endpoints and services
11. Security and access control requirements

Phase 3.4: IMPORTANT - For business_reasoning, business_impact, and business_requirements - provide EXTENSIVE, DETAILED explanations (multiple paragraphs, not just short statements). These should comprehensively explain the business context, value proposition, and requirements that justify the function's existence. Extract ALL available business details from the content, including implicit requirements and impacts that may not be explicitly stated.

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
      "workflow_steps": ["step1", "step2", "step3"],
      "screens_mentioned": ["Screen Name 1", "Screen Name 2", ...]  # Phase 5.3: Screens mentioned in documentation
    }}
  ]
}}

Phase 5.3: For documentation sources, also identify any screens, pages, or UI components mentioned in the documentation. These will be linked to actual web UI screens during knowledge processing.

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
					# Phase 3.4: Enhanced business details extraction with validation
					business_reasoning = func_data.get('business_reasoning')
					business_impact = func_data.get('business_impact')
					business_requirements = func_data.get('business_requirements', [])
					operational_aspects = func_data.get('operational_aspects', [])
					
					# Phase 3.4: Post-process and validate business details
					business_reasoning = self._enhance_business_reasoning(business_reasoning, func_data)
					business_impact = self._enhance_business_impact(business_impact, func_data)
					business_requirements = self._enhance_business_requirements(business_requirements, func_data)
					operational_aspects = self._enhance_operational_aspects(operational_aspects, func_data)
					
					# Phase 5.3: Extract screens mentioned in documentation
					screens_mentioned = func_data.get('screens_mentioned', [])
					
					business_function = BusinessFunction(
						business_function_id=str(uuid4()),
						name=func_data.get('name', 'Unknown'),
						category=func_data.get('category', 'General'),
						description=func_data.get('description', ''),
						business_reasoning=business_reasoning,
						business_impact=business_impact,
						business_requirements=business_requirements,
						operational_aspects=operational_aspects,
						workflow_steps=func_data.get('workflow_steps', []),
						metadata={
							'extraction_method': 'openai',
							'website_id': self.website_id,
							# Phase 5.3: Store screens mentioned in documentation for linking
							'screens_mentioned': screens_mentioned,
							'extracted_from': 'documentation' if has_docs else 'video'
						}
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

				# Phase 5.3: Enhanced prompt for documentation-based business context extraction
				prompt = f"""Analyze this {content_type} content and extract business functions and operational aspects.

Content:
{content[:12000]}  # Increased limit for documentation

Phase 5.3: IMPORTANT - This content is from documentation. Extract comprehensive business context:

Identify ALL business functions described or demonstrated:
1. Business functions (e.g., User Management, Order Processing, Content Management, Data Analysis, Reporting, Configuration, Authentication, Authorization, Payment Processing, Inventory Management, Customer Support, Analytics, Data Export/Import, System Administration, etc.)
2. Business reasoning (EXTENSIVE: why this function exists, what problem it solves, business rationale - provide detailed multi-paragraph explanation covering business context, problem statement, stakeholders affected, historical context if relevant, market conditions, competitive landscape, business drivers)
3. Business impact (EXTENSIVE: business value, impact, or outcomes of this function - provide detailed analysis covering quantitative/qualitative benefits, ROI considerations, user experience impact, competitive advantages, long-term strategic value, revenue impact, cost savings, efficiency gains, customer satisfaction metrics)
4. Business requirements (EXTENSIVE list: explicit requirements that led to this function - provide comprehensive list with detailed explanations for each requirement, regulatory/compliance needs, user needs, business objectives, legal requirements, industry standards, scalability needs, security requirements)
5. Operational aspects (COMPREHENSIVE: technical requirements, validations, side effects, dependencies, performance requirements, error handling, monitoring needs, integration requirements, data flow, security controls, access patterns)
6. High-level workflow steps for each function
7. Business rules and constraints
8. Integration points and dependencies
9. Data models and entities
10. API endpoints and services
11. Security and access control requirements
12. Phase 5.3: Screens mentioned in documentation - identify any screen names, page names, or UI references mentioned (e.g., "Login Screen", "Dashboard", "Settings Page") - these will be linked to actual web UI screens

Phase 3.4 & 5.3: IMPORTANT - For business_reasoning, business_impact, and business_requirements - provide EXTENSIVE, DETAILED explanations (multiple paragraphs, not just short statements). These should comprehensively explain the business context, value proposition, and requirements that justify the function's existence. Extract ALL available business details from the content, including implicit requirements and impacts that may not be explicitly stated. For documentation sources, pay special attention to business context, requirements, and reasoning that may be embedded in explanatory text.

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
    "workflow_steps": ["step1", "step2", "step3"],
    "screens_mentioned": ["Screen Name 1", "Screen Name 2", ...]  # Phase 5.3: Screens mentioned in documentation
  }}
]

Phase 5.3: For documentation sources, also identify any screens, pages, or UI components mentioned in the documentation. These will be linked to actual web UI screens during knowledge processing.

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
					# Phase 3.4: Enhanced business details extraction with validation
					business_reasoning = func_data.get('business_reasoning')
					business_impact = func_data.get('business_impact')
					business_requirements = func_data.get('business_requirements', [])
					operational_aspects = func_data.get('operational_aspects', [])
					
					# Phase 3.4: Post-process and validate business details
					business_reasoning = self._enhance_business_reasoning(business_reasoning, func_data)
					business_impact = self._enhance_business_impact(business_impact, func_data)
					business_requirements = self._enhance_business_requirements(business_requirements, func_data)
					operational_aspects = self._enhance_operational_aspects(operational_aspects, func_data)
					
					# Phase 5.3: Extract screens mentioned in documentation
					screens_mentioned = func_data.get('screens_mentioned', [])
					
					business_function = BusinessFunction(
						business_function_id=str(uuid4()),
						name=func_data.get('name', 'Unknown'),
						category=func_data.get('category', 'General'),
						description=func_data.get('description', ''),
						business_reasoning=business_reasoning,
						business_impact=business_impact,
						business_requirements=business_requirements,
						operational_aspects=operational_aspects,
						workflow_steps=func_data.get('workflow_steps', []),
						metadata={
							'extraction_method': 'gemini',
							'website_id': self.website_id,
							# Phase 5.3: Store screens mentioned in documentation for linking
							'screens_mentioned': screens_mentioned,
							'extracted_from': 'documentation' if has_docs else 'video'
						}
					)
					business_functions.append(business_function)

				logger.info(f"✅ Extracted {len(business_functions)} business functions using Gemini")
				return business_functions

			except Exception as e:
				logger.warning(f"Gemini extraction failed: {e}")

		# If both fail, return empty list
		logger.warning("No LLM available for business function extraction")
		return []
	
	def _enhance_business_reasoning(
		self,
		business_reasoning: str | None,
		func_data: dict[str, Any]
	) -> str | None:
		"""
		Phase 3.4: Enhance business reasoning extraction.
		
		Post-processes and validates business reasoning to ensure it's comprehensive.
		
		Args:
			business_reasoning: Raw business reasoning from LLM
			func_data: Full function data from LLM
		
		Returns:
			Enhanced business reasoning or None
		"""
		if not business_reasoning:
			# Try to extract from description if reasoning is missing
			description = func_data.get('description', '')
			if description and len(description) > 50:
				# Use description as fallback if it contains business context
				if any(keyword in description.lower() for keyword in ['because', 'reason', 'problem', 'need', 'purpose', 'goal']):
					return description
			return None
		
		# Ensure minimum length for quality (at least 100 chars for meaningful reasoning)
		if len(business_reasoning.strip()) < 50:
			logger.debug(f"Business reasoning too short for {func_data.get('name', 'Unknown')}, may need enhancement")
		
		# Clean up common issues
		business_reasoning = business_reasoning.strip()
		
		# Remove markdown formatting if present
		if business_reasoning.startswith('**') or business_reasoning.startswith('*'):
			business_reasoning = business_reasoning.replace('**', '').replace('*', '').strip()
		
		return business_reasoning if business_reasoning else None
	
	def _enhance_business_impact(
		self,
		business_impact: str | None,
		func_data: dict[str, Any]
	) -> str | None:
		"""
		Phase 3.4: Enhance business impact extraction.
		
		Post-processes and validates business impact to ensure it's comprehensive.
		
		Args:
			business_impact: Raw business impact from LLM
			func_data: Full function data from LLM
		
		Returns:
			Enhanced business impact or None
		"""
		if not business_impact:
			return None
		
		# Ensure minimum length for quality
		if len(business_impact.strip()) < 50:
			logger.debug(f"Business impact too short for {func_data.get('name', 'Unknown')}, may need enhancement")
		
		# Clean up common issues
		business_impact = business_impact.strip()
		
		# Remove markdown formatting if present
		if business_impact.startswith('**') or business_impact.startswith('*'):
			business_impact = business_impact.replace('**', '').replace('*', '').strip()
		
		return business_impact if business_impact else None
	
	def _enhance_business_requirements(
		self,
		business_requirements: list[str] | None,
		func_data: dict[str, Any]
	) -> list[str]:
		"""
		Phase 3.4: Enhance business requirements extraction.
		
		Post-processes and validates business requirements to ensure they're comprehensive.
		
		Args:
			business_requirements: Raw business requirements from LLM
			func_data: Full function data from LLM
		
		Returns:
			Enhanced business requirements list
		"""
		if not business_requirements:
			return []
		
		# Filter out empty or too-short requirements
		enhanced_requirements = []
		for req in business_requirements:
			if isinstance(req, str) and len(req.strip()) > 10:  # Minimum meaningful length
				req = req.strip()
				# Remove markdown formatting
				if req.startswith('- ') or req.startswith('* '):
					req = req[2:].strip()
				if req.startswith('**') or req.startswith('*'):
					req = req.replace('**', '').replace('*', '').strip()
				enhanced_requirements.append(req)
			elif isinstance(req, dict):
				# Handle dict format if LLM returns structured requirements
				req_text = req.get('requirement') or req.get('description') or str(req)
				if len(req_text.strip()) > 10:
					enhanced_requirements.append(req_text.strip())
		
		return enhanced_requirements
	
	def _enhance_operational_aspects(
		self,
		operational_aspects: list[str] | None,
		func_data: dict[str, Any]
	) -> list[str]:
		"""
		Phase 3.4: Enhance operational aspects extraction.
		
		Post-processes and validates operational aspects to ensure they're comprehensive.
		
		Args:
			operational_aspects: Raw operational aspects from LLM
			func_data: Full function data from LLM
		
		Returns:
			Enhanced operational aspects list
		"""
		if not operational_aspects:
			return []
		
		# Filter out empty or too-short aspects
		enhanced_aspects = []
		for aspect in operational_aspects:
			if isinstance(aspect, str) and len(aspect.strip()) > 5:  # Minimum meaningful length
				aspect = aspect.strip()
				# Remove markdown formatting
				if aspect.startswith('- ') or aspect.startswith('* '):
					aspect = aspect[2:].strip()
				if aspect.startswith('**') or aspect.startswith('*'):
					aspect = aspect.replace('**', '').replace('*', '').strip()
				enhanced_aspects.append(aspect)
			elif isinstance(aspect, dict):
				# Handle dict format if LLM returns structured aspects
				aspect_text = aspect.get('aspect') or aspect.get('description') or str(aspect)
				if len(aspect_text.strip()) > 5:
					enhanced_aspects.append(aspect_text.strip())
		
		return enhanced_aspects
