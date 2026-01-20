"""
Frame analysis formatting.

Formats frame analysis results as readable text.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def format_frame_analysis(frame_analysis: dict[str, Any]) -> str:
	"""Format frame analysis as readable text."""
	timestamp = frame_analysis.get('timestamp', 0)
	screen_state = frame_analysis.get('screen_state', 'Unknown')
	business_function = frame_analysis.get('business_function', '')
	operational_aspect = frame_analysis.get('operational_aspect', '')
	ui_elements = frame_analysis.get('ui_elements', [])
	visible_actions = frame_analysis.get('visible_actions', [])
	visible_text = frame_analysis.get('visible_text', '')

	text = f"""# Frame Analysis at {timestamp:.2f}s

## Screen State
- **Current Screen**: {screen_state}

## Business Context
- **Business Function**: {business_function}
- **Operational Aspect**: {operational_aspect}

## UI Elements
"""
	for element in ui_elements:
		if isinstance(element, dict):
			element_type = element.get('type', 'element')
			element_label = element.get('label', 'Unknown')
		else:
			element_type = getattr(element, 'type', 'element')
			element_label = getattr(element, 'label', 'Unknown')
		text += f"- **{element_type}**: {element_label}\n"

	if visible_actions:
		text += "\n## Visible Actions\n"
		for action in visible_actions:
			text += f"- {action}\n"

	# Add visible text if available (OCR)
	if visible_text:
		text += f"\n## Visible Text (OCR)\n{visible_text}\n"

	return text
