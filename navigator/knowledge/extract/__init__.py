"""
Knowledge extraction modules.

Extracts structured knowledge from ingested content:
- ScreenExtractor: Screen definitions with negative indicators
- TaskExtractor: Task definitions with iterator spec
- ActionExtractor: Action definitions with preconditions
- TransitionExtractor: Transition definitions
- IteratorExtractor: Iterator and logic extraction
- BusinessFunctionExtractor: Business functions from video content (NEW)
- WorkflowExtractor: Operational workflows from video content (NEW)
- ActionTranslator: Translates ActionDefinition to BrowserUseAction (Phase 2)
"""

from navigator.knowledge.extract.actions import ActionExtractor
from navigator.knowledge.extract.browser_use_mapping import (
	ActionTranslator,
	BrowserUseAction,
	translate_actions_to_browser_use,
	translate_to_browser_use,
)
from navigator.knowledge.extract.business_functions import BusinessFunctionExtractor
from navigator.knowledge.extract.business_features import BusinessFeatureExtractor
from navigator.knowledge.extract.entities import EntityExtractor
from navigator.knowledge.extract.iterators import IteratorExtractor
from navigator.knowledge.extract.resolver import ReferenceResolver
from navigator.knowledge.extract.screens import ScreenExtractor, ScreenRegion
from navigator.knowledge.extract.tasks import TaskExtractor
from navigator.knowledge.extract.transitions import TransitionExtractor
from navigator.knowledge.extract.workflows import WorkflowExtractor

__all__ = [
	'ScreenExtractor',
	'TaskExtractor',
	'ActionExtractor',
	'TransitionExtractor',
	'IteratorExtractor',
	'EntityExtractor',
	'ReferenceResolver',
	'BusinessFunctionExtractor',
	'BusinessFeatureExtractor',  # Phase 8
	'WorkflowExtractor',
	'ScreenRegion',  # Phase 8
	# Phase 2: Browser-Use Mapping
	'BrowserUseAction',
	'ActionTranslator',
	'translate_to_browser_use',
	'translate_actions_to_browser_use',
]
