"""
Document chunking strategies for documentation ingestion.

Handles semantic chunking with code block protection and breadcrumb context.
"""

import logging
import re
from uuid import uuid4

import tiktoken

from navigator.schemas import ContentChunk

logger = logging.getLogger(__name__)


def extract_code_blocks(content: str) -> tuple[str, dict[str, str]]:
	"""
	Extract code blocks before chunking to preserve syntax.
	
	Replaces code blocks with placeholders to prevent recursive splitting
	from breaking JSON objects or Python functions.
	
	Args:
		content: Raw content with code blocks
	
	Returns:
		Tuple of (content with placeholders, code_blocks dict)
	"""
	code_blocks: dict[str, str] = {}
	placeholder_pattern = "<<CODE_BLOCK_{}>>"

	# Pattern to match code blocks (markdown format: ```language\ncode\n```)
	code_block_pattern = r'```(\w+)?\n(.*?)```'

	def replace_code_block(match: re.Match) -> str:
		language = match.group(1) or ""
		code_content = match.group(2)

		# Generate unique ID for this code block
		code_id = str(uuid4())
		placeholder = placeholder_pattern.format(code_id)

		# Store code block with language info
		code_blocks[code_id] = f"```{language}\n{code_content}\n```" if language else f"```\n{code_content}\n```"

		return placeholder

	# Replace all code blocks with placeholders
	content_with_placeholders = re.sub(code_block_pattern, replace_code_block, content, flags=re.DOTALL)

	return content_with_placeholders, code_blocks


def reinsert_code_blocks(content: str, code_blocks: dict[str, str]) -> str:
	"""
	Re-insert code blocks after chunking.
	
	Replaces placeholders with original code block content.
	
	Args:
		content: Content with placeholders
		code_blocks: Dictionary mapping code block IDs to content
	
	Returns:
		Content with code blocks restored
	"""
	for code_id, code_content in code_blocks.items():
		placeholder = f"<<CODE_BLOCK_{code_id}>>"
		content = content.replace(placeholder, code_content)

	return content


def add_breadcrumb_context(content: str, heading_path: list[str], filename: str = "") -> str:
	"""
	Add breadcrumb context prefix to chunk content.
	
	Prepend heading hierarchy (breadcrumb) to chunk text so LLM knows
	the document location even when chunk is retrieved in isolation.
	
	Format: Files: {filename} | Section: {H1} > {H2} > {H3}
	
	Args:
		content: Chunk content
		heading_path: List of headings in hierarchy (from H1 to current)
		filename: Source filename
	
	Returns:
		Content with breadcrumb prefix
	"""
	if not heading_path:
		# No heading hierarchy - just add filename if available
		if filename:
			return f"File: {filename}\n\n{content}"
		return content

	# Build breadcrumb from heading path (strip # symbols, join with >)
	breadcrumb_parts = []
	for heading in heading_path:
		heading_text = heading.lstrip('#').strip()
		breadcrumb_parts.append(heading_text)

	breadcrumb = " > ".join(breadcrumb_parts)

	# Build context prefix
	context_parts = []
	if filename:
		context_parts.append(f"File: {filename}")
	context_parts.append(f"Section: {breadcrumb}")

	context_prefix = " | ".join(context_parts)

	return f"{context_prefix}\n\n{content}"


def split_by_major_headings(content: str) -> list[str]:
	"""
	Split content by major headings (H1, H2).
	
	Preserves complete sections under major headings.
	"""
	# Split by H1 or H2 (major sections) - capture groups preserve delimiters
	parts = re.split(r'\n(#{1,2}\s+.+?)\n', content)

	result = []
	current_section = []

	for i, part in enumerate(parts):
		# Check if this part is a heading (odd indices after split with capture groups)
		if i % 2 == 1:
			# This is a heading - start new section
			if current_section:
				result.append("\n".join(current_section))
				current_section = []
			current_section.append(part)
		else:
			# This is content
			if part.strip():
				current_section.append(part.strip())

	# Add final section
	if current_section:
		result.append("\n".join(current_section))

	# If no major headings found, return entire content as single section
	return result if result else [content]


