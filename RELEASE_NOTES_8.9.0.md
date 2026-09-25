# Release notes — 8.9.0

If this project is useful to you, you can support its development:

# <a href="https://buymeacoffee.com/thefab21" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-black.png" alt="Buy Me A Coffee" height="41" width="174"></a>

> **Status: stable release.** This note covers everything since **8.8.0**
> (8.8.1 → 8.8.25 plus this release). Nothing to reconfigure. A few log lines
> are new or reworded — see [What may look different](#what-may-look-different).

## Highlights

- **The integration has its own icon.** Home Assistant used to show the icon
  registered upstream for the shared `samsungtv_smart` domain.
- **Art Mode no longer freezes or storms.** The Art channel serializes its
  requests, backs off properly when a reconnect doesn't answer, and
  `art_mode_status` can no longer latch for hours.
- **Ports stop flapping and re-healing.** The remote, Art and REST channels
  each keep the port that has proven it works. Each has its own stored value,
  and every change to one is logged.
- **Power-on actually uses your wake method** when a Frame refuses `KEY_POWER`.
- **Far fewer reloads and far less log noise** on unstable or sleeping TVs.

---

## Art Mode: no more freezes, stalls or reconnect storms

Most of this came out of two long threads,
[#12](https://github.com/TheFab21/ha-samsungtv-smart/issues/12) (a 2020 Frame)
and [#273](https://github.com/TheFab21/ha-samsungtv-smart/issues/273)
(a 13-TV fleet). Both reporters measured instead of guessing.

- **Art requests are serialized, with a bounded close**
  ([#268](https://github.com/TheFab21/ha-samsungtv-smart/pull/268), thanks
  [@tothemoonsands](https://github.com/tothemoonsands)). The TV's Art app
  handles one request at a time. Several entities polling it at once piled up
  timeouts and refilled a dying socket, and a half-open transport could hang
  Home Assistant on shutdown.
- **Recovery backoff that adapts.** After a wedge, the cooldown lifts as soon
  as the channel is genuinely ready. Consecutive wedges on connections that
  never answer double it (30 → 60 → 120 → 240 s), and it resets on the first
  real answer. On the 13-TV fleet, wedges went from 94 back down to 7 in a
  comparable window, and a morning burst that used to loop for 3–4 h stopped
  after 2–3 attempts.
- **`art_mode_status` can't latch any more.** A check meant for apps running
  on screen could freeze the value for hours whenever a Frame fast-cycled
  into Art Mode, because the Frame then reports itself as off and the check
  never re-ran. It now only applies while the TV is on. Fleet-wide wrong time
  went from 6.60% back to 0.25%, and the multi-hour stretches are gone.
- **The panel is the source of truth**
  ([#248](https://github.com/TheFab21/ha-samsungtv-smart/issues/248)). With
  IP Control paired, `getTVStates.pictureMode == "Ambient"` decides
  `art_mode_status` ahead of the WebSocket cache. This only applies on
  art-capable TVs, so non-Frames sitting in Samsung's own Ambient Mode aren't
  affected, and never when the panel is powered off.
- **Our own write no longer resets the state**
  ([#264](https://github.com/TheFab21/ha-samsungtv-smart/issues/264),
  diagnosis by jackmcintyre). The reply to `set_artmode_status` was parsed as
  a status report and forced Art Mode to off about 10 s after turning it on,
  on some 2024 Frames.
- **Thumbnails still being generated are no longer reported as failed.** Only
  giving up after the last retry warns now.

## Ports: each channel keeps the one that works

A Frame exposes two WebSocket ports: plain **8001** and secure **8002**. The
integration used to switch between them too eagerly and share one stored
value between channels, so a fix on one channel undid another.

- **The remote channel is paired on the secure 8002 port** whenever the TV
  exposes it. On many Frames 8001 accepts the handshake and even hands out a
  token, which the TV then refuses at runtime. That forced an 8001 → 8002
  re-heal on every restart. 2024 Frames (8002 filtered) and ~2020 sets
  (no 8002) still fall back to 8001, with no delay.
- **The Art channel stores its own port** (`art_port`). While a TV wakes up,
  the art socket could briefly answer on 8001 and overwrite the remote
  channel's 8002.
- **A port that has answered is kept.** On a Wi-Fi Frame, or a sleeping panel,
  both ports look dead at the same time. The Art channel was flipping back
  and forth (55 times each way in one window), and the REST API did the same
  (57 × 8002→8001 against 58 × 8001→8002 in ~50 h across 12 TVs). A proven
  port now stays put, and the retries are spaced out instead.
- **Every stored-port change is logged at INFO**:
  `Persisting WS port …`, `Persisting Art port …` and
  `Persisting REST port … old -> new`. Each should appear at most once and
  then never again. If one keeps recurring, please report it.

## Power-on

- **A rejected `KEY_POWER` no longer counts as a successful wake.** A Frame
  that is reachable but refuses the key answers asynchronously, so the
  integration used to think the key had worked and never tried your
  configured wake method. It now falls back to WOL, SmartThings or
  IP Control, whichever you configured.
- **The same fallback applies when the remote channel can't authorize at
  all**, as on some 2020 Frames that reject both ports. The README explains
  how to wake those from standby.

## Fewer reloads, less noise

- **Runtime facts no longer reload the integration**
  ([#12](https://github.com/TheFab21/ha-samsungtv-smart/issues/12)). Tokens,
  learned ports, capability flags, and the api_key rewritten by every OAuth
  refresh used to reload the whole entry when they changed. On a flaky
  connection that meant a reload every few minutes, with entities flapping
  unavailable. Reloading also reopened the control connection, a common
  trigger for the Frame's on-screen "authorize" prompt.
- **An isolated IP Control `-32002`** ("refused in its current state") keeps
  the previous values instead of turning into an ERROR. It is logged at
  WARNING, and only a run of refusals becomes an error.
- **The SmartThings source-list diagnostics** only log when the list changes.
  Before, it was three DEBUG lines per poll.

## Other fixes and additions

- **"No SmartThings (local only)" reconfigure option**
  ([#258](https://github.com/TheFab21/ha-samsungtv-smart/issues/258)). This
  strips SmartThings from an entry cleanly, including a stale OAuth token that
  kept failing to refresh.
- **Stale SmartThings "Speaker Select" removed when IP Control is on**
  ([#261](https://github.com/TheFab21/ha-samsungtv-smart/issues/261)). It was
  also pushing the live select to `_speaker_select_2`.
- **Hue Sync starts again from Home Assistant**
  ([#266](https://github.com/TheFab21/ha-samsungtv-smart/issues/266)). The
  app is launched when no session is running, and stopping with no session
  now says so instead of silently succeeding.
- **`sw_version` is always sent to the device registry as a string.** A list
  would stop working in Home Assistant 2026.12.
- **Docs**: the HACS install steps are corrected (custom repositories have no
  one-click link), there's an `info.md` panel, and the reporting guide in
  [#224](https://github.com/TheFab21/ha-samsungtv-smart/issues/224) now covers
  capturing long or intermittent faults (thanks
  [@ajguerre1](https://github.com/ajguerre1)).

## What may look different

- **New icon** on the integration card. Do a hard refresh of the browser (or
  clear the app cache) if you still see the old one.
- **New INFO lines** `Persisting WS / Art / REST port … old -> new`. Seeing
  each one once after upgrading is normal.
- **The 8001 → 8002 remote-channel heal is INFO**, not WARNING. Only
  "rejected both the 8001 and the secure 8002" stays a warning.
- **`REST request … switching to it` is gone.** A transient port failure now
  logs at DEBUG.
- **An isolated `-32002` shows as a WARNING** rather than an ERROR.

---

## Thanks

To [@ajguerre1](https://github.com/ajguerre1) and
[@excprocess](https://github.com/excprocess) for months of careful
measurements, a standalone test script and honest corrections in both
directions. To [@tothemoonsands](https://github.com/tothemoonsands) for #268,
and to jackmcintyre for #264.

## Upgrading

HACS → update → restart Home Assistant. Nothing to reconfigure.
