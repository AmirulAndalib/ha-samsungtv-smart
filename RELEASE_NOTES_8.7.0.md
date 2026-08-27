# Release notes — 8.7.0

If this project is useful to you, you can support its development:

# <a href="https://buymeacoffee.com/thefab21" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-black.png" alt="Buy Me A Coffee" height="41" width="174"></a>

> **Status: stable release.** This note covers everything since **8.6.0**, so
> it stands on its own if you are coming from 8.5.x. No breaking changes and
> nothing to reconfigure — but see [One default changed](#one-default-changed)
> for the single behavioural change.

## Highlights

- **The source now follows your remote.** On TVs whose SmartThings status
  reports no input, the current input was read exactly once and then never
  again, so switching with the remote or by HDMI-CEC never reached Home
  Assistant.
- **Local channel number**, read straight from the TV over IP Control, with
  SmartThings kept as the fallback — contributed by
  [@albertoriella](https://github.com/albertoriella).
- **The local poll cadence is yours to set.** It was hard-coded at 30 s; it is
  now an option, and the default is three times faster.
- **A repaired or replaced TV can be re-linked** without deleting the
  integration, and the cloud is no longer hammered when it refuses the device.
- **Hue Sync controls**, where the TV exposes them.
- **Older Samsung TVs get local control back** — Samsung moved the IP Control
  port in 2020 and we only ever tried the new one.
- **Artwork identification recognises famous works** it used to refuse, and
  **picture mode works outside English**.

---

## The source stops following the remote — fixed

Reported in [#230](https://github.com/TheFab21/ha-samsungtv-smart/issues/230)
on a 2022 Frame: changing the input from Home Assistant worked, but changing
it with the remote or by HDMI-CEC never updated `media_player.source`. Waiting
thirty minutes changed nothing, and the debug log showed nothing at all.

On this TV the standard SmartThings capability carries no data:

```
supportedInputSources present=True, value=[]
```

`mediaInputSource.inputSource` is null too, so the current input is only
available from the `samsungvd.mediaInputSource` REST status. That read was
guarded by "only while the source list is still empty" — it ran once, built the
list, and the guard was never true again. The reported input then stayed frozen
on whatever the TV happened to be showing at that moment. Selecting a source
from Home Assistant kept working because that path writes the value directly,
which is exactly the asymmetry that was reported.

The poll now reads the input from `samsungvd.mediaInputSource` as well as the
standard capability, and falls back to the REST read whenever a poll produced
no input value — not only when the source list is missing.

Separately, when SmartThings reports an input that no `source_list` entry maps
to, that mismatch is now logged once per changed input, with the input name and
the current list. It used to fail silently.

## Local tuner channel

`media_player.media_channel` is now read locally over IP Control through
`directChannelControl`, with the SmartThings value kept as fallback. Tested by
the contributor on a UE50DU7170UXZT (Tizen 9.0): channel changes made with the
physical remote and from Home Assistant both show up, switching to HDMI clears
the channel, and switching back restores it.

Three refinements were added on top of the contribution, all driven by
measurements on a Frame:

- **Frame TVs are queried too.** They were excluded on the assumption that
  Frames have no tuner. They do, and the method answers on them:
  `{"atvDtv":"tvplus","airCable":"air","channelNum":"4747"}`. Our own protocol
  reference claimed otherwise and has been corrected.
- **Nothing is asked while Art Mode is displayed.** A Frame in Art Mode still
  reports `inputSource: "TV"`, so the tuner looks active while no channel is on
  screen.
- **`-32601 Method not found` is not treated as a verdict on the model** when
  it arrives in Art Mode. The same call answered a channel number seconds
  earlier on the same TV — the server dispatches this method from a table that
  is not active in ambient mode. Latching on it would have disabled the channel
  until the next Home Assistant restart.

## One default changed

The IP Control state coordinator ran at a hard-coded 30 s. That snapshot
carries the input source, the picture and sound modes, and the tuner channel —
so that constant, not any setting, was what made them take up to half a minute
to follow a change made at the TV.

There is now an **IP Control interval** option (advanced options, 5–600 s):

| | governs | default |
|---|---|---|
| **IP Control interval** | local state: input, picture/sound mode, channel | **10 s** (was a fixed 30 s) |
| **SmartThings interval when on** | the cloud poll, and its rate limit | 30 s |
| **Art content list refresh interval** | the full Frame Art content list | 300 s |

It is deliberately a separate setting rather than reusing the SmartThings one:
that option exists to keep installs under the cloud rate limit, while this is a
LAN call to your TV with no quota behind it. Slowing the cloud down to avoid a
429 is no reason to slow the local sensors down as well.

**This is the one behavioural change in the release**: existing installs move
from 30 s to 10 s and so make three times as many local calls. If your TV is
old or slow to answer, raise it. The floor is 5 s because below that the
requests start overlapping the responses on slower panels, which buys nothing.

While in that screen you may also notice that the content-list field used to be
labelled with its raw key, `content_list_interval`, and that the SmartThings
label was long enough to wrap over its own value on a phone. Both are fixed, in
every supported language.

## A repaired TV can be re-linked

If your TV's mainboard is replaced, its MAC address changes and SmartThings
issues a **new device id**. The integration kept sending the old one, and the
cloud answered `Forbidden` on every poll — 1591 times in 2h14 in the case that
prompted this.

- **Reconfigure → SmartThings device** lets you re-pick the device without
  deleting and re-adding the integration. This step did not exist before.
- Repeated authorisation failures now back off to one attempt every five
  minutes instead of polling at full rate.
- A notification explains what happened and what to do, covering a mainboard
  repair, a factory reset, a TV not yet linked in the SmartThings app, and a
  change of ownership.

## Hue Sync

Where the TV exposes the capability, Hue Sync can be switched from Home
Assistant. TVs that do not expose it answer HTTP 422; that is now reported as
"this TV does not expose the capability" rather than a traceback, and the
capability is skipped instead of being retried.

## Older Samsung TVs

Samsung moved the IP Control port in 2020 — 1515 on 2019-and-earlier sets, 1516
from 2020. We only ever tried 1516, so every older TV looked unsupported.
Pairing now tries both. A 2018 UE50NU8005
([#206](https://github.com/TheFab21/ha-samsungtv-smart/issues/206)) pairs on
1515 and gains its picture calibration, speaker select and reboot entities.

Two findings from that investigation are recorded in
`IP_Control_Protocol_Reference.md`: several methods answer `-32003` on that
generation and are genuinely absent rather than temporarily unavailable, and
the Colour/Tint fields disappear from the state read depending on how the
active **input is classified** (a PC-classified HDMI drops them) — not,
as first assumed, depending on the picture mode.

## Smaller fixes

- **A failed state read no longer blames your picture mode.** Every `-32002`
  used to carry advice written for expert picture *writes* ("switch to
  Standard/Movie/Filmmaker"), which is meaningless for a state read. The
  message now names the method that actually failed.
- **Picture mode works outside English.** The local remote-key fallback matched
  English, French and German names only, so it silently did nothing in every
  other language. Matching is now accent- and case-insensitive across the
  common European spellings.
- **A command the cloud accepts but never delivers** (HTTP 200 with
  `status: FAILED`) is no longer reported as a success.
- **Picture mode names with padding** are stripped, and a failed change now
  reports what every attempt answered rather than only the last.
- **Rate limiting**: the picture-mode retry matrix issued up to four cloud
  requests per change and could trigger a 429 on its own. It stops at the first
  429 now, and skips a capability the TV rejected with a 422.
- **Custom source lists survive SmartThings discovery** — contributed by
  [@serjeleone](https://github.com/serjeleone), who also contributed **local
  source selection over IP Control**.
- **Artwork identification** recognises famous works it used to return as
  "unidentified": the image is sent with its real media type, the prompt no
  longer implies every artwork is a painting, web-detection entities are
  described as the fragments they are, a lone refusal is re-sampled, and the
  14-day negative cache is invalidated when the pipeline changes.
- Dead code removed: `_force_art_coordinator_refresh` never ran — the key it
  waited on was never written.
- Home Assistant's `_reconfigure_entry_id` was being shadowed, which broke
  **every** reconfigure screen with an `UnknownEntry` error.

## Housekeeping

Issue templates are now structured forms with required fields, a pre-flight
checklist and an "AI-assisted" question, and blank issues are disabled. A
report without a debug log and a described reproduction is hard to act on; the
form asks for both up front.

---

## Upgrading

HACS → update → restart Home Assistant. Nothing to reconfigure.

Coming from 8.5.x, the two things to know are the new **IP Control interval**
default of 10 s described above, and — if your TV was ever repaired or reset —
the new **Reconfigure → SmartThings device** step.
