"""
State Diff Engine for Browser Agent

Computes structured state diffs between browser states (before/after action).
"""

import hashlib
import logging
import time
from typing import Any

from browser_use.browser.session import BrowserSession

logger = logging.getLogger(__name__)


class StateSnapshot:
	"""Simplified state snapshot for diff computation."""

	def __init__(
		self,
		url: str,
		title: str,
		dom_elements: dict[int, dict[str, Any]],  # index -> element data
		scroll_x: int = 0,
		scroll_y: int = 0,
		viewport_width: int = 1920,
		viewport_height: int = 1080,
		ready_state: str = "complete",
	):
		"""Initialize state snapshot."""
		self.url = url
		self.title = title
		self.dom_elements = dom_elements  # index -> element data
		self.scroll_x = scroll_x
		self.scroll_y = scroll_y
		self.viewport_width = viewport_width
		self.viewport_height = viewport_height
		self.ready_state = ready_state
		self.timestamp = time.time()

	def compute_hash(self) -> str:
		"""Compute hash of state snapshot."""
		state_str = f"{self.url}|{self.title}|{len(self.dom_elements)}"
		for idx in sorted(self.dom_elements.keys()):
			elem = self.dom_elements[idx]
			state_str += f"|{idx}:{elem.get('tag', '')}:{elem.get('selector', '')}"
		return hashlib.sha256(state_str.encode()).hexdigest()


