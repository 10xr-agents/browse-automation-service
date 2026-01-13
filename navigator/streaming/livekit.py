"""
LiveKit Integration Service for Browser Automation

This service handles:
- Connecting to LiveKit rooms
- Publishing browser video tracks
- Managing video frame capture and encoding
- Session lifecycle management
"""

import asyncio
import io
import logging
from typing import Any

try:
	import livekit.rtc as rtc
	from PIL import Image
	import jwt
	import time

	LIVEKIT_AVAILABLE = True
except (ImportError, AttributeError) as e:
	LIVEKIT_AVAILABLE = False
	logging.warning(f'LiveKit SDK not available: {e}. Install with: pip install livekit pyjwt')

logger = logging.getLogger(__name__)


class LiveKitStreamingService:
	"""Service for streaming browser content to LiveKit."""

	def __init__(
		self,
		livekit_url: str,
		room_name: str,
		livekit_api_key: str | None = None,
		livekit_api_secret: str | None = None,
		livekit_token: str | None = None,
		participant_identity: str | None = None,
		participant_name: str | None = None,
		width: int = 1920,
		height: int = 1080,
		fps: int = 10,
	):
		"""Initialize LiveKit streaming service.

		Args:
			livekit_url: LiveKit server URL
			room_name: Name of the LiveKit room
			livekit_api_key: LiveKit API key (for token generation)
			livekit_api_secret: LiveKit API secret (for token generation)
			livekit_token: Pre-generated LiveKit access token (optional if api_key/secret provided)
			participant_identity: Participant identity for token generation (default: "browser-agent")
			participant_name: Participant name for token generation (default: "Browser Automation Agent")
			width: Video width in pixels
			height: Video height in pixels
			fps: Frames per second
		"""
		if not LIVEKIT_AVAILABLE:
			raise ImportError('LiveKit SDK not installed. Install with: pip install livekit')

		# Normalize URL to WebSocket format (wss:// or ws://)
		# LiveKit requires WebSocket URLs, but users might provide https:// URLs
		if livekit_url.startswith('https://'):
			livekit_url = livekit_url.replace('https://', 'wss://', 1)
		elif livekit_url.startswith('http://'):
			livekit_url = livekit_url.replace('http://', 'ws://', 1)
		elif not (livekit_url.startswith('wss://') or livekit_url.startswith('ws://')):
			# If no protocol specified, assume wss:// for security
			livekit_url = f'wss://{livekit_url}'

		self.livekit_url = livekit_url
		self.room_name = room_name
		self.livekit_api_key = livekit_api_key
		self.livekit_api_secret = livekit_api_secret
		self.livekit_token = livekit_token
		self.participant_identity = participant_identity or 'browser-automation'
		self.participant_name = participant_name or 'Browser Automation Agent'
		self.width = width
		self.height = height
		self.fps = fps

		# Validate that we have either token or api_key/secret
		if not self.livekit_token and not (self.livekit_api_key and self.livekit_api_secret):
			raise ValueError('Either livekit_token or both livekit_api_key and livekit_api_secret must be provided')

		self.room: rtc.Room | None = None
		self.video_source: rtc.VideoSource | None = None
		self.video_track: rtc.LocalVideoTrack | None = None
		self.video_publication: rtc.TrackPublication | None = None
		self.capture_task: asyncio.Task | None = None
		self._is_active = False

	def _generate_token(self) -> str:
		"""Generate LiveKit access token from API key and secret.

		Returns:
			JWT token string
		"""
		logger.debug(f'[LiveKit] Generating token for room: {self.room_name}, identity: {self.participant_identity}')
		
		if self.livekit_token:
			logger.debug('[LiveKit] Using pre-generated token')
			return self.livekit_token

		if not self.livekit_api_key or not self.livekit_api_secret:
			raise ValueError('Cannot generate token: API key and secret required')

		logger.debug(f'[LiveKit] Creating AccessToken with API key (length: {len(self.livekit_api_key)})')
		
		# Generate JWT token with LiveKit claims
		# LiveKit uses HS256 algorithm with API secret as the signing key
		now = int(time.time())
		exp = now + 3600  # Token expires in 1 hour (3600 seconds)
		
		# Build JWT claims following LiveKit token structure
		claims = {
			'iss': self.livekit_api_key,  # Issuer (API key)
			'exp': exp,  # Expiration time
			'nbf': now,  # Not before
			'sub': self.participant_identity or 'browser-automation',  # Subject (participant identity)
			'video': {
				'room': self.room_name,
				'roomJoin': True,
				'canPublish': True,
				'canSubscribe': True,
				'canPublishData': True,
			},
		}
		
		# Add participant name if provided
		if self.participant_name:
			claims['name'] = self.participant_name
		
		# Sign token with API secret
		jwt_token = jwt.encode(claims, self.livekit_api_secret, algorithm='HS256')
		logger.debug(f'[LiveKit] Token generated successfully (length: {len(jwt_token)})')
		return jwt_token

	async def connect(self) -> None:
		"""Connect to LiveKit room."""
		if self.room is not None:
			logger.warning('[LiveKit] Already connected to LiveKit room')
			return

		logger.info(f'[LiveKit] Connecting to room: {self.room_name} at {self.livekit_url}')
		logger.debug(f'[LiveKit] Room dimensions: {self.width}x{self.height}, FPS: {self.fps}')
		
		self.room = rtc.Room()

		# Generate token if needed
		token = self._generate_token()
		logger.debug('[LiveKit] Token generated, connecting to room...')

		# Connect to room
		await self.room.connect(self.livekit_url, token)
		logger.info(f'[LiveKit] ✅ Connected to room: {self.room_name}')
		logger.debug(f'[LiveKit] Local participant: {self.room.local_participant.identity if self.room.local_participant else "None"}')

	async def disconnect(self) -> None:
		"""Disconnect from LiveKit room."""
		try:
			await self.stop_publishing()
		except Exception as e:
			logger.debug(f'Error stopping publishing during disconnect: {e}')
		
		if self.room:
			try:
				await self.room.disconnect()
			except Exception as e:
				logger.debug(f'Error disconnecting from room (may be already closed): {e}')
			self.room = None
			logger.info('Disconnected from LiveKit room')

	async def start_publishing(self, browser_session) -> None:
		"""Start publishing browser video to LiveKit.

		Args:
			browser_session: BrowserSession instance to capture frames from
		"""
		if self._is_active:
			logger.warning('Video publishing already active')
			return

		if not self.room:
			await self.connect()

		logger.info('[LiveKit] Starting video publishing...')
		logger.debug(f'[LiveKit] Video source dimensions: {self.width}x{self.height}')

		# Create video source
		self.video_source = rtc.VideoSource(self.width, self.height)
		logger.debug('[LiveKit] VideoSource created')
		
		self.video_track = rtc.LocalVideoTrack.create_video_track('browser-screen', self.video_source)
		logger.debug('[LiveKit] LocalVideoTrack created: browser-screen')

		# Publish options
		options = rtc.TrackPublishOptions(
			source=rtc.TrackSource.SOURCE_SCREENSHARE,
			simulcast=True,
			video_encoding=rtc.VideoEncoding(
				max_framerate=self.fps,
				max_bitrate=2_000_000,  # 2 Mbps
			),
			video_codec=rtc.VideoCodec.H264,
		)
		logger.debug(f'[LiveKit] TrackPublishOptions: source=SOURCE_SCREENSHARE, fps={self.fps}, bitrate=2Mbps, codec=H264')

		# Publish track
		logger.debug('[LiveKit] Publishing track to room...')
		if not self.room or not self.room.local_participant:
			raise RuntimeError('Room not connected or local participant not available')
		self.video_publication = await self.room.local_participant.publish_track(self.video_track, options)
		logger.info(f'[LiveKit] ✅ Video track published (SID: {self.video_publication.sid})')

		# Start capture loop
		self._is_active = True
		self.capture_task = asyncio.create_task(self._capture_loop(browser_session))

	async def stop_publishing(self) -> None:
		"""Stop publishing video."""
		if not self._is_active:
			return

		logger.info('Stopping video publishing...')
		self._is_active = False

		# Cancel capture task
		if self.capture_task:
			self.capture_task.cancel()
			try:
				# Wait for task to complete, but don't wait forever
				await asyncio.wait_for(self.capture_task, timeout=2.0)
			except (asyncio.CancelledError, asyncio.TimeoutError):
				pass
			except Exception as e:
				logger.debug(f'Error waiting for capture task: {e}')
			self.capture_task = None

		# Unpublish track (handle gracefully if room/participant is already closed)
		if self.video_publication and self.room:
			try:
				if self.room.local_participant:
					await self.room.local_participant.unpublish_track(self.video_publication.sid)
			except Exception as e:
				logger.debug(f'Error unpublishing track (may be already closed): {e}')
			self.video_publication = None

		# Clean up track and source
		# Note: LocalVideoTrack doesn't have a stop() method - it's cleaned up when unpublished
		if self.video_track:
			self.video_track = None
		if self.video_source:
			try:
				await self.video_source.aclose()
			except Exception as e:
				logger.debug(f'Error closing video source: {e}')
			self.video_source = None

		logger.info('Video publishing stopped')

	async def _capture_loop(self, browser_session) -> None:
		"""Capture browser frames and publish to LiveKit."""
		frame_interval = 1.0 / self.fps
		logger.debug(f'[LiveKit] Starting capture loop (interval: {frame_interval:.3f}s, fps: {self.fps})')
		frame_count = 0

		while self._is_active:
			try:
				# Capture screenshot from browser (no debug log - too frequent)
				screenshot_bytes = await browser_session.take_screenshot(
					path=None,
					full_page=False,
					format='png',
				)

				if screenshot_bytes:
					# Convert to video frame
					frame = self._screenshot_to_video_frame(screenshot_bytes)
					if frame and self.video_source:
						self.video_source.capture_frame(frame)
						frame_count += 1
						# Log every 150 frames (~5 seconds at 30fps) instead of every 30
						if frame_count % 150 == 0:
							logger.info(f'[LiveKit] Published {frame_count} frames')
					else:
						logger.warning('[LiveKit] Failed to convert screenshot to video frame')
				else:
					logger.warning('[LiveKit] Screenshot capture returned empty bytes')

				await asyncio.sleep(frame_interval)

			except asyncio.CancelledError:
				logger.debug('[LiveKit] Capture loop cancelled')
				break
			except Exception as e:
				# Check if event loop is closed (happens during shutdown)
				try:
					loop = asyncio.get_running_loop()
					if loop.is_closed():
						logger.debug('[LiveKit] Event loop closed, stopping capture')
						break
				except RuntimeError:
					# No running loop - we're shutting down
					logger.debug('[LiveKit] No running event loop, stopping capture')
					break
				
				logger.error(f'[LiveKit] Error capturing frame: {e}', exc_info=True)
				await asyncio.sleep(0.1)

	def _screenshot_to_video_frame(self, screenshot_bytes: bytes) -> rtc.VideoFrame | None:
		"""Convert screenshot bytes to LiveKit VideoFrame.

		Args:
			screenshot_bytes: PNG screenshot bytes

		Returns:
			VideoFrame or None if conversion fails
		"""
		try:
			# Load image (no debug logs - too frequent at 30fps)
			img = Image.open(io.BytesIO(screenshot_bytes))
			original_size = img.size
			
			img = img.convert('RGBA')

			# Resize if needed
			if img.size != (self.width, self.height):
				img = img.resize((self.width, self.height), Image.Resampling.LANCZOS)

			# Get RGBA pixel data - LiveKit handles encoding conversion automatically
			rgba_data = img.tobytes('raw', 'RGBA')

			# Create video frame with RGBA buffer type
			# LiveKit will automatically convert between buffer encodings as needed
			frame = rtc.VideoFrame(
				self.width,
				self.height,
				rtc.VideoBufferType.RGBA,
				rgba_data,
			)

			return frame

		except Exception as e:
			logger.error(f'[LiveKit] ❌ Error converting screenshot to video frame: {e}', exc_info=True)
			return None

	@property
	def is_active(self) -> bool:
		"""Check if video publishing is active."""
		return self._is_active
