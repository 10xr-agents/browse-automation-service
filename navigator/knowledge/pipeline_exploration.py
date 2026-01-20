"""
Knowledge Pipeline: Exploration Logic

Core exploration loop and page processing logic.
"""

import asyncio
import logging
import time
from typing import Any

from navigator.knowledge.progress_observer import ExplorationProgress
from navigator.knowledge.pipeline_helpers import (
	calculate_estimated_time_remaining,
	calculate_processing_rate,
	should_explore_url,
)

logger = logging.getLogger(__name__)


async def process_exploration_loop(
	pipeline_instance,
	start_url: str,
	max_pages: int | None,
	job_id: str,
	results: dict[str, Any],
) -> None:
	"""
	Main exploration loop for processing URLs.
	
	Args:
		pipeline_instance: KnowledgePipeline instance
		start_url: Starting URL
		max_pages: Maximum pages to process
		job_id: Job ID
		results: Results dictionary to update
	"""
	# Extract website metadata from start page
	try:
		start_content = await pipeline_instance.semantic_analyzer.extract_content(start_url)
		results['website_metadata'] = {
			'title': start_content.get('title', ''),
			'description': start_content.get('description', ''),
			'url': start_url,
		}
	except Exception as e:
		logger.warning(f"Failed to extract website metadata: {e}")
		results['website_metadata'] = {'url': start_url}

	# Emit initial progress
	await pipeline_instance.progress_observer.on_progress(ExplorationProgress(
		job_id=job_id,
		status="running",
		current_page=start_url,
		pages_completed=0,
		pages_queued=1,
		pages_failed=0,
	))

	# Set base URL for external link detection
	pipeline_instance.exploration_engine.base_url = start_url

	# Discover links from start URL
	logger.info(f"🔗 [Job {job_id}] Discovering links from start URL: {start_url}")
	links = await pipeline_instance.exploration_engine.discover_links(start_url)
	logger.info(f"   Discovered {len(links)} links from start URL")

	# Collect URLs to process
	urls_to_process = [start_url]
	processed_urls = set()

	# Add discovered links (only internal links for exploration)
	external_count = 0
	internal_count = 0
	filtered_count = 0
	for link in links:
		link_url = link.get('href', '') or link.get('url', '')
		is_internal = link.get('internal', True)

		# Store all links (internal and external) for graph representation
		try:
			await pipeline_instance.storage.store_link(start_url, link_url, {
				'anchor_text': link.get('text', ''),
				'link_type': 'internal' if is_internal else 'external',
			})
		except Exception as e:
			logger.error(f"Failed to store link {start_url} -> {link_url}: {e}")

		# Only add internal links to exploration queue
		if is_internal and link_url and link_url not in processed_urls:
			# Apply path filtering
			if should_explore_url(link_url, pipeline_instance.include_paths, pipeline_instance.exclude_paths):
				urls_to_process.append(link_url)
				internal_count += 1
			else:
				filtered_count += 1
				logger.debug(f"   ⏭️  Skipping URL due to path restrictions: {link_url}")
		elif not is_internal:
			external_count += 1
			results['external_links_detected'] += 1
			await pipeline_instance.progress_observer.on_external_link_detected(start_url, link_url)
			logger.debug(f"   🔗 External link detected (not exploring): {link_url}")

	logger.info(f"   📊 Link summary: {internal_count} internal, {external_count} external, {filtered_count} filtered")
	logger.info(f"   📋 Total URLs to process: {len(urls_to_process)}")

	# Limit to max_pages if specified
	if max_pages:
		original_count = len(urls_to_process)
		urls_to_process = urls_to_process[:max_pages]
		if len(urls_to_process) < original_count:
			logger.info(f"   ⚠️  Limited to {max_pages} pages (had {original_count} URLs)")

	# Process each URL
	logger.info(f"🔄 [Job {job_id}] Starting to process {len(urls_to_process)} URLs")
	for idx, url in enumerate(urls_to_process, 1):
		# Check for pause
		if pipeline_instance.job_paused:
			pipeline_instance.job_status = "paused"
			await pipeline_instance.progress_observer.on_progress(ExplorationProgress(
				job_id=job_id,
				status="paused",
				current_page=url,
				pages_completed=results['pages_stored'],
				pages_queued=len(urls_to_process) - results['pages_processed'],
				pages_failed=results['pages_failed'],
				links_discovered=len(links),
				external_links_detected=results['external_links_detected'],
			))
			# Wait until resumed
			while pipeline_instance.job_paused:
				await asyncio.sleep(0.5)
			pipeline_instance.job_status = "running"

		if url in processed_urls:
			logger.debug(f"   ⏭️  [Job {job_id}] Skipping already processed URL: {url}")
			continue
		processed_urls.add(url)

		# Check for cancellation
		if pipeline_instance.job_status == "cancelled":
			logger.info(f"   ⛔ [Job {job_id}] Cancelled, stopping exploration")
			break
		elif pipeline_instance.job_status == "cancelling":
			logger.info(f"   ⏸️  [Job {job_id}] Cancelling after current page")

		# Track processing time
		page_start_time = time.time()
		logger.info(f"   📄 [Job {job_id}] Processing page {idx}/{len(urls_to_process)}: {url}")

		# Calculate enhanced metrics
		estimated_time = calculate_estimated_time_remaining(
			pages_completed=results['pages_stored'],
			pages_queued=len(urls_to_process) - results['pages_processed'],
			processing_times=pipeline_instance.page_processing_times,
		)
		processing_rate = calculate_processing_rate(pipeline_instance.page_processing_times)

		# Emit progress before processing
		await pipeline_instance.progress_observer.on_progress(ExplorationProgress(
			job_id=job_id,
			status="running",
			current_page=url,
			pages_completed=results['pages_stored'],
			pages_queued=len(urls_to_process) - results['pages_processed'],
			pages_failed=results['pages_failed'],
			links_discovered=len(links),
			external_links_detected=results['external_links_detected'],
			estimated_time_remaining=estimated_time,
			processing_rate=processing_rate,
			recent_pages=pipeline_instance.recent_completed_pages.copy(),
		))

		# Process page
		process_result = await pipeline_instance.process_url(url)
		process_result['job_id'] = job_id
		results['results'].append(process_result)
		results['pages_processed'] += 1

		# Track processing time
		page_processing_time = time.time() - page_start_time
		pipeline_instance.page_processing_times.append(page_processing_time)
		# Keep only last 20 processing times for rate calculation
		if len(pipeline_instance.page_processing_times) > 20:
			pipeline_instance.page_processing_times = pipeline_instance.page_processing_times[-20:]

		if process_result.get('success'):
			results['pages_stored'] += 1

			# Track recent completed pages with titles
			page_title = process_result.get('content', {}).get('title', url)
			pipeline_instance.recent_completed_pages.append({
				'url': url,
				'title': page_title,
				'completed_at': time.time(),
			})
			# Keep only last N pages
			if len(pipeline_instance.recent_completed_pages) > pipeline_instance.max_recent_pages:
				pipeline_instance.recent_completed_pages = pipeline_instance.recent_completed_pages[-pipeline_instance.max_recent_pages:]

			logger.info(f"   ✅ [Job {job_id}] Page {idx} completed: {page_title[:60]}... ({page_processing_time:.2f}s)")
			await pipeline_instance.progress_observer.on_page_completed(url, process_result)

			# Discover and store links from this page
			try:
				logger.debug(f"      🔍 Discovering links from: {url}")
				page_links = await pipeline_instance.exploration_engine.discover_links(url)
				logger.debug(f"      📊 Found {len(page_links)} links on this page")
				new_links_added = 0
				external_links_found = 0
				for link in page_links:
					link_url = link.get('href', '') or link.get('url', '')
					is_internal = link.get('internal', True)

					if link_url:
						# Store all links (internal and external) for graph representation
						try:
							await pipeline_instance.storage.store_link(url, link_url, {
								'anchor_text': link.get('text', ''),
								'link_type': 'internal' if is_internal else 'external',
							})
						except Exception as e:
							logger.error(f"Failed to store link {url} -> {link_url}: {e}")

						# CRITICAL: External links are detected and stored, but NOT added to exploration queue
						if not is_internal:
							results['external_links_detected'] += 1
							external_links_found += 1
							await pipeline_instance.progress_observer.on_external_link_detected(url, link_url)
							logger.debug(f"         🔗 External: {link_url}")
						elif link_url not in processed_urls and link_url not in urls_to_process:
							# Apply path filtering before adding to queue (using helper function)
							if should_explore_url(link_url, pipeline_instance.include_paths, pipeline_instance.exclude_paths):
								urls_to_process.append(link_url)
								new_links_added += 1
							else:
								logger.debug(f"         ⏭️  Filtered: {link_url}")
				if new_links_added > 0 or external_links_found > 0:
					logger.info(f"      📈 Links: {new_links_added} new internal, {external_links_found} external")
			except Exception as e:
				logger.error(f"      ❌ Failed to discover links from {url}: {e}", exc_info=True)
				await pipeline_instance.progress_observer.on_error(url, str(e))
		else:
			results['pages_failed'] += 1
			results['errors'].append(process_result)
			error_msg = process_result.get('error', 'Unknown error')
			error_type = process_result.get('error_type', 'unknown')
			logger.warning(f"   ❌ [Job {job_id}] Page {idx} failed ({error_type}): {error_msg}")
			await pipeline_instance.progress_observer.on_error(url, error_msg)

		# Check if cancelling after current page
		if pipeline_instance.job_status == "cancelling":
			pipeline_instance.job_status = "cancelled"
			logger.info(f"Job {job_id} cancelled after processing current page")
			break