class StateDiffEngine:
	"""Computes structured state diffs between browser states."""

	def __init__(self):
		"""Initialize state diff engine."""
		pass

	async def capture_state(self, browser_session: BrowserSession) -> StateSnapshot:
		"""Capture current browser state snapshot.
		
		Args:
			browser_session: BrowserSession instance
			
		Returns:
			StateSnapshot object
		"""
		# Get browser state summary
		browser_state = await browser_session.get_browser_state_summary(include_screenshot=False)

		# Extract DOM elements from selector_map
		dom_elements: dict[int, dict[str, Any]] = {}
		if browser_state.dom_state and browser_state.dom_state.selector_map:
			for backend_node_id, element in browser_state.dom_state.selector_map.items():
				# Create simplified element representation
				# Get text content safely
				text_content = ""
				if hasattr(element, 'get_all_children_text'):
					try:
						text_content = element.get_all_children_text(max_depth=1)[:100]
					except Exception:
						pass

				elem_data: dict[str, Any] = {
					"backend_node_id": backend_node_id,
					"tag": element.tag_name,
					"selector": self._generate_selector(element),
					"text_content": text_content,
					"attributes": self._extract_key_attributes(element),
				}

				# Add bounding box if available
				if element.snapshot_node and element.snapshot_node.bounds:
					bounds = element.snapshot_node.bounds
					elem_data["bounding_box"] = {
						"x": bounds.x,
						"y": bounds.y,
						"width": bounds.width,
						"height": bounds.height,
					}

				dom_elements[backend_node_id] = elem_data

		# Extract page info
		scroll_x = 0
		scroll_y = 0
		viewport_width = 1920
		viewport_height = 1080
		ready_state = "complete"

		if browser_state.page_info:
			scroll_x = browser_state.page_info.scroll_x
			scroll_y = browser_state.page_info.scroll_y
			viewport_width = browser_state.page_info.viewport_width
			viewport_height = browser_state.page_info.viewport_height

		return StateSnapshot(
			url=browser_state.url,
			title=browser_state.title,
			dom_elements=dom_elements,
			scroll_x=scroll_x,
			scroll_y=scroll_y,
			viewport_width=viewport_width,
			viewport_height=viewport_height,
			ready_state=ready_state,
		)

	def compute_diff(self, pre_state: StateSnapshot, post_state: StateSnapshot) -> dict[str, Any]:
		"""Compute diff between two state snapshots.
		
		Args:
			pre_state: State snapshot before action
			post_state: State snapshot after action
			
		Returns:
			State diff dictionary
		"""
		start_time = time.time()

		# Compute hashes
		pre_hash = pre_state.compute_hash()
		post_hash = post_state.compute_hash()

		# Compare DOM elements
		pre_indices = set(pre_state.dom_elements.keys())
		post_indices = set(post_state.dom_elements.keys())

		elements_added = []
		elements_removed = []
		elements_modified = []

		# Elements added (in post but not in pre)
		for idx in post_indices - pre_indices:
			elem = post_state.dom_elements[idx]
			elements_added.append({
				"index": idx,
				"selector": elem.get("selector", ""),
				"tag": elem.get("tag", ""),
				"text_content": elem.get("text_content", "")[:100],
				"attributes": elem.get("attributes", {}),
				"bounding_box": elem.get("bounding_box"),
			})

		# Elements removed (in pre but not in post)
		for idx in pre_indices - post_indices:
			elem = pre_state.dom_elements[idx]
			elements_removed.append({
				"index": idx,
				"selector": elem.get("selector", ""),
				"tag": elem.get("tag", ""),
			})

		# Elements modified (in both, but attributes/text changed)
		for idx in pre_indices & post_indices:
			pre_elem = pre_state.dom_elements[idx]
			post_elem = post_state.dom_elements[idx]

			changes: dict[str, Any] = {}
			has_changes = False

			# Check text content
			pre_text = pre_elem.get("text_content", "")
			post_text = post_elem.get("text_content", "")
			if pre_text != post_text:
				changes["text_content"] = {"old": pre_text[:100], "new": post_text[:100]}
				has_changes = True

			# Check attributes
			pre_attrs = pre_elem.get("attributes", {})
			post_attrs = post_elem.get("attributes", {})

			attr_changes: dict[str, dict[str, str]] = {}
			all_attrs = set(pre_attrs.keys()) | set(post_attrs.keys())
			for attr_key in all_attrs:
				pre_val = pre_attrs.get(attr_key)
				post_val = post_attrs.get(attr_key)
				if pre_val != post_val:
					attr_changes[attr_key] = {"old": str(pre_val), "new": str(post_val)}
					has_changes = True

			if attr_changes:
				changes["attributes"] = attr_changes

			# Check classes (common change)
			if "class" in pre_attrs or "class" in post_attrs:
				pre_classes = set(pre_attrs.get("class", "").split())
				post_classes = set(post_attrs.get("class", "").split())
				classes_added = list(post_classes - pre_classes)
				classes_removed = list(pre_classes - post_classes)
				if classes_added or classes_removed:
					changes["classes"] = {"added": classes_added, "removed": classes_removed}
					has_changes = True

			if has_changes:
				elements_modified.append({
					"index": idx,
					"selector": pre_elem.get("selector", ""),
					"changes": changes,
				})

		# Navigation changes
		navigation_changes: dict[str, Any] = {}
		if pre_state.url != post_state.url:
			navigation_changes["url_changed"] = True
			navigation_changes["old_url"] = pre_state.url
			navigation_changes["new_url"] = post_state.url
		else:
			navigation_changes["url_changed"] = False

		if pre_state.title != post_state.title:
			navigation_changes["title_changed"] = True
			navigation_changes["old_title"] = pre_state.title
			navigation_changes["new_title"] = post_state.title
		else:
			navigation_changes["title_changed"] = False

		# Detect semantic events
		semantic_events = self._detect_semantic_events(
			elements_added, elements_removed, elements_modified, navigation_changes
		)

		computation_time_ms = int((time.time() - start_time) * 1000)

		# Build diff structure
		state_diff = {
			"format_version": "1.0",
			"diff_type": "incremental",
			"pre_state_hash": pre_hash,
			"post_state_hash": post_hash,
			"computation_time_ms": computation_time_ms,
			"dom_changes": {
				"elements_added": elements_added,
				"elements_removed": elements_removed,
				"elements_modified": elements_modified,
				"elements_moved": [],  # TODO: Implement element movement detection
			},
			"navigation_changes": navigation_changes,
			"form_state_changes": [],  # TODO: Implement form state tracking
			"accessibility_changes": {
				"focus_changed": {},  # TODO: Implement focus tracking
				"landmarks_added": [],
				"landmarks_removed": [],
				"live_region_updates": [],
			},
			"visual_changes": {
				"significant_change": len(elements_added) > 0 or len(elements_removed) > 0 or navigation_changes.get("url_changed", False),
				"changed_regions": [],  # TODO: Implement visual diff
				"pixel_diff_percent": 0.0,
			},
			"semantic_events": semantic_events,
		}

		logger.debug(
			f"Computed state diff: {len(elements_added)} added, {len(elements_removed)} removed, "
			f"{len(elements_modified)} modified, {len(semantic_events)} semantic events"
		)

		return state_diff

	def _generate_selector(self, element: Any) -> str:
		"""Generate CSS selector for element (simplified)."""
		# Use xpath if available, otherwise generate from tag + attributes
		if hasattr(element, 'xpath') and element.xpath:
			# Extract simple selector from xpath (last component)
			xpath_parts = element.xpath.split('/')
			if xpath_parts:
				last_part = xpath_parts[-1]
				# Convert xpath to CSS selector (simplified)
				if last_part.startswith('*[@'):
					# Extract attribute selectors
					pass  # TODO: Better xpath to CSS conversion

		# Fallback: tag + id/class/name
		tag = element.tag_name.lower() if element.tag_name else 'div'
		attrs = element.attributes or {}

		if 'id' in attrs:
			return f"{tag}#{attrs['id']}"
		elif 'class' in attrs and attrs['class']:
			classes = attrs['class'].split()[0]  # Use first class
			return f"{tag}.{classes}"
		elif 'name' in attrs:
			return f"{tag}[name='{attrs['name']}']"
		else:
			return tag

	def _extract_key_attributes(self, element: Any) -> dict[str, str]:
		"""Extract key attributes from element."""
		attrs = element.attributes or {}

		# Extract important attributes
		key_attrs: dict[str, str] = {}
		important_keys = ['id', 'class', 'type', 'name', 'role', 'aria-label', 'href', 'value']

		for key in important_keys:
			if key in attrs:
				key_attrs[key] = str(attrs[key])

		return key_attrs

	def _detect_semantic_events(
		self,
		elements_added: list[dict[str, Any]],
		elements_removed: list[dict[str, Any]],
		elements_modified: list[dict[str, Any]],
		navigation_changes: dict[str, Any],
	) -> list[dict[str, Any]]:
		"""Detect high-level semantic events from changes.
		
		Args:
			elements_added: List of added elements
			elements_removed: List of removed elements
			elements_modified: List of modified elements
			navigation_changes: Navigation change information
			
		Returns:
			List of semantic events
		"""
		events: list[dict[str, Any]] = []

		# Navigation events
		if navigation_changes.get("url_changed"):
			events.append({
				"event_type": "navigation",
				"event_name": "page_navigation",
				"target_selector": None,
				"confidence": 1.0,
				"metadata": {
					"old_url": navigation_changes.get("old_url"),
					"new_url": navigation_changes.get("new_url"),
				},
			})

		# Detect modal/dialog appearance (common patterns)
		for elem in elements_added:
			tag = elem.get("tag", "").lower()
			role = elem.get("attributes", {}).get("role", "").lower()
			classes = elem.get("attributes", {}).get("class", "").lower()

			if role == "dialog" or "modal" in classes or "dialog" in classes:
				events.append({
					"event_type": "ui_state",
					"event_name": "modal_opened",
					"target_selector": elem.get("selector", ""),
					"confidence": 0.9,
					"metadata": {"tag": tag},
				})

		# Detect error/success messages
		for elem in elements_added:
			classes = elem.get("attributes", {}).get("class", "").lower()
			text = elem.get("text_content", "").lower()

			if "error" in classes or "alert-danger" in classes:
				events.append({
					"event_type": "feedback",
					"event_name": "error_banner_appeared",
					"target_selector": elem.get("selector", ""),
					"confidence": 0.8,
					"metadata": {"text_preview": text[:50]},
				})
			elif "success" in classes or "alert-success" in classes:
				events.append({
					"event_type": "feedback",
					"event_name": "success_message_appeared",
					"target_selector": elem.get("selector", ""),
					"confidence": 0.8,
					"metadata": {"text_preview": text[:50]},
				})

		# Detect form submission (form removed after submission)
		forms_removed = [e for e in elements_removed if e.get("tag", "").lower() == "form"]
		if forms_removed:
			for form in forms_removed:
				events.append({
					"event_type": "form",
					"event_name": "form_submitted",
					"target_selector": form.get("selector", ""),
					"confidence": 0.7,
					"metadata": {},
				})

		return events
