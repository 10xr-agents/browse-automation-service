"""
S3 File Downloader

Downloads files from S3 using presigned URLs.
Supports both AWS S3 and DigitalOcean Spaces.
"""

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Optional

import aiohttp

from navigator.schemas.s3 import FileMetadata, S3DownloadError, S3Reference

logger = logging.getLogger(__name__)


class S3Downloader:
	"""
	Downloads files from S3 using presigned URLs.
	
	Features:
	- Presigned URL validation
	- Expiry checking
	- Streaming downloads for large files
	- Automatic cleanup of temporary files
	"""

	def __init__(
		self,
		timeout_seconds: int = 300,  # 5 minutes default timeout
		chunk_size: int = 1024 * 1024,  # 1MB chunks
	):
		"""
		Initialize S3 downloader.
		
		Args:
			timeout_seconds: Download timeout in seconds
			chunk_size: Chunk size for streaming downloads (bytes)
		"""
		self.timeout_seconds = timeout_seconds
		self.chunk_size = chunk_size

	async def download_file(
		self,
		s3_ref: S3Reference,
		file_metadata: FileMetadata,
		destination_dir: Optional[Path] = None,
	) -> Path:
		"""
		Download file from S3 using presigned URL.
		
		Args:
			s3_ref: S3 reference with presigned URL
			file_metadata: File metadata
			destination_dir: Directory to save file (uses temp dir if None)
		
		Returns:
			Path to downloaded file
		
		Raises:
			S3DownloadError: If download fails or URL expired
		"""
		# Check if presigned URL is expired
		self._validate_presigned_url(s3_ref)

		# Create destination path
		if destination_dir:
			destination_dir.mkdir(parents=True, exist_ok=True)
			destination_path = destination_dir / file_metadata.filename
		else:
			# Use temporary file
			temp_file = NamedTemporaryFile(
				delete=False,
				suffix=Path(file_metadata.filename).suffix,
				prefix="s3_download_"
			)
			destination_path = Path(temp_file.name)
			temp_file.close()

		logger.info(
			"🔽 Starting S3 download",
			extra={
				"bucket": s3_ref.bucket,
				"key": s3_ref.key,
				"file_name": file_metadata.filename,  # Use file_name instead of filename (reserved in LogRecord)
				"size_bytes": file_metadata.size,
				"destination": str(destination_path),
			}
		)

		try:
			await self._download_with_retry(
				presigned_url=s3_ref.presigned_url,
				destination=destination_path,
				expected_size=file_metadata.size,
			)

			logger.info(
				"✅ S3 download completed",
				extra={
					"bucket": s3_ref.bucket,
					"key": s3_ref.key,
					"file_name": file_metadata.filename,  # Use file_name instead of filename (reserved in LogRecord)
					"destination": str(destination_path),
				}
			)

			return destination_path

		except S3DownloadError:
			# Clean up partial download
			if destination_path.exists():
				destination_path.unlink()
			raise
		except Exception as e:
			# Clean up partial download
			if destination_path.exists():
				destination_path.unlink()

			logger.error(
				f"❌ S3 download failed: {e}",
				extra={
					"bucket": s3_ref.bucket,
					"key": s3_ref.key,
					"error": str(e),
				}
			)
			raise S3DownloadError(
				message=f"Failed to download file from S3: {e}",
				status_code=502,
				details={
					"bucket": s3_ref.bucket,
					"key": s3_ref.key,
					"error": str(e),
				}
			)

	def _validate_presigned_url(self, s3_ref: S3Reference) -> None:
		"""
		Validate presigned URL is not expired.
		
		Args:
			s3_ref: S3 reference to validate
		
		Raises:
			S3DownloadError: If URL is expired
		"""
		expires_at = datetime.fromisoformat(s3_ref.expires_at.replace('Z', '+00:00'))
		now = datetime.now(timezone.utc)

		if now >= expires_at:
			raise S3DownloadError(
				message=f"Presigned URL expired at {s3_ref.expires_at}",
				status_code=410,
				details={
					"bucket": s3_ref.bucket,
					"key": s3_ref.key,
					"expired_at": s3_ref.expires_at,
					"current_time": now.isoformat(),
				}
			)

		time_remaining = (expires_at - now).total_seconds()
		logger.debug(
			f"Presigned URL valid for {time_remaining:.0f} seconds",
			extra={
				"bucket": s3_ref.bucket,
				"key": s3_ref.key,
				"expires_at": s3_ref.expires_at,
			}
		)

	async def _download_with_retry(
		self,
		presigned_url: str,
		destination: Path,
		expected_size: int,
		max_retries: int = 3,
	) -> None:
		"""
		Download file with retry logic.
		
		Args:
			presigned_url: Presigned URL for download
			destination: Path to save downloaded file
			expected_size: Expected file size in bytes
			max_retries: Maximum number of retry attempts
		
		Raises:
			S3DownloadError: If download fails after retries
		"""
		for attempt in range(1, max_retries + 1):
			try:
				await self._stream_download(presigned_url, destination, expected_size)
				return  # Success!

			except aiohttp.ClientError as e:
				if attempt == max_retries:
					raise S3DownloadError(
						message=f"Download failed after {max_retries} attempts: {e}",
						status_code=502,
						details={"error": str(e), "attempts": attempt}
					)

				# Exponential backoff
				wait_time = 2 ** attempt
				logger.warning(
					f"⚠️  Download attempt {attempt} failed, retrying in {wait_time}s: {e}",
					extra={"attempt": attempt, "wait_time": wait_time}
				)
				await asyncio.sleep(wait_time)

	async def _stream_download(
		self,
		presigned_url: str,
		destination: Path,
		expected_size: int,
	) -> None:
		"""
		Stream download file from presigned URL.
		
		Args:
			presigned_url: Presigned URL for download
			destination: Path to save downloaded file
			expected_size: Expected file size in bytes
		
		Raises:
			aiohttp.ClientError: If HTTP request fails
			S3DownloadError: If file size mismatch or object not found
		"""
		timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)

		async with aiohttp.ClientSession(timeout=timeout) as session:
			async with session.get(presigned_url) as response:
				# Check HTTP status
				if response.status == 404:
					raise S3DownloadError(
						message="Object not found in S3",
						status_code=404,
						details={"http_status": response.status}
					)
				elif response.status == 403:
					raise S3DownloadError(
						message="Presigned URL expired or invalid",
						status_code=410,
						details={"http_status": response.status}
					)
				elif response.status != 200:
					raise S3DownloadError(
						message=f"S3 download failed with HTTP {response.status}",
						status_code=502,
						details={"http_status": response.status}
					)

				# Stream to file
				bytes_downloaded = 0
				with open(destination, 'wb') as f:
					async for chunk in response.content.iter_chunked(self.chunk_size):
						f.write(chunk)
						bytes_downloaded += len(chunk)

						# Log progress for large files
						if bytes_downloaded % (10 * 1024 * 1024) == 0:  # Every 10MB
							progress_pct = (bytes_downloaded / expected_size * 100) if expected_size else 0
							logger.debug(
								f"Download progress: {bytes_downloaded / (1024 * 1024):.1f}MB ({progress_pct:.1f}%)"
							)

				# Validate file size
				if bytes_downloaded != expected_size:
					raise S3DownloadError(
						message=f"File size mismatch: expected {expected_size} bytes, got {bytes_downloaded} bytes",
						status_code=502,
						details={
							"expected_size": expected_size,
							"actual_size": bytes_downloaded,
						}
					)


# Singleton instance
_downloader: Optional[S3Downloader] = None


def get_s3_downloader() -> S3Downloader:
	"""Get singleton S3 downloader instance."""
	global _downloader
	if _downloader is None:
		_downloader = S3Downloader()
	return _downloader
