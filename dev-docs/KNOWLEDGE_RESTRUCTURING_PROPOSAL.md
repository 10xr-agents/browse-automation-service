# Knowledge Restructuring Proposal

**Goal**: Restructure knowledge to enable general agents to communicate with browser-use agents for website exploration and navigation.

**Date**: 2026-01-14

---

## Problem Analysis

### Current Issues

1. **Mixed Content Types**: Knowledge contains both:
   - **Documentation/Instructional Content** (voice AI guidelines, conversational protocols)
   - **Web UI Knowledge** (actual screens, forms, navigation paths)

2. **Non-Interpretable Screens**: Screens extracted from documentation have:
   - `state_signature` with entire instruction paragraphs (won't match DOM)
   - Generic URL patterns like `.*/div.*` (too broad)
   - No actual UI elements or actionable selectors

3. **Missing Browser-Use Mapping**: Knowledge doesn't directly map to browser-use tools:
   - `navigate`, `click`, `type`, `scroll`, `extract`, etc.
   - No clear translation from knowledge → browser-use actions

4. **Agent Communication Gap**: No standardized format for:
   - General agent → Browser-use agent communication
   - Knowledge query → Actionable instructions

---

## Proposed Solution

### 1. Content Type Separation

**Add `content_type` field to all knowledge entities:**

```python
class ScreenDefinition(BaseModel):
    # ... existing fields ...
    content_type: str = Field(
        default="web_ui",
        description="Content type: 'web_ui' | 'documentation' | 'video_transcript' | 'api_docs'"
    )
    is_actionable: bool = Field(
        default=True,
        description="Whether this screen can be navigated to by browser automation"
    )
```

**Filtering Logic:**
- Only `content_type="web_ui"` and `is_actionable=True` screens are used for navigation
- Documentation screens are stored separately for reference but not used for automation

---

### 2. Browser-Use Action Mapping

**Create `BrowserUseAction` schema that directly maps to browser-use tools:**

```python
class BrowserUseAction(BaseModel):
    """Action directly mappable to browser-use tools."""
    tool_name: str = Field(..., description="Browser-use tool name (navigate, click, type, etc.)")
    parameters: dict[str, Any] = Field(..., description="Tool parameters")
    description: str = Field(..., description="Human-readable description")
    
    # Example:
    # {
    #   "tool_name": "navigate",
    #   "parameters": {"url": "https://app.spadeworks.co/dashboard"},
    #   "description": "Navigate to dashboard"
    # }
```

**Action Translation Layer:**

```python
class ActionTranslator:
    """Translates knowledge actions to browser-use actions."""
    
    def translate_action(self, action: ActionDefinition) -> BrowserUseAction:
        """Convert ActionDefinition to BrowserUseAction."""
        mapping = {
            "navigate": "navigate",
            "click": "click",
            "type": "input",  # browser-use uses 'input' not 'type'
            "scroll": "scroll",
            "wait": "wait",
            # ... etc
        }
        
        tool_name = mapping.get(action.action_type, action.action_type)
        
        # Convert parameters
        params = {}
        if action.action_type == "click":
            params["index"] = self._get_element_index(action.target_selector)
        elif action.action_type == "type":
            params["text"] = action.parameters.get("text", "")
            params["index"] = self._get_element_index(action.target_selector)
        # ... etc
        
        return BrowserUseAction(
            tool_name=tool_name,
            parameters=params,
            description=action.name
        )
```

---

### 3. Agent Communication Protocol

**Create `AgentInstruction` schema for general agent → browser-use agent communication:**

```python
class AgentInstruction(BaseModel):
    """Instruction from general agent to browser-use agent."""
    instruction_type: str = Field(..., description="'navigate_to_screen' | 'execute_task' | 'find_element' | 'explore_website'")
    target: str = Field(..., description="Screen ID, task ID, or URL")
    knowledge_id: str = Field(..., description="Knowledge ID to query")
    context: dict[str, Any] = Field(default_factory=dict, description="Additional context")
    
    # Response format
    response: dict[str, Any] = Field(..., description="Response with browser-use actions")
```

**Example Usage:**

```python
# General agent wants to navigate to dashboard
instruction = AgentInstruction(
    instruction_type="navigate_to_screen",
    target="dashboard_screen_id",
    knowledge_id="696fc99db002d6c4ff0d6b3c",
    context={}
)

# System translates to browser-use actions
response = {
    "actions": [
        {
            "tool": "navigate",
            "params": {"url": "https://app.spadeworks.co/dashboard"}
        },
        {
            "tool": "wait",
            "params": {"seconds": 3}
        },
        {
            "tool": "screenshot",  # Verify we're on correct screen
            "params": {}
        }
    ],
    "expected_screen": {
        "screen_id": "dashboard_screen_id",
        "url_patterns": ["https://app.spadeworks.co/dashboard"],
        "verification": {
            "dom_contains": ["Dashboard", "Call Performance"],
            "url_matches": ".*/dashboard.*"
        }
    }
}
```

---

### 4. Screen Recognition Fixes

**Improve screen extraction to only extract actual web UI screens:**

```python
class ScreenExtractor:
    def _is_web_ui_screen(self, context: str, screen_name: str) -> bool:
        """Determine if this is a web UI screen or documentation."""
        # Documentation indicators
        doc_indicators = [
            "conversational", "phone call", "voice assistant",
            "follow-up questions", "empathetic listener",
            "instruction", "guideline", "protocol"
        ]
        
        context_lower = context.lower()
        name_lower = screen_name.lower()
        
        # If contains documentation keywords, it's not a web UI screen
        if any(indicator in context_lower or indicator in name_lower 
               for indicator in doc_indicators):
            return False
        
        # Web UI indicators
        ui_indicators = [
            "dashboard", "form", "button", "input", "navigation",
            "page", "screen", "modal", "dialog", "menu"
        ]
        
        # Must have URL pattern or UI element mentions
        has_url = bool(re.search(r'https?://|/[\w/-]+', context))
        has_ui = any(indicator in context_lower for indicator in ui_indicators)
        
        return has_url or has_ui
    
    def extract_screens(self, content_chunks: list[ContentChunk]) -> ScreenExtractionResult:
        """Extract screens, filtering out documentation."""
        result = ScreenExtractionResult()
        
        for chunk in content_chunks:
            screens = self._extract_screens_from_chunk(chunk)
            
            for screen in screens:
                # Filter out documentation screens
                if not self._is_web_ui_screen(chunk.content, screen.name):
                    screen.content_type = "documentation"
                    screen.is_actionable = False
                    logger.info(f"Filtered documentation screen: {screen.screen_id}")
                else:
                    screen.content_type = "web_ui"
                    screen.is_actionable = True
                
                result.screens.append(screen)
        
        return result
```

**Improve state signature extraction:**

```python
def _extract_state_signature(self, context: str, screen_name: str) -> StateSignature:
    """Extract state signature with actual DOM indicators."""
    signature = StateSignature()
    
    # Look for actual UI elements, not instruction text
    # Pattern: "button with text 'Submit'", "input field 'email'", etc.
    ui_element_patterns = [
        r'button.*?["\']([^"\']+)["\']',
        r'input.*?["\']([^"\']+)["\']',
        r'link.*?["\']([^"\']+)["\']',
        r'heading.*?["\']([^"\']+)["\']',
    ]
    
    for pattern in ui_element_patterns:
        matches = re.finditer(pattern, context, re.IGNORECASE)
        for match in matches:
            element_text = match.group(1).strip()
            # Only add if it's a reasonable UI element (not instruction text)
            if len(element_text) < 50 and not any(
                word in element_text.lower() 
                for word in ['instruction', 'protocol', 'guideline']
            ):
                signature.required_indicators.append(Indicator(
                    type='dom_contains',
                    value=element_text,
                    selector='body',
                    reason='UI element for screen recognition'
                ))
    
    # Extract URL patterns from actual URLs, not generic paths
    url_patterns = self._extract_url_patterns(context)
    for pattern in url_patterns:
        # Only add specific URL patterns, not generic ones
        if not pattern.startswith('.*/') or len(pattern) > 10:
            signature.required_indicators.append(Indicator(
                type='url_matches',
                pattern=pattern,
                reason='URL pattern for screen recognition'
            ))
    
    return signature
```

---

### 5. Knowledge Query API for Agents

**Create agent-friendly query endpoints:**

```python
@router.post("/knowledge/{knowledge_id}/query")
async def query_knowledge_for_agent(
    knowledge_id: str,
    query: AgentQuery
) -> AgentResponse:
    """
    Agent-friendly knowledge query endpoint.
    
    Query types:
    - "navigate_to": Get navigation instructions to a screen
    - "execute_task": Get task execution steps
    - "find_screen": Find screen by URL or description
    - "get_actions": Get available actions on current screen
    """
    
    if query.query_type == "navigate_to":
        # Get navigation path
        current_url = query.context.get("current_url")
        target_screen_id = query.target
        
        # Find current screen
        current_screen = await find_screen_by_url(current_url, knowledge_id)
        
        if current_screen:
            path = await get_navigation_path(
                current_screen.screen_id,
                target_screen_id,
                knowledge_id
            )
            
            # Translate to browser-use actions
            actions = []
            for step in path['steps']:
                browser_action = translate_to_browser_use(step)
                actions.append(browser_action)
            
            return AgentResponse(
                success=True,
                actions=actions,
                expected_result={
                    "screen_id": target_screen_id,
                    "verification": get_screen_verification(target_screen_id)
                }
            )
    
    elif query.query_type == "execute_task":
        task = await get_task(query.target)
        
        if not task:
            return AgentResponse(success=False, error="Task not found")
        
        # Translate task steps to browser-use actions
        actions = []
        for step in task.steps:
            browser_action = translate_task_step_to_browser_use(step)
            actions.append(browser_action)
        
        return AgentResponse(
            success=True,
            actions=actions,
            expected_result={
                "task_id": task.task_id,
                "success_criteria": task.success_criteria
            }
        )
    
    # ... etc
```

---

### 6. Screen Recognition Service

**Create service to match current browser state to known screens:**

```python
class ScreenRecognitionService:
    """Matches current browser state to known screens."""
    
    async def recognize_screen(
        self,
        current_url: str,
        dom_summary: str,
        knowledge_id: str
    ) -> dict[str, Any]:
        """
        Recognize which screen the browser is currently on.
        
        Returns:
        {
            "screen_id": "dashboard_abc123",
            "confidence": 0.95,
            "matched_indicators": [...],
            "available_actions": [...]
        }
        """
        
        # Get all actionable screens for this knowledge
        screens = await query_screens_by_knowledge_id(
            knowledge_id,
            filter={"content_type": "web_ui", "is_actionable": True}
        )
        
        best_match = None
        best_score = 0.0
        
        for screen in screens:
            score = self._calculate_match_score(
                screen,
                current_url,
                dom_summary
            )
            
            if score > best_score:
                best_score = score
                best_match = screen
        
        if best_match and best_score > 0.7:  # Confidence threshold
            return {
                "screen_id": best_match.screen_id,
                "screen_name": best_match.name,
                "confidence": best_score,
                "matched_indicators": self._get_matched_indicators(
                    best_match,
                    current_url,
                    dom_summary
                ),
                "available_actions": await get_actions_for_screen(
                    best_match.screen_id,
                    knowledge_id
                )
            }
        
        return {
            "screen_id": None,
            "confidence": best_score,
            "message": "No matching screen found"
        }
    
    def _calculate_match_score(
        self,
        screen: ScreenDefinition,
        current_url: str,
        dom_summary: str
    ) -> float:
        """Calculate how well screen matches current state."""
        score = 0.0
        
        # URL pattern matching (40% weight)
        url_match = False
        for pattern in screen.url_patterns:
            if re.match(pattern, current_url):
                url_match = True
                break
        
        if url_match:
            score += 0.4
        
        # DOM indicator matching (60% weight)
        matched_indicators = 0
        total_indicators = len(screen.state_signature.required_indicators)
        
        if total_indicators > 0:
            for indicator in screen.state_signature.required_indicators:
                if indicator.type == "dom_contains":
                    if indicator.value and indicator.value.lower() in dom_summary.lower():
                        matched_indicators += 1
                elif indicator.type == "url_matches":
                    if re.match(indicator.pattern or "", current_url):
                        matched_indicators += 1
            
            indicator_score = matched_indicators / total_indicators
            score += indicator_score * 0.6
        
        return score
```

---

### 7. Task-to-Browser-Use Translation

**Translate task steps to browser-use actions:**

```python
def translate_task_step_to_browser_use(step: TaskStep) -> BrowserUseAction:
    """Convert task step to browser-use action."""
    
    action = step.action
    
    if action.action_type == "click":
        return BrowserUseAction(
            tool_name="click",
            parameters={
                "index": action.target  # Assuming target is element index
            },
            description=step.description or f"Click {action.target}"
        )
    
    elif action.action_type == "type":
        return BrowserUseAction(
            tool_name="input",
            parameters={
                "index": action.target,
                "text": action.parameters.get("text", "")
            },
            description=step.description or f"Type into {action.target}"
        )
    
    elif action.action_type == "navigate":
        return BrowserUseAction(
            tool_name="navigate",
            parameters={
                "url": action.target
            },
            description=step.description or f"Navigate to {action.target}"
        )
    
    # ... handle other action types
```

---

### 6. LLM-Based Action Extrapolation

**Problem**: When we have knowledge about two actions (e.g., "Action A" and "Action C"), we often don't know what intermediate actions or screen transitions occurred between them. This creates gaps in navigation paths.

**Solution**: Use Gemini LLM to infer missing screen actions and transitions based on:
- Known start and end actions
- Screen context
- Website structure
- Common UI patterns

**Extrapolation Schema:**

```python
class ActionGap(BaseModel):
    """Represents a gap between two known actions."""
    from_action_id: str = Field(..., description="Starting action ID")
    to_action_id: str = Field(..., description="Ending action ID")
    from_screen_id: str | None = Field(None, description="Starting screen ID")
    to_screen_id: str | None = Field(None, description="Ending screen ID")
    context: dict[str, Any] = Field(default_factory=dict, description="Additional context")


class ExtrapolationRequest(BaseModel):
    """Request for LLM-based action extrapolation."""
    gaps: list[ActionGap] = Field(..., description="List of action gaps to fill")
    knowledge_id: str = Field(..., description="Knowledge ID for context")
    website_id: str = Field(..., description="Website ID for context")
    include_screens: bool = Field(default=True, description="Whether to infer screen transitions")
    max_intermediate_steps: int = Field(default=5, description="Maximum intermediate steps to infer")


class InferredAction(BaseModel):
    """An action inferred by LLM."""
    action_type: str = Field(..., description="Action type (click, type, navigate, etc.)")
    target: str = Field(..., description="Target element or URL")
    description: str = Field(..., description="Human-readable description")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score (0-1)")
    reasoning: str = Field(..., description="LLM reasoning for this action")
    screen_id: str | None = Field(None, description="Screen ID where this action occurs")


class ExtrapolationResult(BaseModel):
    """Result of action extrapolation."""
    gaps_filled: int = Field(..., description="Number of gaps successfully filled")
    inferred_actions: list[InferredAction] = Field(..., description="Inferred actions")
    inferred_transitions: list[dict[str, Any]] = Field(default_factory=list, description="Inferred screen transitions")
    confidence_scores: dict[str, float] = Field(default_factory=dict, description="Confidence scores per gap")
    errors: list[str] = Field(default_factory=list, description="Extrapolation errors")
```

**Extrapolation Service:**

```python
class ActionExtrapolationService:
    """Uses Gemini LLM to infer missing actions and transitions."""
    
    def __init__(self, llm_client: Any):
        """Initialize with Gemini client."""
        self.llm_client = llm_client
    
    async def extrapolate_actions(
        self,
        request: ExtrapolationRequest
    ) -> ExtrapolationResult:
        """
        Infer missing actions between known actions.
        
        Example scenario:
        - Known: Action A (click "Login") on Screen 1
        - Known: Action C (type "username") on Screen 2
        - Missing: What happened between A and C?
        - Inferred: Action B (navigate to login page, wait for page load)
        """
        result = ExtrapolationResult(gaps_filled=0)
        
        # Get context for each gap
        for gap in request.gaps:
            try:
                # Get known actions
                from_action = await get_action(gap.from_action_id)
                to_action = await get_action(gap.to_action_id)
                
                # Get screen context if available
                from_screen = await get_screen(gap.from_screen_id) if gap.from_screen_id else None
                to_screen = await get_screen(gap.to_screen_id) if gap.to_screen_id else None
                
                # Get website structure for context
                website_screens = await query_screens_by_website(
                    request.website_id,
                    actionable_only=True
                )
                
                # Build prompt for Gemini
                prompt = self._build_extrapolation_prompt(
                    from_action=from_action,
                    to_action=to_action,
                    from_screen=from_screen,
                    to_screen=to_screen,
                    website_screens=website_screens,
                    max_steps=request.max_intermediate_steps
                )
                
                # Call Gemini LLM
                response = await self.llm_client.generate_content(
                    model="gemini-2.0-flash-exp",
                    contents=prompt,
                    generation_config={
                        "temperature": 0.3,  # Lower temperature for more deterministic inference
                        "max_output_tokens": 2000,
                    }
                )
                
                # Parse LLM response
                inferred = self._parse_extrapolation_response(response.text)
                
                # Validate and add to result
                if inferred:
                    result.inferred_actions.extend(inferred['actions'])
                    if request.include_screens and inferred.get('transitions'):
                        result.inferred_transitions.extend(inferred['transitions'])
                    result.gaps_filled += 1
                    result.confidence_scores[gap.from_action_id] = inferred.get('confidence', 0.7)
                
            except Exception as e:
                logger.error(f"Failed to extrapolate actions for gap {gap.from_action_id} -> {gap.to_action_id}: {e}")
                result.errors.append(f"Gap {gap.from_action_id} -> {gap.to_action_id}: {str(e)}")
        
        return result
    
    def _build_extrapolation_prompt(
        self,
        from_action: ActionDefinition,
        to_action: ActionDefinition,
        from_screen: ScreenDefinition | None,
        to_screen: ScreenDefinition | None,
        website_screens: list[ScreenDefinition],
        max_steps: int
    ) -> str:
        """Build prompt for Gemini to infer missing actions."""
        
        prompt = f"""You are analyzing a website automation workflow. You need to infer what actions occurred between two known actions.

KNOWN START ACTION:
- Action ID: {from_action.action_id}
- Action Type: {from_action.action_type}
- Action Name: {from_action.name}
- Target: {from_action.target_selector or 'N/A'}
- Screen: {from_screen.name if from_screen else 'Unknown'}

KNOWN END ACTION:
- Action ID: {to_action.action_id}
- Action Type: {to_action.action_type}
- Action Name: {to_action.name}
- Target: {to_action.target_selector or 'N/A'}
- Screen: {to_screen.name if to_screen else 'Unknown'}

WEBSITE CONTEXT:
Available screens: {', '.join([s.name for s in website_screens[:10]])}

TASK:
Infer the most likely sequence of actions that occurred between the start and end actions.
Consider:
1. Common UI patterns (navigation, form filling, waiting for page loads)
2. Screen transitions (if screens are different)
3. Required intermediate steps (e.g., page navigation, element waiting, scrolling)
4. Browser automation best practices

OUTPUT FORMAT (JSON):
{{
  "actions": [
    {{
      "action_type": "navigate|click|type|wait|scroll|...",
      "target": "element selector, URL, or description",
      "description": "Human-readable description",
      "confidence": 0.0-1.0,
      "reasoning": "Why this action is likely",
      "screen_id": "screen_id if known, null otherwise"
    }}
  ],
  "transitions": [
    {{
      "from_screen_id": "...",
      "to_screen_id": "...",
      "trigger_action": "action description"
    }}
  ],
  "confidence": 0.0-1.0,
  "reasoning": "Overall reasoning for the inferred sequence"
}}

Limit to maximum {max_steps} intermediate actions.
"""
        return prompt
    
    def _parse_extrapolation_response(self, response_text: str) -> dict[str, Any] | None:
        """Parse Gemini LLM response into structured format."""
        try:
            import json
            # Extract JSON from response (handle markdown code blocks)
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', response_text, re.DOTALL)
            if not json_match:
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            
            if json_match:
                data = json.loads(json_match.group(1))
                return data
            else:
                logger.warning("Could not parse JSON from LLM response")
                return None
        except Exception as e:
            logger.error(f"Failed to parse extrapolation response: {e}")
            return None
```

**Integration with Knowledge Pipeline:**

```python
class KnowledgePipeline:
    # ... existing code ...
    
    async def fill_action_gaps(
        self,
        knowledge_id: str,
        website_id: str
    ) -> ExtrapolationResult:
        """
        Identify and fill gaps in action sequences using LLM extrapolation.
        
        This method:
        1. Analyzes all known actions and transitions
        2. Identifies gaps (actions that should be connected but aren't)
        3. Uses Gemini LLM to infer missing actions
        4. Validates and stores inferred actions
        """
        # Get all actions for this knowledge
        actions = await query_actions_by_knowledge_id(knowledge_id)
        transitions = await query_transitions_by_knowledge_id(knowledge_id)
        
        # Identify gaps
        gaps = self._identify_action_gaps(actions, transitions)
        
        if not gaps:
            logger.info("No action gaps found")
            return ExtrapolationResult(gaps_filled=0)
        
        logger.info(f"Found {len(gaps)} action gaps, extrapolating with LLM...")
        
        # Create extrapolation service
        from navigator.knowledge.ingest.video.frame_analysis.vision import get_gemini_client
        llm_client = get_gemini_client()
        extrapolation_service = ActionExtrapolationService(llm_client)
        
        # Extrapolate
        request = ExtrapolationRequest(
            gaps=gaps,
            knowledge_id=knowledge_id,
            website_id=website_id,
            include_screens=True,
            max_intermediate_steps=5
        )
        
        result = await extrapolation_service.extrapolate_actions(request)
        
        # Store inferred actions (with lower confidence flag)
        for inferred_action in result.inferred_actions:
            if inferred_action.confidence > 0.6:  # Only store high-confidence inferences
                await self._store_inferred_action(inferred_action, knowledge_id, website_id)
        
        logger.info(f"✅ Filled {result.gaps_filled} action gaps with {len(result.inferred_actions)} inferred actions")
        
        return result
    
    def _identify_action_gaps(
        self,
        actions: list[ActionDefinition],
        transitions: list[TransitionDefinition]
    ) -> list[ActionGap]:
        """Identify gaps in action sequences."""
        gaps = []
        
        # Build action graph
        action_to_screen = {}
        screen_to_actions = {}
        
        for action in actions:
            for screen_id in action.screen_ids:
                action_to_screen[action.action_id] = screen_id
                if screen_id not in screen_to_actions:
                    screen_to_actions[screen_id] = []
                screen_to_actions[screen_id].append(action.action_id)
        
        # Find transitions that don't have clear action paths
        for transition in transitions:
            from_screen_id = transition.from_screen_id
            to_screen_id = transition.to_screen_id
            
            # If transition has no action, it's a gap
            if not transition.action_id:
                # Find actions on from_screen and to_screen
                from_actions = screen_to_actions.get(from_screen_id, [])
                to_actions = screen_to_actions.get(to_screen_id, [])
                
                if from_actions and to_actions:
                    # Create gap between last action on from_screen and first action on to_screen
                    gaps.append(ActionGap(
                        from_action_id=from_actions[-1],
                        to_action_id=to_actions[0],
                        from_screen_id=from_screen_id,
                        to_screen_id=to_screen_id
                    ))
        
        return gaps
```

**Usage Example:**

```python
# After knowledge extraction, fill gaps
pipeline = KnowledgePipeline(...)
result = await pipeline.fill_action_gaps(knowledge_id, website_id)

# Inferred actions are now available for navigation
# They're marked with confidence scores and can be validated
```

---

## Implementation Plan

### Phase 1: Content Type Separation ✅ COMPLETE
1. ✅ Add `content_type` and `is_actionable` fields to `ScreenDefinition`
2. ✅ Update screen extractor to classify screens with `_is_web_ui_screen()` method
3. ✅ Filter documentation screens from navigation queries
4. ✅ Add content type statistics to extraction results
5. ✅ Update query functions (`query_screens_by_knowledge_id`, `query_screens_by_website`) with filtering

**Implementation Details:**
- Added `content_type` field with validator (valid types: 'web_ui', 'documentation', 'video_transcript', 'api_docs', 'unknown')
- Added `is_actionable` boolean field
- Classification logic filters out documentation screens (voice AI, conversational, instructional content)
- Statistics track: `web_ui_screens`, `documentation_screens`, `actionable_screens`, `non_actionable_screens`
- Query functions support `content_type` and `actionable_only` parameters

**Files Modified:**
- `navigator/knowledge/extract/screens.py`: Added fields, classification method, statistics
- `navigator/knowledge/persist/documents/screens.py`: Added filtering parameters to query functions

### Phase 2: Browser-Use Action Mapping ✅ COMPLETE
1. ✅ Create `BrowserUseAction` schema with tool_name, parameters, description
2. ✅ Implement `ActionTranslator` class with full action type mapping
3. ✅ Add translation methods for all action types (40+ action types mapped)
4. ✅ Parameter conversion logic for all major action types
5. ✅ Convenience functions for easy translation

**Implementation Details:**
- Created `BrowserUseAction` Pydantic model with tool_name, parameters, description, confidence, screen_id
- `ActionTranslator` class maps knowledge action types to browser-use tool names
- Comprehensive parameter conversion for: navigate, click, type/input, scroll, wait, send_keys, upload_file, select_dropdown, fill_form, drag_drop, evaluate, extract, and more
- Handles element index vs selector conversion
- Supports all browser-use tools: navigate, click, input, scroll, wait, go_back, go_forward, refresh, send_keys, right_click, double_click, hover, drag_drop, type_slowly, select_all, copy, paste, cut, clear, upload_file, select_dropdown, fill_form, submit_form, reset_form, play_video, pause_video, seek_video, adjust_volume, toggle_mute, screenshot, evaluate, extract, switch, close

**Files Created:**
- `navigator/knowledge/extract/browser_use_mapping.py`: Complete translation layer with ActionTranslator class and convenience functions

### Phase 3: Agent Communication API ✅ COMPLETE
1. ✅ Create `AgentInstruction` and `AgentResponse` schemas
2. ✅ Implement agent query endpoint (`POST /knowledge/{knowledge_id}/query`)
3. ✅ Add `ScreenRecognitionService` for matching browser state to screens
4. ✅ Support for all instruction types: navigate_to_screen, execute_task, find_screen, get_actions, get_screen_context

**Implementation Details:**
- Created `AgentInstruction` schema with instruction_type, target, knowledge_id, context
- Created `AgentResponse` schema with success, actions (BrowserUseAction list), expected_result, error, metadata
- `ScreenRecognitionService` matches current browser state (URL + DOM) to known screens using:
  - URL pattern matching (40% weight)
  - DOM indicator matching (60% weight)
  - Confidence threshold of 0.7 for positive matches
- Agent query endpoint supports:
  - `navigate_to_screen`: Get navigation path and translate to browser-use actions
  - `execute_task`: Get task steps and translate to browser-use actions
  - `find_screen`: Recognize screen from current URL/DOM
  - `get_actions`: Get available actions on current screen
  - `get_screen_context`: Get complete screen context (business functions, user flows, etc.)
- Automatic screen recognition when current_screen_id not provided
- Returns browser-use actions ready for execution

**Files Created:**
- `navigator/knowledge/agent_communication.py`: AgentInstruction, AgentResponse schemas, ScreenRecognitionService

**Files Modified:**
- `navigator/knowledge/rest_api_knowledge.py`: Added agent query endpoint

### Phase 4: Screen Recognition Improvements ✅ COMPLETE
1. ✅ Improve screen extraction to only extract web UI screens (already done in Phase 1)
2. ✅ Fix state signature extraction to use actual DOM indicators
3. ✅ Improve URL pattern extraction to be more specific

**Implementation Details:**
- **State Signature Extraction Improvements:**
  - Now extracts actual UI elements (buttons, headings, links, inputs) instead of instruction text
  - Uses patterns like: `button.*?["']([^"']{1,50})["']` to find button text
  - Filters out instruction/documentation keywords: 'instruction', 'protocol', 'guideline', 'conversational', 'phone call', 'voice assistant', etc.
  - Limits element text to 50 characters max
  - Adds appropriate selectors based on element type:
    - Buttons: `button, .btn, [role="button"]`
    - Headings: `h1, h2, h3, .page-title, .screen-title`
    - Inputs: `input, label, [role="textbox"]`
    - Links: `a, [role="link"]`
  - Adds URL patterns as indicators (only specific URLs starting with `^https://` or `^http://`)
  - Filters out numbered lists and instruction text starting with "Your"

- **URL Pattern Extraction Improvements:**
  - Extracts full URLs (https://domain.com/path)
  - Extracts domain + path patterns (more specific than generic paths)
  - Filters out generic paths like `/div`, `/span`, `/p`, `/a`, `/button`, `/input`, `/form`
  - Filters out overly generic patterns like `.*/.*` or `.*`
  - Only includes paths longer than 3 characters
  - Creates specific regex patterns: `^https?://domain.com/path.*`

**Files Modified:**
- `navigator/knowledge/extract/screens.py`: 
  - Improved `_extract_state_signature()` method with UI element extraction
  - Improved `_extract_url_patterns()` method with filtering and specificity

### Phase 5: LLM-Based Action Extrapolation ✅ COMPLETE
1. ✅ Create `ActionExtrapolationService` with Gemini LLM integration
2. ✅ Implement gap identification logic (`_identify_action_gaps`)
3. ✅ Add extrapolation prompt engineering with comprehensive context
4. ✅ Store inferred actions with confidence scores (only >0.6 confidence)
5. ✅ Validate and integrate inferred actions into knowledge graph
6. ✅ Add `fill_action_gaps()` method to KnowledgePipeline

**Implementation Details:**
- Created schemas: `ActionGap`, `ExtrapolationRequest`, `InferredAction`, `ExtrapolationResult`
- `ActionExtrapolationService` uses Gemini 2.0 Flash Exp model for inference
- Prompt includes: known start/end actions, screen context, website structure, available screens
- Gap identification finds transitions without clear action paths
- LLM infers intermediate actions considering:
  - Common UI patterns (navigation, form filling, waiting for page loads)
  - Screen transitions (if screens are different)
  - Required intermediate steps (page navigation, element waiting, scrolling)
  - Browser automation best practices
- Response parsing handles JSON extraction from markdown code blocks
- Only stores inferred actions with confidence > 0.6
- Inferred actions marked with `metadata.inferred=True` and include confidence/reasoning

**Files Created:**
- `navigator/knowledge/extrapolation.py`: Complete extrapolation service with schemas and LLM integration

**Files Modified:**
- `navigator/knowledge/pipeline.py`: Added `fill_action_gaps()` method and `_identify_action_gaps()` helper

### Phase 6: Integration ✅ COMPLETE
1. ✅ Update knowledge API to use new schemas (added agent_query support)
2. ✅ Update MCP tools to return browser-use compatible actions
3. ✅ Add new MCP tools for agent communication and action extrapolation
4. ✅ Integrate extrapolation service into knowledge pipeline (already done in Phase 5)

**Implementation Details:**

#### 1. New MCP Tools Added

**Tool 1: `query_knowledge_for_agent`**
- **Purpose**: Agent-friendly knowledge query that returns browser-use compatible actions
- **Input Parameters**:
  - `knowledge_id` (required): Knowledge ID to query
  - `instruction_type` (required): One of: `navigate_to_screen`, `execute_task`, `find_screen`, `get_actions`, `get_screen_context`
  - `target` (required): Screen ID, task ID, URL, or description depending on instruction type
  - `context` (optional): Additional context (current_url, current_screen_id, dom_summary, etc.)
- **Returns**: `AgentResponse` with:
  - `success`: Boolean indicating if query succeeded
  - `actions`: List of `BrowserUseAction` objects ready for browser-use execution
  - `expected_result`: Expected outcome (screen_id, verification criteria, etc.)
  - `error`: Error message if query failed
- **Handler**: `_query_knowledge_for_agent()` - Implements all 5 instruction types:
  - `navigate_to_screen`: Finds navigation path between screens, returns browser-use actions
  - `execute_task`: Retrieves task steps, translates to browser-use actions
  - `find_screen`: Uses `ScreenRecognitionService` to identify current screen
  - `get_actions`: Returns available actions for a screen
  - `get_screen_context`: Returns full screen context and metadata

**Tool 2: `fill_action_gaps`**
- **Purpose**: LLM-based action extrapolation to infer missing actions and transitions
- **Input Parameters**:
  - `knowledge_id` (required): Knowledge ID to analyze
  - `website_id` (required): Website ID for context
- **Returns**: Dictionary with:
  - `gaps_filled`: Number of gaps successfully filled
  - `inferred_actions`: List of inferred actions with confidence scores
  - `inferred_transitions`: List of inferred transitions
  - `confidence_scores`: Confidence scores for each inferred action
  - `errors`: List of errors if any occurred
- **Handler**: `_fill_action_gaps()` - Calls `KnowledgePipeline.fill_action_gaps()` with proper error handling and browser session management

#### 2. Knowledge API Updates

**Modified**: `navigator/knowledge/api.py`
- Added `agent_query` query type support in `KnowledgeAPI.query()` method
- Redirects to proper REST endpoint or MCP tool (maintains backward compatibility)
- Updated available query types list to include `agent_query`

#### 3. Integration Points

**Action Translation Integration:**
- MCP tools use `ActionTranslator` to convert `ActionDefinition` to `BrowserUseAction`
- All knowledge actions are automatically translated to browser-use tool format
- Parameter conversion handles: `target_selector` → `index`/`selector`, `url`, `text`, `direction`, `seconds`

**Screen Recognition Integration:**
- `ScreenRecognitionService` integrated for automatic screen recognition
- Uses URL patterns (40% weight) and DOM indicators (60% weight) for matching
- Confidence threshold of 0.7 for screen identification
- Automatic recognition when `current_screen_id` not provided but `current_url` is available

**Response Format:**
- All agent queries return `AgentResponse` with standardized format
- `BrowserUseAction` objects include: `tool_name`, `parameters`, `description`, `confidence`, `screen_id`
- Ready for direct execution by browser-use agents

**Extrapolation Integration:**
- `ActionExtrapolationService` integrated into `KnowledgePipeline.fill_action_gaps()`
- Automatically identifies gaps in action sequences
- Uses Gemini LLM (`gemini-2.0-flash-exp`) for inference
- Stores high-confidence inferred actions (>0.6) into knowledge graph

#### 4. Code Structure

**MCP Tool Registration:**
```python
# In get_knowledge_tools()
types.Tool(
    name='query_knowledge_for_agent',
    description='Agent-friendly knowledge query...',
    inputSchema={...}
),
types.Tool(
    name='fill_action_gaps',
    description='Use LLM to infer missing actions...',
    inputSchema={...}
)
```

**Handler Registration:**
```python
# In register_knowledge_tool_handlers()
handlers['query_knowledge_for_agent'] = _query_knowledge_for_agent
handlers['fill_action_gaps'] = _fill_action_gaps
```

**Files Modified:**
- `navigator/server/mcp_knowledge_tools.py`: 
  - Added 2 new MCP tool definitions in `get_knowledge_tools()`
  - Implemented `_query_knowledge_for_agent()` handler (~250 lines)
  - Implemented `_fill_action_gaps()` handler (~30 lines)
  - Registered handlers in `register_knowledge_tool_handlers()`
- `navigator/knowledge/api.py`: 
  - Added `agent_query` query type support
  - Maintains backward compatibility with existing query types

**Key Features:**
- ✅ No breaking changes to existing MCP tools
- ✅ Backward compatible with existing knowledge API
- ✅ Proper error handling and logging
- ✅ Type-safe with Pydantic models
- ✅ Async/await throughout
- ✅ No Temporal code modified

---

## Example: Restructured Knowledge Format

### Before (Current):
```json
{
  "screen_id": "1_core_goalbr_br_your_primary_5545122a",
  "name": "1. Core Goal<br />...entire instruction text...",
  "state_signature": {
    "required_indicators": [{
      "value": "Your primary goal is to conduct a Baseline Emotional Profile..."
    }]
  },
  "url_patterns": [".*/div.*"]
}
```

### After (Restructured):
```json
{
  "screen_id": "dashboard_call_analytics_abc123",
  "name": "Dashboard - Call Analytics",
  "content_type": "web_ui",
  "is_actionable": true,
  "url_patterns": [
    "^https://app\\.spadeworks\\.co/dashboard$",
    "^https://app\\.spadeworks\\.co/dashboard/.*"
  ],
  "state_signature": {
    "required_indicators": [
      {
        "type": "dom_contains",
        "value": "Call Performance",
        "selector": "h1, h2, .page-title",
        "reason": "Dashboard title"
      },
      {
        "type": "url_matches",
        "pattern": ".*/dashboard.*",
        "reason": "Dashboard URL pattern"
      }
    ]
  },
  "available_browser_use_actions": [
    {
      "tool": "click",
      "params": {"index": 5},
      "description": "Click Dashboard navigation link"
    },
    {
      "tool": "scroll",
      "params": {"direction": "down"},
      "description": "Scroll to view call metrics"
    }
  ]
}
```

---

## Benefits

1. **Clear Separation**: Documentation vs. Web UI knowledge clearly separated
2. **Direct Mapping**: Knowledge directly maps to browser-use tools
3. **Agent-Friendly**: Standardized format for agent-to-agent communication
4. **Better Recognition**: Improved screen recognition with actual DOM indicators
5. **Actionable**: All knowledge is immediately usable by browser automation agents
6. **Gap Filling**: LLM-based extrapolation infers missing actions and transitions, creating complete navigation paths even when knowledge is incomplete

---

## Migration Strategy

1. **Backward Compatibility**: Keep existing schemas, add new fields as optional
2. **Gradual Migration**: Mark old screens as `content_type="unknown"`, migrate gradually
3. **Dual Support**: Support both old and new formats during transition
4. **Validation**: Add validation to ensure new extractions use correct format

---

---

## LLM-Based Extrapolation Use Cases

### Use Case 1: Video Walkthrough Gaps

**Scenario**: Video shows user clicking "Login" button, then typing username. But the video doesn't show the page navigation or form loading.

**Solution**: LLM extrapolates:
- Action: `navigate` to login page (after click)
- Action: `wait` for page load
- Transition: Screen 1 → Login Screen

### Use Case 2: Documentation Incompleteness

**Scenario**: Documentation says "Fill form and submit" but doesn't detail all form fields.

**Solution**: LLM extrapolates:
- Required form fields based on screen context
- Typical form filling sequence
- Validation steps

### Use Case 3: Multi-Step Workflows

**Scenario**: We know workflow starts with "Navigate to dashboard" and ends with "View report", but missing intermediate steps.

**Solution**: LLM extrapolates:
- Navigation path through multiple screens
- Required actions at each screen
- Data dependencies between steps

---

---

## Authenticated Portal Integration

**Status**: ✅ Fully Integrated

Authenticated portal crawling (via Browser-Use) automatically uses all new knowledge restructuring formats:

### Content Classification
- **Content Chunks**: Created with `chunk_type="webpage"` from authenticated portals
- **Screen Classification**: Screens automatically classified as `content_type="web_ui"` and `is_actionable=True`
- **Classification Logic**: Uses `_is_web_ui_screen()` method to distinguish web UI from documentation
- **Result**: All authenticated portal screens are marked as actionable web UI screens

### Action Mapping
- **Automatic Translation**: Actions extracted from authenticated portals automatically translated to browser-use actions
- **ActionTranslator**: Uses `ActionTranslator` to convert `ActionDefinition` → `BrowserUseAction`
- **Parameter Conversion**: Parameters converted to browser-use format (e.g., `target_selector` → `index`)
- **Ready for Execution**: All actions ready for direct execution by browser-use agents

### Screen Recognition
- **DOM Indicators**: Uses actual UI element patterns (buttons, headings, inputs, links)
- **URL Patterns**: Generates specific URL patterns (e.g., `^https://app\\.example\\.com/dashboard.*`)
- **Filtering**: Excludes documentation phrases and generic patterns
- **Improved Accuracy**: Better screen recognition for authenticated portals

### Agent Communication
- **Query API**: Agent-friendly query API available for authenticated portal knowledge
- **Browser-Use Actions**: Queries return browser-use compatible actions
- **Screen Recognition**: Automatic screen recognition when querying authenticated portals

### Action Extrapolation
- **Gap Filling**: LLM-based extrapolation available for authenticated portal knowledge
- **Missing Actions**: Infers missing actions and transitions in authenticated portal workflows
- **Confidence Scoring**: Stores inferred actions with confidence scores

**Implementation Location**: `navigator/knowledge/ingest/website.py`
- Content chunks created with `chunk_type="webpage"`
- Processed through `ScreenExtractor` which applies new formats
- Actions processed through `ActionTranslator` for browser-use mapping

**Documentation**: See [Authenticated Portal Guide](./KNOWLEDGE_EXTRACTION_AUTHENTICATED_PORTAL.md) for details.

---

**Last Updated**: 2026-01-14
