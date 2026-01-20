"""
Markdown parser for documentation ingestion.

Handles parsing of Markdown files with comprehensive feature extraction.
"""

import logging
from pathlib import Path
from typing import Any

import markdown
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def parse_markdown(file_path: Path) -> tuple[str, dict[str, Any]]:
	"""
	Parse Markdown file with comprehensive feature extraction.
	
	Converts to HTML for structure extraction, then extracts text
	while preserving headings, code blocks, tables, lists, and metadata.
	
	Args:
		file_path: Path to Markdown file
	
	Returns:
		Tuple of (extracted content with structure markers, metadata dict)
	"""
	with open(file_path, 'r', encoding='utf-8') as f:
		md_content = f.read()

	# Extract frontmatter if present (YAML metadata)
	metadata = {}
	if md_content.startswith('---'):
		parts = md_content.split('---', 2)
		if len(parts) >= 3:
			frontmatter = parts[1].strip()
			md_content = parts[2]
			# Simple YAML parsing (basic)
			for line in frontmatter.split('\n'):
				if ':' in line:
					key, value = line.split(':', 1)
					key = key.strip()
					value = value.strip().strip('"').strip("'")
					if key == 'tags':
						metadata['tags'] = [t.strip() for t in value.split(',')]
					else:
						metadata[key] = value

	# Convert to HTML with extensions for better parsing
	html = markdown.markdown(
		md_content,
		extensions=['fenced_code', 'tables', 'toc', 'codehilite', 'meta']
	)

	# Parse HTML to extract structure
	soup = BeautifulSoup(html, 'html.parser')

	# Extract structured content
	content_parts = []
	tables_found = []
	code_blocks_found = []
	images_found = []

	for element in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'pre', 'code', 'ul', 'ol', 'table', 'img', 'blockquote', 'hr']):
		# Headings
		if element.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
			level = int(element.name[1])
			heading_text = element.get_text().strip()
			content_parts.append(f"\n{'#' * level} {heading_text}\n")

		# Code blocks
		elif element.name == 'pre':
			code = element.get_text().strip()
			code_blocks_found.append(code[:100])  # Store snippet
			content_parts.append(f"\n```\n{code}\n```\n")

		# Inline code
		elif element.name == 'code' and element.parent.name != 'pre':
			content_parts.append(f"`{element.get_text().strip()}`")

		# Paragraphs
		elif element.name == 'p':
			text = element.get_text().strip()
			if text:
				content_parts.append(text + "\n")

		# Lists
		elif element.name in ['ul', 'ol']:
			for li in element.find_all('li', recursive=False):
				content_parts.append(f"- {li.get_text().strip()}\n")

		# Tables (comprehensive extraction)
		elif element.name == 'table':
			table_data = []
			content_parts.append("\n[Table Start]\n")
			headers = []
			for row_idx, row in enumerate(element.find_all('tr')):
				cells = [cell.get_text().strip() for cell in row.find_all(['td', 'th'])]
				if row_idx == 0:
					headers = cells
					content_parts.append(" | ".join(cells) + "\n")
					content_parts.append(" | ".join(['---'] * len(cells)) + "\n")
				else:
					content_parts.append(" | ".join(cells) + "\n")
					# Store structured table data
					if headers:
						table_data.append(dict(zip(headers, cells)))
			content_parts.append("[Table End]\n")
			if table_data:
				tables_found.append(table_data)

		# Images
		elif element.name == 'img':
			alt = element.get('alt', '')
			src = element.get('src', '')
			images_found.append({'alt': alt, 'src': src})
			content_parts.append(f"\n[Image: {alt} ({src})]\n")

		# Blockquotes
		elif element.name == 'blockquote':
			quote_text = element.get_text().strip()
			content_parts.append(f"\n> {quote_text}\n")

		# Horizontal rules
		elif element.name == 'hr':
			content_parts.append("\n---\n")

	# Store extracted features in metadata
	metadata['tables'] = len(tables_found)
	metadata['code_blocks'] = len(code_blocks_found)
	metadata['images'] = len(images_found)
	metadata['table_data'] = tables_found
	metadata['code_snippets'] = code_blocks_found[:10]  # First 10
	metadata['image_refs'] = images_found

	return "".join(content_parts), metadata
