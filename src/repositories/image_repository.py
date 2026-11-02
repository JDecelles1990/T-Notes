"""Repository for scratchpad image binary storage."""

from typing import Dict, Optional, Set
from src.database.connection import DatabaseManager


class ImageRepository:
    """Manages SQLite BLOB operations for embedded scratchpad images."""

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def save_image(
        self,
        scratchpad_id: int,
        image_name: str,
        image_data: bytes,
        mime_type: str = "image/jpeg",
    ) -> int:
        """Stores or replaces a JPEG image BLOB associated with a scratchpad."""
        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO scratchpad_images (scratchpad_id, image_name, image_data, mime_type)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(scratchpad_id, image_name) DO UPDATE SET
                    image_data = excluded.image_data,
                    mime_type = excluded.mime_type
                """,
                (scratchpad_id, image_name, image_data, mime_type),
            )
            return cursor.lastrowid

    def get_images_for_scratchpad(self, scratchpad_id: int) -> Dict[str, bytes]:
        """Returns a mapping of {image_name: image_bytes} for the given scratchpad."""
        conn = self.db.get_connection()
        rows = conn.execute(
            """
            SELECT image_name, image_data
            FROM scratchpad_images
            WHERE scratchpad_id = ?
            """,
            (scratchpad_id,),
        ).fetchall()
        return {row["image_name"]: row["image_data"] for row in rows}

    def get_image(self, scratchpad_id: int, image_name: str) -> Optional[bytes]:
        """Retrieves raw image bytes for a single image."""
        conn = self.db.get_connection()
        row = conn.execute(
            """
            SELECT image_data
            FROM scratchpad_images
            WHERE scratchpad_id = ? AND image_name = ?
            """,
            (scratchpad_id, image_name),
        ).fetchone()
        return row["image_data"] if row else None

    def delete_unreferenced_images(self, scratchpad_id: int, active_image_names: Set[str]) -> int:
        """
        Removes image BLOBs belonging to scratchpad_id whose image_name is no longer
        present in active_image_names. Keeps the database lean.
        """
        conn = self.db.get_connection()
        with conn:
            if not active_image_names:
                cursor = conn.execute(
                    "DELETE FROM scratchpad_images WHERE scratchpad_id = ?",
                    (scratchpad_id,),
                )
            else:
                placeholders = ",".join("?" for _ in active_image_names)
                sql = f"""
                    DELETE FROM scratchpad_images
                    WHERE scratchpad_id = ? AND image_name NOT IN ({placeholders})
                """
                params = [scratchpad_id] + list(active_image_names)
                cursor = conn.execute(sql, params)
            return cursor.rowcount

    def delete_images_for_scratchpad(self, scratchpad_id: int) -> None:
        """Deletes all images associated with a scratchpad."""
        conn = self.db.get_connection()
        with conn:
            conn.execute(
                "DELETE FROM scratchpad_images WHERE scratchpad_id = ?",
                (scratchpad_id,),
            )

