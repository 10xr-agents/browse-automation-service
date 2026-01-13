"""
Auto-Scaling RQ Worker Manager

Manages RQ workers as subprocesses with automatic scaling based on queue length.
Integrates with FastAPI startup/shutdown lifecycle.

Features:
- Automatic worker spawning and lifecycle management
- Dynamic auto-scaling based on queue length
- Health monitoring and automatic restart
- Extensible configuration for new job types
- Production-grade resilience and observability
"""

import asyncio
import logging
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any

# macOS fork safety: Disable Objective-C runtime fork safety check
# This prevents crashes when spawning subprocesses on macOS
if sys.platform == 'darwin':
	os.environ.setdefault('OBJC_DISABLE_INITIALIZE_FORK_SAFETY', 'YES')

logger = logging.getLogger(__name__)

# RQ integration
try:
	from rq import Queue
	from redis import Redis
	
	RQ_AVAILABLE = True
except ImportError:
	RQ_AVAILABLE = False
	logging.warning('RQ not installed. Install with: pip install rq redis')


@dataclass
class JobTypeConfig:
	"""
	Configuration for a job type managed by the JobManager.
	
	Attributes:
		queue_name: Name of the RQ queue for this job type
		min_workers: Minimum number of workers to keep running
		max_workers: Maximum number of workers allowed
		scale_up_threshold: Queue length that triggers scale-up (default: 5)
		scale_down_threshold: Queue length that triggers scale-down (default: 0)
		scale_cooldown: Seconds to wait between scaling operations (default: 30)
		health_check_interval: Seconds between health checks (default: 60)
		worker_timeout: Seconds before considering a worker unresponsive (default: 300)
	"""
	queue_name: str
	min_workers: int = 1
	max_workers: int = 5
	scale_up_threshold: int = 5
	scale_down_threshold: int = 0
	scale_cooldown: int = 30
	health_check_interval: int = 60
	worker_timeout: int = 300


@dataclass
class WorkerProcess:
	"""
	Represents a managed RQ worker process.
	
	Attributes:
		process: subprocess.Popen instance
		queue_name: Queue this worker is processing
		worker_id: Unique identifier for this worker
		started_at: Timestamp when worker started
		last_health_check: Timestamp of last successful health check
		restart_count: Number of times this worker has been restarted
	"""
	process: subprocess.Popen
	queue_name: str
	worker_id: str
	started_at: float
	last_health_check: float = field(default_factory=time.time)
	restart_count: int = 0


