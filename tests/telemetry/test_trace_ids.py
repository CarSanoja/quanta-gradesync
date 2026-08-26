from autocurricula.core.telemetry import cloud_trace_id, cloud_trace_url


def test_cloud_trace_id_is_identity_for_32_hex() -> None:
    trace_id = "0123456789abcdef0123456789abcdef"
    assert cloud_trace_id(trace_id) == trace_id
    assert cloud_trace_id(trace_id.upper()) == trace_id


def test_cloud_trace_id_falls_back_to_deterministic_hash() -> None:
    first = cloud_trace_id("job-42-trace")
    second = cloud_trace_id("job-42-trace")
    assert first == second
    assert len(first) == 32
    assert int(first, 16) > 0
    assert first != cloud_trace_id("job-43-trace")


def test_cloud_trace_url_requires_project_and_trace() -> None:
    assert cloud_trace_url("", "job-42-trace") is None
    assert cloud_trace_url("proj", "") is None
    url = cloud_trace_url("proj", "0123456789abcdef0123456789abcdef")
    assert url is not None
    assert "project=proj" in url
    assert "tid=0123456789abcdef0123456789abcdef" in url
