"""
S3 Reference Schemas for File-Based Ingestion

Defines models for S3-based file uploads and downloads.
Supports both AWS S3 and DigitalOcean Spaces.
"""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class S3Reference(BaseModel):
	"""
	S3 object reference with presigned URL.
	
	Supports:
	- AWS S3 (IAM-based in production)
	- DigitalOcean Spaces (Access Key based in development)
	"""

	bucket: str = Field(..., description="S3 bucket name")
	key: str = Field(..., description="Object key/path in bucket")
	region: str | None = Field(None, description="AWS region (e.g., 'us-east-1'). Optional for DigitalOcean Spaces.")
	endpoint: str | None = Field(None, description="Custom S3 endpoint for DigitalOcean Spaces (e.g., 'https://nyc3.digitaloceanspaces.com')")
	presigned_url: str = Field(..., description="Presigned URL for downloading (valid for 1 hour)")
	expires_at: str = Field(..., description="ISO 8601 timestamp when presigned URL expires")

	@field_validator('expires_at')
	@classmethod
	def validate_expires_at(cls, v: str) -> str:
		"""Validate expires_at is a valid ISO 8601 timestamp."""
		try:
			datetime.fromisoformat(v.replace('Z', '+00:00'))
			return v
		except ValueError:
			raise ValueError(f"expires_at must be ISO 8601 timestamp, got: {v}")


class FileMetadata(BaseModel):
	"""
	Metadata for uploaded files.
	
	Provided by the UI server after file upload to S3.
	"""

	filename: str = Field(..., description="Original filename")
	size: int = Field(..., description="File size in bytes", gt=0)
	content_type: str = Field(..., description="MIME type (e.g., 'application/pdf', 'video/mp4')")
	uploaded_at: str = Field(..., description="ISO 8601 timestamp when file was uploaded")

	@field_validator('uploaded_at')
	@classmethod
	def validate_uploaded_at(cls, v: str) -> str:
		"""Validate uploaded_at is a valid ISO 8601 timestamp."""
		try:
			datetime.fromisoformat(v.replace('Z', '+00:00'))
			return v
		except ValueError:
			raise ValueError(f"uploaded_at must be ISO 8601 timestamp, got: {v}")

	@field_validator('content_type')
	@classmethod
	def validate_content_type(cls, v: str) -> str:
		"""Validate content_type follows MIME type format."""
		if '/' not in v:
			raise ValueError(f"content_type must be a valid MIME type, got: {v}")
		return v


class S3DownloadError(Exception):
	"""
	Raised when S3 download fails.
	
	Maps to HTTP status codes:
	- 502 Bad Gateway: S3 download failure
	- 410 Gone: Presigned URL expired
	- 404 Not Found: Object not found in S3
	"""

	def __init__(self, message: str, status_code: int = 502, details: dict | None = None):
		"""
		Initialize S3 download error.
		
		Args:
			message: Error message
			status_code: HTTP status code (502, 410, or 404)
			details: Additional error details
		"""
		super().__init__(message)
		self.status_code = status_code
		self.details = details or {}
