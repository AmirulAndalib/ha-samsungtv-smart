# Release notes — 8.2.0 (since 8.1.0)

> **Status: pre-release (beta).** 8.2.0 builds on 8.1.0.

## Folder Gallery card — handle big folders of full-size originals

- **Thumbnails are now loaded/unloaded on demand (IntersectionObserver)**:
  pointing the gallery at a folder of original photos (several MB each, many of
  them) used to give every `<img>` its `src` up front, so the browser
  downloaded and decoded the entire set at once and could choke. The card now
  only sets `src` on images near the viewport and **drops it again** once they
  scroll far offscreen, so the number of decoded bitmaps held in memory stays
  bounded regardless of how large the folder is. Images also decode
  asynchronously (`decoding="async"`), and tiles keep their size while
  unloaded so scrolling stays stable.

  > Note: this bounds the browser's memory/CPU; the full-size file is still
  > downloaded when a tile actually scrolls into view. A future step may add
  > server-side resized thumbnails for local folders to also cut bandwidth.
