import base64
import binascii
import json
from typing import Any

from pydantic import ConfigDict, Field

from autocurricula.schemas.common import ClassId, FrozenStrictModel, JobId, TzAwareDatetime


class PubSubJobEvent(FrozenStrictModel):
    job_id: JobId
    bucket: str = Field(min_length=1)
    exam_batch_prefix: str = Field(min_length=1)
    class_id: ClassId
    subject: str = Field(min_length=1)
    triggered_at: TzAwareDatetime


class PubSubMessage(FrozenStrictModel):
    model_config = ConfigDict(populate_by_name=True)

    data: str = ""
    attributes: dict[str, str] = Field(default_factory=dict)
    message_id: str = Field(min_length=1, alias="messageId")
    publish_time: TzAwareDatetime | None = Field(default=None, alias="publishTime")


class PubSubEnvelope(FrozenStrictModel):
    message: PubSubMessage
    subscription: str = Field(min_length=1)


def parse_push_body(body: dict[str, Any]) -> PubSubJobEvent:
    envelope = PubSubEnvelope.model_validate(body)
    try:
        decoded = base64.b64decode(envelope.message.data, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError) as error:
        raise ValueError("pubsub message data is not valid base64-encoded utf-8") from error
    try:
        payload = json.loads(decoded)
    except json.JSONDecodeError as error:
        raise ValueError("pubsub message data is not valid json") from error
    return PubSubJobEvent.model_validate(payload)
