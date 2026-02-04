"""
Frame vision analysis using Gemini Vision.

Analyzes video frames using Gemini Vision LLM to extract UI elements, screen states,
business context, and visible text (OCR).
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from tenacity import (
	retry,
	retry_if_exception,
	stop_after_attempt,
	wait_exponential,
)

from navigator.schemas import FrameAnalysisResponse

logger = logging.getLogger(__name__)

# Global client cache to reuse Gemini client across frame analyses (improves performance)
_gemini_client_cache: dict[str, Any] = {}


def _get_gemini_client(google_key: str):
	"""Get or create cached Gemini client for API key (reuse client for better performance)."""
	global _gemini_client_cache
	if google_key not in _gemini_client_cache:
		from google import genai
		_gemini_client_cache[google_key] = genai.Client(api_key=google_key)
	return _gemini_client_cache[google_key]


def _is_503_unavailable_error(exception: Exception) -> bool:
	"""Check if exception is a 503 UNAVAILABLE error from Gemini API."""
	if hasattr(exception, 'error') and isinstance(exception.error, dict):
		error_info = exception.error
		if error_info.get('code') == 503 or error_info.get('status') == 'UNAVAILABLE':
			return True
	# Also check if error message contains 503 or UNAVAILABLE
	error_str = str(exception)
	if '503' in error_str or 'UNAVAILABLE' in error_str or 'overloaded' in error_str.lower():
		return True
	return False


@retry(
	stop=stop_after_attempt(6),  # Initial attempt + 5 retries = 6 total (30 minutes)
	wait=wait_exponential(multiplier=300, min=300, max=300),  # 5 minutes (300 seconds) between retries
	retry=retry_if_exception(_is_503_unavailable_error),
	reraise=True  # Reraise so outer function can catch and log properly
)


async def _analyze_frame_with_retry(
	frame_path: Path,
	timestamp: float,
	google_key: str
) -> dict[str, Any] | None:
	"""Internal function with retry logic for 503 errors."""
	from PIL import Image

	# Reuse cached client instead of creating new one per frame (better performance)
	client = _get_gemini_client(google_key)

	prompt = """Analyze this video frame COMPREHENSIVELY and identify ALL features:

IMPORTANT: Return ONLY valid JSON. Do not include markdown formatting or explanatory text. Start directly with { and end with }.

JSON structure:

1. **ALL Visible UI elements** (buttons, forms, menus, text fields, navigation, icons, images, logos, headers, footers, sidebars, modals, tooltips, badges, labels, links, dropdowns, checkboxes, radio buttons, sliders, progress bars, tabs, breadcrumbs, search bars, filters, pagination, notifications, alerts, dialogs, popups)
   - For EACH element, provide position as {x, y, width, height, bounding_box: {x, y, width, height}}
   - x, y: Top-left corner coordinates (pixels from top-left of frame)
   - width, height: Element dimensions in pixels
   - bounding_box: Same as position (for consistency)
   - Estimate position visually - be as accurate as possible
2. **Current screen/page state** (exact screen name, page type, application state)
3. **ALL user interactions visible** (cursor position, highlighted elements, hover states, active states, focus states, selected items, expanded/collapsed states)
4. **Business context** (what business function is being demonstrated? what domain/application?)
5. **Operational aspects** (what operational workflow step is this? what process?)
6. **ALL visible text** (extract every piece of text visible on screen - labels, headings, body text, button text, form placeholders, error messages, tooltips, notifications)
7. **Layout and structure** (Phase 5.2: Extract structured layout information)
   - layout_type: "grid" | "flexbox" | "columns" | "standard"
   - columns: number (1, 2, 3, etc.)
   - regions: array of {type: "header"|"sidebar"|"main"|"footer"|"modal"|"navigation", bounds: {x, y, width, height}}
   - sections: array of section names/descriptions
8. **Visual hierarchy** (Phase 5.2: Extract visual importance)
   - For each UI element, estimate importance_score (0.0-1.0):
     - 1.0 = Most important (primary actions, main content)
     - 0.7-0.9 = Important (navigation, key features)
     - 0.4-0.6 = Moderate (secondary actions, supporting content)
     - 0.1-0.3 = Low (footer links, decorative elements)
   - Consider: size, position (top/center = more important), visual prominence
9. **Visual indicators** (loading states, success indicators, error states, warning states, info states)
10. **Data visible** (tables, lists, cards, any displayed data)
11. **Navigation elements** (menus, breadcrumbs, tabs, pagination, back/forward buttons)

