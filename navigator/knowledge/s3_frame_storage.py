"""
S3 Frame Storage for Distributed Video Processing

Stores video frames in S3 to enable cross-server activity execution.
Supports both local filesystem (single-server) and S3 (multi-server) modes.

When multiple browser automation service instances are running as Temporal workers,
activities can execute on different servers. Local filesystem storage won't work
in this scenario, so frames must be stored in shared S3 storage.

**Configuration:**
- **Single-server mode** (default): Uses local filesystem (`{tempdir}/video_frames/`)
- **Multi-server mode**: Uses S3 (reuses `S3_BUCKET` from knowledge extraction)
  - Frames stored in: `{S3_BUCKET}/frames/{ingestion_id}/frame_{timestamp}.jpg`
  - **Development** (`ENVIRONMENT=development`): DigitalOcean Spaces (auto-configured endpoint, requires access keys)
  - **Production** (`ENVIRONMENT=production` or unset): AWS S3 (uses IAM roles, no credentials needed)

**Environment Variables:**
- `S3_BUCKET`: S3 bucket name (required for S3 mode, same bucket as knowledge extraction assets)
- `ENVIRONMENT`: Environment name - `development` = DigitalOcean Spaces, other = AWS S3 (defaults to `development`)
- `S3_ENDPOINT`: DigitalOcean Spaces endpoint (e.g., `https://nyc3.digitaloceanspaces.com`) - auto-configured in development if not set
- `DO_SPACES_REGION`: DigitalOcean Spaces region for auto-configuration (defaults to `nyc3` if not set)
- `AWS_REGION`: AWS region (optional, defaults to us-east-1 for AWS S3)
- `DO_SPACES_ACCESS_KEY` / `DO_SPACES_SECRET_KEY`: DigitalOcean Spaces credentials (required in development)
- `S3_ACCESS_KEY_ID` / `S3_SECRET_ACCESS_KEY`: Alternative credential names (falls back to AWS keys)
- `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`: AWS credentials (optional, IAM roles preferred in production)

**Usage:**
    # Single-server mode (local filesystem) - default (no S3_BUCKET env var)
    storage = S3FrameStorage()
    frame_ref = await storage.upload_frame(frame_bytes, ingestion_id, timestamp)
    
    # Multi-server mode (S3) - auto-detects from S3_BUCKET env var
    # Uses same bucket as knowledge extraction: {S3_BUCKET}/frames/{ingestion_id}/
    storage = S3FrameStorage()
    frame_ref = await storage.upload_frame(frame_bytes, ingestion_id, timestamp)
    frame_bytes = await storage.download_frame(frame_ref)
"""

import logging
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from navigator.schemas.s3 import S3Reference

logger = logging.getLogger(__name__)


class FrameReference:
	"""
	Reference to a frame, either local or S3-based.
	
	Unified interface for frame references to abstract away
	whether the frame is stored locally or in S3.
	"""

	def __init__(
		self,
		local_path: Optional[Path] = None,
		s3_ref: Optional[S3Reference] = None,
		timestamp: float = 0.0,
	):
		"""
		Initialize frame reference.
		
		Args:
			local_path: Local filesystem path (for single-server mode)
			s3_ref: S3 reference with presigned URL (for multi-server mode)
			timestamp: Frame timestamp in video
		"""
		self.local_path = local_path
		self.s3_ref = s3_ref
		self.timestamp = timestamp

		if not local_path and not s3_ref:
			raise ValueError("FrameReference must have either local_path or s3_ref")

	@property
	def is_local(self) -> bool:
		"""Check if frame is stored locally."""
		return self.local_path is not None

	@property
	def is_s3(self) -> bool:
		"""Check if frame is stored in S3."""
		return self.s3_ref is not None

	def to_path_string(self) -> str:
		"""Convert to path string for backward compatibility."""
		if self.local_path:
			return str(self.local_path)
		elif self.s3_ref:
			# For S3, return a URL-like string (activities will download)
			# Format: s3://bucket/key
			return f"s3://{self.s3_ref.bucket}/{self.s3_ref.key}"
		else:
			raise ValueError("FrameReference has no valid path or S3 reference")

	@classmethod
	def from_path_string(cls, path_string: str, timestamp: float) -> 'FrameReference':
		"""
		Create FrameReference from path string.
		
		Args:
			path_string: Path string (local path or s3://bucket/key)
			timestamp: Frame timestamp
		
		Returns:
			FrameReference object
		"""
		if path_string.startswith('s3://'):
			# S3 URL - parse bucket and key
			parts = path_string.replace('s3://', '').split('/', 1)
			if len(parts) != 2:
				raise ValueError(f"Invalid S3 URL format: {path_string}")

			bucket, key = parts

			# Create minimal S3Reference (presigned URL will be generated on-demand)
			s3_ref = S3Reference(
				bucket=bucket,
				key=key,
				region=None,  # Will be inferred from env
				endpoint=None,  # Will be inferred from env
				presigned_url='',  # Will be generated on-demand
				expires_at='',  # Not needed for on-demand generation
			)
			return cls(s3_ref=s3_ref, timestamp=timestamp)
		else:
			# Local filesystem path
			return cls(local_path=Path(path_string), timestamp=timestamp)


