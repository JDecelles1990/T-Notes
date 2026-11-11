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

---

## 5. Image Export & Clipboard Copy (Context Menu)

When right-clicking directly on any embedded image in `TechPadEditor`:
- **Image Hit Detection (`_get_image_at_pos`):** Resolves the character format under cursor (and adjacent character positions) to verify `fmt.isImageFormat()`, retrieving the associated `QImage` directly from `QTextDocument.resource()`.
- **`📋 Copy Image`:** Copies raw uncompressed pixel data into the system clipboard via `QApplication.clipboard().setImage(qimage)`, enabling instantaneous pasting (`Ctrl+V`) into Slack, Teams, Outlook, Jira, or Paint.
- **`💾 Save Image As...`:** Prompts standard `QFileDialog.getSaveFileName` for PNG or JPEG export. If the user saves as JPEG, the original stored JPEG bytes are written directly without generational quality loss from re-compression.

---

## 6. Multi-Selection & Rich Text Clipboard Export (Base64 Embedding)

When users copy highlighted content containing both text, formatting, colors, and embedded images:
- **Challenge:** Qt's native `createMimeDataFromSelection()` generates HTML containing internal URI references (`<img src="image://local/<uuid>.jpg">`). External applications (Microsoft Word, Outlook, Teams, Slack, Google Docs, Chrome, etc.) cannot resolve `image://local/` and will fail to display or drop the images.
- **Solution (`_enrich_html_with_base64_images`):**
  1. `TechPadEditor.createMimeDataFromSelection()` intercepts the HTML clipboard payload.
  2. Parses all `<img>` tags and matches internal image resource names against `in_memory_images`, the database repository `scratchpad_images`, or `document().resource()`.
  3. Replaces internal references with self-contained **Base64 Data URIs** (`data:image/jpeg;base64,...`).
  4. Preserves all font colors, backgrounds, code blocks, and headings.
  5. If an image is selected alone without text, also provides raw bitmap data via `mime_data.setImageData(first_qimage)` for bitmap-only paste targets (e.g. Paint).
  6. Replaces the Unicode object replacement character `\uFFFC` in plain-text with `[Screenshot]` for clean terminal or Notepad pasting.
- **Full Note Copy (`copy_formatted_note`):** Clicking `📋 Copy Note` on the ribbon or pressing `Ctrl+Shift+C` packages the entire active document with Base64-embedded images and rich styles onto the clipboard.




## 7. Interactive Image Resizing & Proportional Scaling (Normal & Split Views)

`TechPadEditor` supports complete, interactive image resizing across both normal full-width editor panes and narrower Split View side panels:

### 7.1 Resizing Methods
1. **Interactive Visual Drag Resizing:**
   - **Selection Outline & Corner Handle:** Clicking an embedded image highlights it with an accent blue selection border (`#007acc`) and a bottom-right corner resize handle.
   - **Hover Feedback:** Hovering over the corner handle displays `Qt.SizeFDiagCursor` (`↘`).
   - **Live Drag Preview:** Dragging the handle draws a real-time dashed preview box (`#60a5fa`) with a high-contrast pill badge displaying target dimensions (e.g. `480 × 270 px`).
   - **Aspect Ratio Locking:** Dragging maintains proportional aspect ratio by default. Holding `Shift` unconstrains the aspect ratio.
   - **Smooth Execution:** The format is finalized on mouse release, preventing layout jitter and collapsing changes into a single undo step.
2. **Context Menu Quick Resize (`📏 Quick Resize`):**
   - **Fit to Pane Width:** Computes available pane width (`viewport().width() - 24`). In Split View sidebar, this scales the image down to fit the side panel without horizontal scrollbars; in normal view, it scales to fit the main window.
   - **Presets:** `100% (Original Size)`, `75%`, `50%`, `25%`.
3. **Image Editor Window (`🖼️ Image Editor` / Double-Click):**
   - Double-clicking an image opens the modal `Image Editor` window (`ResizeImageDialog` / `ImageEditorDialog`).
   - **Full Screen Maximize:** Double-clicking either the OS window title bar or the in-dialog top toolbar frame (or pressing `F11` / clicking `⛶ Maximize`) expands the editor to full screen for maximum workspace visibility.
   - **Precision Zoom & Pan:** Technicians can zoom in/out via `Ctrl + Mouse Wheel`, toolbar `➕`/`➖` buttons, or `Ctrl++`/`Ctrl+-` shortcuts (25% to 500%), with `1:1` reset and middle-click panning.
   - **Paint-Style Text Rectangle:** Clicking and dragging on the canvas defines a dashed bounding box for text placement, allowing custom font size selection (8 to 96 pt), multi-line text input, optional callout border box, and word-wrapped high-contrast rendering.
   - **Proportional Resizing:** Technicians can enter exact pixel dimensions (`Width` and `Height` spinboxes) or select presets (`25%`, `50%`, `75%`, `100%`, `Fit to Pane Width`).
   - Integrated `ImageAnnotationCanvas` provides freehand drawing (`✏️`), circle callouts (`⭕`), rectangle callouts (`🔲`), and text overlays (`🔤`) with full color palette selection and reversible 30-level history (`↺ Undo`, `↻ Redo`, `🔄 Reset Image`).
4. **Keyboard Deletion:**
   - Pressing `Delete` or `Backspace` while an image is selected immediately deletes the screenshot from the document.

### 7.2 Persistence & HTML Fidelity
- Resized dimensions are serialized natively by Qt as HTML attributes (`<img src="image://local/<uuid>.jpg" width="W" height="H" />`).
- Re-opening tickets, switching tabs, and restoring session states preserves exact dimensions.
- Copying rich notes (`📋 Copy Note`) embeds Base64 data with matching `width` and `height` attributes so external applications render scaled images.

### 7.3 Visual Annotation & Markup Pipeline
- **Canvas Viewport Mapping with Zoom/Pan:** Mouse coordinates are normalized to the underlying source image dimensions using aspect-ratio-preserving bounds calculation with dynamic zoom factor and pan offset, guaranteeing pixel-perfect accuracy regardless of magnification.
- **ARGB32 Premultiplied Rendering:** Interactive drawings operate on an in-memory ARGB32 Premultiplied copy with Qt anti-aliasing.
- **Paint-Style Text Layout:** Text overlays render inside the user's defined bounding box with automatic word wrapping, selectable font size, and an 8-point boundary shadow in semi-transparent black behind the colored text to ensure legibility on both dark consoles and white documents.
- **Storage Synchronization:** When annotations are confirmed via `OK`:
  1. The annotated image is compressed into JPEG (85% quality per `AGENTS.md`) using `ImageService.compress_qimage_to_jpeg()`.
  2. The updated JPEG bytes are stored in `editor.in_memory_images[raw_name]`.
  3. The `QTextDocument` resource cache is refreshed under `image://local/<raw_name>` and `<raw_name>`.
  4. `editor.content_modified.emit(scratchpad_id)` marks the note dirty for background SQLite persistence during debounced auto-save.

---

## Atomic note save and cache ownership

The Notes save path extracts the `image://local/<name>` reference set and snapshots
the pending JPEG cache. HTML, referenced JPEGs and orphan cleanup commit in one
repository transaction. A reference must resolve to this ticket's existing BLOB
or its pending cache; another ticket's image never satisfies it. The independent
`sync_scratchpad_images` helper is retained for existing callers but is not used
by `ScratchpadService.save_content`. Failure preserves the original cache and
document. Only a committed receipt for the current editor revision clears them.