Return a JSON object with:
- ui_elements: array of {type, label, position: {x, y, width, height, bounding_box: {x, y, width, height}}, state, importance_score: 0.0-1.0, layout_context: "header"|"sidebar"|"main"|"footer"|"modal"|"navigation"} - include EVERY element with position data
- screen_state: string (exact screen name)
- business_function: string
- operational_aspect: string
- visible_actions: array of strings (all visible interactions)
- visible_text: string (all text visible on screen)
- layout_structure: object {layout_type, columns, regions: [{type, bounds: {x, y, width, height}}], sections: []} (Phase 5.2: structured layout data)
- visual_hierarchy: object {elements: [{element_label, importance_score, visual_properties: {size, position, prominence}}]} (Phase 5.2: visual hierarchy data)
- data_elements: array of {type, content} (tables, lists, etc.)
- visual_indicators: array of {type, message} (loading, errors, etc.)

CRITICAL: 
- Return ONLY valid JSON without markdown code blocks. Start with { and end with }.
- Be COMPREHENSIVE - do not miss any features!
- Phase 5.2: For position data, estimate pixel coordinates based on frame dimensions. If frame is 1920x1080, provide coordinates relative to that.
- Phase 5.2: Include importance_score and layout_context for EVERY ui_element.
- Phase 5.2: Provide structured layout_structure object, not just a string description."""

	# Open PIL Image and pass directly to SDK
	with Image.open(frame_path) as img:
		response = client.models.generate_content(
			model="gemini-2.5-flash",
			contents=[prompt, img]
		)

	content = response.text

	if not content:
		logger.warning(f"Gemini returned empty content for frame {timestamp}s")
		return None

	# Parse and validate JSON response
	analysis_dict = None

	# Step 1: Try direct JSON parsing
	try:
		analysis_dict = json.loads(content)
	except json.JSONDecodeError:
		# Step 2: Try to extract JSON from markdown code blocks
		text = content.strip()

		# Try ```json ... ``` first
		if text.startswith('```json') and '```' in text:
			text = text[7:]
			if text.endswith('```'):
				text = text[:-3].strip()
			else:
				json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
				if json_match:
					text = json_match.group(1).strip()
		# Try plain ``` ... ``` code block
		elif text.startswith('```') and text.count('```') >= 2:
			if text.endswith('```'):
				text = text[3:-3].strip()
			else:
				json_match = re.search(r'```\s*(.*?)\s*```', content, re.DOTALL)
				if json_match:
					text = json_match.group(1).strip()

		# Step 3: Try to find JSON object/array in the text
		if not analysis_dict:
			json_obj_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
			if json_obj_match:
				text = json_obj_match.group(0)

		# Step 4: Try parsing the extracted/cleaned text
		try:
			analysis_dict = json.loads(text)
		except json.JSONDecodeError:
			# Step 5: Last resort - find JSON between first { and last }
			first_brace = text.find('{')
			if first_brace >= 0:
				brace_count = 0
				for i in range(first_brace, len(text)):
					if text[i] == '{':
						brace_count += 1
					elif text[i] == '}':
						brace_count -= 1
						if brace_count == 0:
							json_str = text[first_brace:i+1]
							try:
								analysis_dict = json.loads(json_str)
								break
							except json.JSONDecodeError:
								pass

			if not analysis_dict:
				logger.warning(f"Failed to parse JSON from LLM response for frame {timestamp}s. Attempted multiple extraction methods.")
				logger.debug(f"Raw response (first 500 chars): {content[:500]}")

	# Phase 5.2: Post-process spatial information from frame analysis
	if analysis_dict:
		# Normalize position data in ui_elements
		if 'ui_elements' in analysis_dict and isinstance(analysis_dict['ui_elements'], list):
			for element in analysis_dict['ui_elements']:
				if isinstance(element, dict):
					# Ensure position has proper structure
					if 'position' in element and isinstance(element['position'], dict):
						pos = element['position']
						# Ensure bounding_box exists
						if 'bounding_box' not in pos and all(k in pos for k in ['x', 'y', 'width', 'height']):
							element['position']['bounding_box'] = {
								'x': pos.get('x', 0),
								'y': pos.get('y', 0),
								'width': pos.get('width', 0),
								'height': pos.get('height', 0),
							}
					
					# Normalize importance_score
					if 'importance_score' in element:
						try:
							score = float(element['importance_score'])
							element['importance_score'] = max(0.0, min(1.0, score))
						except (ValueError, TypeError):
							element['importance_score'] = None
					
					# Normalize layout_context
					if 'layout_context' in element and element['layout_context']:
						valid_contexts = ['header', 'sidebar', 'main', 'footer', 'modal', 'navigation']
						if element['layout_context'].lower() not in valid_contexts:
							# Try to infer from position
							if element.get('position') and isinstance(element['position'], dict):
								x = element['position'].get('x', 0)
								y = element['position'].get('y', 0)
								if y < 100:
									element['layout_context'] = 'header'
								elif x < 300:
									element['layout_context'] = 'sidebar'
								elif y > 930:
									element['layout_context'] = 'footer'
								else:
									element['layout_context'] = 'main'
		
		# Normalize layout_structure (convert string to dict if needed)
		if 'layout_structure' in analysis_dict:
			layout = analysis_dict['layout_structure']
			if isinstance(layout, str) and layout:
				# Try to parse structured layout from string description
				# For now, keep as string but log for future enhancement
				logger.debug(f"Layout structure is string, not structured object for frame {timestamp}s")
			elif isinstance(layout, dict):
				# Ensure required fields exist
				if 'layout_type' not in layout:
					layout['layout_type'] = 'standard'
				if 'columns' not in layout:
					layout['columns'] = 1
				if 'regions' not in layout:
					layout['regions'] = []
				if 'sections' not in layout:
					layout['sections'] = []
		
		# Normalize visual_hierarchy
		if 'visual_hierarchy' in analysis_dict and isinstance(analysis_dict['visual_hierarchy'], dict):
			vh = analysis_dict['visual_hierarchy']
			if 'elements' in vh and isinstance(vh['elements'], list):
				for vh_elem in vh['elements']:
					if isinstance(vh_elem, dict) and 'importance_score' in vh_elem:
						try:
							score = float(vh_elem['importance_score'])
							vh_elem['importance_score'] = max(0.0, min(1.0, score))
						except (ValueError, TypeError):
							vh_elem['importance_score'] = None

	# Validate and normalize using Pydantic model
	if analysis_dict:
		try:
			frame_analysis = FrameAnalysisResponse.from_dict(analysis_dict)
			analysis_dict = frame_analysis.model_dump()
		except Exception as e:
			logger.warning(f"Failed to validate frame analysis with Pydantic model for {timestamp}s: {e}")
			logger.debug(f"Raw analysis dict: {analysis_dict}")
			# Phase 5.2: Try to preserve spatial data even if validation fails
			if 'ui_elements' in analysis_dict:
				# Keep ui_elements with spatial info even if validation fails
				pass
	else:
		# Fallback: create minimal structured response
		logger.warning(f"Could not parse JSON from LLM response for frame {timestamp}s, using fallback")
		analysis_dict = {
			'ui_elements': [],
			'screen_state': 'Unknown',
			'business_function': content[:200] if len(content) > 0 else 'Unknown',
			'operational_aspect': '',
			'visible_actions': [],
			'visible_text': content[:500] if len(content) > 0 else '',
			'layout_structure': None,
			'visual_hierarchy': None,
			'data_elements': [],
			'visual_indicators': [],
		}

	return {
		'timestamp': timestamp,
		'frame_path': str(frame_path),
		'provider': 'gemini',
		**analysis_dict
	}


async def analyze_frame_with_vision(
	frame_path: Path,
	timestamp: float
) -> dict[str, Any] | None:
	"""Analyze a single frame using Gemini Vision with retry logic for 503 errors.
	
	When encountering 503 UNAVAILABLE errors (model overloaded), this function will:
	- Wait 5 minutes between retries
	- Retry for up to 30 minutes (6 attempts total: initial + 5 retries)
	- Return None if all retries are exhausted
	"""
	try:
		# Use GOOGLE_API_KEY (standardized - GEMINI_API_KEY is deprecated)
		google_key = os.getenv('GOOGLE_API_KEY')
		if not google_key:
			logger.warning(f"No Gemini API key available (GOOGLE_API_KEY) for frame {timestamp}s")
			return None

		try:
			# Call the retry-enabled function
			result = await _analyze_frame_with_retry(frame_path, timestamp, google_key)
			return result
		except Exception as e:
			# If all retries exhausted and it's still a 503 error, log and return None
			if _is_503_unavailable_error(e):
				logger.warning(
					f"Gemini Vision analysis failed for frame {timestamp}s after 30 minutes of retries (6 attempts): {e}. "
					f"Model is still overloaded. Skipping this frame."
				)
			else:
				logger.warning(f"Gemini Vision analysis failed for frame {timestamp}s: {e}")
			return None

	except Exception as e:
		logger.warning(f"Frame analysis failed for {timestamp}s: {e}")
		return None
