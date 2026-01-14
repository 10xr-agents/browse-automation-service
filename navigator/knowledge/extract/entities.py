"""
Entity and relationship extraction.

Extracts graph-ready entities and relationships from extracted knowledge:
- UI elements, parameters, data types (entities)
- CONTAINS, REQUIRES, TRIGGERS, EXECUTES (relationships)
"""

import logging
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from navigator.knowledge.extract.actions import ActionDefinition
from navigator.knowledge.extract.screens import ScreenDefinition
from navigator.knowledge.extract.tasks import TaskDefinition
from navigator.knowledge.extract.transitions import TransitionDefinition

logger = logging.getLogger(__name__)


# =============================================================================
# Entity Models
# =============================================================================

class UIElementEntity(BaseModel):
	"""UI element entity (buttons, inputs, links, dropdowns)."""
	entity_id: str = Field(..., description="Unique entity ID")
	entity_type: str = Field(default="UIElement", description="Entity type")
	name: str = Field(..., description="Element name")
	element_type: str = Field(..., description="Element type (button, input, link, dropdown)")
	selector: str | None = Field(None, description="CSS selector")
	screen_id: str | None = Field(None, description="Associated screen ID")
	metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class ParameterEntity(BaseModel):
	"""Parameter entity (action parameters, task inputs/outputs)."""
	entity_id: str = Field(..., description="Unique entity ID")
	entity_type: str = Field(default="Parameter", description="Entity type")
	name: str = Field(..., description="Parameter name")
	param_type: str = Field(..., description="Parameter type (input, output, action_param)")
	data_type: str = Field(..., description="Data type (string, integer, boolean, object)")
	required: bool = Field(default=True, description="Whether parameter is required")
	task_id: str | None = Field(None, description="Associated task ID")
	action_id: str | None = Field(None, description="Associated action ID")
	metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


# =============================================================================
# Relationship Models
# =============================================================================

class RelationshipDefinition(BaseModel):
	"""Relationship between entities."""
	relationship_id: str = Field(..., description="Unique relationship ID")
	relationship_type: str = Field(..., description="Relationship type")
	from_entity_id: str = Field(..., description="Source entity ID")
	to_entity_id: str = Field(..., description="Target entity ID")
	properties: dict[str, Any] = Field(default_factory=dict, description="Relationship properties")


# =============================================================================
# Extraction Result Models
# =============================================================================

class EntityExtractionResult(BaseModel):
	"""Result of entity and relationship extraction."""
	extraction_id: str = Field(default_factory=lambda: str(uuid4()), description="Extraction ID")
	
	# Entities
	ui_elements: list[UIElementEntity] = Field(default_factory=list, description="UI element entities")
	parameters: list[ParameterEntity] = Field(default_factory=list, description="Parameter entities")
	
	# Relationships
	relationships: list[RelationshipDefinition] = Field(default_factory=list, description="Relationships")
	
	# Metadata
	success: bool = Field(default=True, description="Whether extraction succeeded")
	errors: list[dict[str, Any]] = Field(default_factory=list, description="Extraction errors")
	statistics: dict[str, Any] = Field(default_factory=dict, description="Extraction statistics")
	
	def add_error(self, error_type: str, message: str, context: dict[str, Any] | None = None) -> None:
		"""Add an error to the result."""
		self.errors.append({
			'type': error_type,
			'message': message,
			'context': context or {}
		})
		self.success = False
	
	def calculate_statistics(self) -> None:
		"""Calculate extraction statistics."""
		# Count relationships by type
		relationship_types = {}
		for rel in self.relationships:
			relationship_types[rel.relationship_type] = relationship_types.get(rel.relationship_type, 0) + 1
		
		self.statistics = {
			'total_entities': len(self.ui_elements) + len(self.parameters),
			'ui_elements': len(self.ui_elements),
			'parameters': len(self.parameters),
			'total_relationships': len(self.relationships),
			'relationship_types': relationship_types,
			'orphaned_entities': self._count_orphaned_entities(),
		}
	
	def _count_orphaned_entities(self) -> int:
		"""Count entities with no relationships."""
		entity_ids = {e.entity_id for e in self.ui_elements} | {p.entity_id for p in self.parameters}
		referenced_ids = {r.from_entity_id for r in self.relationships} | {r.to_entity_id for r in self.relationships}
		return len(entity_ids - referenced_ids)


# =============================================================================
# Entity Extractor
# =============================================================================

