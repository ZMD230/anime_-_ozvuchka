import subprocess
from pathlib import Path

POS_MAP = {
    "bottom-left": "10:main_h-overlay_h-10",
    "bottom-right": "main_w-overlay_w-10:main_h-overlay_h-10",
    "top-left": "10:10",
    "top-right": "main_w-overlay_w-10:10",
    "center": "(main_w-overlay_w)/2:(main_h-overlay_h)/2",
}


def overlay_logo(video_path: str, logo_path: str, out_path: str, position: str = "bottom-left", scale: float = 0.15, margin: int = 10):
    """Overlay logo onto video using ffmpeg.
    - scale is relative width (logo width = video_width * scale)
    - position is one of POS_MAP keys
    """
    video_path = str(video_path)
    logo_path = str(logo_path)
    out_path = str(out_path)

    pos = POS_MAP.get(position, POS_MAP["bottom-left"])

    # Build filter: scale logo to (main_w*scale):-1 and overlay at pos
    # Using expression to compute scale based on main_w
    filter_complex = f"[1]scale=trunc(iw*{scale}):-1[logo];[0][logo]overlay={pos}"

    cmd = [
        "ffmpeg", "-y", "-i", video_path, "-i", logo_path,
        "-filter_complex", filter_complex,
        "-c:a", "copy", out_path
    ]
    subprocess.run(cmd, check=True)
    return out_path
