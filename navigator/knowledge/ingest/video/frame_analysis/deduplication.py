"""
Frame deduplication using SSIM and pixel difference.

Computes structural similarity (SSIM) and pixel differences between frames
to identify duplicates and detect visual changes.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def compute_ssim(frame1_path: Path, frame2_path: Path, ssim_threshold: float = 0.96) -> float:
	"""
	Compute Structural Similarity Index (SSIM) between two frames.
	
	SSIM measures perceptual similarity between images (0.0 to 1.0).
	Higher SSIM (>0.98) means frames are virtually identical.
	
	Args:
		frame1_path: Path to first frame
		frame2_path: Path to second frame
		ssim_threshold: SSIM threshold for duplicate detection
	
	Returns:
		SSIM value between 0.0 and 1.0
	"""
	try:
		import cv2
		from skimage.metrics import structural_similarity as ssim
	except ImportError:
		logger.warning("OpenCV or scikit-image not available, skipping SSIM deduplication")
		return 0.5  # Default: assume different if libraries unavailable

	try:
		# Load frames as grayscale
		img1 = cv2.imread(str(frame1_path), cv2.IMREAD_GRAYSCALE)
		img2 = cv2.imread(str(frame2_path), cv2.IMREAD_GRAYSCALE)

		if img1 is None or img2 is None:
			logger.debug(f"Failed to load frames for SSIM: {frame1_path}, {frame2_path}")
			return 0.5

		# Resize to same dimensions if needed
		if img1.shape != img2.shape:
			img2 = cv2.resize(img2, (img1.shape[1], img1.shape[0]))

		# Compute SSIM (returns a float value)
		ssim_value = ssim(img1, img2)
		# ssim returns a float, but type checker may see it as tuple, so ensure float
		return float(ssim_value) if isinstance(ssim_value, (int, float)) else 0.5

	except Exception as e:
		logger.debug(f"SSIM computation failed: {e}")
		return 0.5  # Default: assume different on error


def compute_frame_diff(frame1_path: Path, frame2_path: Path) -> float:
	"""
	Compute pixel difference percentage between two frames.
	
	Used for action-triggered frame sampling (detects UI changes).
	
	Args:
		frame1_path: Path to first frame
		frame2_path: Path to second frame
	
	Returns:
		Percentage difference (0.0 to 100.0)
	"""
	try:
		import cv2
		import numpy as np
	except ImportError:
		logger.warning("OpenCV not available, skipping frame diff computation")
		return 50.0  # Default: assume different if library unavailable

	try:
		# Load frames as grayscale
		img1 = cv2.imread(str(frame1_path), cv2.IMREAD_GRAYSCALE)
		img2 = cv2.imread(str(frame2_path), cv2.IMREAD_GRAYSCALE)

		if img1 is None or img2 is None:
			logger.debug(f"Failed to load frames for diff: {frame1_path}, {frame2_path}")
			return 50.0

		# Resize to same dimensions if needed
		if img1.shape != img2.shape:
			img2 = cv2.resize(img2, (img1.shape[1], img1.shape[0]))

		# Compute absolute difference
		diff = cv2.absdiff(img1, img2)

		# Calculate percentage of different pixels
		total_pixels = diff.shape[0] * diff.shape[1]
		changed_pixels = np.count_nonzero(diff > 30)  # Threshold for "changed" pixel
		diff_percentage = (changed_pixels / total_pixels) * 100.0

		return float(diff_percentage)

	except Exception as e:
		logger.debug(f"Frame diff computation failed: {e}")
		return 50.0  # Default: assume different on error
