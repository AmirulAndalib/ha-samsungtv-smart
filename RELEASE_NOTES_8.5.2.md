# Release notes — 8.5.2

If this project is useful to you, you can support its development:

# <a href="https://buymeacoffee.com/thefab21" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-black.png" alt="Buy Me A Coffee" height="41" width="174"></a>

> **Status: stable release.** This note covers the **whole 8.5 line** (8.5.0 →
> 8.5.2), so it stands on its own if you are coming from 8.4.x. No breaking
> changes and nothing to reconfigure anywhere in the line.

## Highlights of the 8.5 line

- **One-click artwork upload from any device.** A bundled Lovelace card lets
  you pick an image on your phone or laptop and push it straight to The Frame —
  no pre-placed file, no folder sensor, no service call to hand-write.
- **iPhone HEIC photos just work**, and every upload is now normalised so The
  Frame can actually decode it — no more artwork landing as a **grey rectangle
  with no preview**.
- **Uploading never hijacks your screen.** The TV stays exactly where it is,
  whether it's showing art or an HDMI input.
- **New `send_text` service** to type into a text field on the TV.
- **Multi-TV OAuth no longer breaks itself** — refreshing the SmartThings token
  on one TV stopped invalidating the others.
- **Much quieter debug logs** — the biggest single source of noise is gone.

---

## One-click artwork upload

Getting a *new* picture onto The Frame used to take some setup: drop a file
where Home Assistant can see it, then call the `art_upload` service. The
SmartThings app is easier, but only works when you're in front of the TV.

The integration now bundles a Lovelace card, `samsung-art-upload-card`,
registered automatically — nothing to install or add as a resource. Put it on
any dashboard:

```yaml
type: custom:samsung-art-upload-card
# entity: media_player.the_frame   # optional — a picker appears if omitted and you have several Frames
# matte: shadowbox_polar           # optional default matte
# title: Upload to The Frame       # optional
```

Pick an image from your phone or laptop, tap **Upload to Frame**, done. The card
POSTs the file to an **authenticated** endpoint (`/api/samsungtv_smart/art_upload`)
which reuses the normal upload flow and reports back the new content id.

Pin a TV with `entity:` and it always uploads there. Omit it and, with more than
one Frame, you get a per-upload selector; with a single Frame there is no
selector at all.

## Uploads that actually land — including on 2024 Frames

This is the bulk of the work in 8.5.1 and 8.5.2. Uploads could fail with
*"no content_id returned"*, or succeed-but-not-really: the artwork appeared in
the TV's library as a **grey rectangle with no thumbnail**. It hit 2024 panels
(QE55LS03D and friends) while the same picture uploaded fine to a 2023 Frame.

There were **two independent causes**, which is why it looked random for so long.

**1. Our own watchdog was killing uploads mid-flight.** The zombie-channel
circuit breaker (added in 8.3.4) counts consecutive request timeouts and
force-closes the art WebSocket when the channel looks wedged — which cancels
every pending request. A freshly uploaded artwork takes a while before the TV
can serve its thumbnail, so those thumbnail timeouts piled up *while an upload
was waiting for its confirmation*, tripped the breaker, and the upload was
reported as failed even though the TV was still happily processing it. The
breaker is now suspended for the duration of an upload: the channel is
demonstrably alive there — the TV has just accepted the transfer — so there is
nothing for a wedged-channel heuristic to detect.

**2. The image itself could be undecodable for the TV.** The Frame is far
pickier than a browser: progressive JPEGs, unusual chroma subsampling, CMYK,
16-bit or paletted samples, fat EXIF blobs — and above all **images larger than
the panel** — get *stored* and then fail to render. Every upload is now
normalised once, the way the SmartThings app does it: decoded (HEIC included),
EXIF orientation applied, metadata dropped, fitted to the panel, re-encoded as a
plain baseline JPEG (quality 92, 4:2:0).

**8.5.2 extends that normalisation to every path.** In 8.5.1 it only covered the
card, so `art_upload` and `art_upload_batch` still sent raw bytes and could
still produce grey rectangles. It now lives in one place that all three paths
funnel through — card, service and folder batch behave identically.

> Batch idempotency is unaffected: skip-unchanged (mtime) and perceptual dedup
> are computed on the **source** file before the re-encode, so re-running a
> folder still uploads nothing.

Uploads are also written to the TV in chunks instead of one buffered write.

## Uploading no longer changes what's on screen

Storing a picture in the art library doesn't require the panel to be showing
art — the SmartThings app uploads while the TV is on a normal input, and so do
we now. `art_upload` and `art_upload_batch` only ensure the TV is **powered**;
they no longer force Art Mode on.

Equally important, a TV that is already running is never woken. A Frame in Art
Mode reports its media_player state as `off`, so the TV is now asked directly
(REST `PowerState`, then IP Control) before anything is powered on — previously
this could toggle a Frame out of Art Mode onto the last HDMI input.

Operations that genuinely change the display (select image, matte, slideshow,
brightness…) still ensure Art Mode, as before.

## Panel-aware image fitting

Images are fitted using the resolution **the TV reports**, exposed as a new
`screen_resolution` attribute on the media player — so a future 8K set is served
at 8K instead of being capped at 4K.

The bounding box follows the image's orientation, mapping the panel's long and
short edges onto the image's own:

