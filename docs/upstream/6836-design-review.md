# adk-python#6836 — the design argument, and the patch we built to test it

Posted to [google/adk-python#6836](https://github.com/google/adk-python/issues/6836)
while the maintainers were deciding between two shapes of fix. We built the
one they preferred against adk-python 2.7.0 to check it survived contact.

---

Following up on Dean's redirect, since I filed this one and had already signed off on the kwargs version.

To be clear about what my earlier test did and did not say: #6837 does fix the failure and I stand by those five results. Dean's objection is about API surface rather than correctness, and on that axis I think he is right — it is also the option I put in the issue. The title is "no discoverable path", and what cost me the session was not that `temperature=` is rejected: it is that the raw failure is literally the single word `temperature`. An error that names the destination fixes that for all 35 fields at once, where accepting a subset leaves the rest failing the same way, now against a learned expectation that generation settings work as kwargs.

I built Dean's spec against adk-python 2.7.0 to check it survives contact — a `model_validator(mode="before")` that fires only on keys unknown to `LlmAgent` which are also `GenerateContentConfig` fields, about 25 lines:

| case | result |
|---|---|
| `temperature=0.2` | error naming `generate_content_config=types.GenerateContentConfig(temperature=...)` |
| `system_instruction=` / `response_schema=` | redirected to `instruction` / `output_schema` |
| `temperature=` and `top_p=` together | both named in one error, not just the first |
| `temperatur=0.2` (a real typo) | untouched: plain `extra_forbidden`, no lecture |
| `tools=[]`, `generate_content_config=...` | construct normally |
| subclasses of `LlmAgent` | inherit the validator |

Two things from @a2105z's PR that should survive into the smaller shape:

1. The `system_instruction` / `response_schema` redirect map. It is the best idea in the thread and it reads better than what I originally asked for.
2. The camelCase alias map. All 35 config fields carry an alias, so `topP=` and `maxOutputTokens=` are as likely a first attempt as the snake_case spellings; without the alias lookup they fall back to a bare `extra_forbidden` and the fix misses exactly the users it is for.

One trap for whoever writes it: `tools` is the only name present on both `LlmAgent` and `GenerateContentConfig` (35 config fields against 33 agent fields today). Gating on "unknown to the agent" rather than "matches a config field" is what keeps `tools` working — worth a regression test so it cannot drift into hijacking it.

@a2105z happy to hand you the implementation and the edge-case tests so this stays your PR, or to open it myself if you would rather not redo it — whichever unblocks it faster. Either way I will re-test whatever lands before merge.
