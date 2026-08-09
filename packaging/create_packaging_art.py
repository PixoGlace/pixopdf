from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
BUILD_OUTPUT = ROOT / "build" / "packaging"
DMG_OUTPUT = ASSETS / "dmg"

NAVY = (23, 43, 77)
TEAL = (20, 184, 166)
AMBER = (245, 158, 11)
DARK = (15, 23, 42)
LIGHT = (248, 250, 252)
WHITE = (255, 255, 255)
MUTED = (100, 116, 139)


def font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        (
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
            if bold
            else "/System/Library/Fonts/Supplemental/Arial.ttf"
        ),
        (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            if bold
            else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        ),
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    ]
    for candidate in candidates:
        path = Path(candidate)
        if path.is_file():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def contained(source: Image.Image, size: tuple[int, int]) -> Image.Image:
    image = source.convert("RGBA")
    image.thumbnail(size, Image.Resampling.LANCZOS)
    return image


def paste_centered(
    canvas: Image.Image,
    source: Image.Image,
    center: tuple[int, int],
    size: tuple[int, int],
) -> None:
    image = contained(source, size)
    canvas.alpha_composite(
        image,
        (center[0] - image.width // 2, center[1] - image.height // 2),
    )


def application_icon() -> Image.Image:
    icon = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    logo = Image.open(ASSETS / "logo_white.png")
    paste_centered(icon, logo, (512, 512), (860, 860))
    return icon


def make_application_icons() -> None:
    icon = application_icon()
    icon.save(ASSETS / "PixoPDF.png", format="PNG", optimize=True)
    icon.save(
        ASSETS / "PixoPDF.ico",
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    icon.save(ASSETS / "PixoPDF.icns", format="ICNS")


def make_dmg_background() -> None:
    size = (660, 420)
    canvas = Image.new("RGBA", size, LIGHT + (255,))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((24, 20, 636, 398), radius=32, fill=WHITE, outline=(203, 213, 225))
    draw.rounded_rectangle((48, 150, 612, 350), radius=56, fill=(226, 248, 245))
    draw.ellipse((500, 24, 620, 144), fill=(214, 246, 242))
    draw.ellipse((26, 292, 126, 392), fill=(255, 238, 207))

    logo = Image.open(ASSETS / "logo_white.png")
    paste_centered(canvas, logo, (66, 66), (52, 60))
    draw.text((102, 50), "PixoPDF", fill=NAVY, font=font(24, bold=True))
    title = "Glissez PixoPDF vers Applications"
    title_font = font(25, bold=True)
    title_box = draw.textbbox((0, 0), title, font=title_font)
    draw.text(((size[0] - title_box[2]) / 2, 102), title, fill=NAVY, font=title_font)

    draw.rounded_rectangle((64, 180, 192, 326), radius=26, fill=WHITE, outline=(203, 213, 225))
    draw.rounded_rectangle((468, 180, 596, 326), radius=26, fill=WHITE, outline=(203, 213, 225))
    draw.line((226, 255, 434, 255), fill=NAVY, width=5)
    draw.polygon([(434, 255), (412, 241), (412, 269)], fill=NAVY)
    hint = "INSTALLER"
    hint_font = font(11, bold=True)
    hint_box = draw.textbbox((0, 0), hint, font=hint_font)
    draw.rounded_rectangle((278, 205, 382, 232), radius=14, fill=TEAL)
    draw.text(((size[0] - hint_box[2]) / 2, 211), hint, fill=DARK, font=hint_font)
    footer = "Local · Open source · GNU GPL v3"
    footer_font = font(11, bold=True)
    footer_box = draw.textbbox((0, 0), footer, font=footer_font)
    draw.text(((size[0] - footer_box[2]) / 2, 374), footer, fill=MUTED, font=footer_font)

    DMG_OUTPUT.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(DMG_OUTPUT / "pixopdf-dmg-background.png", optimize=True)


def make_windows_images() -> None:
    logo = Image.open(ASSETS / "logo_dark.png")
    wizard = Image.new("RGBA", (164, 314), NAVY + (255,))
    draw = ImageDraw.Draw(wizard)
    draw.rectangle((0, 210, 164, 314), fill=DARK)
    draw.polygon([(0, 244), (164, 190), (164, 314), (0, 314)], fill=(17, 94, 89))
    draw.ellipse((98, -34, 210, 78), fill=TEAL)
    draw.ellipse((-38, 236, 50, 324), fill=AMBER)
    paste_centered(wizard, logo, (82, 82), (74, 88))
    draw.text((23, 148), "PixoPDF", fill=WHITE, font=font(23, bold=True))
    draw.text((23, 184), "PDF tools, locally", fill=(203, 213, 225), font=font(12))
    wizard.convert("RGB").save(BUILD_OUTPUT / "windows-wizard.bmp")

    small = Image.new("RGBA", (55, 55), NAVY + (255,))
    paste_centered(small, logo, (27, 27), (38, 44))
    small.convert("RGB").save(BUILD_OUTPUT / "windows-small.bmp")


def make_linux_banner() -> None:
    banner = Image.new("RGBA", (720, 260), LIGHT + (255,))
    draw = ImageDraw.Draw(banner)
    draw.rounded_rectangle((22, 22, 698, 238), radius=26, fill=WHITE, outline=(203, 213, 225))
    draw.rectangle((22, 22, 698, 94), fill=NAVY)
    logo = Image.open(ASSETS / "logo_dark.png")
    paste_centered(banner, logo, (64, 58), (42, 50))
    draw.text((96, 43), "PixoPDF", fill=WHITE, font=font(24, bold=True))
    draw.text(
        (54, 124),
        "Organize, transform and protect PDFs locally",
        fill=NAVY,
        font=font(23, bold=True),
    )
    draw.text(
        (54, 164),
        "Desktop launcher, AppStream metadata and Debian package included.",
        fill=MUTED,
        font=font(16),
    )
    draw.rounded_rectangle((54, 198, 188, 226), radius=14, fill=TEAL)
    draw.text((76, 203), "Linux ready", fill=DARK, font=font(14, bold=True))
    banner.save(BUILD_OUTPUT / "linux-banner.png")


def main() -> None:
    BUILD_OUTPUT.mkdir(parents=True, exist_ok=True)
    DMG_OUTPUT.mkdir(parents=True, exist_ok=True)
    make_application_icons()
    make_dmg_background()
    make_windows_images()
    make_linux_banner()


if __name__ == "__main__":
    main()