class S3FrameStorage:
	"""
	Frame storage that supports both local filesystem and S3.
	
	Automatically handles uploading frames to S3 in multi-server mode,
	or storing them locally in single-server mode.
	"""

	def __init__(
		self,
		use_s3: Optional[bool] = None,  # None = auto-detect from env
		bucket: Optional[str] = None,  # S3 bucket name (required if use_s3=True)
		region: Optional[str] = None,  # AWS region (optional, defaults to env)
		endpoint: Optional[str] = None,  # Custom S3 endpoint for DigitalOcean Spaces
		local_base_dir: Optional[Path] = None,  # Local storage base directory
		frame_prefix: str = 'frames',  # S3 key prefix for frames (subfolder within bucket)
	):
		"""
		Initialize frame storage.
		
		Args:
			use_s3: Whether to use S3 (True) or local filesystem (False)
				If None, auto-detects from S3_BUCKET env var
			bucket: S3 bucket name (required if use_s3=True)
				If None, uses S3_BUCKET env var (same bucket as knowledge extraction assets)
			region: AWS region (optional, defaults to AWS_REGION env var)
			endpoint: Custom S3 endpoint for DigitalOcean Spaces (optional, defaults to S3_ENDPOINT env var)
			local_base_dir: Base directory for local storage (defaults to tempdir)
			frame_prefix: S3 key prefix for frames (default: 'frames' - creates frames/ subfolder)
		"""
		# Auto-detect S3 mode if not specified
		# Use S3 if S3_BUCKET is set (reuse same bucket as knowledge extraction)
		if use_s3 is None:
			use_s3 = bool(os.getenv('S3_BUCKET') or bucket)

		# Use S3_BUCKET (same bucket as knowledge extraction assets)
		self.bucket = bucket or os.getenv('S3_BUCKET', '')

		# Auto-detect environment: development = DigitalOcean Spaces, production = AWS S3
		environment = os.getenv('ENVIRONMENT', 'development').lower()
		is_development = environment == 'development'

		# Auto-configure endpoint for DigitalOcean Spaces in development
		if is_development and not endpoint and not os.getenv('S3_ENDPOINT'):
			# Default DigitalOcean Spaces endpoint (can be overridden with S3_ENDPOINT env var)
			# Common DO Spaces endpoints: https://{region}.digitaloceanspaces.com
			# Default to nyc3 if no region specified
			default_region = os.getenv('DO_SPACES_REGION', 'nyc3')
			self.endpoint = f"https://{default_region}.digitaloceanspaces.com"
			logger.info(f"🔧 Auto-configured DigitalOcean Spaces endpoint for development: {self.endpoint}")
		else:
			# Use explicit endpoint or S3_ENDPOINT env var
			self.endpoint = endpoint or os.getenv('S3_ENDPOINT')

		# AWS region (optional, defaults to us-east-1 if not specified)
		# In development with DigitalOcean Spaces, region is not needed
		if not self.endpoint:  # AWS S3 mode
			self.region = region or os.getenv('AWS_REGION') or os.getenv('AWS_DEFAULT_REGION') or 'us-east-1'
		else:  # DigitalOcean Spaces mode
			self.region = region or os.getenv('AWS_REGION') or os.getenv('AWS_DEFAULT_REGION')

		self.frame_prefix = frame_prefix  # Subfolder prefix for frames

		# Verify boto3 is available if S3 mode is requested
		# boto3 is required for both DigitalOcean Spaces and AWS S3
		if use_s3 and self.bucket:
			try:
				import boto3
			except ImportError:
				error_msg = (
					"❌ S3_BUCKET is set but boto3 is not installed. "
					"boto3 is required for S3 storage (both DigitalOcean Spaces and AWS S3). "
					"Install with: uv pip install boto3"
				)
				logger.error(error_msg)
				raise ImportError(error_msg)

		self.use_s3 = use_s3

		# Local storage configuration
		if local_base_dir:
			self.local_base_dir = Path(local_base_dir)
		else:
			self.local_base_dir = Path(tempfile.gettempdir()) / 'video_frames'

		# S3 client (lazy initialization)
		self._s3_client = None

		if self.use_s3:
			if not self.bucket:
				raise ValueError(
					"S3 frame storage requires S3_BUCKET env var or bucket parameter. "
					"Frames will be stored in {bucket}/{frame_prefix}/ subfolder."
				)

			# Log S3 configuration (detect provider from endpoint)
			environment = os.getenv('ENVIRONMENT', 'development').lower()
			if self.endpoint:
				provider = "DigitalOcean Spaces"
				env_note = f" (ENVIRONMENT={environment})"
			else:
				provider = "AWS S3"
				env_note = f" (ENVIRONMENT={environment})"

			# Detect credential type (check for DO Spaces, S3, and AWS keys)
			# Order: DO_SPACES_* (preferred) > S3_* (env.example) > AWS_* (fallback)
			has_access_keys = bool(
				os.getenv('DO_SPACES_ACCESS_KEY') or
				os.getenv('S3_ACCESS_KEY_ID') or
				os.getenv('AWS_ACCESS_KEY_ID')
			)
			credentials_note = "access keys" if has_access_keys else "IAM role"

			logger.info(
				f"🗄️  Frame storage: S3 mode ({provider}{env_note}, bucket={self.bucket}, "
				f"prefix={self.frame_prefix}/, credentials={credentials_note})"
			)
		else:
			logger.info(f"📁 Frame storage: Local filesystem mode (dir={self.local_base_dir})")

	def _get_s3_client(self):
		"""
		Get boto3 S3 client (lazy initialization).
		
		Supports:
		- AWS S3: Uses IAM roles (no credentials needed in production) or env vars (AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY)
		- DigitalOcean Spaces: Uses S3_ENDPOINT and access keys from env (DO_SPACES_ACCESS_KEY/DO_SPACES_SECRET_KEY) or AWS env vars
		"""
		if self._s3_client is None:
			try:
				import boto3
			except ImportError:
				raise ImportError(
					"boto3 is required for S3 frame storage. Install with: uv pip install boto3 "
					"or uv pip install browser-use[aws]"
				)

			# Create S3 client configuration
			s3_config = {}

			# DigitalOcean Spaces endpoint (for dev environment)
			if self.endpoint:
				s3_config['endpoint_url'] = self.endpoint

			# AWS region (optional, defaults to us-east-1 if not specified)
			if self.region:
				s3_config['region_name'] = self.region

			# Credentials handling:
			# - AWS S3: Use IAM roles (default in production) or AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY env vars
			# - DigitalOcean Spaces: Use DO_SPACES_*/S3_* env vars (preferred) or fallback to AWS_* env vars
			if self.endpoint:
				# DigitalOcean Spaces - prefer DO-specific keys, then S3_* (from .env.example), then AWS keys
				do_access_key = (
					os.getenv('DO_SPACES_ACCESS_KEY') or
					os.getenv('S3_ACCESS_KEY_ID') or
					os.getenv('AWS_ACCESS_KEY_ID')
				)
				do_secret_key = (
					os.getenv('DO_SPACES_SECRET_KEY') or
					os.getenv('S3_SECRET_ACCESS_KEY') or
					os.getenv('AWS_SECRET_ACCESS_KEY')
				)

				if do_access_key and do_secret_key:
					s3_config['aws_access_key_id'] = do_access_key
					s3_config['aws_secret_access_key'] = do_secret_key
				# If no keys provided, boto3 will use default credential chain (for development with IAM)
			# AWS S3: No credentials in config - boto3 will use IAM roles or AWS env vars automatically

			# Create S3 client (boto3 handles IAM roles automatically if no credentials provided)
			self._s3_client = boto3.client('s3', **s3_config)

		return self._s3_client

	async def upload_frame(
		self,
		frame_bytes: bytes,
		ingestion_id: str,
		timestamp: float,
	) -> FrameReference:
		"""
		Upload frame to storage (local or S3).
		
		Args:
			frame_bytes: Frame image bytes (JPEG)
			ingestion_id: Ingestion identifier
			timestamp: Frame timestamp in video
		
		Returns:
			FrameReference pointing to stored frame
		"""
		# Store frames in subfolder: {frame_prefix}/{ingestion_id}/frame_{timestamp}.jpg
		# Example: frames/{ingestion_id}/frame_10.00.jpg (in same bucket as knowledge assets)
		frame_key = f"{self.frame_prefix}/{ingestion_id}/frame_{timestamp:.2f}.jpg"

		if self.use_s3:
			return await self._upload_to_s3(frame_bytes, frame_key, timestamp)
		else:
			return await self._store_local(frame_bytes, ingestion_id, timestamp)

	async def _store_local(
		self,
		frame_bytes: bytes,
		ingestion_id: str,
		timestamp: float,
	) -> FrameReference:
		"""Store frame in local filesystem."""
		frame_dir = self.local_base_dir / ingestion_id
		frame_dir.mkdir(parents=True, exist_ok=True)

		frame_path = frame_dir / f"frame_{timestamp:.2f}.jpg"

		# Write frame bytes
		with open(frame_path, 'wb') as f:
			f.write(frame_bytes)

		logger.debug(f"📁 Stored frame locally: {frame_path}")

		return FrameReference(local_path=frame_path, timestamp=timestamp)

	async def _upload_to_s3(
		self,
		frame_bytes: bytes,
		frame_key: str,
		timestamp: float,
	) -> FrameReference:
		"""Upload frame to S3 and generate presigned URL."""
		import asyncio
		from io import BytesIO

		s3_client = self._get_s3_client()

		# Upload to S3 (using thread pool for blocking boto3 call)
		loop = asyncio.get_event_loop()
		await loop.run_in_executor(
			None,
			lambda: s3_client.put_object(
				Bucket=self.bucket,
				Key=frame_key,
				Body=BytesIO(frame_bytes),
				ContentType='image/jpeg',
			)
		)

		# Generate presigned URL (valid for 24 hours - frames need to be accessible across activities)
		expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
		presigned_url = s3_client.generate_presigned_url(
			'get_object',
			Params={'Bucket': self.bucket, 'Key': frame_key},
			ExpiresIn=24 * 3600,  # 24 hours
		)

		s3_ref = S3Reference(
			bucket=self.bucket,
			key=frame_key,
			region=self.region,
			endpoint=self.endpoint,
			presigned_url=presigned_url,
			expires_at=expires_at.isoformat(),
		)

		logger.debug(f"☁️  Uploaded frame to S3: s3://{self.bucket}/{frame_key}")

		return FrameReference(s3_ref=s3_ref, timestamp=timestamp)

	async def upload_frames_batch(
		self,
		frames: list[tuple[bytes, float]],  # List of (frame_bytes, timestamp) tuples
		ingestion_id: str,
	) -> list[FrameReference]:
		"""
		Upload multiple frames to storage concurrently (local or S3).
		
		Args:
			frames: List of (frame_bytes, timestamp) tuples
			ingestion_id: Ingestion identifier
		
		Returns:
			List of FrameReference objects in the same order as input frames
			(None entries for failed uploads to maintain order)
		"""
		import asyncio

		# Upload all frames concurrently
		upload_tasks = [
			self.upload_frame(frame_bytes, ingestion_id, timestamp)
			for frame_bytes, timestamp in frames
		]

		# Execute all uploads concurrently
		frame_refs = await asyncio.gather(*upload_tasks, return_exceptions=True)

		# Handle any exceptions - maintain order by keeping None for failures
		result_refs = []
		success_count = 0
		for i, ref in enumerate(frame_refs):
			if isinstance(ref, Exception):
				logger.error(f"❌ Failed to upload frame {frames[i][1]:.2f}s: {ref}")
				result_refs.append(None)  # Maintain order with None for failures
			else:
				result_refs.append(ref)
				success_count += 1

		logger.info(f"☁️  Batch uploaded {success_count}/{len(frames)} frames to storage")

		return result_refs

	async def download_frame(self, frame_ref: FrameReference) -> bytes:
		"""
		Download frame from storage (local or S3).
		
		Args:
			frame_ref: Frame reference (local or S3)
		
		Returns:
			Frame image bytes (JPEG)
		"""
		if frame_ref.is_local:
			# Read from local filesystem
			with open(frame_ref.local_path, 'rb') as f:
				return f.read()
		elif frame_ref.is_s3:
			# Download from S3 (generate presigned URL on-demand if needed)
			return await self._download_from_s3(frame_ref.s3_ref)
		else:
			raise ValueError("FrameReference has no valid path or S3 reference")

	async def download_frame_from_path(self, path_string: str) -> bytes:
		"""
		Download frame from path string (local or S3 URL).
		
		Convenience method that handles path string parsing.
		
		Args:
			path_string: Path string (local path or s3://bucket/key)
		
		Returns:
			Frame image bytes (JPEG)
		"""
		if path_string.startswith('s3://'):
			# Parse S3 URL
			parts = path_string.replace('s3://', '').split('/', 1)
			if len(parts) != 2:
				raise ValueError(f"Invalid S3 URL format: {path_string}")

			bucket, key = parts

			# Download from S3 using S3 client directly (more reliable than presigned URLs)
			import asyncio

			s3_client = self._get_s3_client()

			# Download object using thread pool for blocking boto3 call
			loop = asyncio.get_event_loop()
			response = await loop.run_in_executor(
				None,
				lambda: s3_client.get_object(Bucket=bucket, Key=key)
			)

			# Read body
			body_bytes = response['Body'].read()
			return body_bytes
		else:
			# Local filesystem path
			with open(path_string, 'rb') as f:
				return f.read()

	async def _download_from_s3(self, s3_ref: S3Reference) -> bytes:
		"""Download frame from S3 using S3 client or presigned URL."""
		import asyncio

		# If presigned URL is provided and valid, use it
		if s3_ref.presigned_url and s3_ref.presigned_url != '':
			import aiohttp

			async with aiohttp.ClientSession() as session:
				async with session.get(s3_ref.presigned_url) as response:
					if response.status != 200:
						raise Exception(f"S3 download failed: HTTP {response.status}")

					return await response.read()
		else:
			# Generate presigned URL on-demand or use S3 client directly
			# Use S3 client directly (more reliable)
			s3_client = self._get_s3_client()

			# Download object using thread pool for blocking boto3 call
			loop = asyncio.get_event_loop()
			response = await loop.run_in_executor(
				None,
				lambda: s3_client.get_object(Bucket=s3_ref.bucket, Key=s3_ref.key)
			)

			# Read body
			body_bytes = response['Body'].read()
			return body_bytes


# Singleton instance
_storage: Optional[S3FrameStorage] = None


def get_frame_storage() -> S3FrameStorage:
	"""
	Get singleton frame storage instance.
	
	Re-initializes if S3_BUCKET is set but storage is not using S3
	(to handle cases where singleton was initialized before S3_BUCKET was set).
	"""
	global _storage

	# Check if S3_BUCKET is set but storage is not using S3
	# This can happen if singleton was initialized before S3_BUCKET was set
	s3_bucket_env = os.getenv('S3_BUCKET')
	if _storage is not None and s3_bucket_env and not _storage.use_s3:
		logger.warning(
			f"⚠️ Frame storage singleton has use_s3=False but S3_BUCKET={s3_bucket_env} is set. "
			f"Re-initializing frame storage with S3 configuration..."
		)
		_storage = None  # Force re-initialization

	if _storage is None:
		_storage = S3FrameStorage()

	return _storage
