# Filed upstream: https://github.com/googleapis/python-genai/issues/2889

**Title:** Vertex structured output silently returns empty dict-typed fields (additionalProperties) — model complies but the payload arrives stripped

## Summary

With a Pydantic response schema containing a plain dict field:

```python
class AuditResult(BaseModel):
    mappings: dict[str, list[str]]
```

used as `response_schema` on Vertex (`gemini-3.5-flash-lite`, location
`global`), the model is explicitly instructed to return e.g.
`{"mappings": {"alg-factor-1": ["A-SSE.2"]}}` — and the API response contains
`"mappings": {}` every time. No error, no warning: `dict[str, ...]` compiles to
JSON-Schema `additionalProperties`, which Vertex structured output does not
honor, so the field arrives empty.

## Why this is worse than a rejection

The call succeeds and validates. In our grading pipeline the curriculum-audit
agent silently reported zero curriculum coverage for weeks of development — the
feature was fully dead in production while every test on the SDK surface
passed. A hard error on unsupported schema constructs (or dropping the field
from the generated schema with a warning) would have surfaced this instantly.

## Reproduction

1. Define the model above; call `generate_content` on Vertex with
   `response_mime_type="application/json"`, `response_schema=AuditResult`.
2. Prompt: "Return mappings = {'alg-factor-1': ['A-SSE.2']}".
3. Observe `mappings == {}` in the parsed response.

Workaround we shipped: a list-shaped wire model
(`[{"criterion_id": ..., "competency_codes": [...]}]`) converted back to the
dict-shaped domain model after parsing.

## Environment

google-genai 2.18.1 (Vertex mode), gemini-3.5-flash-lite @ global, Python 3.13.
Found while building a K-12 exam-grading fleet for the All Things Agentic
hackathon.
