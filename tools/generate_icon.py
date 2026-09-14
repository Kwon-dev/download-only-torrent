from pathlib import Path

from PIL import Image, ImageDraw


OUT = Path("assets/app.ico")
OUT.parent.mkdir(parents=True, exist_ok=True)

sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
images = []

for size in sizes:
    scale = 4
    canvas = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    s = size * scale
    margin = int(s * 0.08)
    radius = int(s * 0.22)
    draw.rounded_rectangle(
        (margin, margin, s - margin, s - margin),
        radius=radius,
        fill=(25, 118, 210, 255),
    )

    cx = s * 0.5
    shaft_w = s * 0.17
    top = s * 0.22
    body_bottom = s * 0.53
    arrow_bottom = s * 0.75
    arrow_half = s * 0.24
    points = [
        (cx - shaft_w / 2, top),
        (cx + shaft_w / 2, top),
        (cx + shaft_w / 2, body_bottom),
        (cx + arrow_half, body_bottom),
        (cx, arrow_bottom),
        (cx - arrow_half, body_bottom),
        (cx - shaft_w / 2, body_bottom),
    ]
    draw.polygon(points, fill=(255, 255, 255, 255))
    draw.rounded_rectangle(
        (s * 0.28, s * 0.79, s * 0.72, s * 0.86),
        radius=int(s * 0.025),
        fill=(255, 255, 255, 255),
    )

    image = canvas.resize((size, size), Image.Resampling.LANCZOS)
    images.append(image)

images[-1].save(
    OUT,
    format="ICO",
    sizes=[(size, size) for size in sizes],
    append_images=images[:-1],
)
print(f"Generated {OUT}")
