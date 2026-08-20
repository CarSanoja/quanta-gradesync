# Draft issue — google/adk-python

**Title:** LlmAgent rejects `temperature=` with extra_forbidden — no discoverable path from the most common generation knob to the right field

## Summary

Coming from `google-genai` (where `GenerateContentConfig(temperature=...)` is
routine), the natural first attempt with ADK is:

```python
from google.adk.agents import LlmAgent

agent = LlmAgent(
    name="grader",
    model="gemini-3.5-flash-lite",
    instruction="...",
    output_schema=MySchema,
    temperature=0.1,
)
```

On ADK 2.7.0 this fails at construction time:

```
pydantic_core._pydantic_core.ValidationError: 1 validation error for LlmAgent
temperature
  Extra inputs are not permitted [type=extra_forbidden, input_value=0.1, input_type=float]
```

The working form is `generate_content_config=genai_types.GenerateContentConfig(temperature=0.1)`,
but nothing in the error, the docstring, or the validation message points there.
In our project this crashed every structured agent in a production pipeline and
cost a debugging session to trace (model_fields introspection).

## Suggested fixes (any one would do)

1. Accept `temperature` as a convenience kwarg and fold it into
   `generate_content_config`.
2. Or add a custom pydantic error message for common generation kwargs
   (`temperature`, `top_p`, `max_output_tokens`) pointing to
   `generate_content_config`.
3. Or document the mapping prominently in the LlmAgent docstring.

## Environment

google-adk 2.7.0, google-genai 2.18.1, Python 3.13, macOS. Found while building
a K-12 exam-grading fleet for the All Things Agentic hackathon.
