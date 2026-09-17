"""Validate uploaded pictures and normalize them before passing them to Gemma."""
import io

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_IMAGE_BYTES = 8 * 1024 * 1024


def normalize_image(blob: bytes) -> bytes:
    if len(blob) > MAX_IMAGE_BYTES:
        raise ValueError("Images must be 8 MB or smaller")
    try:
        with Image.open(io.BytesIO(blob)) as image:
            if image.format not in {"JPEG", "PNG", "WEBP"}:
                raise ValueError("Use a JPEG, PNG, or WebP image")
            if image.width * image.height > 16_000_000:
                raise ValueError("Images must contain at most 16 million pixels")
            image = ImageOps.exif_transpose(image).convert("RGBA")
            background = Image.new("RGBA", image.size, "white")
            image = Image.alpha_composite(background, image).convert("RGB")
            image.thumbnail((1536, 1536))
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=95)
            return output.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("Cannot read this image") from exc
