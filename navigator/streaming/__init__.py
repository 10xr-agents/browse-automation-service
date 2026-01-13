"""Video and event streaming."""
from navigator.streaming.broadcaster import EventBroadcaster
from navigator.streaming.livekit import LiveKitStreamingService, LIVEKIT_AVAILABLE

__all__ = ['EventBroadcaster', 'LiveKitStreamingService', 'LIVEKIT_AVAILABLE']

# Import new streaming components (optional - only if needed)
try:
	from navigator.streaming.state_publisher import StatePublisher
	from navigator.streaming.command_consumer import CommandConsumer
	from navigator.streaming.redis_client import get_redis_streams_client, get_redis_url
	from navigator.streaming.command_consumer_factory import create_command_consumer
	__all__.extend(['StatePublisher', 'CommandConsumer', 'get_redis_streams_client', 'get_redis_url', 'create_command_consumer'])
except ImportError:
	pass
