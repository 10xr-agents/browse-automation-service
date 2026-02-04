"""
Navigation Query Helpers (Phase 3).

High-level navigation functions that leverage cross-references to provide
complete navigation paths, flow instructions, and context for knowledge entities.

These functions use the bidirectional cross-references established in Phase 2
to enable easy navigation and understanding of relationships.
"""

import logging
from typing import Any

from navigator.knowledge.graph.queries import find_shortest_path
from navigator.knowledge.persist.documents import (
	get_action,
	get_business_function,
	get_screen,
	get_task,
	get_transition,
	get_user_flow,
	get_workflow,
)

logger = logging.getLogger(__name__)


async def get_navigation_path(
	from_screen_id: str,
	to_screen_id: str,
	knowledge_id: str,
	job_id: str | None = None
) -> dict[str, Any]:
	"""
	Find shortest path between two screens with complete navigation instructions.
	
	Returns detailed path information including:
	- Screen sequence
	- Transitions between screens
	- Actions required for each transition
	- Step-by-step instructions
	
	Args:
		from_screen_id: Source screen ID
		to_screen_id: Target screen ID
		knowledge_id: Knowledge ID for querying
		job_id: Optional job ID for historical queries
	
	Returns:
		Dict with:
		- path: List of screen IDs
		- transitions: List of transition data
		- actions: List of action data
		- steps: List of step-by-step instructions
		- total_cost: Estimated total cost in milliseconds
		- total_reliability: Combined reliability score
	"""
	try:
		# Get source and target screens to find website_id
		from_screen = await get_screen(from_screen_id)
		to_screen = await get_screen(to_screen_id)

		if not from_screen or not to_screen:
			logger.warning(f"Screen not found: from={from_screen_id}, to={to_screen_id}")
			return {
				'path': [],
				'transitions': [],
				'actions': [],
				'steps': [],
				'total_cost': 0,
				'total_reliability': 0.0,
				'error': 'Screen not found'
			}

		website_id = from_screen.website_id

		# Find shortest path using existing graph query
		path_result = await find_shortest_path(
			from_screen_id,
			to_screen_id,
			max_depth=20,
			website_id=website_id
		)

		if not path_result.get('path'):
			return {
				'path': [],
				'transitions': [],
				'actions': [],
				'steps': [],
				'total_cost': 0,
				'total_reliability': 0.0,
				'error': 'No path found'
			}

		path = path_result['path']
		transitions_data = path_result.get('edges', [])

		# Enhance transitions with full data
		transitions = []
		actions = []
		steps = []
		total_cost = 0
		total_reliability = 1.0

		for i in range(len(path) - 1):
			from_screen_id_step = path[i]
			to_screen_id_step = path[i + 1]

			# Get transition data
			transition = None
			if i < len(transitions_data):
				transition_dict = transitions_data[i]
				if isinstance(transition_dict, dict) and 'transition_id' in transition_dict:
					transition = await get_transition(transition_dict['transition_id'])

			# If transition not found in path result, query directly
			if not transition:
				from navigator.knowledge.persist.documents import query_transitions_by_source
				transitions_list = await query_transitions_by_source(from_screen_id_step, limit=100)
				for t in transitions_list:
					if t.to_screen_id == to_screen_id_step:
						transition = t
						break

			if transition:
				transitions.append(transition.dict())

				# Get action that triggers this transition
				action = None
				if transition.action_id:
					action = await get_action(transition.action_id)
				elif transition.triggered_by and transition.triggered_by.element_id:
					action = await get_action(transition.triggered_by.element_id)

				if action:
					actions.append(action.dict())
					action_name = action.name
				else:
					action_name = transition.triggered_by.action_type if transition.triggered_by else "unknown"

				# Get screen names
				from_screen_step = await get_screen(from_screen_id_step)
				to_screen_step = await get_screen(to_screen_id_step)
				from_name = from_screen_step.name if from_screen_step else from_screen_id_step
				to_name = to_screen_step.name if to_screen_step else to_screen_id_step

				# Build step instruction
				step = {
					'step_number': i + 1,
					'from_screen': {
						'screen_id': from_screen_id_step,
						'screen_name': from_name
					},
					'to_screen': {
						'screen_id': to_screen_id_step,
						'screen_name': to_name
					},
					'action': {
						'action_id': action.action_id if action else None,
						'action_name': action_name,
						'action_type': transition.triggered_by.action_type if transition.triggered_by else None
					},
					'transition_id': transition.transition_id,
					'instruction': f"On {from_name}, {action_name} to navigate to {to_name}"
				}
				steps.append(step)

				# Accumulate cost and reliability
				if transition.cost:
					total_cost += transition.cost.get('estimated_ms', 2000)
				if transition.reliability_score:
					total_reliability *= transition.reliability_score
			else:
				# Transition not found, create basic step
				from_screen_step = await get_screen(from_screen_id_step)
				to_screen_step = await get_screen(to_screen_id_step)
				from_name = from_screen_step.name if from_screen_step else from_screen_id_step
				to_name = to_screen_step.name if to_screen_step else to_screen_id_step

				step = {
					'step_number': i + 1,
					'from_screen': {
						'screen_id': from_screen_id_step,
						'screen_name': from_name
					},
					'to_screen': {
						'screen_id': to_screen_id_step,
						'screen_name': to_name
					},
					'action': {
						'action_id': None,
						'action_name': 'Navigate',
						'action_type': 'navigate'
					},
					'transition_id': None,
					'instruction': f"Navigate from {from_name} to {to_name}"
				}
				steps.append(step)

		return {
			'path': path,
			'transitions': transitions,
			'actions': actions,
			'steps': steps,
			'total_cost': total_cost,
			'total_reliability': total_reliability,
			'path_length': len(path),
			'hops': len(path) - 1
		}

	except Exception as e:
		logger.error(f"Failed to get navigation path: {e}", exc_info=True)
		return {
			'path': [],
			'transitions': [],
			'actions': [],
			'steps': [],
			'total_cost': 0,
			'total_reliability': 0.0,
			'error': str(e)
		}


