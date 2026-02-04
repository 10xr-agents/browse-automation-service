"""
Business feature extraction from content.

Business features are distinct from business functions:
- **Business Functions**: High-level capabilities (e.g., "User Management", "Order Processing")
- **Business Features**: Specific features within functions (e.g., "User Registration", "Password Reset", "Order Tracking")

Extracts business features from:
- Documentation
- Video demonstrations
- Authenticated portal exploration
"""

import hashlib
import logging
import re
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from navigator.schemas import ContentChunk

logger = logging.getLogger(__name__)


class BusinessFeature(BaseModel):
	"""Business feature definition (distinct from business functions)."""
	feature_id: str = Field(..., description="Feature identifier")
	name: str = Field(..., description="Feature name")
	description: str = Field(..., description="Feature description")
	category: str = Field(default="general", description="Feature category")
	website_id: str = Field(..., description="Website identifier")
	
	# Business context
	business_value: str | None = Field(None, description="Business value of this feature")
	user_benefit: str | None = Field(None, description="User benefit description")
	metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
	
	# Cross-reference fields
	business_function_ids: list[str] = Field(
		default_factory=list,
		description="Business function IDs this feature supports"
	)
	screen_ids: list[str] = Field(
		default_factory=list,
		description="Screen IDs where this feature is available"
	)
	action_ids: list[str] = Field(
		default_factory=list,
		description="Action IDs for this feature"
	)
	task_ids: list[str] = Field(
		default_factory=list,
		description="Task IDs that use this feature"
	)
	user_flow_ids: list[str] = Field(
		default_factory=list,
		description="User flow IDs that include this feature"
	)
	workflow_ids: list[str] = Field(
		default_factory=list,
		description="Workflow IDs that use this feature"
	)


class BusinessFeatureExtractionResult(BaseModel):
	"""Result of business feature extraction."""
	features: list[BusinessFeature] = Field(default_factory=list)
	success: bool = True
	errors: list[str] = Field(default_factory=list)
	statistics: dict[str, Any] = Field(default_factory=dict)
	
	def calculate_statistics(self):
		"""Calculate extraction statistics."""
		self.statistics = {
			'total_features': len(self.features),
			'categories': list(set(f.category for f in self.features)),
			'features_with_screens': sum(1 for f in self.features if f.screen_ids),
			'features_with_actions': sum(1 for f in self.features if f.action_ids),
		}
	
	def add_error(self, error_type: str, error_message: str, error_context: dict[str, Any] | None = None):
		"""Add an error to the result."""
		error_str = f"{error_type}: {error_message}"
		if error_context:
			error_str += f" (Context: {error_context})"
		self.errors.append(error_str)
		self.success = False