| panel | image | result |
|---|---|---|
| 3840×2160 | 4259×2160 (landscape) | 3840×1947 |
| 3840×2160 | 2160×4259 (portrait) | 1947×3840 |
| 7680×4320 (8K) | 8000×4000 | 7680×3840 |
| any | smaller than the panel | unchanged |

Without this, portrait artwork was squashed to 2160 px tall — throwing away half
the detail a portrait-mounted Frame can display.

## Multi-TV OAuth: token rotation no longer breaks sibling entries

Reported and fixed by @tdalejandro (#180, #181).

With several TVs set up as separate entries sharing one set of SmartThings
Application Credentials, every entry stored its own copy of the same OAuth token
pair. SmartThings **rotates the refresh token** on each refresh, so the first
entry to refresh got the new pair while the others kept the now-dead predecessor
— they failed with `400 / invalid_grant` and demanded manual reauthentication.
Reauthenticating them all restored service and immediately recreated the same
condition, so OAuth was never really maintenance-free in a multi-TV setup.

Refreshes are now coordinated per *token group* rather than per entry:

- entries sharing an OAuth implementation **and** the same refresh token share
  one lock, so a rotation is requested **once** instead of once per TV;
- the rotated pair is propagated to exactly those sibling entries that held the
  same predecessor — entries on other credentials are never touched;
- the same propagation happens after a manual reauthentication, so reauthing
  **one** TV now fixes them all;
- stale "token invalid" state and the matching Repairs issues are cleared on
  every entry that was updated.

> **Note:** storing the rotated token reloads each updated entry, so on a
> routine refresh all TVs sharing the token reload together (entities are
> briefly unavailable). That replaces the previous behaviour where the sibling
> entries simply broke.

## New: `send_text` service

The integration could always type text on the TV, but only through a generic
`play_media` call nobody could discover. It is now a first-class service:

```yaml
action: samsungtv_smart.send_text
target:
  entity_id: media_player.samsung_tv
data:
  text: "hello"
```

> **Scope.** This drives the native **Tizen IME**, so it only produces text
> where a real Tizen text field is focused — Settings search, the built-in
> browser's address bar, a Wi-Fi password or a login form. It does **not** work
> in the search screens of Netflix, YouTube, Prime Video and friends: those draw
> their own on-screen character grid rather than a text field. A physical
> Bluetooth keyboard works there only because the TV injects it as HID at a
> lower level, and Samsung's remote APIs expose no alphabet keys at all
> (WebSocket and IP Control both offer only the standard remote keyset). This is
> a platform limitation, not something the integration can work around.

## Quieter debug logs

If you run this integration with debug logging on, the REST device-info payload
(~40 mostly-immutable fields) was dumped **on every poll cycle** — about every
5 s per TV, whether the TV was on or off.

Measured on a real 26-hour debug log: **31 376 lines, 46 MB — 21 % of the whole
file — for exactly 5 distinct payloads.** Only `PowerState` ever moves.

It is now logged in full only when it actually changes; otherwise a one-liner
carries the field that does:

```
Device info on 192.168.1.161 unchanged (PowerState=on)
```

Genuine changes are still dumped in full, so nothing is lost for diagnosis.

---

## Upgrade notes

- No configuration changes. Update via HACS and restart Home Assistant.
- If you previously had failed uploads on a 2024 Frame, delete the leftover grey
  entries from the TV's art library — they cannot recover on their own.
- Multi-TV OAuth users: if some entries are currently in an error state,
  reauthenticate **one** of them — the restored token now propagates to every
  entry that shared the old one.
- A `Could not download thumbnail` warning right after an upload is expected and
  self-healing: the TV needs time to generate the thumbnail, and a delayed retry
  picks it up (you'll see `thumbnail … is now available (delayed retry)`).

---

## Changelog

### 8.5.2

- **Fix:** every upload path is normalised, not just the card — `art_upload` and
  `art_upload_batch` no longer send raw bytes that a 2024 Frame can't decode.
- **Perf:** the REST device-info payload is logged only when it changes,
  removing the single biggest source of debug-log noise.

### 8.5.1

- **Fix:** the timeout circuit breaker no longer force-closes the art channel
  during an upload, which cancelled the upload's own `image_added` wait.
- **Fix:** uploads are normalised (baseline JPEG, EXIF stripped, fitted to the
  panel) so 2024 Frames can decode them.
- **Fix:** images are fitted to the TV's reported resolution, orientation-aware
  — no more squashed portrait artwork, and 8K-ready.
- **Fix:** uploading no longer forces Art Mode on, and never wakes a TV that is
  already running (which used to switch a Frame to HDMI).
- **Fix:** image data is sent to the TV in chunks instead of one buffered write.
- **Fix:** OAuth refresh-token rotation is coordinated across TV entries that
  share credentials (#180, thanks @tdalejandro).
- **New:** `samsungtv_smart.send_text` service, plus a `screen_resolution`
  media-player attribute.
- **Docs:** `send_text` scope, and the integration's local-first design with
  SmartThings used only as a secondary status layer.

### 8.5.0

- **New:** bundled `samsung-art-upload-card` Lovelace card (auto-registered).
- **New:** authenticated `/api/samsungtv_smart/art_upload` HTTP endpoint.
- **New:** server-side HEIC/HEIF → JPEG transcoding for uploads.
- **Change:** the `art_upload` service returns the upload result (`content_id`).
- **Fix:** bundled card resources register immediately when the integration is
  reloaded after Home Assistant has already started.
