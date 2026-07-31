# Release notes — 8.6.0

If this project is useful to you, you can support its development:

# <a href="https://buymeacoffee.com/thefab21" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-black.png" alt="Buy Me A Coffee" height="41" width="174"></a>

> **Status: stable release.** Focused on Artwork Identification: it stops
> breaking when a provider retires a model, and it works with the current
> generation of reasoning models. No breaking changes; existing configurations
> keep working.

## Highlights

- **The model list is now read from your provider**, instead of being
  hardcoded — so a retired model no longer silently breaks identification.
- **Gemini 3.x models work.** Identification failed with a cryptic JSON error
  on the newer models; the cause was the reply being cut off, not malformed.
- **A model that becomes unavailable now tells you so**, and lists the models
  your key can actually use.

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

## Upgrade notes

- No configuration changes. Update via HACS and restart Home Assistant.
- **If Artwork Identification stopped working**, open *Configure → Art
  Identification*, clear the **Model** field and save: the best available model
  for your key is selected automatically. Re-opening the page then shows the
  full dropdown.
- Nothing else in the integration is affected — this release touches only the
  identification pipeline and its configuration step.

---

## Changelog

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
- **Fix:** truncation is detected from each provider's own stop signal
  (`stop_reason` / `finish_reason` / `finishReason`) and reported as such,
  instead of a misleading JSON delimiter error.
- **Fix:** an unavailable model raises a dedicated error listing usable models
  rather than failing silently on every artwork.
- **Fix:** the gallery card uploads to a Frame that is actually reachable
  instead of falling back to the configured entity when only one is found.
- **Fix:** a cached "not identified" is retried when the identification logic
  changes, instead of masking the improvement for up to 14 days.
- **Fix:** well-known artworks were reported unidentified when reverse image
  search returned only generic filler — the filler is now stripped, and the
  model may identify a work it recognises unaided (confidence capped at 0.6).
- **Fix:** an upload to an unreachable TV fails immediately with a clear
  message instead of hanging on a power-on that cannot happen.
