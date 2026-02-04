"""
Explore primary URL activity for knowledge extraction workflow.

Comprehensive primary URL exploration to enrich extracted knowledge.
"""

import asyncio
import logging
from typing import Any
from uuid import uuid4

from temporalio import activity

from navigator.schemas import ExplorePrimaryUrlInput, ExplorePrimaryUrlResult
from navigator.temporal.activities.shared import get_idempotency_manager

logger = logging.getLogger(__name__)


@activity.defn(name="explore_primary_url")
async def explore_primary_url_activity(
	input: ExplorePrimaryUrlInput,
) -> ExplorePrimaryUrlResult:
	"""
	Comprehensive primary URL exploration to enrich extracted knowledge.
	
	This activity performs a full-blown website exploration:
	1. Navigates to primary URL
	2. Handles login if credentials provided
	3. Recursively explores DOM structure by clicking on clickable links
	4. Filters out non-explorable links (login, share, email, logout, etc.)
	5. For each page:
	   - Extracts detailed form information including all fields
	   - Identifies field types, names, labels, placeholders, required status
	   - Detects multi-step forms
	6. Covers all pages up to max_pages and max_depth
	7. Extracts and enriches knowledge with real-world findings
	8. Persists exploration results to database
	"""
	workflow_id = activity.info().workflow_id
	_idempotency_manager = get_idempotency_manager()

	if _idempotency_manager:
		cached = await _idempotency_manager.check_already_executed(
			workflow_id, "explore_primary_url", input
		)
		if cached:
			return ExplorePrimaryUrlResult(**cached)

	activity.heartbeat({"status": "exploring", "url": input.primary_url})

	try:
		from browser_use import BrowserSession
		from navigator.knowledge.auth_service import AuthenticationService, Credentials
		from navigator.knowledge.exploration_engine import ExplorationEngine, ExplorationStrategy
		from navigator.knowledge.extract.actions import ActionExtractor
		from navigator.knowledge.extract.screens import ScreenExtractor
		from navigator.knowledge.persist.documents import get_screen, save_actions, save_screens
		from navigator.knowledge.persist.ingestion import save_ingestion_result
		from navigator.schemas import ContentChunk, IngestionResult, SourceMetadata, SourceType

		logger.info(f"🌐 Starting primary URL exploration: {input.primary_url}")

		# Create browser session
		from browser_use.browser.profile import BrowserProfile
		profile = BrowserProfile(headless=True, use_cloud=False)
		browser_session = BrowserSession(browser_profile=profile)
		await browser_session.start()

		result = ExplorePrimaryUrlResult()

		try:
			# Step 1: Navigate to primary URL
			logger.info(f"📍 Navigating to primary URL: {input.primary_url}")
			from browser_use.browser.events import NavigateToUrlEvent
			event = browser_session.event_bus.dispatch(NavigateToUrlEvent(url=input.primary_url))
			await event
			await asyncio.sleep(2)  # Wait for page load

			# Step 2: Handle login if credentials provided
			if input.credentials:
				logger.info("🔐 Credentials provided - attempting login")
				auth_service = AuthenticationService(browser_session)
				creds = Credentials(
					username=input.credentials.get('username', ''),
					password=input.credentials.get('password', ''),
					login_url=input.credentials.get('login_url'),
				)

				login_result = await auth_service.perform_login(creds, login_url=input.credentials.get('login_url'))
				if login_result.get('success'):
					result.login_successful = True
					logger.info(f"✅ Login successful - logged in at: {login_result.get('logged_in_url')}")
					await asyncio.sleep(1)  # Wait after login
				else:
					logger.warning(f"⚠️ Login failed: {login_result.get('message')} - {login_result.get('error')}")
					result.errors.append(f"Login failed: {login_result.get('message')}")

			# Step 3: Comprehensive DOM exploration with link clicking and form extraction
			logger.info("🔍 Starting comprehensive DOM exploration with recursive link clicking")

			# Helper function to filter out non-explorable links
			def is_explorable_link(link: dict[str, Any]) -> bool:
				"""Filter out login, share, email, logout, and other non-explorable links."""
				href = (link.get('href') or link.get('url', '')).lower()
				text = (link.get('text') or '').lower()

				# Exclude patterns
				exclude_patterns = [
					'login', 'logout', 'signin', 'signout', 'sign-in', 'sign-out',
					'share', 'email', 'mailto:', 'tel:', 'javascript:',
					'print', 'download', 'pdf', '.pdf', '.doc', '.docx',
					'facebook', 'twitter', 'linkedin', 'instagram', 'pinterest',
					'whatsapp', 'telegram', 'reddit', 'tumblr',
					'#', 'javascript:void', 'void(0)',
				]

				for pattern in exclude_patterns:
					if pattern in href or pattern in text:
						return False

				# Must be internal link
				return link.get('internal', True)

			# Helper function to extract detailed form information
			async def extract_forms_from_page(browser_state) -> list[dict[str, Any]]:
				"""Extract detailed form information including fields."""
				forms = []
				selector_map = browser_state.dom_state.selector_map if browser_state.dom_state else {}

				if not selector_map:
					return forms

				# Group form elements by form container
				form_containers: dict[str | int, dict[str, Any]] = {}

				for idx, element in selector_map.items():
					if not hasattr(element, 'tag_name'):
						continue

					tag = element.tag_name.lower() if element.tag_name else ''

					# Find form containers
					if tag == 'form':
						form_id = getattr(element, 'form_id', None) or idx
						if form_id not in form_containers:
							form_containers[form_id] = {
								'form_id': form_id,
								'fields': [],
								'action': getattr(element, 'action', ''),
								'method': getattr(element, 'method', 'GET'),
							}

					# Find form fields
					elif tag in ['input', 'textarea', 'select']:
						# Try to find parent form
						form_id = getattr(element, 'form_id', None) or getattr(element, 'parent_form_id', None)
						if not form_id:
							# Create standalone form for orphaned fields
							form_id = f"orphan_{idx}"
							if form_id not in form_containers:
								form_containers[form_id] = {
									'form_id': form_id,
									'fields': [],
									'action': '',
									'method': 'GET',
								}

						field_info = {
							'type': tag,
							'input_type': getattr(element, 'type', 'text'),
							'name': getattr(element, 'name', ''),
							'id': getattr(element, 'id', ''),
							'label': getattr(element, 'label', ''),
							'placeholder': getattr(element, 'placeholder', ''),
							'required': getattr(element, 'required', False),
							'disabled': getattr(element, 'disabled', False),
							'readonly': getattr(element, 'readonly', False),
						}

						if form_id in form_containers:
							form_containers[form_id]['fields'].append(field_info)

				# Convert to list and detect multi-step forms
				for form_data in form_containers.values():
					if form_data['fields']:
						# Check for multi-step indicators
						field_names = [f.get('name', '') for f in form_data['fields']]
						has_step_indicators = any(
							'step' in name.lower() or 'page' in name.lower() or 'stage' in name.lower()
							for name in field_names
						)

						# Check for multiple submit buttons (common in multi-step)
						submit_count = sum(1 for f in form_data['fields'] if f.get('input_type') == 'submit')

						form_data['is_multi_step'] = has_step_indicators or submit_count > 1
						form_data['field_count'] = len(form_data['fields'])
						forms.append(form_data)

				return forms

			# Helper function to click on a link
			async def click_link(link: dict[str, Any]) -> bool:
				"""Click on a link and return success status."""
				try:
					href = link.get('href') or link.get('url', '')
					if not href:
						return False

					# Try to find the link element in DOM and click it
					from browser_use.browser.events import ClickElementEvent

					# Get browser state to find link element
					browser_state = await browser_session.get_browser_state_summary(include_screenshot=False)
					selector_map = browser_state.dom_state.selector_map if browser_state.dom_state else {}

					# Find link element by href or text
					link_node = None
					for idx, element in selector_map.items():
						if hasattr(element, 'tag_name') and element.tag_name.lower() == 'a':
							element_href = getattr(element, 'href', '') or ''
							element_text = getattr(element, 'text', '') or ''

							if href in element_href or link.get('text', '').lower() in element_text.lower():
								# Get the node using get_element_by_index
								link_node = await browser_session.get_element_by_index(idx)
								break

					if link_node is not None:
						event = browser_session.event_bus.dispatch(ClickElementEvent(node=link_node))
						await event
						await asyncio.sleep(1.5)  # Wait for navigation
						return True
					else:
						# Fallback: navigate directly to URL
						event = browser_session.event_bus.dispatch(NavigateToUrlEvent(url=href))
						await event
						await asyncio.sleep(1.5)
						return True

				except Exception as e:
					logger.warning(f"⚠️ Error clicking link {link.get('href', '')}: {e}")
					return False

			# Start comprehensive exploration
			exploration_engine = ExplorationEngine(
				browser_session=browser_session,
				max_depth=input.max_depth,
				strategy=ExplorationStrategy.BFS,
				base_url=input.primary_url,
			)

			explored_pages = []
			urls_to_explore = [(input.primary_url, 0)]  # (url, depth)
			visited_urls = set()
			page_forms: dict[str, list[dict[str, Any]]] = {}  # url -> forms

			while urls_to_explore and len(explored_pages) < input.max_pages:
				current_url, current_depth = urls_to_explore.pop(0)

				if current_url in visited_urls:
					continue

				if current_depth > input.max_depth:
					continue

				visited_urls.add(current_url)
				logger.info(f"📄 Exploring page {len(explored_pages) + 1}/{input.max_pages} (depth {current_depth}): {current_url}")

				try:
					# Navigate to page
					event = browser_session.event_bus.dispatch(NavigateToUrlEvent(url=current_url))
					await event
					await asyncio.sleep(2)  # Wait for page load

					# Get DOM state
					browser_state = await browser_session.get_browser_state_summary(include_screenshot=False)

					# Extract detailed form information
					page_forms_list = await extract_forms_from_page(browser_state)
					page_forms[current_url] = page_forms_list

					if page_forms_list:
						result.forms_identified += len(page_forms_list)
						forms_with_fields = sum(1 for f in page_forms_list if f.get('field_count', 0) > 0)
						result.forms_with_fields += forms_with_fields
						multi_step_count = sum(1 for f in page_forms_list if f.get('is_multi_step', False))
						result.multi_step_forms += multi_step_count

						logger.info(
							f"📝 Found {len(page_forms_list)} form(s) on {current_url}: "
							f"{forms_with_fields} with fields, {multi_step_count} multi-step"
						)

					# Extract page content
					from browser_use.dom.markdown_extractor import extract_clean_markdown
					page_content, _ = await extract_clean_markdown(
						browser_session=browser_session,
						extract_links=True
					)

					# Create content chunk
					page_chunk = ContentChunk(
						chunk_id=str(uuid4()),
						content=page_content,
						chunk_index=len(explored_pages),
						token_count=len(page_content.split()),  # Approximate
						chunk_type="exploration",
						section_title=browser_state.title or current_url,
					)

					explored_pages.append({
						'url': current_url,
						'title': browser_state.title or current_url,
						'chunk': page_chunk,
						'forms': page_forms_list,
						'depth': current_depth,
					})

					# Discover and filter links
					all_links = await exploration_engine.discover_links(current_url)
					explorable_links = [link for link in all_links if is_explorable_link(link)]

					logger.info(f"🔗 Found {len(all_links)} total links, {len(explorable_links)} explorable")

					# Add explorable links to queue (they will be explored in subsequent iterations)
					from urllib.parse import urlparse
					parsed_base = urlparse(input.primary_url)

					links_added = 0
					for link in explorable_links:
						link_url = link.get('href') or link.get('url', '')

						if not link_url:
							continue

						# Check if internal
						parsed_link = urlparse(link_url)

						if parsed_link.netloc and parsed_link.netloc != parsed_base.netloc:
							continue  # Skip external links

						# Normalize URL (remove fragments, etc.)
						normalized_url = f"{parsed_link.scheme}://{parsed_link.netloc}{parsed_link.path}"
						if parsed_link.query:
							normalized_url += f"?{parsed_link.query}"

						# Add to queue if not already visited or queued
						if (normalized_url not in visited_urls and
						    (normalized_url, current_depth + 1) not in urls_to_explore and
						    current_depth + 1 <= input.max_depth):
							urls_to_explore.append((normalized_url, current_depth + 1))
							links_added += 1
							logger.debug(f"  ➕ Queued: {normalized_url} (depth {current_depth + 1})")

					# Click on a few links to verify they're clickable and discover dynamic content
					# This helps find pages that might only be accessible via JavaScript navigation
					clicked_count = 0
					for link in explorable_links[:3]:  # Click first 3 links to verify accessibility
						if clicked_count >= 3 or len(explored_pages) >= input.max_pages:
							break

						link_url = link.get('href') or link.get('url', '')
						if not link_url:
							continue

						parsed_link = urlparse(link_url)
						if parsed_link.netloc and parsed_link.netloc != parsed_base.netloc:
							continue

						normalized_url = f"{parsed_link.scheme}://{parsed_link.netloc}{parsed_link.path}"
						if parsed_link.query:
							normalized_url += f"?{parsed_link.query}"

						# Only click if we haven't explored this URL yet
						if normalized_url not in visited_urls:
							click_success = await click_link(link)
							if click_success:
								result.links_clicked += 1
								clicked_count += 1

								# Check if we navigated to a new page
								# Get current URL from browser state
								browser_state_after_click = await browser_session.get_browser_state_summary(include_screenshot=False)
								current_browser_url = browser_state_after_click.url if browser_state_after_click else None
								if current_browser_url and current_browser_url != current_url:
									# We navigated to a new page - add it to queue if not already there
									if (current_browser_url not in visited_urls and
									    (current_browser_url, current_depth + 1) not in urls_to_explore):
										urls_to_explore.append((current_browser_url, current_depth + 1))
										logger.info(f"  🎯 Discovered new page via click: {current_browser_url}")

								# Navigate back to continue exploring current page
								event = browser_session.event_bus.dispatch(NavigateToUrlEvent(url=current_url))
								await event
								await asyncio.sleep(1)

					if links_added > 0:
						logger.info(f"  ➕ Added {links_added} new URLs to exploration queue")

					result.pages_explored += 1
					activity.heartbeat({
						"status": "exploring",
						"pages": result.pages_explored,
						"url": current_url,
						"forms": len(page_forms_list),
						"links_clicked": result.links_clicked
					})

				except Exception as e:
					logger.warning(f"⚠️ Error exploring {current_url}: {e}")
					result.errors.append(f"Error exploring {current_url}: {str(e)}")
					continue

			# Step 4: Convert exploration data into navigatable and functionable knowledge
			if explored_pages:
				logger.info(f"📊 Converting exploration data into knowledge: {len(explored_pages)} pages")

				# Helper function to convert forms into actions and tasks
				async def convert_forms_to_knowledge(pages_with_forms: list[dict[str, Any]]) -> tuple[list, list]:
					"""Convert form data into actions and tasks."""
					form_actions = []
					form_tasks = []

					from navigator.knowledge.extract.actions import ActionDefinition, ActionPostcondition, ActionPrecondition
					from navigator.knowledge.extract.tasks import TaskDefinition, TaskStep

					for page_data in pages_with_forms:
						page_url = page_data['url']
						page_title = page_data.get('title', page_url)
						forms = page_data.get('forms', [])

						for form_idx, form in enumerate(forms):
							form_id = form.get('form_id', f"form_{form_idx}")
							form_fields = form.get('fields', [])
							form_action = form.get('action', '')
							form_method = form.get('method', 'GET')
							is_multi_step = form.get('is_multi_step', False)

							# Create actions for each form field
							for field in form_fields:
								field_name = field.get('name', '') or field.get('id', '')
								field_type = field.get('type', 'input')
								input_type = field.get('input_type', 'text')

								if not field_name:
									continue

								# Create "fill field" action
								action_id = f"fill_{field_name}_{form_id}_{uuid4().hex[:8]}"
								action = ActionDefinition(
									action_id=action_id,
									name=f"Fill {field_name} field",
									website_id=input.website_id,
									action_type="type" if input_type in ['text', 'email', 'password', 'number'] else "select_option",
									category="form_interaction",
									target_selector=f"input[name='{field_name}'], input[id='{field_name}'], textarea[name='{field_name}'], select[name='{field_name}']",
									parameters={
										'field_name': field_name,
										'field_type': field_type,
										'input_type': input_type,
										'required': field.get('required', False),
										'placeholder': field.get('placeholder', ''),
										'label': field.get('label', ''),
									},
									preconditions=[
										ActionPrecondition(
											type='screen_state',
											hard_dependency=True,
											auto_remediate=False
										)
									],
									postconditions=[
										ActionPostcondition(
											type='field_filled',
											success=True
										)
									],
									idempotent=True,
									reversible_by=None,
									metadata={
										'extraction_method': 'form_exploration',
										'form_id': form_id,
										'page_url': page_url,
										'form_action': form_action,
									}
								)
								form_actions.append(action)

							# Create form submission task/workflow
							if form_fields:
								task_id = f"submit_form_{form_id}_{uuid4().hex[:8]}"
								steps = []

								# Add steps for each required field
								step_order = 1
								for field in form_fields:
									if field.get('required', False) or not field.get('disabled', False):
										field_name = field.get('name', '') or field.get('id', '')
										if field_name:
											steps.append(TaskStep(
												step_id=f"step_{step_order}_{field_name}",
												order=step_order,
												type="form_fill",
												action={
													'action_type': 'type',
													'target': field_name,
													'field_type': field.get('type', 'input'),
													'input_type': field.get('input_type', 'text'),
												},
												preconditions=[],
												postconditions=[],
												required=field.get('required', False),
												can_skip=not field.get('required', False),
											))
											step_order += 1

								# Add submit step
								steps.append(TaskStep(
									step_id=f"step_{step_order}_submit",
									order=step_order,
									type="submit",
									action={
										'action_type': 'click',
										'target': 'submit_button',
										'form_action': form_action,
										'form_method': form_method,
									},
									preconditions=[],
									postconditions=[],
									required=True,
									can_skip=False,
								))

								from navigator.knowledge.extract.tasks import IOInput, IOSpec, IteratorSpec, TaskDefinition

								task = TaskDefinition(
									task_id=task_id,
									name=f"Submit form on {page_title}",
									website_id=input.website_id,
									description=f"Fill and submit form with {len(form_fields)} fields on {page_title}",
									io_spec=IOSpec(
										inputs=[
											IOInput(
												name=field.get('name', '') or field.get('id', ''),
												type=field.get('input_type', 'string'),
												required=field.get('required', False),
												description=field.get('label', '') or field.get('placeholder', ''),
												source="user_input",
												volatility="high",
												default=None
											)
											for field in form_fields if field.get('name') or field.get('id')
										],
										outputs=[]
									),
									iterator_spec=IteratorSpec(
										type='none',
										collection_selector=None,
										item_action=None,
										termination_condition=None,
									),
									steps=steps,
									metadata={
										'extraction_method': 'form_exploration',
										'form_id': form_id,
										'page_url': page_url,
										'form_action': form_action,
										'form_method': form_method,
										'is_multi_step': is_multi_step,
										'field_count': len(form_fields),
									}
								)
								form_tasks.append(task)

					return form_actions, form_tasks

			# Convert forms to actions and tasks
			form_actions, form_tasks = await convert_forms_to_knowledge(explored_pages)

			# Create content chunks from explored pages
			exploration_chunks = [page['chunk'] for page in explored_pages]

			# Extract screens
			screen_extractor = ScreenExtractor(
				website_id=input.website_id,
				confidence_threshold=0.3,  # Priority 9: Auto-reject screens below 0.3 confidence
				knowledge_id=input.knowledge_id if hasattr(input, 'knowledge_id') else None  # Priority 9: Enable cross-reference validation
			)
			screens_result = await screen_extractor.extract_screens(exploration_chunks)

			if screens_result.screens:
				# Save new screens with knowledge_id and job_id
				await save_screens(screens_result.screens, knowledge_id=input.knowledge_id, job_id=input.job_id)
				result.new_screens_found = len(screens_result.screens)
				logger.info(f"✅ Extracted {result.new_screens_found} new screen(s) from exploration")

				# Check if any enrich existing screens
				for screen in screens_result.screens:
					# Try to find matching existing screen by URL pattern or name
					for existing_screen_id in input.screen_ids:
						existing_screen = await get_screen(existing_screen_id)
						if existing_screen:
							# Simple matching: same URL pattern or similar name
							# ScreenDefinition uses url_patterns (list), check if any patterns match
							screen_patterns = set(screen.url_patterns) if screen.url_patterns else set()
							existing_patterns = set(existing_screen.url_patterns) if existing_screen.url_patterns else set()
							if screen_patterns and existing_patterns and screen_patterns.intersection(existing_patterns):
								result.screens_enriched += 1
								break

			# Extract actions from content (pattern-based)
			action_extractor = ActionExtractor(website_id=input.website_id)
			content_actions_result = action_extractor.extract_actions(exploration_chunks)

			# Combine form-based actions with content-based actions
			all_actions = form_actions + (content_actions_result.actions if content_actions_result.actions else [])

			if all_actions:
				# Save all actions with knowledge_id and job_id
				await save_actions(all_actions, knowledge_id=input.knowledge_id, job_id=input.job_id)
				result.new_actions_found = len(all_actions)
				logger.info(
					f"✅ Extracted {result.new_actions_found} action(s): "
					f"{len(form_actions)} from forms, "
					f"{len(content_actions_result.actions) if content_actions_result.actions else 0} from content"
				)

				# Actions enrichment is implicit (new actions complement existing ones)
				result.actions_enriched = result.new_actions_found

			# Save form-based tasks with knowledge_id and job_id
			if form_tasks:
				from navigator.knowledge.persist.documents import save_tasks
				await save_tasks(form_tasks, knowledge_id=input.knowledge_id, job_id=input.job_id)
				logger.info(f"✅ Created {len(form_tasks)} task(s) from form exploration")

				# Note: Business functions and workflows are extracted in the main workflow
				# The exploration chunks are saved as ingestion and will be processed by
				# extract_business_functions_activity and extract_workflows_activity
				logger.info(
					"ℹ️ Form data converted to actions and tasks. "
					"Business functions and workflows will be extracted in main workflow phase."
				)

			# Step 5: Save exploration results as ingestion
			if explored_pages:
				exploration_ingestion = IngestionResult(
					ingestion_id=str(uuid4()),
					source_type=SourceType.WEBSITE_DOCUMENTATION,
					metadata=SourceMetadata(
						source_type=SourceType.WEBSITE_DOCUMENTATION,
						url=input.primary_url,
						title=f"Primary URL Exploration: {input.primary_url}",
					),
					content_chunks=[page['chunk'] for page in explored_pages],
				)
				await save_ingestion_result(exploration_ingestion)
				logger.info(f"💾 Saved exploration results as ingestion: {exploration_ingestion.ingestion_id}")

			result.success = True
			logger.info(
				f"✅ Primary URL exploration completed: "
				f"{result.pages_explored} pages explored, "
				f"{result.links_clicked} links clicked, "
				f"{result.forms_identified} forms identified, "
				f"{result.forms_with_fields} forms with field details, "
				f"{result.multi_step_forms} multi-step forms detected, "
				f"{result.new_screens_found} new screens, "
				f"{result.new_actions_found} new actions"
			)

		finally:
			# Clean up browser session
			try:
				# BrowserSession cleanup - use kill() method
				await browser_session.kill()
			except Exception as e:
				logger.warning(f"Error closing browser session: {e}")

		if _idempotency_manager:
			await _idempotency_manager.record_execution(
				workflow_id, "explore_primary_url", input, result.__dict__, True
			)

		return result

	except Exception as e:
		logger.error(f"❌ Primary URL exploration failed: {e}", exc_info=True)
		if _idempotency_manager:
			await _idempotency_manager.record_execution(
				workflow_id, "explore_primary_url", input, {}, False, str(e)
			)
		raise
