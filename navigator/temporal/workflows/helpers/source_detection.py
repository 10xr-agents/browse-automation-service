"""
Source type detection helper.

Auto-detects source type from URL or file path.
"""


def detect_source_type(source_url: str | None, provided_type: str | None) -> str:
	"""
	Auto-detect source type from URL or file path.
	
	Intelligently detects whether an asset is a video, documentation file, or website
	based on file extension or URL pattern.
	
	Args:
		source_url: URL or file path
		provided_type: Explicitly provided source type (if any)
	
	Returns:
		Detected source type string
	"""
	if not source_url:
		return provided_type or 'website_documentation'

	# If type explicitly provided and not 'file', use it
	if provided_type and provided_type != 'file':
		return provided_type

	# Auto-detect from file extension or URL
	source_lower = source_url.lower()

	# Check for video extensions
	if any(source_lower.endswith(ext) for ext in ['.mp4', '.webm', '.mov', '.avi', '.mkv']):
		return 'video_walkthrough'

	# Check for documentation file extensions
	if any(source_lower.endswith(ext) for ext in ['.pdf', '.md', '.txt', '.html', '.rst', '.docx', '.doc']):
		return 'technical_documentation'

	# Check for file:// URLs (S3 downloads)
	if source_url.startswith('file://'):
		# Default to documentation for file:// URLs (will be refined by router)
		return 'technical_documentation'

	# Check for HTTP(S) URLs
	if source_url.startswith('http://') or source_url.startswith('https://'):
		return 'website_documentation'

	# Default fallback
	return provided_type or 'website_documentation'
