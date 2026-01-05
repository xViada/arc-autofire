"""Hash-based image detection utilities."""

import sys
from pathlib import Path
from typing import Optional, Tuple
import cv2
import numpy as np
from PIL import ImageGrab, Image
import imagehash


class HashDetector:
    """Perceptual hash-based image detector."""
    
    def __init__(self, hash_threshold: int = 5, hash_size: int = 16):
        """
        Initialize the hash detector.
        
        Args:
            hash_threshold: Hamming distance threshold (0-10 recommended)
            hash_size: Hash size (8, 16, or 32) - larger = more precise
        """
        self.hash_threshold = hash_threshold
        self.hash_size = hash_size
    
    def calculate_hash(self, img_array: np.ndarray) -> Optional[imagehash.ImageHash]:
        """
        Calculate perceptual hash from numpy array.
        
        Args:
            img_array: Grayscale or BGR image array
            
        Returns:
            ImageHash object or None if error
        """
        try:
            pil_img = self._numpy_to_pil(img_array)
            phash = imagehash.phash(pil_img, hash_size=self.hash_size)
            return phash
        except Exception as e:
            print(f"Hash calculation error: {e}", file=sys.stderr)
            return None

    def _numpy_to_pil(self, img_array: np.ndarray) -> Image.Image:
        """Convert numpy array to PIL Image."""
        if len(img_array.shape) == 2:  # Grayscale
            return Image.fromarray(img_array)
        return Image.fromarray(cv2.cvtColor(img_array, cv2.COLOR_BGR2RGB))
    
    def capture_region(self, region: Tuple[int, int, int, int]) -> Optional[np.ndarray]:
        """
        Capture a specific region from screen.
        
        Args:
            region: Tuple (left, top, right, bottom)
            
        Returns:
            Grayscale image array or None if error
        """
        try:
            img = ImageGrab.grab(bbox=region)
            img_array = np.array(img)
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            return gray
        except Exception as e:
            print(f"Region capture error: {e}", file=sys.stderr)
            return None
    
    def detect_hash(
        self,
        region_img: Optional[np.ndarray],
        target_hash: Optional[imagehash.ImageHash],
        debug: bool = False,
    ) -> Tuple[bool, int]:
        """
        Detect using perceptual hash comparison.
        
        Args:
            region_img: Captured region image
            target_hash: Template hash to compare against
            debug: Enable debug output
            
        Returns:
            Tuple (detected: bool, distance: int)
        """
        MAX_DISTANCE = 999
        
        if target_hash is None or region_img is None:
            return False, MAX_DISTANCE

        try:
            current_hash = self.calculate_hash(region_img)
            if current_hash is None:
                return False, MAX_DISTANCE

            distance = target_hash - current_hash
            detected = distance <= self.hash_threshold

            return detected, distance

        except Exception as e:
            if debug:
                print(f"Detection error: {e}", file=sys.stderr)
            return False, MAX_DISTANCE
    
    def load_image(self, image_path: Path) -> Optional[np.ndarray]:
        """
        Load a grayscale template image.
        
        Args:
            image_path: Path to image file
            
        Returns:
            Grayscale image array or None if file doesn't exist
        """
        if not image_path.exists():
            return None

        return cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)

