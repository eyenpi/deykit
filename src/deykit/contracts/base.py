"""Strict immutable records. Arbitrary user JSON belongs in source strings."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator


class FrozenModel(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid", validate_default=True)


class Record(FrozenModel):
    schema_version: Literal[1] = 1

    @field_validator("schema_version", mode="before")
    @classmethod
    def exact_version(cls, value: Any) -> Any:
        if type(value) is not int or value != 1:
            raise ValueError("unsupported_schema_version")
        return value