class JobManager:
	"""
	Auto-scaling RQ worker manager.
	
	Manages RQ workers as subprocesses with automatic scaling based on queue length.
	Integrates with FastAPI startup/shutdown lifecycle.
	"""
	
	def __init__(
		self,
		redis_url: str | None = None,
		job_types: list[JobTypeConfig] | None = None,
		enabled: bool = True,
	):
		"""
		Initialize JobManager.
		
		Args:
			redis_url: Redis URL (defaults to REDIS_URL env var)
			job_types: List of job type configurations (defaults to knowledge-retrieval)
			enabled: Whether to enable worker management (default: True)
		"""
		self.enabled = enabled and RQ_AVAILABLE
		
		if not self.enabled:
			logger.warning('JobManager disabled (RQ not available or explicitly disabled)')
			self.redis_url = None
			self.redis_client = None
			self.job_types = []
			self.workers: dict[str, list[WorkerProcess]] = {}
			self._scaling_task: asyncio.Task | None = None
			self._running = False
			return
		
		# Redis connection
		self.redis_url = redis_url or os.getenv("REDIS_URL")
		if not self.redis_url:
			logger.warning('REDIS_URL not set - JobManager disabled')
			self.enabled = False
			self.redis_client = None
		else:
			try:
				# RQ requires decode_responses=False because it stores binary data (pickled objects) in Redis
				# RQ handles encoding/decoding internally
				self.redis_client = Redis.from_url(self.redis_url, decode_responses=False)
				self.redis_client.ping()
				logger.info(f'JobManager initialized with Redis: {self.redis_url}')
			except Exception as e:
				logger.error(f'Failed to connect to Redis: {e} - JobManager disabled')
				self.enabled = False
				self.redis_client = None
		
		# Job type configurations
		if job_types is None:
			# Default: knowledge-retrieval queue
			job_types = [
				JobTypeConfig(
					queue_name="knowledge-retrieval",
					min_workers=1,
					max_workers=5,
					scale_up_threshold=5,
					scale_down_threshold=0,
				)
			]
		
		self.job_types = {config.queue_name: config for config in job_types}
		
		# Worker tracking
		self.workers: dict[str, list[WorkerProcess]] = {
			queue_name: [] for queue_name in self.job_types.keys()
		}
		
		# Scaling state
		self._scaling_task: asyncio.Task | None = None
		self._running = False
		self._last_scale_time: dict[str, float] = {
			queue_name: 0.0 for queue_name in self.job_types.keys()
		}
		
		logger.info(f'JobManager initialized with {len(self.job_types)} job types: {list(self.job_types.keys())}')
	
	def _get_queue(self, queue_name: str) -> Queue | None:
		"""Get RQ queue instance for queue name."""
		if not self.redis_client:
			return None
		try:
			return Queue(queue_name, connection=self.redis_client)
		except Exception as e:
			logger.error(f'Failed to get queue {queue_name}: {e}')
			return None
	
	def _get_queue_length(self, queue_name: str) -> int:
		"""Get current queue length (number of pending jobs)."""
		if not self.redis_client:
			return 0
		try:
			queue = self._get_queue(queue_name)
			if queue is None:
				return 0
			return len(queue)
		except Exception as e:
			logger.warning(f'Failed to get queue length for {queue_name}: {e}')
			return 0
	
	def _start_worker(self, queue_name: str) -> WorkerProcess | None:
		"""
		Start a new RQ worker process for the given queue.
		
		Args:
			queue_name: Queue name to start worker for
		
		Returns:
			WorkerProcess instance or None if failed
		"""
		if not self.enabled:
			return None
		
		# Generate unique worker ID
		worker_id = f"{queue_name}-{int(time.time() * 1000)}"
		
		# Build RQ worker command
		# Use 'rq worker' CLI command (RQ uses REDIS_URL env var, not CLI arg)
		# Try to use 'uv run' if available to ensure correct environment
		import shutil
		uv_path = shutil.which('uv')
		
		# Prefer using the worker script which has proper path setup
		# This ensures navigator modules can be imported correctly
		project_root = os.getcwd()
		worker_script = os.path.join(project_root, "navigator", "knowledge", "worker.py")
		
		if os.path.exists(worker_script) and uv_path:
			# Use worker script with uv run (ensures correct environment and path setup)
			cmd = [uv_path, "run", "python", worker_script]
		elif uv_path:
			# Fallback: Use uv run rq worker (rq is available as a CLI command in venv)
			cmd = [
				uv_path, "run",
				"rq", "worker",
				queue_name,
			]
		else:
			# Fallback: try direct rq command or use worker script
			rq_cmd = shutil.which('rq')
			if rq_cmd:
				# Use rq command directly
				cmd = [rq_cmd, "worker", queue_name]
			elif os.path.exists(worker_script):
				# Last resort: use worker script with system Python
				cmd = [sys.executable, worker_script]
			else:
				logger.error(f'Cannot find rq command or worker script for {queue_name}')
				return None
		
		# Set environment variables
		env = os.environ.copy()
		env["REDIS_URL"] = self.redis_url
		# Ensure project root is in PYTHONPATH so workers can import navigator modules
		project_root = os.getcwd()
		if 'PYTHONPATH' in env:
			env['PYTHONPATH'] = f"{project_root}:{env['PYTHONPATH']}"
		else:
			env['PYTHONPATH'] = project_root
		
		# Start worker process
		# On macOS, we need to avoid fork crashes with Objective-C runtime
		# Use start_new_session=True and preexec_fn=None to avoid fork issues
		try:
			# Set environment variable to help with fork safety on macOS
			env['OBJC_DISABLE_INITIALIZE_FORK_SAFETY'] = 'YES'
			
			# Start worker process with log forwarding
			# Use PIPE for stdout/stderr and read them in background threads to prevent blocking
			process = subprocess.Popen(
				cmd,
				stdout=subprocess.PIPE,  # Capture stdout for logging
				stderr=subprocess.PIPE,  # Capture stderr for logging
				env=env,
				cwd=os.getcwd(),  # Use current working directory
				start_new_session=True,  # Start in new session to avoid fork issues
				preexec_fn=None,  # Don't use preexec_fn (can cause fork issues)
			)
			
			# Start background threads to read and log worker output
			# This prevents buffer blocking while still showing logs in main console
			def log_worker_output(pipe, prefix: str, is_stderr: bool = False):
				"""Read from pipe and log to main console."""
				try:
					for line in iter(pipe.readline, b''):
						if line:
							# Decode and log the line
							line_str = line.decode('utf-8', errors='replace').rstrip()
							if line_str:  # Only log non-empty lines
								# Use appropriate log level based on source and content
								if is_stderr:
									# Stderr might contain errors, but also warnings from uv/rq
									# Check if it looks like an error
									line_lower = line_str.lower()
									if 'error' in line_lower or 'exception' in line_lower or 'traceback' in line_lower:
										logger.error(f'[Worker-{prefix}] {line_str}')
									elif 'warning' in line_lower or 'deprecated' in line_lower:
										logger.warning(f'[Worker-{prefix}] {line_str}')
									else:
										# Other stderr (might be info redirected to stderr)
										logger.info(f'[Worker-{prefix}] {line_str}')
								else:
									# Stdout contains normal worker logs
									# Parse log level from the line if it's a formatted log
									if ' - ' in line_str and ('INFO' in line_str or 'DEBUG' in line_str or 'WARNING' in line_str or 'ERROR' in line_str):
										# It's a formatted log line, extract the level
										if ' - ERROR - ' in line_str:
											logger.error(f'[Worker-{prefix}] {line_str}')
										elif ' - WARNING - ' in line_str:
											logger.warning(f'[Worker-{prefix}] {line_str}')
										elif ' - DEBUG - ' in line_str:
											logger.debug(f'[Worker-{prefix}] {line_str}')
										else:
											logger.info(f'[Worker-{prefix}] {line_str}')
									else:
										# Plain output
										logger.info(f'[Worker-{prefix}] {line_str}')
					pipe.close()
				except Exception as e:
					logger.debug(f'Error reading worker {prefix} output: {e}')
			
			# Start threads to read stdout and stderr
			# These are daemon threads so they won't prevent shutdown
			stdout_thread = threading.Thread(
				target=log_worker_output,
				args=(process.stdout, worker_id[:12], False),
				daemon=True,
				name=f'worker-stdout-{worker_id}',
			)
			stderr_thread = threading.Thread(
				target=log_worker_output,
				args=(process.stderr, worker_id[:12], True),
				daemon=True,
				name=f'worker-stderr-{worker_id}',
			)
			stdout_thread.start()
			stderr_thread.start()
			
			# Log worker startup confirmation
			logger.debug(f'Worker {worker_id} started with command: {" ".join(cmd)}')
			
			worker = WorkerProcess(
				process=process,
				queue_name=queue_name,
				worker_id=worker_id,
				started_at=time.time(),
			)
			
			logger.info(f'✅ Started worker {worker_id} for queue {queue_name} (PID: {process.pid})')
			return worker
		
		except Exception as e:
			logger.error(f'❌ Failed to start worker for {queue_name}: {e}')
			return None
	
	def _stop_worker(self, worker: WorkerProcess, force: bool = False) -> bool:
		"""
		Stop a worker process gracefully or forcefully.
		
		Args:
			worker: WorkerProcess to stop
			force: Whether to force kill (default: False)
		
		Returns:
			True if stopped successfully, False otherwise
		"""
		try:
			if worker.process.poll() is None:
				# Process is still running
				if force:
					worker.process.kill()
					logger.info(f'🔪 Force killed worker {worker.worker_id}')
				else:
					worker.process.terminate()
					logger.info(f'🛑 Terminated worker {worker.worker_id}')
				
				# Wait for process to exit (with timeout)
				try:
					worker.process.wait(timeout=10)
				except subprocess.TimeoutExpired:
					worker.process.kill()
					logger.warning(f'⚠️  Worker {worker.worker_id} did not exit gracefully, killed')
			
			return True
		
		except Exception as e:
			logger.error(f'❌ Error stopping worker {worker.worker_id}: {e}')
			return False
	
	def _check_worker_health(self, worker: WorkerProcess) -> bool:
		"""
		Check if a worker process is healthy.
		
		Args:
			worker: WorkerProcess to check
		
		Returns:
			True if healthy, False otherwise
		"""
		if worker.process.poll() is not None:
			# Process has exited
			exit_code = worker.process.returncode
			logger.warning(f'⚠️  Worker {worker.worker_id} process has exited (exit code: {exit_code})')
			# Note: stderr will be captured when worker is removed from tracking
			return False
		
		# Process is running - update health check timestamp
		worker.last_health_check = time.time()
		return True
	
	async def _scale_workers(self):
		"""Main scaling loop - runs continuously while manager is running."""
		logger.info('🔧 Scaling loop started')
		
		while self._running:
			try:
				await asyncio.sleep(10)  # Check every 10 seconds
				
				if not self.enabled:
					continue
				
				# Scale each job type independently
				for queue_name, config in self.job_types.items():
					await self._scale_queue_workers(queue_name, config)
			
			except asyncio.CancelledError:
				logger.info('Scaling loop cancelled')
				break
			except Exception as e:
				logger.error(f'Error in scaling loop: {e}', exc_info=True)
				await asyncio.sleep(30)  # Wait longer on error
	
	async def _scale_queue_workers(self, queue_name: str, config: JobTypeConfig):
		"""
		Scale workers for a specific queue based on queue length.
		
		Args:
			queue_name: Queue name
			config: Job type configuration
		"""
		# Check cooldown
		now = time.time()
		if now - self._last_scale_time[queue_name] < config.scale_cooldown:
			return  # Still in cooldown period
		
		# Get current state
		queue_length = self._get_queue_length(queue_name)
		current_workers = self.workers[queue_name]
		active_workers = [w for w in current_workers if self._check_worker_health(w)]
		
		# Remove dead workers from tracking
		dead_workers = [w for w in current_workers if w not in active_workers]
		for worker in dead_workers:
			# Try to capture error output from dead worker
			error_output = ""
			try:
				if worker.process.stderr:
					# Read stderr (non-blocking)
					import select
					if select.select([worker.process.stderr], [], [], 0)[0]:
						error_output = worker.process.stderr.read().decode('utf-8', errors='ignore')[:1000]
			except Exception:
				pass
			
			if error_output:
				logger.warning(f'🪦 Removing dead worker {worker.worker_id} from tracking (exit code: {worker.process.returncode})')
				logger.warning(f'   Worker error output: {error_output}')
			else:
				logger.warning(f'🪦 Removing dead worker {worker.worker_id} from tracking (exit code: {worker.process.returncode})')
			self.workers[queue_name].remove(worker)
		
		# Update current_workers to only active ones
		current_workers = active_workers
		worker_count = len(current_workers)
		
		# Determine target worker count
		target_workers = worker_count
		
		if queue_length > config.scale_up_threshold and worker_count < config.max_workers:
			# Scale up: add one worker
			target_workers = min(worker_count + 1, config.max_workers)
		elif queue_length <= config.scale_down_threshold and worker_count > config.min_workers:
			# Scale down: remove one worker
			target_workers = max(worker_count - 1, config.min_workers)
		elif worker_count < config.min_workers:
			# Below minimum: scale up to minimum
			target_workers = config.min_workers
		
		# Scale workers
		if target_workers > worker_count:
			# Scale up
			workers_to_add = target_workers - worker_count
			logger.info(f'📈 Scaling up {queue_name}: {worker_count} → {target_workers} workers (queue: {queue_length} jobs)')
			
			for _ in range(workers_to_add):
				worker = self._start_worker(queue_name)
				if worker:
					self.workers[queue_name].append(worker)
					self._last_scale_time[queue_name] = now
				else:
					logger.error(f'Failed to start worker for {queue_name}, stopping scale-up')
					break
		
		elif target_workers < worker_count:
			# Scale down
			workers_to_remove = worker_count - target_workers
			logger.info(f'📉 Scaling down {queue_name}: {worker_count} → {target_workers} workers (queue: {queue_length} jobs)')
			
			# Remove workers (oldest first)
			for _ in range(workers_to_remove):
				if self.workers[queue_name]:
					worker = self.workers[queue_name][0]  # Remove oldest
					if self._stop_worker(worker, force=False):
						self.workers[queue_name].remove(worker)
						self._last_scale_time[queue_name] = now
	
	async def start(self):
		"""Start the JobManager and begin managing workers."""
		if not self.enabled:
			logger.warning('JobManager is disabled, not starting')
			return
		
		if self._running:
			logger.warning('JobManager is already running')
			return
		
		logger.info('=' * 80)
		logger.info('🚀 Starting JobManager')
		logger.info('=' * 80)
		
		self._running = True
		
		# Start initial workers for each job type
		for queue_name, config in self.job_types.items():
			logger.info(f'Starting {config.min_workers} initial worker(s) for {queue_name}')
			for _ in range(config.min_workers):
				worker = self._start_worker(queue_name)
				if worker:
					self.workers[queue_name].append(worker)
		
		# Start scaling loop
		self._scaling_task = asyncio.create_task(self._scale_workers())
		
		logger.info('=' * 80)
		logger.info('✅ JobManager started successfully')
		logger.info(f'   Managing {len(self.job_types)} job type(s): {list(self.job_types.keys())}')
		logger.info('=' * 80)
	
	async def stop(self, timeout: int = 30):
		"""
		Stop the JobManager and all workers gracefully.
		
		Args:
			timeout: Seconds to wait for workers to stop gracefully
		"""
		if not self._running:
			return
		
		logger.info('=' * 80)
		logger.info('🛑 Stopping JobManager')
		logger.info('=' * 80)
		
		self._running = False
		
		# Stop scaling loop
		if self._scaling_task:
			self._scaling_task.cancel()
			try:
				await self._scaling_task
			except asyncio.CancelledError:
				pass
		
		# Stop all workers gracefully
		for queue_name, workers in self.workers.items():
			logger.info(f'Stopping {len(workers)} worker(s) for {queue_name}')
			for worker in workers:
				self._stop_worker(worker, force=False)
		
		# Wait for workers to exit
		start_time = time.time()
		while time.time() - start_time < timeout:
			all_stopped = True
			for workers in self.workers.values():
				for worker in workers:
					if worker.process.poll() is None:
						all_stopped = False
						break
				if not all_stopped:
					break
			
			if all_stopped:
				break
			
			await asyncio.sleep(1)
		
		# Force kill any remaining workers
		for workers in self.workers.values():
			for worker in workers:
				if worker.process.poll() is None:
					logger.warning(f'Force killing worker {worker.worker_id}')
					self._stop_worker(worker, force=True)
		
		# Clear worker tracking
		for queue_name in self.workers:
			self.workers[queue_name].clear()
		
		logger.info('=' * 80)
		logger.info('✅ JobManager stopped')
		logger.info('=' * 80)
	
	def get_status(self) -> dict[str, Any]:
		"""
		Get current status of the JobManager.
		
		Returns:
			Dictionary with status information
		"""
		status = {
			'enabled': self.enabled,
			'running': self._running,
			'job_types': {},
		}
		
		for queue_name, config in self.job_types.items():
			workers = self.workers.get(queue_name, [])
			active_workers = [w for w in workers if self._check_worker_health(w)]
			queue_length = self._get_queue_length(queue_name) if self.enabled else 0
			
			status['job_types'][queue_name] = {
				'config': {
					'min_workers': config.min_workers,
					'max_workers': config.max_workers,
					'scale_up_threshold': config.scale_up_threshold,
					'scale_down_threshold': config.scale_down_threshold,
				},
				'workers': {
					'total': len(workers),
					'active': len(active_workers),
					'workers': [
						{
							'worker_id': w.worker_id,
							'pid': w.process.pid,
							'started_at': w.started_at,
							'last_health_check': w.last_health_check,
							'status': 'active' if self._check_worker_health(w) else 'dead',
						}
						for w in workers
					],
				},
				'queue_length': queue_length,
			}
		
		return status


# Global JobManager instance
_job_manager: JobManager | None = None


def get_job_manager(redis_url: str | None = None, job_types: list[JobTypeConfig] | None = None) -> JobManager:
	"""
	Get or create global JobManager instance.
	
	Args:
		redis_url: Redis URL (only used if creating new instance)
		job_types: Job type configurations (only used if creating new instance)
	
	Returns:
		JobManager instance
	"""
	global _job_manager
	
	if _job_manager is None:
		_job_manager = JobManager(redis_url=redis_url, job_types=job_types)
	
	return _job_manager
