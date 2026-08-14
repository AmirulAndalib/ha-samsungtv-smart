# Release notes — 8.6.3

If this project is useful to you, you can support its development:

# <a href="https://buymeacoffee.com/thefab21" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-black.png" alt="Buy Me A Coffee" height="41" width="174"></a>

> **Status: stable release.** This note covers the **whole 8.6 line**
> (8.6.0 → 8.6.3), so it stands on its own if you are coming from 8.5.x. No
> breaking changes and nothing to reconfigure anywhere in the line.

## Highlights of the 8.6 line

- **Artwork identification stops breaking** when a provider retires a model —
  the model list is read live from your provider — and it now recognises
  famous works it used to refuse.
- **Older Samsung TVs get local control back.** Samsung moved the IP Control
  port in 2020; we only ever tried the new one, so every 2019-and-earlier set
  looked unsupported. A 2018 model now pairs and gains its picture
  calibration, speaker select and reboot entities.
- **Picture mode works outside English.** The local remote-key fallback was
  matched against English, French and German names only, so it silently did
  nothing everywhere else.
- **Failures say what actually failed** — the picture mode error now names the
  SmartThings response for every attempt, and a command the cloud accepts but
  never delivers no longer looks like a success.

---

## Model discovery: pick from what your key can actually use

Until now the model was a free-text field with a hardcoded default per
provider. That gives every default an expiry date: when Google retired
`gemini-2.5-flash` for new users, identification stopped working for everyone
who had never touched the setting, with only a `404` in the log
([#188](https://github.com/TheFab21/ha-samsungtv-smart/issues/188)).

The integration now asks the provider what it offers, the same way Home
Assistant's own Google Generative AI integration does:

| provider | endpoint | filtering |
|---|---|---|
| Gemini | `GET /v1beta/models` | keeps only models supporting `generateContent` |
| OpenAI | `GET /v1/models` | drops embeddings, audio, image and moderation models |
| Anthropic | `GET /v1/models` | newest first, as returned by the API |

**In the config flow** (*Configure → Art Identification*), once a provider and
an API key are saved, the **Model** field becomes a dropdown listing the models
that key can use. It stays free-text-capable, so a brand-new model missing from
the list — or a fine-tune — can still be typed in. If the API can't be reached,
the field simply falls back to plain text: a network problem never leaves you
with an un-fillable form.

**Leaving the model blank** no longer pins a constant. The best available model
is chosen from the live list, preferring the cheap fast tiers (`flash-lite` /
`flash`, `mini`, `haiku`) that suit this task — a constrained extraction, not a
reasoning problem. Hardcoded values remain only as a last resort for when the
list can't be read at all.

## Gemini 3.x: replies were being cut off, not malformed

Setting a newer Gemini model reached the API but failed with:

```text
Expecting ',' delimiter: line 20 column 6 (char 2439)
```

That looks like a broken model. It wasn't. On Gemini 2.5+/3.x, **"thinking"
tokens are drawn from the same budget as the answer**, and these models reason
by default. Our output cap was spent before the JSON was finished, so the reply
arrived truncated mid-structure — hence a parse error at a seemingly random
offset, differing between attempts. It also explains why `gemini-3.1-flash-lite`
worked immediately: lite models think far less.

Three changes:

- **Thinking is disabled for this call** (`thinkingConfig.thinkingBudget = 0`).
  Identification is a constrained extraction against a candidate list supplied
  by the reverse image search — there is nothing to reason about.
- **The output budget is raised** from 3 000 to 8 000 tokens, which the
  five-language reply needs comfortably.
- **JSON mode uses the documented REST spelling** (`responseMimeType`).

## The same hardening for OpenAI and Anthropic

Truncation is not a Gemini quirk — OpenAI's reasoning models (o-series, gpt-5)
also spend reasoning tokens from `max_completion_tokens`, and any model can be
cut short by a budget that is too tight. So instead of inferring truncation
from a parse error after the fact, the integration now reads **the provider's
own stop signal**:

| provider | field | truncated when |
|---|---|---|
| Anthropic | `stop_reason` | `max_tokens` |
| OpenAI | `choices[].finish_reason` | `length` |
| Gemini | `candidates[].finishReason` | `MAX_TOKENS` |

The raised output budget (8 000 tokens) and the model-discovery dropdown apply
to all three providers as well — only the thinking switch is Gemini-specific,
because it is the only one of the three that reasons by default on this call.

All three providers now also constrain the reply format at the API level rather
than trusting the prompt:

| provider | mechanism |
|---|---|
| Anthropic | `output_config.format` with a JSON Schema |
| OpenAI | `response_format: {"type": "json_object"}` |
| Gemini | `responseMimeType: "application/json"` |

> **A note on Anthropic:** prefilling the assistant turn with `{` is the classic
> trick for forcing JSON, but it is no longer supported on Claude 4.6 / Sonnet
> 4.5 and later — adopting it would have re-created exactly the kind of
> obsolescence this release fixes. Structured outputs are the supported
> replacement, and the schema is generated from the same constants the parser
> uses, so the two cannot drift apart. Models released before the feature reject
> it with a `400`; that case is detected and retried once without it, falling
> back to the prompt-driven contract instead of failing.

## Uploading to a Frame that is not there

Two problems compounded when one TV of several was unreachable.

**The gallery card sent uploads to the wrong Frame.** It discovers Frames by
looking for the `art_mode_status` attribute, which an unreachable TV does not
expose — so with two configured and one down, discovery returned a single
Frame. That failed the "more than one, ask the user" test, so no chooser
appeared and the card fell back to the entity named in the card's YAML: the
very TV discovery had just excluded for being unreachable. Now a single
discovered Frame is used directly; two or more still open the chooser.

**And the upload then hung silently.** `art_upload` tried to wake the TV,
waited on a power-on that could never complete, and reported nothing. The
integration now tells a TV in standby (which still answers its REST endpoint)
apart from one that is unplugged or faulty (which does not), and fails straight
away with *"<host> is unreachable — cannot upload"* instead of stalling.

## Famous artworks no longer come back "not identified"

Well-known paintings were being reported as unidentified with a confidence
around 0.1, even though the description of what the model *saw* was accurate.
The pipeline was working; the rules it was given were not.

**Reverse image search often fails on artwork, and fails noisily.** When Google
Vision does not find the picture anywhere, it does not return nothing — it
returns plausible-looking filler: entities like *Painting*, *Art*, *Artwork*,
and page titles like *"How To Master Painting With Zero Experience"* or
*"The Basics Of Digital Illustration - YouTube"*. Two consequences:

- **The filler is now stripped.** Generic entities are pushed behind the
  concrete ones, and tutorial/listicle pages are dropped outright — so an empty
  page list honestly means *found nowhere*, instead of looking well-sourced.
  On a real case from the logs, the useful leads *The Kimono* and
  *Thyssen-Bornemisza National Museum* were sitting third and first in a list
  otherwise made of *Painting / Art / Drawing / Artist / Artwork*, alongside
  five painting tutorials. Genuine museum and Wikipedia pages are untouched.
- **The model may now identify from its own knowledge** when no candidate is
  usable. Previously it was told to confirm a candidate *or nothing* — a
  deliberate guard against invented attributions, but one that made a Renoir
  unidentifiable the moment the reverse search came back empty. It can now name
  a work it genuinely recognises, with `matched_candidate` left `null` and
  **confidence capped at 0.6** to mark that nothing external corroborates it.
  The guard itself stays: recognising a style, a period or a school is
  explicitly *not* recognising the work, and attribution by resemblance is
  still forbidden.

So a high confidence still means "corroborated by the web", and anything at
0.6 or below means "the model recognised it unaided" — the two remain
distinguishable in the sensor attributes.

**The Art Store is not a museum of oil paintings.** Even once it could answer
freely, the model kept declining on graphic works — its own description gave
the reason: *"looks like a modern icon or doodle rather than a traditional
painting"*. It was echoing the instruction, which asked it to recognise "a
famous painting". The catalogue is full of photography, prints, posters,
street art, cartoons and contemporary illustration, so the prompt now says so
explicitly, and an artist's named signature motif counts as an
identification. The refusal rule is unchanged: recognising a style is still
not recognising the work.

**The thumbnail is sent with its real media type.** Every provider was told
`image/jpeg` unconditionally, but a Frame thumbnail is stored as
`current.jpg` whatever the TV actually sent — the Art API reports the true
type in its header. A PNG or WebP announced as JPEG is undefined behaviour,
and it showed: the model described a winged figure as *"a small dog-like
figure, crouched or mid-run"*. The type is now sniffed from the bytes, and
the description came back correct.

**Web entities are explained for what they are: fragments.** Vision returns an
unordered bag — a title here, a holding museum there, the artist somewhere
else, mixed with generic labels. Presented as a flat "candidate" list, the
model treated each one as a whole answer to accept or reject, and rejected
them all. For William Merritt Chase's *The Kimono* it was handed
`The Kimono` **and** `Thyssen-Bornemisza National Museum` — the title and the
museum that actually holds it — and still declined four times out of four,
explaining that *"the specific work is not confidently recognizable"*. The
prompt now says the entities are fragments to be read together, and that
naming one specific work from fragments plus the image counts as a
confirmation, with the artist and date filled in from the model's own
knowledge.

**A lone "not identified" is checked twice.** When there is no candidate to
confirm, the answer rests entirely on what the model recalls — and that is not
deterministic. On one artwork, everything else held constant, four runs gave
two refusals and two correct identifications (Keith Haring, confidence
0.58–0.60). Temperature cannot be lowered to settle it: the current reasoning
models only accept the default. So when the model declines *and* the reverse
search produced nothing to check against, one more sample is taken — a second
refusal is evidence, a single one was a coin toss. Every other path still costs
exactly one call.

**Past failures are retried instead of being served from cache.** A failed
identification was cached for 14 days, so the artworks an improvement is
written for were precisely the ones that could not benefit from it — the old
"not identified" kept being replayed. Cached failures now carry the pipeline
revision that produced them and are ignored once that logic changes, so the
work is re-identified on the next artwork change. Confirmed identifications are
untouched: they stay valid and are not re-fetched.

## Clearer failures

Two error paths that used to mislead:

- **A truncated reply** now says so — *"LLM reply was cut off mid-JSON — the
  model ran out of output tokens"* — instead of `Expecting ',' delimiter`,
  which pointed at the wrong problem entirely.
- **A retired or mistyped model** (HTTP 404) now raises a distinct error naming
  the models your key *can* use, and pointing at *Configure → Art
  Identification*. Previously it retried forever against a model that no longer
  exists.

---

## Picture mode: saying what actually failed

A report of picture mode simply not working ([#197](https://github.com/TheFab21/ha-samsungtv-smart/issues/197))
turned into four separate defects, none of which changed the panel but all of
which hid the real cause.

**The error said nothing.** `Failed to set picture mode 'Movie' via any
capability/form` means every attempt was rejected — but the HTTP errors behind
those rejections were logged at debug level only, so a bug report contained
nothing to act on. They are now named in the error itself:

```text
Failed to set picture mode 'Movie' — every attempt was rejected by SmartThings:
custom.picturemode (name='Movie'): 409 Conflict;
samsungvd.pictureMode (id='modeMovie'): 422 Unprocessable Entity
```

**We were causing our own rate limiting.** Each change fires up to four
commands (two capabilities × two argument forms), plus a refresh and a
read-back. A 422 is a verdict on the *capability*, so retrying it with the
other argument form is a guaranteed-wasted request — and enough of those walk
the device into SmartThings' rate limiter, after which everything fails
regardless. A 422 now marks the capability unsupported, and a 429 abandons the
remaining attempts instead of digging deeper.

**Localized mode names arrived padded.** Samsung returns them with leading
whitespace in some locales (` Prirodzený`, ` Dynamický`), which we passed
straight into the dropdown and back out as the command argument. Now stripped.

**The local fallback was locked to three languages.** When the cloud cannot
apply a picture mode, the integration also sends a WebSocket remote key
directly to the TV. That key was looked up by *display name*, and only English,
French and German were listed — so on any other locale the fallback silently
never fired. It is now looked up by the internal mode id (`modeStandard`,
`modeDynamic`, …), which is the same in every language.

> **Note:** `FILMMAKER MODE` and `Natural` still have no remote key. Rather
> than send an approximation, they send nothing — the table maps "natural" to
> the *Movie* key, and quietly setting the wrong mode is worse than setting
> none.

**And the most consequential one: a command can be accepted and never run.**
`HTTP 200` from SmartThings only means the request was accepted; whether the TV
executed it is in the body:

```json
{"results": [{"id": "…", "status": "FAILED"}]}
```

We logged that verbatim and never read it. In the report above, `refresh`
returned `FAILED` on all twelve calls while the log read like a success — which
is exactly what a TV looks like when it is registered in the SmartThings cloud
but can no longer reach it (commonly: DNS or ad-blocking rules catching
`samsung*` domains). That now raises an explicit warning naming the cause,
rather than leaving a working-looking log and a TV that ignores everything.

---

## Older TVs: the IP Control port moved in 2020

IP Control is the local JSON-RPC channel that provides the backlight, colour
tone, picture calibration and reboot entities, plus a SmartThings-free power
path. It has always been paired on port **1516** — because this integration was
developed against 2024/2025 Frames.

Samsung moved that port once: **1515 up to the 2019 models, 1516 from 2020
onwards**, as documented by the RTI and Allonis control drivers. So every
pre-2020 TV was told, instantly and confidently, that it had no IP Control
server — when it was listening one port down all along.

Pairing now tries 1516, then 1515, and remembers which one answered so every
entity keeps talking to the right port. Confirmed on a 2018 UE50NU8005
([#206](https://github.com/TheFab21/ha-samsungtv-smart/issues/206)), which went
from five entities to a working picture calibration, speaker select and reboot
button. Two things had to line up on that TV: the port, and the existing
weak-Diffie-Hellman TLS fallback, without which the handshake fails outright.

> **Not every model has it**, and the port change does not alter that — some TVs
> simply do not run the server. What changed is that we now ask both doors
> before concluding.

Nothing changes for a TV that already pairs on 1516: it is tried first, in one
attempt, exactly as before.

## Picture mode: the local fallback now works in any language

When the cloud will not apply a picture mode, the integration also sends a
remote key straight to the TV. That fallback was looked up from a table of
**display names in English, French and German** — so on any other language it
quietly did nothing, which is precisely where it was needed most.

Two reports made this visible. A Slovak TV got a key only for `Film`, and a
Norwegian one only for `Standard` — in both cases by coincidence of spelling,
with `Dynamický` and `Dynamisk` left with no local path at all.

The internal mode id (`modeDynamic`, …) is language-independent and is now
tried first. When the TV exposes no id map — which is the case for every model
offering only `custom.picturemode` — the display name is normalised (case and
accents stripped) and matched on its stem, so `Dynamisk`, `Dynamický`,
`Dinâmico`, `Estándar`, `Öko` and their relatives all resolve.

Two modes deliberately still get **no** key, because sending the wrong one is
worse than sending none: **FILMMAKER MODE** (no remote key exists, and it
contains "film", so it would otherwise select Movie), and **Natural** outside
English, whose legacy mapping points at the *Movie* key on evidence we do not
have.

## Clearer pairing failures

Pairing waits up to 30 seconds for the on-screen prompt, so a failure that
comes back *instantly* never got that far — the connection was refused. Both
cases used to produce the same message, telling you to check the TV's state and
the *IP Remote* setting, neither of which can cause a refused connection. A
transport failure now says so, and names the likely cause: the model has no IP
Control server.

---

## Upgrade notes

- No configuration changes anywhere in the 8.6 line. Update via HACS and
  restart Home Assistant.
- **If Artwork Identification stopped working**, open *Configure → Art
  Identification*, clear the **Model** field and save: the best available model
  for your key is selected automatically. Re-opening the page then shows the
  full dropdown.
- **If your TV is a 2019 or earlier model and IP Control never paired**, it is
  worth trying again under *Reconfigure → IP Control* — the port it needs is
  now tried too.
- **If picture mode has never worked on your TV**, the new error message says
  why. A `FAILED` result or a 409 on every attempt means the SmartThings cloud
  cannot reach the TV itself — check the TV's own internet access before
  suspecting the integration.

---

## Changelog

### 8.6.3

- **New:** the `getVideoStates` payload is logged when its shape changes,
  separating fields the TV omitted from fields it returned in a form the slider
  cannot use — a picture slider sitting "unavailable" can now be traced to
  which of the two it is.

- **Fix:** the local remote-key fallback for picture mode is resolved by mode
  id, and by a language-independent match on the display name when the TV
  exposes no id map — it previously worked in English, French and German only
  ([#206](https://github.com/TheFab21/ha-samsungtv-smart/issues/206),
  [#197](https://github.com/TheFab21/ha-samsungtv-smart/issues/197)).

### 8.6.2

- **New:** IP Control pairing tries port 1515 as well as 1516, so TVs from 2019
  and earlier can pair; the working port is remembered per TV
  ([#206](https://github.com/TheFab21/ha-samsungtv-smart/issues/206)).

### 8.6.1

- **Fix:** a pairing attempt that cannot reach the TV is reported as such,
  instead of advice about the TV's state that cannot apply.
- **Fix:** localized picture mode names are stripped of the leading whitespace
  Samsung returns in some locales.
- **Fix:** a failed picture mode change names the SmartThings response for
  every attempt instead of reporting only "via any capability/form"
  ([#197](https://github.com/TheFab21/ha-samsungtv-smart/issues/197)).
- **Fix:** a 422 no longer triggers a second attempt on the same capability,
  and a 429 stops the remaining attempts.
- **New:** a command the cloud accepts but the TV never executes
  (`{"status": "FAILED"}`) raises a warning naming the likely cause, instead of
  appearing in the log as a success.

### 8.6.0

- **New:** the model list is fetched from the provider (Gemini, OpenAI,
  Anthropic) and offered as a dropdown in the config flow, with free text kept
  as an escape hatch.
- **New:** a blank model resolves to the best model the key can use, chosen
  from the live list instead of a hardcoded constant.
- **Fix:** Gemini 2.5+/3.x replies were truncated because thinking tokens share
  the output budget — thinking is now disabled for this call and the budget
  raised ([#188](https://github.com/TheFab21/ha-samsungtv-smart/issues/188)).
- **Fix:** Gemini JSON mode uses the documented REST field name
  (`responseMimeType`).
- **New:** Anthropic replies are constrained by a JSON Schema
  (`output_config.format`), with an automatic fallback for models that predate
  structured outputs.
- **Fix:** truncation is detected from each provider's own stop signal and
  reported as such, instead of a misleading JSON delimiter error.
- **Fix:** an unavailable model raises a dedicated error listing usable models.
- **Fix:** well-known artworks were reported unidentified when reverse image
  search returned only generic filler — the filler is now stripped, and the
  model may identify a work it recognises unaided (confidence capped at 0.6).
- **Fix:** a cached "not identified" is retried when the identification logic
  changes, instead of masking the improvement for up to 14 days.
- **Fix:** the gallery card uploads to a Frame that is actually reachable
  instead of falling back to the configured entity when only one is found.
- **Fix:** an upload to an unreachable TV fails immediately with a clear
  message instead of hanging on a power-on that cannot happen.
