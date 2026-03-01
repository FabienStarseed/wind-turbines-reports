"""
ingest.py — DJI inspection folder parser for BDDA
Reads DJI P1 mission folders and extracts blade/zone/position metadata.

DJI folder naming: DJI_{datetime}_{seq}_{type}-{cam}-{blade}-{zone}-{position}
Example: DJI_202508011544_069_C-N-B-TE-N
  type: C=Camera mission, P=Panorama/app
  cam:  N=Normal
  blade: A, B, C (the three rotor blades)
  zone:  LE, TE, PS, SS (leading/trailing edge, pressure/suction side)
  position: N=Normal/Mid, T=Tip, R=Root
"""

import os
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict


# Position suffix mapping
POSITION_MAP = {
    "N": "Mid",
    "T": "Tip",
    "R": "Root",
    "M": "Mid",
}

VALID_BLADES = {"A", "B", "C"}
VALID_ZONES = {"LE", "TE", "PS", "SS"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}


@dataclass
class MissionFolder:
    folder_path: Path
    folder_name: str
    blade: str          # A, B, or C
    zone: str           # LE, TE, PS, SS
    position: str       # Root, Mid, Tip
    sequence: int       # Mission sequence number
    datetime_str: str   # Raw datetime from folder name
    image_paths: List = field(default_factory=list)
    is_valid: bool = True


@dataclass
class IngestResult:
    turbine_id: str
    turbine_path: Path
    total_folders: int
    valid_mission_folders: int
    total_images: int
    missions: List  # list of MissionFolder
    skipped_folders: List  # folders that didn't match the pattern


def parse_folder_name(folder_name: str) -> Optional[Dict]:
    """
    Parse a DJI mission folder name into its components.
    Returns None if folder doesn't match expected pattern.

    Pattern: DJI_{datetime}_{seq}_{type}-{cam}-{blade}-{zone}-{position}
    """
    # Match the main DJI camera mission pattern
    pattern = r"DJI_(\d{12})_(\d+)_C-[A-Z]-([ABC])-(LE|TE|PS|SS)-([NTRM])"
    match = re.match(pattern, folder_name)

    if not match:
        return None

    datetime_str, seq_str, blade, zone, position_code = match.groups()

    return {
        "datetime_str": datetime_str,
        "sequence": int(seq_str),
        "blade": blade,
        "zone": zone,
        "position": POSITION_MAP.get(position_code, "Mid"),
    }


def get_images_in_folder(folder_path: Path) -> List[Path]:
    """Return all image files in a folder (non-recursive)."""
    images = []
    for f in sorted(folder_path.iterdir()):
        if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS:
            images.append(f)
    return images


def ingest_turbine_folder(turbine_path, turbine_id: str = None) -> IngestResult:
    """
    Scan a turbine inspection folder and parse all DJI mission subfolders.

    Args:
        turbine_path: Path to the top-level turbine folder (e.g., .../TW02/)
        turbine_id: Optional turbine ID override; if None, uses folder name

    Returns:
        IngestResult with all missions and images parsed
    """
    turbine_path = Path(turbine_path)
    if not turbine_path.exists():
        raise FileNotFoundError(f"Turbine folder not found: {turbine_path}")

    if turbine_id is None:
        turbine_id = turbine_path.name

    missions = []
    skipped = []
    total_images = 0

    for item in sorted(turbine_path.iterdir()):
        if not item.is_dir():
            continue

        parsed = parse_folder_name(item.name)

        if parsed is None:
            skipped.append(item.name)
            continue

        images = get_images_in_folder(item)
        total_images += len(images)

        mission = MissionFolder(
            folder_path=item,
            folder_name=item.name,
            blade=parsed["blade"],
            zone=parsed["zone"],
            position=parsed["position"],
            sequence=parsed["sequence"],
            datetime_str=parsed["datetime_str"],
            image_paths=images,
            is_valid=len(images) > 0,
        )
        missions.append(mission)

    return IngestResult(
        turbine_id=turbine_id,
        turbine_path=turbine_path,
        total_folders=len(list(turbine_path.iterdir())),
        valid_mission_folders=len(missions),
        total_images=total_images,
        missions=missions,
        skipped_folders=skipped,
    )


def get_all_images_flat(result: IngestResult) -> List[Dict]:
    """
    Flatten all mission images into a list of dicts with metadata attached.
    Each dict has: path, turbine_id, blade, zone, position, mission_folder.
    """
    images = []
    for mission in result.missions:
        for img_path in mission.image_paths:
            images.append({
                "path": img_path,
                "turbine_id": result.turbine_id,
                "blade": mission.blade,
                "zone": mission.zone,
                "position": mission.position,
                "mission_folder": mission.folder_name,
                "sequence": mission.sequence,
            })
    return images


def print_ingest_summary(result: IngestResult):
    """Print a readable summary of the ingest result."""
    print(f"\n{'='*60}")
    print(f"BDDA Ingest Summary: {result.turbine_id}")
    print(f"{'='*60}")
    print(f"Path:           {result.turbine_path}")
    print(f"Total folders:  {result.total_folders}")
    print(f"Mission folders: {result.valid_mission_folders}")
    print(f"Skipped folders: {len(result.skipped_folders)}")
    print(f"Total images:   {result.total_images}")

    # Group by blade
    print(f"\nImages by blade and zone:")
    by_blade = {}
    for m in result.missions:
        key = (m.blade, m.zone)
        by_blade.setdefault(key, 0)
        by_blade[key] += len(m.image_paths)

    for blade in ["A", "B", "C"]:
        for zone in ["LE", "TE", "PS", "SS"]:
            count = by_blade.get((blade, zone), 0)
            if count > 0:
                print(f"  Blade {blade} / {zone}: {count} images")

    if result.skipped_folders:
        print(f"\nSkipped (not standard DJI camera missions):")
        for f in result.skipped_folders:
            print(f"  - {f}")

    print(f"{'='*60}\n")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python ingest.py <turbine_folder_path> [turbine_id]")
        sys.exit(1)

    path = sys.argv[1]
    tid = sys.argv[2] if len(sys.argv) > 2 else None

    result = ingest_turbine_folder(path, tid)
    print_ingest_summary(result)
