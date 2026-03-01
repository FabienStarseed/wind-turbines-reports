"""
tile.py — Image tiling utility for BDDA
Splits large DJI P1 images (45MP) into overlapping tiles for AI processing.

Strategy: DTU dataset approach — 1024×1024 tiles with 20% overlap.
A 45MP image (~8192×5460) produces ~70 tiles at 1024px with 20% overlap.
"""

import base64
import io
from pathlib import Path
from typing import List, Tuple, Optional

try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


def tile_image_cv2(
    image_path: Path,
    tile_size: int = 1024,
    overlap: float = 0.2,
    max_tiles: int = 50,
) -> Tuple[List, List[Tuple[int, int, int, int]]]:
    """
    Tile an image using OpenCV. Returns (tiles_as_numpy, coords).
    coords: list of (x, y, w, h) for each tile.
    """
    img = cv2.imread(str(image_path))
    if img is None:
        raise ValueError(f"Could not read image: {image_path}")

    h, w = img.shape[:2]
    stride = int(tile_size * (1 - overlap))
    tiles, coords = [], []

    for y in range(0, max(1, h - tile_size + 1), stride):
        for x in range(0, max(1, w - tile_size + 1), stride):
            tile = img[y:y + tile_size, x:x + tile_size]
            tiles.append(tile)
            coords.append((x, y, tile_size, tile_size))
            if len(tiles) >= max_tiles:
                return tiles, coords

    # Handle right/bottom edges
    if h > tile_size:
        y_last = h - tile_size
        for x in range(0, max(1, w - tile_size + 1), stride):
            if (x, y_last, tile_size, tile_size) not in coords:
                tile = img[y_last:y_last + tile_size, x:x + tile_size]
                tiles.append(tile)
                coords.append((x, y_last, tile_size, tile_size))
                if len(tiles) >= max_tiles:
                    return tiles, coords

    return tiles, coords


def tile_image_pil(
    image_path: Path,
    tile_size: int = 1024,
    overlap: float = 0.2,
    max_tiles: int = 50,
) -> Tuple[List, List[Tuple[int, int, int, int]]]:
    """
    Tile an image using Pillow. Returns (tiles_as_PIL_images, coords).
    """
    img = Image.open(image_path)
    w, h = img.size
    stride = int(tile_size * (1 - overlap))
    tiles, coords = [], []

    for y in range(0, max(1, h - tile_size + 1), stride):
        for x in range(0, max(1, w - tile_size + 1), stride):
            tile = img.crop((x, y, x + tile_size, y + tile_size))
            tiles.append(tile)
            coords.append((x, y, tile_size, tile_size))
            if len(tiles) >= max_tiles:
                return tiles, coords

    return tiles, coords


def tile_to_base64(tile, format: str = "JPEG", quality: int = 85) -> str:
    """
    Convert a tile (PIL Image or numpy array) to base64 JPEG string.
    Used for API calls (Kimi, Gemini) that accept base64 images.
    """
    if HAS_PIL:
        if not isinstance(tile, Image.Image):
            # numpy array from cv2 (BGR) → PIL (RGB)
            tile = Image.fromarray(cv2.cvtColor(tile, cv2.COLOR_BGR2RGB))
        buf = io.BytesIO()
        tile.save(buf, format=format, quality=quality)
        return base64.b64encode(buf.getvalue()).decode("utf-8")
    elif HAS_CV2:
        # Encode directly with cv2
        _, buffer = cv2.imencode(".jpg", tile, [cv2.IMWRITE_JPEG_QUALITY, quality])
        return base64.b64encode(buffer).decode("utf-8")
    else:
        raise RuntimeError("Neither Pillow nor OpenCV is available for image encoding")


def get_image_dimensions(image_path: Path) -> Tuple[int, int]:
    """Return (width, height) of an image."""
    if HAS_PIL:
        with Image.open(image_path) as img:
            return img.size
    elif HAS_CV2:
        img = cv2.imread(str(image_path))
        h, w = img.shape[:2]
        return w, h
    else:
        raise RuntimeError("Neither Pillow nor OpenCV is available")


def tile_image(
    image_path: Path,
    tile_size: int = 1024,
    overlap: float = 0.2,
    max_tiles: int = 50,
    as_base64: bool = False,
) -> Tuple[List, List[Tuple[int, int, int, int]]]:
    """
    Primary tiling function. Auto-selects Pillow or OpenCV.

    Args:
        image_path: Path to image file
        tile_size: Tile dimension in pixels (square)
        overlap: Fraction of overlap between adjacent tiles (0.2 = 20%)
        max_tiles: Maximum tiles to generate (prevents memory issues on huge images)
        as_base64: If True, return tiles as base64 strings instead of objects

    Returns:
        (tiles, coords) where tiles is list of PIL/numpy/base64 and
        coords is list of (x, y, w, h) tuples
    """
    image_path = Path(image_path)

    if HAS_PIL:
        tiles, coords = tile_image_pil(image_path, tile_size, overlap, max_tiles)
    elif HAS_CV2:
        tiles, coords = tile_image_cv2(image_path, tile_size, overlap, max_tiles)
    else:
        raise RuntimeError("Install Pillow or OpenCV: pip install pillow opencv-python-headless")

    if as_base64:
        tiles = [tile_to_base64(t) for t in tiles]

    return tiles, coords


def select_representative_tiles(
    tiles: List,
    coords: List[Tuple],
    image_width: int,
    image_height: int,
    n: int = 8,
) -> Tuple[List, List[Tuple]]:
    """
    Select n representative tiles spread across the image.
    Used for quick triage when we don't want to process all tiles.

    Strategy: uniform sampling across tile list (covers full blade span).
    """
    if len(tiles) <= n:
        return tiles, coords

    step = len(tiles) // n
    indices = [i * step for i in range(n)]
    return [tiles[i] for i in indices], [coords[i] for i in indices]


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python tile.py <image_path>")
        sys.exit(1)

    path = Path(sys.argv[1])
    print(f"Tiling: {path}")

    dims = get_image_dimensions(path)
    print(f"Dimensions: {dims[0]}×{dims[1]} px")

    tiles, coords = tile_image(path)
    print(f"Generated {len(tiles)} tiles")
    print(f"First tile coords: {coords[0]}")
    print(f"Last tile coords: {coords[-1]}")

    if tiles:
        b64 = tile_to_base64(tiles[0])
        print(f"Base64 sample (first 60 chars): {b64[:60]}...")