async def get_flow_navigation(
	user_flow_id: str,
	knowledge_id: str,
	job_id: str | None = None
) -> dict[str, Any]:
	"""
	Get complete navigation instructions for a user flow.
	
	Returns:
		Dict with:
		- flow_id: User flow ID
		- flow_name: User flow name
		- screens: Ordered list of screens with actions
		- navigation_instructions: Step-by-step instructions
		- total_steps: Total number of steps
		- estimated_duration: Estimated duration in seconds
	"""
	try:
		from navigator.knowledge.persist.documents import get_user_flow

		# Get user flow from MongoDB
		user_flow = await get_user_flow(user_flow_id)
		if not user_flow:
			return {
				'flow_id': user_flow_id,
				'flow_name': None,
				'screens': [],
				'navigation_instructions': [],
				'total_steps': 0,
				'estimated_duration': 0,
				'error': 'User flow not found'
			}

		# Build screen sequence with full details
		screens_list = []
		navigation_instructions = []

		# Use screen_sequence if available (Phase 4 enhancement)
		if hasattr(user_flow, 'screen_sequence') and user_flow.screen_sequence:
			for seq_item in user_flow.screen_sequence:
				screen_id = seq_item.get('screen_id')
				screen_name = seq_item.get('screen_name', '')
				transition_id = seq_item.get('transition_id')
				order = seq_item.get('order', 0)

				# Get full screen details
				screen = await get_screen(screen_id) if screen_id else None

				# Get transition and action details
				action_name = None
				action_id = None
				if transition_id:
					transition = await get_transition(transition_id)
					if transition:
						if transition.action_id:
							action = await get_action(transition.action_id)
							if action:
								action_name = action.name
								action_id = action.action_id
						elif transition.triggered_by:
							action_name = transition.triggered_by.action_type

				screen_data = {
					'screen_id': screen_id,
					'screen_name': screen_name or (screen.name if screen else screen_id),
					'order': order,
					'actions_available': [],
					'transition_to': None,
					'transition_action': action_name,
					'transition_id': transition_id
				}

				# Get available actions for this screen
				if screen and hasattr(screen, 'action_ids') and screen.action_ids:
					for act_id in screen.action_ids:
						act = await get_action(act_id)
						if act:
							screen_data['actions_available'].append({
								'action_id': act.action_id,
								'action_name': act.name,
								'action_type': act.action_type
							})

				# Get next screen from sequence
				if order < len(user_flow.screen_sequence) - 1:
					next_item = user_flow.screen_sequence[order + 1]
					screen_data['transition_to'] = {
						'screen_id': next_item.get('screen_id'),
						'screen_name': next_item.get('screen_name', '')
					}

				screens_list.append(screen_data)

				# Build instruction
				if action_name:
					instruction = f"{order}. On {screen_data['screen_name']}, {action_name}"
					if screen_data['transition_to']:
						instruction += f" to navigate to {screen_data['transition_to']['screen_name']}"
				else:
					instruction = f"{order}. Navigate to {screen_data['screen_name']}"

				navigation_instructions.append(instruction)
		else:
			# Fallback: Use steps if screen_sequence not available
			for step in user_flow.steps:
				screen_id = step.screen_id
				screen_name = step.screen_name
				action = step.action

				screen = await get_screen(screen_id) if screen_id else None

				screen_data = {
					'screen_id': screen_id,
					'screen_name': screen_name,
					'order': step.step_number,
					'actions_available': [],
					'transition_to': None,
					'transition_action': action,
					'description': step.description
				}

				if screen and hasattr(screen, 'action_ids') and screen.action_ids:
					for act_id in screen.action_ids:
						act = await get_action(act_id)
						if act:
							screen_data['actions_available'].append({
								'action_id': act.action_id,
								'action_name': act.name,
								'action_type': act.action_type
							})

				screens_list.append(screen_data)
				navigation_instructions.append(
					f"{step.step_number}. On {screen_name}, {action}"
				)

		return {
			'flow_id': user_flow.user_flow_id,
			'flow_name': user_flow.name,
			'description': user_flow.description,
			'category': user_flow.category,
			'business_function': user_flow.business_function,
			'entry_screen': user_flow.entry_screen,
			'exit_screen': user_flow.exit_screen,
			'screens': screens_list,
			'navigation_instructions': navigation_instructions,
			'total_steps': user_flow.total_steps or len(screens_list),
			'estimated_duration': user_flow.estimated_duration,
			'complexity': user_flow.complexity,
			'mermaid_diagram': user_flow.mermaid_diagram
		}

	except Exception as e:
		logger.error(f"Failed to get flow navigation: {e}", exc_info=True)
		return {
			'flow_id': user_flow_id,
			'flow_name': None,
			'screens': [],
			'navigation_instructions': [],
			'total_steps': 0,
			'estimated_duration': 0,
			'error': str(e)
		}


