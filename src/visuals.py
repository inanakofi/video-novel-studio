"""Local image preparation and understated title/end cards."""
from pathlib import Path
import textwrap

from PIL import Image, ImageDraw, ImageFont, ImageOps


def font(size: int):
    for name in ('C:/Windows/Fonts/arial.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', '/System/Library/Fonts/Supplemental/Arial.ttf'):
        if Path(name).is_file():
            return ImageFont.truetype(name, size)
    return ImageFont.load_default(size=size)


def prepare_image(source: Path, output: Path, size: tuple[int, int], *, foreground=False):
    with Image.open(source) as image:
        image = ImageOps.exif_transpose(image).convert('RGBA' if foreground else 'RGB')
        if foreground:
            fitted = ImageOps.contain(image, size, Image.Resampling.LANCZOS)
            canvas = Image.new('RGBA', size)
            canvas.alpha_composite(fitted, ((size[0] - fitted.width) // 2, (size[1] - fitted.height) // 2))
        else:
            canvas = ImageOps.fit(image, size, Image.Resampling.LANCZOS)
        canvas.save(output)


def card(text: str, output: Path, size: tuple[int, int], *, kicker='VIDEO NOVEL STUDIO',
         background='#111B2D', accent='#61D7BB', text_color='#F5F3EE'):
    width, height = size
    image = Image.new('RGB', size, background)
    base = image.getpixel((0, 0))
    draw = ImageDraw.Draw(image)
    for y in range(height):
        draw.line((0, y, width, y), fill=tuple(min(255, v + int(10 * y / height)) for v in base))
    draw.line((width * .12, height * .33, width * .3, height * .33), fill=accent, width=max(2, width // 200))
    draw.text((width * .12, height * .37), kicker, font=font(max(10, width // 35)), fill=accent)
    wrapped = '\n'.join(textwrap.wrap(text, width=22))
    draw.multiline_text((width * .12, height * .44), wrapped, font=font(max(18, width // 16)), fill=text_color, spacing=width // 40)
    image.save(output)
