"""Unit tests for ImageService (compression, resource URLs, and SQLite sync)."""

import io
import pytest
from PIL import Image
from PySide6.QtGui import QImage
from src.database.connection import DatabaseManager
from src.database.migrations import init_database
from src.repositories.image_repository import ImageRepository
from src.repositories.scratchpad_repository import ScratchpadRepository
from src.services.image_service import ImageService


@pytest.fixture
def image_service(tmp_path):
    db_file = tmp_path / "test_images.db"
    manager = DatabaseManager(db_file)
    init_database(manager)
    repo = ImageRepository(manager)
    service = ImageService(repo)
    yield service
    manager.close()


def test_compress_bytes_to_jpeg(image_service):
    # Create raw PNG image in memory with alpha channel
    img = Image.new("RGBA", (200, 100), color=(255, 0, 0, 128))
    raw_buffer = io.BytesIO()
    img.save(raw_buffer, format="PNG")
    raw_bytes = raw_buffer.getvalue()

    jpeg_bytes = image_service.compress_bytes_to_jpeg(raw_bytes, quality=85)
    assert len(jpeg_bytes) > 0
    # Verify resulting output is a valid JPEG
    with Image.open(io.BytesIO(jpeg_bytes)) as result_img:
        assert result_img.format == "JPEG"
        assert result_img.size == (200, 100)


def test_compress_qimage_to_jpeg(qapp, image_service):
    # Create a QImage
    qimg = QImage(150, 80, QImage.Format_ARGB32)
    qimg.fill(0xFF00FF00)  # Solid green

    jpeg_bytes = image_service.compress_qimage_to_jpeg(qimg, quality=85)
    assert len(jpeg_bytes) > 0

    with Image.open(io.BytesIO(jpeg_bytes)) as result_img:
        assert result_img.format == "JPEG"
        assert result_img.size == (150, 80)


def test_create_embedded_image(qapp, image_service):
    qimg = QImage(100, 50, QImage.Format_RGB32)
    qimg.fill(0xFF0000FF)

    name, url, data, loaded_qimg = image_service.create_embedded_image(qimg)
    assert name.endswith(".jpg")
    assert url == f"image://local/{name}"
    assert len(data) > 0
    assert not loaded_qimg.isNull()


def test_extract_referenced_image_names(image_service):
    html = """
    <p>Some text</p>
    <img src="image://local/snip_1.jpg" alt="test" />
    <p>More notes</p>
    <img src='image://local/snip_2.jpg'>
    """
    names = image_service.extract_referenced_image_names(html)
    assert names == {"snip_1.jpg", "snip_2.jpg"}


def test_sync_scratchpad_images(image_service, tmp_path):
    manager = image_service.repo.db
    scratch_repo = ScratchpadRepository(manager)
    sid = scratch_repo.create(ticket_number="INC-999")

    # In-memory images simulating unsaved clipboard captures
    cache = {
        "pic1.jpg": b"fake_data_1",
        "pic2.jpg": b"fake_data_2",
    }

    # Document references both pic1 and pic2
    html_both = '<p><img src="image://local/pic1.jpg"><img src="image://local/pic2.jpg"></p>'
    image_service.sync_scratchpad_images(sid, html_both, cache)

    saved = image_service.repo.get_images_for_scratchpad(sid)
    assert "pic1.jpg" in saved
    assert "pic2.jpg" in saved

    # Now technician deletes pic2 from the editor
    html_only_pic1 = '<p><img src="image://local/pic1.jpg"></p>'
    image_service.sync_scratchpad_images(sid, html_only_pic1, {})

    updated_saved = image_service.repo.get_images_for_scratchpad(sid)
    assert "pic1.jpg" in updated_saved
    assert "pic2.jpg" not in updated_saved  # Purged to keep db lean