def split_by_paragraphs(content: str) -> list[str]:
	"""
	Split content by paragraphs (double newlines).
	
	Preserves code blocks, tables, and other structured elements.
	"""
	# Split by double newlines, but preserve code blocks and tables
	paragraphs = []
	current_para = []

	lines = content.split('\n')
	in_code_block = False
	in_table = False

	for line in lines:
		# Track code blocks
		if line.strip().startswith('```'):
			in_code_block = not in_code_block
			current_para.append(line)
			continue

		# Track tables (markdown table format)
		if '|' in line and ('---' in line or '|' in line):
			in_table = True
			current_para.append(line)
			continue

		# If empty line and not in code/table, end paragraph
		if not line.strip() and not in_code_block and not in_table:
			if current_para:
				paragraphs.append('\n'.join(current_para))
				current_para = []
			in_table = False
			continue

		# If not in table but previously was, end table
		if not in_code_block and '|' not in line and in_table:
			in_table = False

		current_para.append(line)

	# Add final paragraph
	if current_para:
		paragraphs.append('\n'.join(current_para))

	return paragraphs


def split_by_sentences(text: str) -> list[str]:
	"""
	Split text by sentences (last resort for very long paragraphs).
	
	Uses simple sentence boundary detection.
	"""
	# Simple sentence splitting (preserve periods in abbreviations, etc.)
	# Split on . ! ? followed by space or newline
	sentences = re.split(r'([.!?]\s+)', text)

	result = []
	current_sent = ""

	for i, part in enumerate(sentences):
		current_sent += part

		# If part ends with sentence delimiter, add sentence
		if re.search(r'[.!?]\s+$', part):
			if current_sent.strip():
				result.append(current_sent.strip())
			current_sent = ""

	# Add final sentence if any
	if current_sent.strip():
		result.append(current_sent.strip())

	return result if result else [text]


