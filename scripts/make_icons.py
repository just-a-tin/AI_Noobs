"""Generate the extension's shield icons. Run once; output is committed."""

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parents[1] / "extension" / "assets" / "icons"
NAVY = (15, 23, 42, 255)
SKY = (56, 189, 248, 255)


def shield(size: int) -> Image.Image:
    scale = 8
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.22), fill=NAVY)

    m = s * 0.24
    top, bottom = m, s - m
    width = (s - 2 * m) * 0.9
    cx = s / 2
    d.polygon(
        [
            (cx - width / 2, top),
            (cx + width / 2, top),
            (cx + width / 2, top + (bottom - top) * 0.5),
            (cx, bottom),
            (cx - width / 2, top + (bottom - top) * 0.5),
        ],
        fill=SKY,
    )

    # Checkmark, only legible at the larger sizes.
    if size >= 48:
        d.line(
            [
                (cx - width * 0.22, top + (bottom - top) * 0.42),
                (cx - width * 0.04, top + (bottom - top) * 0.58),
                (cx + width * 0.26, top + (bottom - top) * 0.22),
            ],
            fill=NAVY,
            width=int(s * 0.055),
            joint="curve",
        )

    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for size in (16, 48, 128):
        path = OUT / f"icon{size}.png"
        shield(size).save(path)
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
