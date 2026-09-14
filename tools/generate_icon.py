from pathlib import Path

from PIL import Image, ImageDraw


OUT = Path("assets/app.ico")
OUT.parent.mkdir(parents=True, exist_ok=True)
SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]

# Draw once at high resolution. Pillow creates the requested ICO sub-images.
size = 1024
image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
draw = ImageDraw.Draw(image)

margin = int(size * 0.08)
radius = int(size * 0.22)
draw.rounded_rectangle(
    (margin, margin, size - margin, size - margin),
    radius=radius,
    fill=(25, 118, 210, 255),
)

cx = size * 0.5
shaft_w = size * 0.17
top = size * 0.22
body_bottom = size * 0.53
arrow_bottom = size * 0.75
arrow_half = size * 0.24
draw.polygon(
    [
        (cx - shaft_w / 2, top),
        (cx + shaft_w / 2, top),
        (cx + shaft_w / 2, body_bottom),
        (cx + arrow_half, body_bottom),
        (cx, arrow_bottom),
        (cx - arrow_half, body_bottom),
        (cx - shaft_w / 2, body_bottom),
    ],
    fill=(255, 255, 255, 255),
)
draw.rounded_rectangle(
    (size * 0.28, size * 0.79, size * 0.72, size * 0.86),
    radius=int(size * 0.025),
    fill=(255, 255, 255, 255),
)

image.save(OUT, format="ICO", sizes=[(s, s) for s in SIZES])
print(f"Generated {OUT}")
