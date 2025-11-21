import base64
from pathlib import Path
from typing import Any, Dict, List

from PIL import Image, ImageDraw, ImageFont

from .config import OUT_DIR


def image_to_data_url(path: Path) -> str:
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:image/png;base64,{b64}"


def draw_ids_on_image(
    screenshot_path: Path,
    elements: List[Dict[str, Any]],
    draw_only_selected: bool = True,
) -> Path:
    """Overlay numeric ids on the screenshot for selected elements."""
    img = Image.open(screenshot_path).convert("RGB")
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    for elem in elements:
        if draw_only_selected and not elem.get("selected_for_agent", False):
            continue

        box = elem["bounding_box"]
        elem_id = elem["id"]

        x = int(box["x"])
        y = int(box["y"])
        w = int(box["width"])
        h = int(box["height"])

        draw.rectangle([x, y, x + w, y + h], outline=(255, 0, 0), width=2)

        label = elem_id
        text_pos = (x + 2, y + 2)
        draw.text(text_pos, label, fill=(255, 0, 0), font=font)

    annotated_path = OUT_DIR / "annotated_topk.png"
    img.save(annotated_path)
    return annotated_path