async def get_business_feature_flows(
	business_function_id: str,
	knowledge_id: str,
	job_id: str | None = None
) -> dict[str, Any]:
	"""
	Get all user flows and navigation for a business feature.
	
	Returns:
		Dict with:
		- business_function_id: Business function ID
		- business_function_name: Business function name
		- user_flows: List of user flows with navigation
		- all_screens: All screens used by this feature
		- all_actions: All actions used by this feature
	"""
	try:
		# Get business function
		business_function = await get_business_function(business_function_id)
		if not business_function:
			return {
				'business_function_id': business_function_id,
				'business_function_name': None,
				'user_flows': [],
				'all_screens': [],
				'all_actions': [],
				'error': 'Business function not found'
			}

		# Get related entities from cross-references
		related_screens = []
		related_actions = []
		related_workflows = []

		# Get screens
		if hasattr(business_function, 'related_screens') and business_function.related_screens:
			for screen_id in business_function.related_screens:
				screen = await get_screen(screen_id)
				if screen:
					related_screens.append(screen.dict())

		# Get actions
		if hasattr(business_function, 'related_actions') and business_function.related_actions:
			for action_id in business_function.related_actions:
				action = await get_action(action_id)
				if action:
					related_actions.append(action.dict())

		# Get workflows
		if hasattr(business_function, 'related_workflows') and business_function.related_workflows:
			for workflow_id in business_function.related_workflows:
				workflow = await get_workflow(workflow_id)
				if workflow:
					related_workflows.append(workflow.dict())

		# Get user flows (Phase 4: Now using persisted user flows)
		user_flows = []
		if hasattr(business_function, 'related_user_flows') and business_function.related_user_flows:
			for flow_id in business_function.related_user_flows:
				user_flow = await get_user_flow(flow_id)
				if user_flow:
					# Get navigation for this flow
					flow_nav = await get_flow_navigation(flow_id, knowledge_id, job_id)
					user_flows.append({
						'flow_id': user_flow.user_flow_id,
						'flow_name': user_flow.name,
						'description': user_flow.description,
						'category': user_flow.category,
						'screens': flow_nav.get('screens', []),
						'navigation': flow_nav.get('navigation_instructions', []),
						'total_steps': user_flow.total_steps,
						'estimated_duration': user_flow.estimated_duration
					})
				else:
					# Flow not found, add placeholder
					user_flows.append({
						'flow_id': flow_id,
						'note': 'User flow not found in database'
					})

		return {
			'business_function_id': business_function.business_function_id,
			'business_function_name': business_function.name,
			'description': business_function.description,
			'category': business_function.category,
			'user_flows': user_flows,
			'workflows': related_workflows,
			'all_screens': related_screens,
			'all_actions': related_actions,
			'total_screens': len(related_screens),
			'total_actions': len(related_actions),
			'total_workflows': len(related_workflows),
			'total_user_flows': len(user_flows)
		}

	except Exception as e:
		logger.error(f"Failed to get business feature flows: {e}", exc_info=True)
		return {
			'business_function_id': business_function_id,
			'business_function_name': None,
			'user_flows': [],
			'all_screens': [],
			'all_actions': [],
			'error': str(e)
		}


