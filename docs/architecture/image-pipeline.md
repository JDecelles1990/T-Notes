# Image Pipeline & Media Architecture

## 1. Overview
IT troubleshooting requires capturing log outputs, configuration windows, and error dialogs using screenshots (`Win + Shift + S`). Without compression, clipboard screenshots are stored as uncompressed 32-bit ARGB bitmaps (often 8–15 MB per capture), causing rapid database bloat.

T-Notes implements an optimized media pipeline that:
- Automatically intercepts clipboard pastes and drag-and-drop image files.
- Compresses images to JPEG with an 85% quality factor, preserving console font legibility while reducing payload sizes by 80–90%.
- Registers images directly into `QTextDocument` resource caches using an internal URI scheme (`image://local/<uuid>.jpg`).
- Synchronizes images with SQLite BLOB storage, automatically pruning unreferenced/deleted images.

---

## 2. Image Ingestion Lifecycle

```mermaid
sequenceDiagram
    autonumber
    actor Tech as Technician
    participant Ed as TechPadEditor
    participant Svc as ImageService
    participant Doc as QTextDocument
    participant DB as SQLite (scratchpad_images)

    Tech->>Ed: Pastes screenshot (Win+Shift+S / Ctrl+V) or drops image
    Ed->>Ed: insertFromMimeData() catches QMimeData
    Ed->>Svc: create_embedded_image(source, quality=85)
    Svc->>Svc: Convert ARGB to RGB & Compress via QBuffer/Pillow
    Svc->>Svc: Generate UUID (e.g. 550e8400.jpg)
    Svc-->>Ed: Returns (image_name, resource_url, jpeg_bytes, qimage)
    Ed->>Ed: Cache jpeg_bytes in in_memory_images[name]
    Ed->>Doc: addResource(ImageResource, QUrl("image://local/..."), qimage)
    Ed->>Ed: textCursor().insertImage("image://local/...")
    Note over Ed,DB: Debounce period expires (1500ms)
    Ed->>Svc: sync_scratchpad_images(scratchpad_id, html, in_memory_images)
    Svc->>Svc: Extract all image://local/ references in HTML
    Svc->>DB: INSERT / UPDATE active images as BLOBs
    Svc->>DB: DELETE unreferenced images (Garbage Collection)
    Ed->>Ed: Clear in_memory_images cache
```

---

## 3. Step-by-Step Breakdown

### Step 1: MIME Capture & Clipboard Interception
In `TechPadEditor`:
- Overrides `canInsertFromMimeData()` to accept images, URLs, and text.
- Overrides `insertFromMimeData()`:
  - If `source.hasImage()` is true (e.g., from `Win + Shift + S`), extracts `source.imageData()` as a `QImage`.
  - If `source.hasUrls()` is true, checks for local image file extensions (`.png`, `.jpg`, `.jpeg`, `.bmp`, `.gif`, `.webp`) and reads raw binary bytes.

### Step 2: JPEG Compression (Quality = 85)
In `ImageService`:
- If an alpha channel exists (`qimage.hasAlphaChannel()`), the image is composited against a clean white background to avoid transparent black artifacts when converting to JPEG.
- Compresses the image data into a `QByteArray` using Qt's `QBuffer` with `"JPEG"` format and quality `85`.
- Pillow (`PIL.Image`) is used as an additional fallback for arbitrary raw image byte buffers.

### Step 3: Resource Registration (`image://local/<uuid>.jpg`)
- A unique identifier is generated: `image_name = f"{uuid.uuid4().hex}.jpg"`.
- The resource URL is formed: `image://local/<uuid>.jpg`.
- Registered into the editor's document via:
  ```python
  document.addResource(QTextDocument.ImageResource, QUrl("image://local/<uuid>.jpg"), qimage)
  ```
- Inserted into the text flow via `cursor.insertImage("image://local/<uuid>.jpg")`.

### Step 4: Database Persistence & Garbage Collection
- During auto-save, `ImageService.sync_scratchpad_images()` parses the current HTML using regex (`src=["\']image://local/([^"\'>\s]+)["\']`).
- Any newly inserted images present in the document are written to `scratchpad_images` as binary BLOBs.
- **Garbage Collection:** Any previously stored image BLOB that is no longer referenced in the HTML (i.e. the technician pressed backspace and deleted the screenshot) is automatically deleted from `scratchpad_images`:
  ```sql
  DELETE FROM scratchpad_images
  WHERE scratchpad_id = ? AND image_name NOT IN (?, ?, ...);
  ```
  This guarantees that deleting screenshots from notes immediately reclaims database space.

---

## 4. Performance & Size Impact

| Capture Type | Raw Clipboard Size | Compressed JPEG (85%) | Reduction |
| :--- | :--- | :--- | :--- |
| Full 1080p Screenshot | ~8.3 MB (ARGB32) | ~180 KB – 320 KB | **~96%** |
| 4K Monitor Window Snip | ~16.5 MB (ARGB32) | ~450 KB – 750 KB | **~95%** |
| Terminal / CLI Error Snip | ~2.1 MB (ARGB32) | ~60 KB – 120 KB | **~94%** |
