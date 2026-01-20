"""
Video ingestion module.

Provides VideoIngester for processing video walkthrough files with:
- Metadata extraction
- Audio transcription (Deepgram)
- Subtitle extraction
- Frame analysis (Vision LLMs)
- Action sequence extraction
- Thumbnail generation
"""

from navigator.knowledge.ingest.video.ingester import VideoIngester

__all__ = ['VideoIngester']