class BusinessFeatureExtractor:
	"""
	Extracts business features from content chunks.
	
	Features are more granular than business functions:
	- Business Function: "User Management"
	- Business Features: "User Registration", "Password Reset", "Profile Update", "Account Deletion"
	"""
	
	def __init__(self, website_id: str = "unknown"):
		"""
		Initialize business feature extractor.
		
		Args:
			website_id: Website identifier for extracted features
		"""
		self.website_id = website_id
	
	def extract_features(
		self,
		content_chunks: list[ContentChunk],
		business_functions: list[Any] | None = None
	) -> BusinessFeatureExtractionResult:
		"""
		Extract business features from content chunks.
		
		Args:
			content_chunks: Content chunks to process
			business_functions: Optional list of business functions to link features to
		
		Returns:
			BusinessFeatureExtractionResult
		"""
		result = BusinessFeatureExtractionResult()
		
		try:
			logger.info(f"Extracting business features from {len(content_chunks)} content chunks")
			
			# Extract features from each chunk
			for chunk in content_chunks:
				features = self._extract_features_from_chunk(chunk, business_functions)
				result.features.extend(features)
			
			# Deduplicate features
			result.features = self._deduplicate_features(result.features)
			
			# Calculate statistics
			result.calculate_statistics()
			
			logger.info(
				f"✅ Extracted {result.statistics['total_features']} business features "
				f"({result.statistics['features_with_screens']} with screens, "
				f"{result.statistics['features_with_actions']} with actions)"
			)
		
		except Exception as e:
			logger.error(f"❌ Error extracting business features: {e}", exc_info=True)
			result.add_error("ExtractionError", str(e), {"exception_type": type(e).__name__})
		
		return result
	
	def _extract_features_from_chunk(
		self,
		chunk: ContentChunk,
		business_functions: list[Any] | None = None
	) -> list[BusinessFeature]:
		"""
		Extract business features from a single content chunk.
		
		Args:
			chunk: Content chunk to process
			business_functions: Optional list of business functions for linking
		
		Returns:
			List of extracted business features
		"""
		features = []
		
		# Pattern 1: Feature headings (## Feature Name, ### Feature Name)
		feature_patterns = [
			r'##\s+(.+?)\s+(?:Feature|Functionality|Capability)',
			r'###\s+(.+?)\s+(?:Feature|Functionality|Capability)',
			r'Feature:\s+(.+)',
			r'Functionality:\s+(.+)',
		]
		
		for pattern in feature_patterns:
			matches = re.finditer(pattern, chunk.content, re.IGNORECASE | re.MULTILINE)
			for match in matches:
				feature_name = match.group(1).strip()
				
				# Skip if it's actually a business function (too high-level)
				if self._is_business_function(feature_name):
					continue
				
				feature_id = self._generate_feature_id(feature_name)
				
				# Extract context around the match
				start = max(0, match.start() - 200)
				end = min(len(chunk.content), match.end() + 1000)
				context = chunk.content[start:end]
				
				# Create feature definition
				feature = self._create_feature_from_context(
					feature_id,
					feature_name,
					context,
					business_functions
				)
				features.append(feature)
		
		# Pattern 2: Feature lists (bullet points, numbered lists)
		list_patterns = [
			r'[-*]\s+(.+?)\s+(?:feature|functionality)',
			r'\d+\.\s+(.+?)\s+(?:feature|functionality)',
		]
		
		for pattern in list_patterns:
			matches = re.finditer(pattern, chunk.content, re.IGNORECASE)
			for match in matches:
				feature_name = match.group(1).strip()
				
				if self._is_business_function(feature_name):
					continue
				
				feature_id = self._generate_feature_id(feature_name)
				
				# Extract context
				start = max(0, match.start() - 100)
				end = min(len(chunk.content), match.end() + 500)
				context = chunk.content[start:end]
				
				feature = self._create_feature_from_context(
					feature_id,
					feature_name,
					context,
					business_functions
				)
				features.append(feature)
		
		return features
	
	def _create_feature_from_context(
		self,
		feature_id: str,
		feature_name: str,
		context: str,
		business_functions: list[Any] | None = None
	) -> BusinessFeature:
		"""
		Create feature definition from extracted context.
		
		Args:
			feature_id: Feature identifier
			feature_name: Feature name
			context: Surrounding context text
			business_functions: Optional business functions for linking
		
		Returns:
			BusinessFeature
		"""
		# Extract description (first paragraph after feature name)
		description = self._extract_description(context, feature_name)
		
		# Extract category
		category = self._extract_category(context, feature_name)
		
		# Extract business value
		business_value = self._extract_business_value(context)
		
		# Extract user benefit
		user_benefit = self._extract_user_benefit(context)
		
		# Link to business functions if provided
		business_function_ids = []
		if business_functions:
			business_function_ids = self._link_to_business_functions(
				feature_name,
				description,
				business_functions
			)
		
		# Phase 5.3: Extract screens mentioned in feature context
		screens_mentioned = self._extract_screens_mentioned(context)
		
		return BusinessFeature(
			feature_id=feature_id,
			name=feature_name,
			description=description,
			category=category,
			website_id=self.website_id,
			business_value=business_value,
			user_benefit=user_benefit,
			business_function_ids=business_function_ids,
			metadata={
				'extraction_method': 'rule_based',
				'extracted_from': 'documentation',
				# Phase 5.3: Store screens mentioned for linking
				'screens_mentioned': screens_mentioned,
			}
		)
	
	def _extract_description(self, context: str, feature_name: str) -> str:
		"""Extract feature description from context."""
		# Look for description after feature name
		# Pattern: feature name followed by description
		desc_pattern = rf'{re.escape(feature_name)}[:\s]+(.+?)(?:\n\n|\n##|$)'
		match = re.search(desc_pattern, context, re.IGNORECASE | re.DOTALL)
		
		if match:
			desc = match.group(1).strip()
			# Limit to first 500 characters
			return desc[:500] if len(desc) > 500 else desc
		
		# Fallback: use first sentence/paragraph
		sentences = re.split(r'[.!?]\s+', context)
		if sentences:
			return sentences[0][:500]
		
		return f"Feature: {feature_name}"
	
	def _extract_category(self, context: str, feature_name: str) -> str:
		"""Extract feature category from context."""
		# Common categories
		categories = {
			'authentication': ['login', 'sign in', 'sign up', 'register', 'password', 'auth'],
			'user_management': ['profile', 'account', 'user', 'settings', 'preferences'],
			'content': ['create', 'edit', 'delete', 'view', 'publish', 'content'],
			'communication': ['message', 'chat', 'email', 'notification', 'alert'],
			'commerce': ['cart', 'checkout', 'payment', 'order', 'purchase', 'product'],
			'analytics': ['report', 'analytics', 'dashboard', 'statistics', 'metrics'],
			'navigation': ['menu', 'search', 'filter', 'browse', 'explore'],
		}
		
		context_lower = context.lower()
		feature_lower = feature_name.lower()
		
		for category, keywords in categories.items():
			if any(keyword in context_lower or keyword in feature_lower for keyword in keywords):
				return category
		
		return "general"
	
	def _extract_business_value(self, context: str) -> str | None:
		"""Extract business value from context."""
		# Look for business value indicators
		value_patterns = [
			r'business value[:\s]+(.+?)(?:\n|$)',
			r'value proposition[:\s]+(.+?)(?:\n|$)',
			r'benefits[:\s]+(.+?)(?:\n|$)',
		]
		
		for pattern in value_patterns:
			match = re.search(pattern, context, re.IGNORECASE)
			if match:
				return match.group(1).strip()[:500]
		
		return None
	
	def _extract_screens_mentioned(self, context: str) -> list[str]:
		"""
		Phase 5.3: Extract screen names mentioned in feature context.
		
		Identifies screens, pages, or UI components mentioned in documentation.
		"""
		screens = []
		
		# Pattern 1: Screen/page mentions (e.g., "Login Screen", "Dashboard Page")
		screen_patterns = [
			r'(?:screen|page|view|interface|UI)[:\s]+["\']?([^"\'\n]+)["\']?',
			r'["\']([^"\']+(?:Screen|Page|View|Interface|UI))["\']',
			r'(?:on|in|from|to)\s+(?:the\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:screen|page|view)',
		]
		
		for pattern in screen_patterns:
			matches = re.finditer(pattern, context, re.IGNORECASE)
			for match in matches:
				screen_name = match.group(1).strip()
				# Filter out generic terms
				if screen_name and len(screen_name) > 3 and screen_name.lower() not in ['the', 'this', 'that', 'page', 'screen', 'view']:
					if screen_name not in screens:
						screens.append(screen_name)
		
		return screens
	
	def _extract_user_benefit(self, context: str) -> str | None:
		"""Extract user benefit from context."""
		# Look for user benefit indicators
		benefit_patterns = [
			r'user benefit[:\s]+(.+?)(?:\n|$)',
			r'users can[:\s]+(.+?)(?:\n|$)',
			r'enables users to[:\s]+(.+?)(?:\n|$)',
		]
		
		for pattern in benefit_patterns:
			match = re.search(pattern, context, re.IGNORECASE)
			if match:
				return match.group(1).strip()[:500]
		
		return None
	
	def _link_to_business_functions(
		self,
		feature_name: str,
		description: str,
		business_functions: list[Any]
	) -> list[str]:
		"""Link feature to relevant business functions."""
		linked_ids = []
		
		# Simple keyword matching
		feature_text = f"{feature_name} {description}".lower()
		
		for bf in business_functions:
			bf_text = f"{bf.name} {bf.description}".lower()
			
			# Check for keyword overlap
			feature_words = set(feature_text.split())
			bf_words = set(bf_text.split())
			
			# Common words (excluding stop words)
			stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
			feature_words = feature_words - stop_words
			bf_words = bf_words - stop_words
			
			# If significant overlap, link them
			if len(feature_words & bf_words) >= 2:
				linked_ids.append(bf.business_function_id)
		
		return linked_ids
	
	def _is_business_function(self, name: str) -> bool:
		"""Check if name is too high-level to be a feature (likely a business function)."""
		# Business functions are typically broader
		broad_terms = [
			'management', 'processing', 'administration', 'system',
			'platform', 'service', 'infrastructure', 'architecture'
		]
		
		name_lower = name.lower()
		return any(term in name_lower for term in broad_terms)
	
	def _deduplicate_features(self, features: list[BusinessFeature]) -> list[BusinessFeature]:
		"""Deduplicate features by name similarity."""
		if not features:
			return []
		
		unique_features = []
		seen_names = set()
		
		for feature in features:
			# Normalize name for comparison
			normalized = feature.name.lower().strip()
			
			if normalized not in seen_names:
				seen_names.add(normalized)
				unique_features.append(feature)
			else:
				# Merge with existing feature
				existing = next(f for f in unique_features if f.name.lower().strip() == normalized)
				# Merge metadata, IDs, etc.
				existing.screen_ids = list(set(existing.screen_ids + feature.screen_ids))
				existing.action_ids = list(set(existing.action_ids + feature.action_ids))
				existing.task_ids = list(set(existing.task_ids + feature.task_ids))
		
		return unique_features
	
	def _generate_feature_id(self, feature_name: str) -> str:
		"""Generate feature ID from name."""
		# Normalize name
		normalized = re.sub(r'[^a-zA-Z0-9\s]', '', feature_name.lower())
		normalized = re.sub(r'\s+', '_', normalized.strip())
		
		# Generate hash suffix for uniqueness
		hash_obj = hashlib.md5(feature_name.encode('utf-8'))
		hash_suffix = hash_obj.hexdigest()[:8]
		
		# Limit length
		if len(normalized) > 50:
			normalized = normalized[:50]
		
		return f"{normalized}_{hash_suffix}"