class EntityExtractor:
	"""
	Extracts entities and relationships from knowledge definitions.
	
	Features:
	- UI element entity extraction
	- Parameter entity extraction
	- Relationship extraction (CONTAINS, REQUIRES, TRIGGERS, EXECUTES)
	- Graph-ready format
	"""
	
	def __init__(self):
		"""Initialize entity extractor."""
		pass
	
	def extract_entities_and_relationships(
		self,
		screens: list[ScreenDefinition],
		tasks: list[TaskDefinition],
		actions: list[ActionDefinition],
		transitions: list[TransitionDefinition]
	) -> EntityExtractionResult:
		"""
		Extract entities and relationships from all knowledge definitions.
		
		Args:
			screens: Screen definitions
			tasks: Task definitions
			actions: Action definitions
			transitions: Transition definitions
		
		Returns:
			EntityExtractionResult with entities and relationships
		"""
		result = EntityExtractionResult()
		
		try:
			logger.info(
				f"Extracting entities from {len(screens)} screens, {len(tasks)} tasks, "
				f"{len(actions)} actions, {len(transitions)} transitions"
			)
			
			# Extract UI elements from screens
			for screen in screens:
				ui_elements = self._extract_ui_elements_from_screen(screen)
				result.ui_elements.extend(ui_elements)
				
				# Create CONTAINS relationships
				for element in ui_elements:
					result.relationships.append(RelationshipDefinition(
						relationship_id=str(uuid4()),
						relationship_type='CONTAINS',
						from_entity_id=screen.screen_id,
						to_entity_id=element.entity_id,
						properties={'source': 'screen_ui_elements'}
					))
			
			# Extract parameters from tasks
			for task in tasks:
				parameters = self._extract_parameters_from_task(task)
				result.parameters.extend(parameters)
			
			# Create REQUIRES relationships (actions → UI elements)
			for action in actions:
				requires_rels = self._create_requires_relationships(action, result.ui_elements)
				result.relationships.extend(requires_rels)
			
			# Create TRIGGERS relationships (actions → transitions)
			for transition in transitions:
				triggers_rels = self._create_triggers_relationships(transition, actions)
				result.relationships.extend(triggers_rels)
			
			# Create EXECUTES relationships (task steps → actions)
			for task in tasks:
				executes_rels = self._create_executes_relationships(task, actions)
				result.relationships.extend(executes_rels)
			
			# Deduplicate entities
			result.ui_elements = self._deduplicate_ui_elements(result.ui_elements)
			result.parameters = self._deduplicate_parameters(result.parameters)
			result.relationships = self._deduplicate_relationships(result.relationships)
			
			# Validate
			validation_errors = self._validate_extraction(result)
			if validation_errors:
				for error in validation_errors:
					result.add_error("ValidationError", error)
			
			# Calculate statistics
			result.calculate_statistics()
			
			logger.info(
				f"✅ Extracted {result.statistics['total_entities']} entities "
				f"and {result.statistics['total_relationships']} relationships"
			)
		
		except Exception as e:
			logger.error(f"❌ Error extracting entities: {e}", exc_info=True)
			result.add_error("ExtractionError", str(e), {"exception_type": type(e).__name__})
		
		return result
	
	def _extract_ui_elements_from_screen(self, screen: ScreenDefinition) -> list[UIElementEntity]:
		"""Extract UI element entities from screen definition."""
		entities = []
		
		for element in screen.ui_elements:
			# Extract CSS selector from strategies
			css_selector = None
			if element.selector and element.selector.strategies:
				for strategy in element.selector.strategies:
					if strategy.type == "css" and strategy.css:
						css_selector = strategy.css
						break
			
			entity = UIElementEntity(
				entity_id=element.element_id,
				name=element.element_id,  # Use element_id as name since UIElement doesn't have name field
				element_type=element.type,  # Use element.type (not element_type)
				selector=css_selector,
				screen_id=screen.screen_id,
				metadata={
					'affordances': [a.dict() for a in element.affordances],
					'metadata': element.metadata,
				}
			)
			entities.append(entity)
		
		return entities
	
	def _extract_parameters_from_task(self, task: TaskDefinition) -> list[ParameterEntity]:
		"""Extract parameter entities from task definition."""
		entities = []
		
		# Extract inputs
		for input_param in task.io_spec.inputs:
			entity = ParameterEntity(
				entity_id=f"{task.task_id}__input__{input_param.name}",
				name=input_param.name,
				param_type='input',
				data_type=input_param.type,
				required=input_param.required,
				task_id=task.task_id,
				metadata={
					'volatility': input_param.volatility,
					'source': input_param.source,
					'description': input_param.description,
				}
			)
			entities.append(entity)
		
		# Extract outputs
		for output_param in task.io_spec.outputs:
			entity = ParameterEntity(
				entity_id=f"{task.task_id}__output__{output_param.name}",
				name=output_param.name,
				param_type='output',
				data_type=output_param.type,
				required=False,  # Outputs are produced, not required
				task_id=task.task_id,
				metadata={
					'extraction': output_param.extraction,
					'description': output_param.description,
				}
			)
			entities.append(entity)
		
		return entities
	
	def _create_requires_relationships(
		self,
		action: ActionDefinition,
		ui_elements: list[UIElementEntity]
	) -> list[RelationshipDefinition]:
		"""Create REQUIRES relationships (action → UI element)."""
		relationships = []
		
		# Match action target_selector with UI element selectors
		if action.target_selector:
			for element in ui_elements:
				if element.selector == action.target_selector:
					relationships.append(RelationshipDefinition(
						relationship_id=str(uuid4()),
						relationship_type='REQUIRES',
						from_entity_id=action.action_id,
						to_entity_id=element.entity_id,
						properties={'selector': action.target_selector}
					))
		
		return relationships
	
	def _create_triggers_relationships(
		self,
		transition: TransitionDefinition,
		actions: list[ActionDefinition]
	) -> list[RelationshipDefinition]:
		"""Create TRIGGERS relationships (action → transition)."""
		relationships = []
		
		# Match transition trigger with actions
		trigger_action_type = transition.triggered_by.action_type
		
		for action in actions:
			if action.action_type == trigger_action_type:
				relationships.append(RelationshipDefinition(
					relationship_id=str(uuid4()),
					relationship_type='TRIGGERS',
					from_entity_id=action.action_id,
					to_entity_id=transition.transition_id,
					properties={'trigger_type': trigger_action_type}
				))
		
		return relationships
	
	def _create_executes_relationships(
		self,
		task: TaskDefinition,
		actions: list[ActionDefinition]
	) -> list[RelationshipDefinition]:
		"""Create EXECUTES relationships (task step → action)."""
		relationships = []
		
		for step in task.steps:
			# Match step action with action definitions
			step_action_type = step.type
			
			for action in actions:
				if action.action_type == step_action_type:
					relationships.append(RelationshipDefinition(
						relationship_id=str(uuid4()),
						relationship_type='EXECUTES',
						from_entity_id=f"{task.task_id}__step__{step.step_id}",
						to_entity_id=action.action_id,
						properties={'step_order': step.order}
					))
		
		return relationships
	
	def _deduplicate_ui_elements(self, elements: list[UIElementEntity]) -> list[UIElementEntity]:
		"""Deduplicate UI elements by entity_id."""
		seen = set()
		unique = []
		
		for element in elements:
			if element.entity_id not in seen:
				seen.add(element.entity_id)
				unique.append(element)
		
		return unique
	
	def _deduplicate_parameters(self, parameters: list[ParameterEntity]) -> list[ParameterEntity]:
		"""Deduplicate parameters by entity_id."""
		seen = set()
		unique = []
		
		for param in parameters:
			if param.entity_id not in seen:
				seen.add(param.entity_id)
				unique.append(param)
		
		return unique
	
	def _deduplicate_relationships(self, relationships: list[RelationshipDefinition]) -> list[RelationshipDefinition]:
		"""Deduplicate relationships by from_entity_id + to_entity_id + type."""
		seen = set()
		unique = []
		
		for rel in relationships:
			key = (rel.from_entity_id, rel.to_entity_id, rel.relationship_type)
			if key not in seen:
				seen.add(key)
				unique.append(rel)
		
		return unique
	
	def _validate_extraction(self, result: EntityExtractionResult) -> list[str]:
		"""Validate extraction result."""
		errors = []
		
		# Check for duplicate entity IDs
		all_entity_ids = [e.entity_id for e in result.ui_elements] + [p.entity_id for p in result.parameters]
		if len(all_entity_ids) != len(set(all_entity_ids)):
			errors.append("Duplicate entity IDs found")
		
		# Relationships reference external IDs (screens, tasks, actions, transitions)
		# So we don't validate them against extracted entities
		# This is intentional - relationships connect entities to their containers/definitions
		
		return errors


def extract_entities_and_relationships(
	screens: list[ScreenDefinition],
	tasks: list[TaskDefinition],
	actions: list[ActionDefinition],
	transitions: list[TransitionDefinition]
) -> EntityExtractionResult:
	"""
	Extract entities and relationships from knowledge definitions.
	
	Args:
		screens: Screen definitions
		tasks: Task definitions
		actions: Action definitions
		transitions: Transition definitions
	
	Returns:
		EntityExtractionResult
	"""
	extractor = EntityExtractor()
	return extractor.extract_entities_and_relationships(screens, tasks, actions, transitions)
