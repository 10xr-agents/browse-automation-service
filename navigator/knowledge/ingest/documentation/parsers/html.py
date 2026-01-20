"""
HTML parser for documentation ingestion.

Handles parsing of HTML files with comprehensive feature extraction.
"""

import logging
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def parse_html(file_path: Path) -> tuple[str, dict[str, Any]]:
	"""
	Parse HTML file with comprehensive feature extraction.
	
	Extracts semantic structure (headings, paragraphs, code blocks, tables, images)
	while removing scripts, styles, and navigation elements.
	
	Args:
		file_path: Path to HTML file
	
	Returns:
		Tuple of (extracted content with structure, metadata dict)
	"""
	with open(file_path, 'r', encoding='utf-8') as f:
		html_content = f.read()

	soup = BeautifulSoup(html_content, 'html.parser')

	# Extract metadata
	metadata = {}
	meta_tags = soup.find_all('meta')
	for meta in meta_tags:
		name = meta.get('name') or meta.get('property', '')
		content = meta.get('content', '')
		if name:
			metadata[name.lower()] = content

	# Extract author, description, keywords
	author_tag = soup.find('meta', {'name': 'author'})
	if author_tag:
		metadata['author'] = author_tag.get('content', '')

	# Remove scripts, styles, navigation
	for element in soup(['script', 'style', 'nav', 'header', 'footer', 'aside']):
		element.decompose()

	# Extract title
	title = soup.find('title')
	content_parts = []
	tables_found = []
	images_found = []
	links_found = []

	if title:
		content_parts.append(f"# {title.get_text().strip()}\n\n")

	# Extract main content
	main_content = soup.find('main') or soup.find('article') or soup.find('body')

	if main_content:
		for element in main_content.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'pre', 'code', 'ul', 'ol', 'table', 'img', 'a', 'blockquote', 'hr']):
			# Headings
			if element.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
				level = int(element.name[1])
				content_parts.append(f"\n{'#' * level} {element.get_text().strip()}\n")

			# Code blocks
			elif element.name == 'pre':
				code = element.get_text().strip()
				content_parts.append(f"\n```\n{code}\n```\n")

			# Paragraphs
			elif element.name == 'p':
				text = element.get_text().strip()
				if text:
					content_parts.append(text + "\n")

			# Lists
			elif element.name in ['ul', 'ol']:
				for li in element.find_all('li', recursive=False):
					content_parts.append(f"- {li.get_text().strip()}\n")

			# Tables
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

			# Links
			elif element.name == 'a':
				href = element.get('href', '')
				text = element.get_text().strip()
				if href and text:
					links_found.append({'text': text, 'href': href})
					content_parts.append(f"[{text}]({href})")

			# Blockquotes
			elif element.name == 'blockquote':
				quote_text = element.get_text().strip()
				content_parts.append(f"\n> {quote_text}\n")

			# Horizontal rules
			elif element.name == 'hr':
				content_parts.append("\n---\n")

	# Store extracted features
	metadata['tables'] = len(tables_found)
	metadata['images'] = len(images_found)
	metadata['links'] = len(links_found)
	metadata['table_data'] = tables_found
	metadata['image_refs'] = images_found
	metadata['link_refs'] = links_found[:50]  # First 50 links

	return "".join(content_parts), metadata
