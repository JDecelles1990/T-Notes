"""Image processing service for compressing and managing embedded screenshots."""

import io
import re
import uuid
from typing import Optional, Set, Tuple, Union
from PIL import Image
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QUrl
from PySide6.QtGui import QImage, QTextDocument
from src.core.constants import JPEG_COMPRESSION_QUALITY, LOCAL_IMAGE_URL_PREFIX
from src.repositories.image_repository import ImageRepository


class ImageService:
    """Handles image conversion, JPEG compression (82–85 quality), and resource registration."""

    # Regex to extract image names from <img src="image://local/<name>">
    IMG_SRC_PATTERN = re.compile(r'src=["\']image://local/([^"\'>\s]+)["\']', re.IGNORECASE)

    def __init__(self, image_repo: ImageRepository):
        self.repo = image_repo

    def compress_qimage_to_jpeg(self, qimage: QImage, quality: int = JPEG_COMPRESSION_QUALITY) -> bytes:
        """Compresses a QImage to JPEG bytes using Qt's QBuffer."""
        # Convert formats that don't directly write to JPEG cleanly (like ARGB with transparency)
        if qimage.hasAlphaChannel():
            # Create a white background image and paint the alpha onto it
            converted = QImage(qimage.size(), QImage.Format_RGB32)
            converted.fill(0xFFFFFF)
            from PySide6.QtGui import QPainter
            painter = QPainter(converted)
            painter.drawImage(0, 0, qimage)
            painter.end()
        else:
            converted = qimage.convertToFormat(QImage.Format_RGB32)

        byte_array = QByteArray()
        buffer = QBuffer(byte_array)
        buffer.open(QIODevice.WriteOnly)
        converted.save(buffer, "JPEG", quality)
        return bytes(byte_array.data())

    def compress_bytes_to_jpeg(self, image_bytes: bytes, quality: int = JPEG_COMPRESSION_QUALITY) -> bytes:
        """Compresses arbitrary image bytes to JPEG using Pillow."""
        with Image.open(io.BytesIO(image_bytes)) as pil_img:
            if pil_img.mode in ("RGBA", "LA", "P"):
                # Convert with white background
                rgb_img = Image.new("RGB", pil_img.size, (255, 255, 255))
                if pil_img.mode == "P":
                    pil_img = pil_img.convert("RGBA")
                rgb_img.paste(pil_img, mask=pil_img.split()[-1] if "A" in pil_img.mode else None)
            elif pil_img.mode != "RGB":
                rgb_img = pil_img.convert("RGB")
            else:
                rgb_img = pil_img

            output = io.BytesIO()
            rgb_img.save(output, format="JPEG", quality=quality, optimize=True)
            return output.getvalue()

    def create_embedded_image(
        self,
        source: Union[QImage, bytes],
        quality: int = JPEG_COMPRESSION_QUALITY
    ) -> Tuple[str, str, bytes, QImage]:
        """
        Compresses an image, generates a unique name, and creates its resource URL.
        Returns: (image_name, resource_url, jpeg_bytes, qimage)
        """
        image_name = f"{uuid.uuid4().hex}.jpg"
        resource_url = f"{LOCAL_IMAGE_URL_PREFIX}{image_name}"

        if isinstance(source, QImage):
            jpeg_bytes = self.compress_qimage_to_jpeg(source, quality)
        else:
            jpeg_bytes = self.compress_bytes_to_jpeg(source, quality)

        # Load back into QImage for QTextDocument resource registration
        qimage = QImage()
        qimage.loadFromData(jpeg_bytes, "JPEG")
        return image_name, resource_url, jpeg_bytes, qimage

    def register_image_in_document(
        self,
        document: QTextDocument,
        image_name: str,
        qimage: QImage
    ) -> str:
        """Registers a QImage into the document's resource cache with its local URL."""
        url_str = f"{LOCAL_IMAGE_URL_PREFIX}{image_name}"
        document.addResource(QTextDocument.ImageResource, QUrl(url_str), qimage)
        return url_str

    def load_scratchpad_images_into_document(
        self,
        scratchpad_id: int,
        document: QTextDocument
    ) -> None:
        """Fetches all stored images for a scratchpad and registers them in the document."""
        images = self.repo.get_images_for_scratchpad(scratchpad_id)
        for image_name, image_data in images.items():
            qimage = QImage()
            if qimage.loadFromData(image_data, "JPEG"):
                self.register_image_in_document(document, image_name, qimage)

    def extract_referenced_image_names(self, html_content: str) -> Set[str]:
        """Scans HTML content and returns the set of all referenced image_name strings."""
        if not html_content:
            return set()
        matches = self.IMG_SRC_PATTERN.findall(html_content)
        return set(matches)

    def sync_scratchpad_images(
        self,
        scratchpad_id: int,
        html_content: str,
        in_memory_cache: dict[str, bytes]
    ) -> None:
        """
        Persists newly added images and cleans up deleted images from the database.
        """
        active_names = self.extract_referenced_image_names(html_content)

        # Save any in-memory images that appear in active_names
        for name in active_names:
            if name in in_memory_cache:
                self.repo.save_image(scratchpad_id, name, in_memory_cache[name])

        # Delete any images in DB that were removed from the document
        self.repo.delete_unreferenced_images(scratchpad_id, active_names)