async def get_screen_context(
	screen_id: str,
	knowledge_id: str,
	job_id: str | None = None
) -> dict[str, Any]:
	"""
	Get complete context for a screen.
	
	Returns:
		Dict with:
		- screen_id: Screen ID
		- screen_name: Screen name
		- business_functions: Business functions that use this screen
		- user_flows: User flows that include this screen
		- available_actions: Actions available on this screen
		- available_tasks: Tasks that can be performed on this screen
		- can_navigate_to: Screens that can be navigated to from here
		- can_navigate_from: Screens that can navigate to here
	"""
	try:
		# Get screen
		screen = await get_screen(screen_id)
		if not screen:
			return {
				'screen_id': screen_id,
				'screen_name': None,
				'error': 'Screen not found'
			}

		# Get business functions
		business_functions = []
		if hasattr(screen, 'business_function_ids') and screen.business_function_ids:
			for bf_id in screen.business_function_ids:
				bf = await get_business_function(bf_id)
				if bf:
					business_functions.append({
						'business_function_id': bf.business_function_id,
						'name': bf.name,
						'category': bf.category
					})

		# Get user flows (Phase 4: Now using persisted user flows)
		user_flows = []
		if hasattr(screen, 'user_flow_ids') and screen.user_flow_ids:
			for flow_id in screen.user_flow_ids:
				user_flow = await get_user_flow(flow_id)
				if user_flow:
					user_flows.append({
						'flow_id': user_flow.user_flow_id,
						'flow_name': user_flow.name,
						'description': user_flow.description,
						'category': user_flow.category
					})
				else:
					user_flows.append({
						'flow_id': flow_id,
						'note': 'User flow not found in database'
					})

		# Get available actions
		available_actions = []
		if hasattr(screen, 'action_ids') and screen.action_ids:
			for action_id in screen.action_ids:
				action = await get_action(action_id)
				if action:
					action_dict = {
						'action_id': action.action_id,
						'name': action.name,
						'action_type': action.action_type,
						'category': action.category
					}
					# Phase 1.4: Include browser-use action mapping if available
					if hasattr(action, 'browser_use_action') and action.browser_use_action:
						action_dict['browser_use_action'] = action.browser_use_action
					if hasattr(action, 'confidence_score') and action.confidence_score is not None:
						action_dict['confidence_score'] = action.confidence_score
					available_actions.append(action_dict)

		# Get available tasks
		available_tasks = []
		if hasattr(screen, 'task_ids') and screen.task_ids:
			for task_id in screen.task_ids:
				task = await get_task(task_id)
				if task:
					available_tasks.append({
						'task_id': task.task_id,
						'name': task.name,
						'description': task.description,
						'category': task.category,
						'complexity': task.complexity
					})

		# Get outgoing transitions (can navigate to)
		can_navigate_to = []
		if hasattr(screen, 'outgoing_transitions') and screen.outgoing_transitions:
			for transition_id in screen.outgoing_transitions:
				transition = await get_transition(transition_id)
				if transition:
					to_screen = await get_screen(transition.to_screen_id)
					action = None
					if transition.action_id:
						action = await get_action(transition.action_id)

					can_navigate_to.append({
						'screen_id': transition.to_screen_id,
						'screen_name': to_screen.name if to_screen else transition.to_screen_id,
						'transition_id': transition.transition_id,
						'action': {
							'action_id': action.action_id if action else None,
							'action_name': action.name if action else transition.triggered_by.action_type if transition.triggered_by else None
						},
						'reliability': transition.reliability_score,
						'cost_ms': transition.cost.get('estimated_ms', 2000) if transition.cost else 2000
					})

		# Get incoming transitions (can navigate from)
		can_navigate_from = []
		if hasattr(screen, 'incoming_transitions') and screen.incoming_transitions:
			for transition_id in screen.incoming_transitions:
				transition = await get_transition(transition_id)
				if transition:
					from_screen = await get_screen(transition.from_screen_id)
					action = None
					if transition.action_id:
						action = await get_action(transition.action_id)

					can_navigate_from.append({
						'screen_id': transition.from_screen_id,
						'screen_name': from_screen.name if from_screen else transition.from_screen_id,
						'transition_id': transition.transition_id,
						'action': {
							'action_id': action.action_id if action else None,
							'action_name': action.name if action else transition.triggered_by.action_type if transition.triggered_by else None
						},
						'reliability': transition.reliability_score,
						'cost_ms': transition.cost.get('estimated_ms', 2000) if transition.cost else 2000
					})

		# Get workflows
		workflows = []
		if hasattr(screen, 'workflow_ids') and screen.workflow_ids:
			for workflow_id in screen.workflow_ids:
				workflow = await get_workflow(workflow_id)
				if workflow:
					workflows.append({
						'workflow_id': workflow.workflow_id,
						'name': workflow.name,
						'description': workflow.description
					})

		return {
			'screen_id': screen.screen_id,
			'screen_name': screen.name,
			'url_patterns': screen.url_patterns,
			'business_functions': business_functions,
			'user_flows': user_flows,
			'workflows': workflows,
			'available_actions': available_actions,
			'available_tasks': available_tasks,
			'can_navigate_to': can_navigate_to,
			'can_navigate_from': can_navigate_from,
			'total_actions': len(available_actions),
			'total_tasks': len(available_tasks),
			'total_outgoing': len(can_navigate_to),
			'total_incoming': len(can_navigate_from),
			'total_business_functions': len(business_functions),
			'total_user_flows': len(user_flows)
		}

	except Exception as e:
		logger.error(f"Failed to get screen context: {e}", exc_info=True)
		return {
			'screen_id': screen_id,
			'screen_name': None,
			'error': str(e)
		}
