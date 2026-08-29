# adk-python#6836 — our re-test of the maintainers' fix

Posted to [google/adk-python#6836](https://github.com/google/adk-python/issues/6836)
after the ADK team reworked the fix. Fourteen cases against their branch,
including the ones their own suite did not cover.

---

Re-tested, as promised. **This resolves the issue for me, and it is better than what I proposed.**

Clean venv, Python 3.13, google-genai 2.20.0, branch at 14ac8d2. Your own suite: `20 passed`. My table, all against the branch:

| case | result |
|---|---|
| `temperature=0.2` | `temperature is a GenerateContentConfig field. Pass generate_content_config=types.GenerateContentConfig(temperature=...) instead.` |
| `topP=0.9` (camelCase) | resolved and reported as **`top_p`** |
| `maxOutputTokens=256` | resolved and reported as **`max_output_tokens`** |
| `system_instruction=` | `must be set via LlmAgent.instruction` |
| `response_schema=` | `must be set via LlmAgent.output_schema` |
| `temperature=` + `top_p=` | both named, and the suggested constructor carries both |
| `temperatur=0.2` (a real typo) | plain `extra_forbidden` — untouched |
| `tools=[]` | constructs |
| `generate_content_config=...` | constructs |
| `generate_content_config=` + `instruction=` | constructs |
| subclass of `LlmAgent` | inherits the validator |
| `LlmAgent.model_validate({... "temperature": 0.2})` | same error on the dict path |
| `Agent(...)` (the alias) | same error |
| `temperature=None` | still redirected, which is right |

Two things you did that I had not thought of, and that I would keep:

1. **Reporting the canonical name for an alias.** `topP=` fails with `top_p is a GenerateContentConfig field`, so the message teaches the spelling that will actually work rather than echoing the one that failed.
2. **The combined suggestion for several fields at once** — one error that ends in `GenerateContentConfig(temperature=..., top_p=...)` is a copy-paste fix instead of two round trips.

One optional bit of polish, not a blocker, and I would understand leaving it: when a real typo and a config field arrive together (`temperatur=0.2, top_k=5`), the error names `top_k` and stays silent about `temperatur`. The user fixes the config field, re-runs, and only then meets the typo. Same for `system_instruction=` together with `temperature=`: the redirect is reported and the config field is not. If pydantic makes it easy to raise once with both kinds, it would fit the discoverability goal; if it does not, this is a strictly better message than what is on main today.

Thanks for reworking it and for the tests — `test_llm_agent_error_messages.py` covers the cases I care about, including the `tools` gate. From my side this is ready.
