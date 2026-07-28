# Release notes — 8.5.1

If this project is useful to you, you can support its development:

# <a href="https://buymeacoffee.com/thefab21" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-black.png" alt="Buy Me A Coffee" height="41" width="174"></a>

> **Status: stable release.** A maintenance release on top of 8.5.0 — no
> breaking changes and no configuration to touch. It makes the new upload card
> actually reliable on 2024 Frames, fixes OAuth for multi-TV setups, and adds a
> `send_text` service.

## Highlights

- **Artwork upload now works on 2024 Frames.** Uploads that used to fail with
  *"no content_id returned"* — or land as a **grey rectangle with no preview** —
  now go through.
- **Uploading no longer hijacks your screen.** The TV stays where it is,
  whether you're in Art Mode or watching an HDMI input.
- **Images are fitted to your panel**, in either orientation, using the
  resolution the TV itself reports (so 8K sets are not shrunk to 4K).
- **New `send_text` service** to type into a text field on the TV.
- **Multi-TV OAuth no longer breaks itself** — refreshing the SmartThings token
  on one TV stopped invalidating the others.

---

## Upload reliability on 2024 Frames

Two independent problems made uploads fail on 2024 panels (QE55LS03D and
friends) while the same picture uploaded fine on a 2023 Frame.

**1. An upload could be killed mid-flight by our own watchdog.** The
zombie-channel circuit breaker (added in 8.3.4) counts consecutive request
timeouts and force-closes the art WebSocket when it looks wedged — which
cancels every pending request. On TVs whose `get_thumbnail` never answers, the
gallery's thumbnail timeouts piled up *while an upload was waiting*, tripped the
breaker, and the upload was reported as failed even though the TV was still
processing it. That also explains why the failure looked random: it only
happened when enough thumbnail timeouts accumulated during the transfer. The
breaker is now suspended for the duration of an upload — the channel is
demonstrably alive there, so there is nothing for it to detect.

**2. The image itself could be undecodable for the TV.** The Frame is far
pickier than a browser: progressive JPEGs, unusual chroma subsampling, CMYK,
16-bit or paletted samples, oversized EXIF blobs — and, above all, **images
larger than the panel** — get *stored* and then fail to render, leaving a grey
rectangle and no `image_added` event. Uploads through the card are now
normalised once, the way the SmartThings app does it: decoded, EXIF orientation
applied, metadata dropped, fitted to the panel, and re-encoded as a plain
baseline JPEG (quality 92, 4:2:0).

Uploads are also written to the TV in chunks rather than one buffered write.

## Uploading no longer changes what's on screen

Storing a picture in the art library does not require the panel to be showing
art — the SmartThings app uploads while the TV is on a normal input, and so do
we now. `art_upload` and `art_upload_batch` only ensure the TV is **powered**;
they no longer force Art Mode on.

Equally important, a TV that is already running is never woken: a Frame in Art
Mode reports its media_player state as `off`, so the TV is asked directly
(REST `PowerState`, then IP Control) before anything is powered on. Previously
this could toggle a Frame out of Art Mode onto the last HDMI input.

Operations that genuinely change the display (select image, matte, slideshow,
brightness…) still ensure Art Mode, as before.

## Panel-aware image fitting

Images are fitted to the panel using the resolution **the TV reports**, exposed
as a new `screen_resolution` attribute on the media player — so a future 8K set
is served at 8K instead of being capped at 4K.

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
Application Credentials, every entry stored its own copy of the same OAuth
token pair. SmartThings **rotates the refresh token** on each refresh, so the
first entry to refresh got the new pair while the others kept the now-dead
predecessor — they failed with `400 / invalid_grant` and demanded manual
reauthentication. Reauthenticating them all restored service and immediately
recreated the same condition, so OAuth was never really maintenance-free in a
multi-TV setup.

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
`play_media` call that nobody could discover. It is now a first-class service:

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

---

## Upgrade notes

- No configuration changes. Update via HACS and restart Home Assistant.
- If you had failed uploads on a 2024 Frame, delete the leftover grey entries
  from the TV's art library — they cannot recover on their own.
- Multi-TV OAuth users: if some entries are currently in an error state,
  reauthenticate **one** of them — the restored token now propagates to every
  entry that shared the old one.

---

## Changelog

- **Fix:** the timeout circuit breaker no longer force-closes the art channel
  during an upload, which cancelled the upload's own `image_added` wait.
- **Fix:** uploads through the card are normalised (baseline JPEG, EXIF
  stripped, fitted to the panel) so 2024 Frames can decode them.
- **Fix:** images are fitted to the TV's reported resolution, orientation-aware
  — no more squashed portrait artwork, and 8K-ready.
- **Fix:** uploading no longer forces Art Mode on, and never wakes a TV that is
  already running (which used to switch a Frame to HDMI).
- **Fix:** image data is sent to the TV in chunks instead of one buffered write.
- **Fix:** OAuth refresh-token rotation is coordinated across TV entries that
  share credentials, so refreshing one TV no longer invalidates the others
  (#180, thanks @tdalejandro).
- **New:** `samsungtv_smart.send_text` service, plus a new `screen_resolution`
  media-player attribute.
- **Docs:** `send_text` scope, and the integration's local-first design with
  SmartThings used only as a secondary status layer (relevant to the upcoming
  SmartThings API pricing change).
