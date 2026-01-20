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
	from google import genai
	from PIL import Image

	# Create client with API key
	client = genai.Client(api_key=google_key)

	prompt = """Analyze this video frame COMPREHENSIVELY and identify ALL features:

IMPORTANT: Return ONLY valid JSON. Do not include markdown formatting or explanatory text. Start directly with { and end with }.

JSON structure:

1. **ALL Visible UI elements** (buttons, forms, menus, text fields, navigation, icons, images, logos, headers, footers, sidebars, modals, tooltips, badges, labels, links, dropdowns, checkboxes, radio buttons, sliders, progress bars, tabs, breadcrumbs, search bars, filters, pagination, notifications, alerts, dialogs, popups)
2. **Current screen/page state** (exact screen name, page type, application state)
3. **ALL user interactions visible** (cursor position, highlighted elements, hover states, active states, focus states, selected items, expanded/collapsed states)
4. **Business context** (what business function is being demonstrated? what domain/application?)
5. **Operational aspects** (what operational workflow step is this? what process?)
6. **ALL visible text** (extract every piece of text visible on screen - labels, headings, body text, button text, form placeholders, error messages, tooltips, notifications)
7. **Layout and structure** (page layout, sections, columns, regions)
8. **Visual indicators** (loading states, success indicators, error states, warning states, info states)
9. **Data visible** (tables, lists, cards, any displayed data)
10. **Navigation elements** (menus, breadcrumbs, tabs, pagination, back/forward buttons)

Return a JSON object with:
- ui_elements: array of {type, label, position, state} - include EVERY element
- screen_state: string (exact screen name)
- business_function: string
- operational_aspect: string
- visible_actions: array of strings (all visible interactions)
- visible_text: string (all text visible on screen)
- layout_structure: string (description of page layout)
- data_elements: array of {type, content} (tables, lists, etc.)
- visual_indicators: array of {type, message} (loading, errors, etc.)

CRITICAL: Return ONLY valid JSON without markdown code blocks. Start with { and end with }. Be COMPREHENSIVE - do not miss any features!"""

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

	# Validate and normalize using Pydantic model
	if analysis_dict:
		try:
			frame_analysis = FrameAnalysisResponse.from_dict(analysis_dict)
			analysis_dict = frame_analysis.model_dump()
		except Exception as e:
			logger.warning(f"Failed to validate frame analysis with Pydantic model for {timestamp}s: {e}")
			logger.debug(f"Raw analysis dict: {analysis_dict}")
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
		# Check both GOOGLE_API_KEY and GEMINI_API_KEY
		google_key = os.getenv('GOOGLE_API_KEY') or os.getenv('GEMINI_API_KEY')
		if not google_key:
			logger.warning(f"No Gemini API key available (GOOGLE_API_KEY or GEMINI_API_KEY) for frame {timestamp}s")
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
