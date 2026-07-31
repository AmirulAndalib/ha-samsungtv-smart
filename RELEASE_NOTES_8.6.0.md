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
- **Fix:** a truncated LLM reply is reported as such, instead of a misleading
  JSON delimiter error.
- **Fix:** an unavailable model raises a dedicated error listing usable models
  rather than failing silently on every artwork.
