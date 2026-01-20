"""
Action sequence extraction from frame analyses.

Compares consecutive frames to detect actions (clicks, typing, navigation, scrolling)
and extracts actions from transcription/subtitle keywords.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def extract_action_sequence(
	frame_analyses: list[dict[str, Any]],
	transcription_data: dict[str, Any] | None = None,
	subtitle_data: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
	"""
	Extract action sequence from frame analyses and transcription.
	
	Compares consecutive frames to detect actions (clicks, typing, navigation, scrolling).
	Also extracts actions from transcription/subtitle keywords.
	
	Args:
		frame_analyses: List of frame analysis dictionaries
		transcription_data: Optional transcription data with segments
		subtitle_data: Optional subtitle data with segments
	
	Returns:
		List of action dictionaries with timestamp, type, target, context
	"""
	actions = []

	try:
		# Sort frame analyses by timestamp
		sorted_frames = sorted(frame_analyses, key=lambda x: x.get('timestamp', 0))

		# Extract actions from frame comparisons
		for i in range(len(sorted_frames) - 1):
			prev_frame = sorted_frames[i]
			next_frame = sorted_frames[i + 1]

			prev_screen = prev_frame.get('screen_state', 'Unknown')
			next_screen = next_frame.get('screen_state', 'Unknown')
			prev_ui = prev_frame.get('ui_elements', [])
			next_ui = next_frame.get('ui_elements', [])

			# Detect screen transitions (navigation)
			if prev_screen != next_screen and next_screen != 'Unknown':
				frame_time = next_frame.get('timestamp', 0)
				actions.append({
					'timestamp': frame_time,
					'action_type': 'navigation',
					'target': next_screen,
					'screen': next_screen,
					'context': f"Navigated from {prev_screen} to {next_screen}",
					'business_function': next_frame.get('business_function', ''),
				})

			# Detect UI element changes (clicks, interactions)
			if len(next_ui) != len(prev_ui) or any(
				next_elem.get('state') != prev_elem.get('state')
				for next_elem, prev_elem in zip(next_ui[:min(len(next_ui), len(prev_ui))], prev_ui[:min(len(next_ui), len(prev_ui))])
			):
				frame_time = next_frame.get('timestamp', 0)
				# Find changed elements
				changed_elements = [e for e in next_ui if e not in prev_ui]
				if changed_elements:
					target = changed_elements[0].get('label', 'UI Element') if isinstance(changed_elements[0], dict) else 'UI Element'
					actions.append({
						'timestamp': frame_time,
						'action_type': 'interaction',
						'target': target,
						'screen': next_screen,
						'context': f"UI element changed: {target}",
						'business_function': next_frame.get('business_function', ''),
					})

		# Extract actions from transcription
		if transcription_data:
			segments = transcription_data.get('segments', [])
			for segment in segments:
				segment_text = segment.get('text', '').lower()
				# Look for action keywords in transcription
				if any(keyword in segment_text for keyword in ['click', 'type', 'enter', 'fill', 'navigate', 'go to', 'select', 'choose']):
					# Find corresponding frame
					segment_start = segment.get('start', 0)
					next_frame = next((f for f in sorted_frames if f.get('timestamp', 0) >= segment_start), None)
					if next_frame:
						frame_time = next_frame.get('timestamp', 0)
						next_screen = next_frame.get('screen_state', 'Unknown')
						actions.append({
							'timestamp': frame_time,
							'action_type': 'interaction',
							'target': 'UI Element',
							'screen': next_screen,
							'context': segment['text'],
							'business_function': next_frame.get('business_function', ''),
						})

		# Extract actions from subtitles
		if subtitle_data:
			subtitles = subtitle_data.get('subtitles', [])
			for subtitle in subtitles:
				subtitle_text = subtitle.get('text', '').lower()
				if any(keyword in subtitle_text for keyword in ['click', 'type', 'enter', 'fill', 'navigate', 'go to']):
					subtitle_start = subtitle.get('start', 0)
					next_frame = next((f for f in sorted_frames if f.get('timestamp', 0) >= subtitle_start), None)
					if next_frame:
						frame_time = next_frame.get('timestamp', 0)
						next_screen = next_frame.get('screen_state', 'Unknown')
						actions.append({
							'timestamp': frame_time,
							'action_type': 'interaction',
							'target': 'UI Element',
							'screen': next_screen,
							'context': subtitle['text'],
							'business_function': next_frame.get('business_function', ''),
							'source': 'subtitle',
						})

		# Deduplicate actions (same timestamp + type)
		seen = set()
		deduplicated = []
		for action in actions:
			key = (action['timestamp'], action['action_type'], action.get('target', ''))
			if key not in seen:
				seen.add(key)
				deduplicated.append(action)

		logger.info(f"🎬 Extracted {len(deduplicated)} unique actions from {len(actions)} detected actions")
		return deduplicated

	except Exception as e:
		logger.warning(f"Action extraction failed: {e}", exc_info=True)
		return []