def create_chunks(
	content: str,
	ingestion_id: str,
	filename: str = "",
	max_tokens_per_chunk: int = 2000
) -> list[ContentChunk]:
	"""
	Create semantic chunks using recursive splitting strategy with code block protection and breadcrumb context.
	
	Recursive splitting priority:
	1. Major headings (H1, H2) - preserve complete sections
	2. Paragraphs - preserve logical units
	3. Sentences - only if paragraph exceeds token limit
	
	Features:
	- Code Block Safe Zones: Extracts code blocks before chunking to preserve syntax
	- Breadcrumb Context: Tracks heading hierarchy and prepends to chunks for context
	
	This avoids slicing complex logic rules or procedures in half.
	
	Args:
		content: Raw content to chunk
		ingestion_id: ID of the ingestion
		filename: Source filename for breadcrumb context
		max_tokens_per_chunk: Maximum tokens per chunk
	
	Returns:
		List of ContentChunk objects
	"""
	tokenizer = tiktoken.get_encoding("cl100k_base")  # GPT-4 tokenizer

	# Step 0: Extract code blocks before chunking to preserve syntax
	content_with_placeholders, code_blocks = extract_code_blocks(content)

	chunks = []
	heading_path: list[str] = []  # Track heading hierarchy for breadcrumb context

	# Step 1: Split by major headings (H1, H2) - highest priority
	major_sections = split_by_major_headings(content_with_placeholders)

	chunk_index = 0

	for section in major_sections:
		section_title = None
		section_content = section

		# Extract section title if it starts with a heading
		heading_match = re.match(r'^(#{1,2}\s+.+?)\n', section)
		if heading_match:
			section_title = heading_match.group(1).strip()
			section_content = section[len(heading_match.group(0)):].strip()

			# Update heading path for breadcrumb context
			heading_level_match = re.match(r'^(#+)', section_title)
			if heading_level_match:
				heading_level = len(heading_level_match.group(1))  # Count # symbols

				# Update path: remove headings at same or deeper level, then add current
				# Filter out headings at same or deeper level
				new_path = []
				for h in heading_path:
					h_match = re.match(r'^(#+)', h)
					if h_match and len(h_match.group(1)) < heading_level:
						new_path.append(h)
				new_path.append(section_title)
				heading_path = new_path

		# Step 2: Split section by paragraphs
		paragraphs = split_by_paragraphs(section_content)

		current_chunk = []
		current_tokens = 0

		# Add section title to first chunk if available
		if section_title:
			current_chunk.append(section_title)
			current_tokens += len(tokenizer.encode(section_title))

		for para in paragraphs:
			if not para.strip():
				continue

			para_tokens = len(tokenizer.encode(para))

			# Step 3: If paragraph fits, add it
			if para_tokens <= max_tokens_per_chunk:
				# Check if adding would exceed limit
				if (current_tokens + para_tokens > max_tokens_per_chunk) and current_chunk:
					# Create chunk before adding this paragraph
					chunk_content = "\n".join(current_chunk)
					# Re-insert code blocks before creating chunk
					chunk_content = reinsert_code_blocks(chunk_content, code_blocks)
					# Add breadcrumb context prefix
					chunk_content = add_breadcrumb_context(chunk_content, heading_path, filename)
					chunks.append(ContentChunk(
						chunk_id=f"{ingestion_id}_{chunk_index}",
						content=chunk_content,
						chunk_index=chunk_index,
						token_count=current_tokens,
						section_title=section_title,
						chunk_type="documentation"
					))

					# Reset for next chunk
					chunk_index += 1
					current_chunk = []
					current_tokens = 0

					# Carry over section title if this is the first chunk after split
					if section_title:
						current_chunk.append(section_title)
						current_tokens += len(tokenizer.encode(section_title))

				# Add paragraph
				current_chunk.append(para)
				current_tokens += para_tokens
			else:
				# Step 3 (fallback): Paragraph exceeds limit - split by sentences
				# Only use this for extremely long paragraphs
				if current_chunk:
					# Save current chunk first
					chunk_content = "\n".join(current_chunk)
					# Re-insert code blocks
					chunk_content = reinsert_code_blocks(chunk_content, code_blocks)
					# Add breadcrumb context
					chunk_content = add_breadcrumb_context(chunk_content, heading_path, filename)
					chunks.append(ContentChunk(
						chunk_id=f"{ingestion_id}_{chunk_index}",
						content=chunk_content,
						chunk_index=chunk_index,
						token_count=current_tokens,
						section_title=section_title,
						chunk_type="documentation"
					))

					chunk_index += 1
					current_chunk = []
					current_tokens = 0

				# Split long paragraph by sentences
				sentences = split_by_sentences(para)

				sentence_chunk = []
				sentence_tokens = 0

				for sentence in sentences:
					sent_tokens = len(tokenizer.encode(sentence))

					# Check if sentence fits
					if sent_tokens <= max_tokens_per_chunk:
						if (sentence_tokens + sent_tokens > max_tokens_per_chunk) and sentence_chunk:
							# Create chunk for sentences
							sent_chunk_content = " ".join(sentence_chunk)
							# Re-insert code blocks
							sent_chunk_content = reinsert_code_blocks(sent_chunk_content, code_blocks)
							# Add breadcrumb context
							sent_chunk_content = add_breadcrumb_context(sent_chunk_content, heading_path, filename)
							chunks.append(ContentChunk(
								chunk_id=f"{ingestion_id}_{chunk_index}",
								content=sent_chunk_content,
								chunk_index=chunk_index,
								token_count=sentence_tokens,
								section_title=section_title,
								chunk_type="documentation"
							))

							chunk_index += 1
							sentence_chunk = []
							sentence_tokens = 0

						sentence_chunk.append(sentence)
						sentence_tokens += sent_tokens
					else:
						# Sentence itself exceeds limit (very rare) - use as-is
						sentence_content = reinsert_code_blocks(sentence, code_blocks)
						sentence_content = add_breadcrumb_context(sentence_content, heading_path, filename)
						chunks.append(ContentChunk(
							chunk_id=f"{ingestion_id}_{chunk_index}",
							content=sentence_content,
							chunk_index=chunk_index,
							token_count=sent_tokens,
							section_title=section_title,
							chunk_type="documentation"
						))
						chunk_index += 1

				# Add remaining sentences
				if sentence_chunk:
					sent_chunk_content = " ".join(sentence_chunk)
					current_chunk.append(sent_chunk_content)
					current_tokens = sentence_tokens

		# Add final chunk for section
		if current_chunk:
			chunk_content = "\n".join(current_chunk)
			# Re-insert code blocks
			chunk_content = reinsert_code_blocks(chunk_content, code_blocks)
			# Add breadcrumb context
			chunk_content = add_breadcrumb_context(chunk_content, heading_path, filename)
			chunks.append(ContentChunk(
				chunk_id=f"{ingestion_id}_{chunk_index}",
				content=chunk_content,
				chunk_index=chunk_index,
				token_count=current_tokens,
				section_title=section_title,
				chunk_type="documentation"
			))
			chunk_index += 1

	return chunks
