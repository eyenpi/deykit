"""Explicit column mapping; metadata and expectations cannot alias input columns."""

from typing import Literal, Self

from pydantic import Field, model_validator

from deykit.contracts.base import FrozenModel, Record
from deykit.contracts.identities import ResourceId


class InputField(FrozenModel):
    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    parse_json: bool = False


class OptionAlias(FrozenModel):
    value: str
    option_id: ResourceId


class ImportMapping(Record):
    input_kind: Literal["text", "json"]
    input_column: str | None = None
    input_parse_json: bool = False
    fields: tuple[InputField, ...] = ()
    id_column: str | None = None
    expected_column: str | None = None
    expected_parse_json: bool = False
    option_aliases: tuple[OptionAlias, ...] = ()
    group_column: str | None = None
    tags_column: str | None = None
    tags_parse_json: bool = False
    split_column: str | None = None
    metadata_column: str | None = None
    metadata_parse_json: bool = False

    @model_validator(mode="after")
    def explicit_separation(self) -> Self:
        if bool(self.input_column) == bool(self.fields):
            raise ValueError("choose_input_column_or_fields")
        if self.fields and (self.input_kind != "json" or self.input_parse_json):
            raise ValueError("invalid_field_mapping")
        if len({field.target for field in self.fields}) != len(self.fields):
            raise ValueError("duplicate_target_field")
        if len({alias.value for alias in self.option_aliases}) != len(self.option_aliases):
            raise ValueError("duplicate_option_alias")
        metadata = tuple(
            column
            for column in (
                self.id_column,
                self.expected_column,
                self.group_column,
                self.tags_column,
                self.split_column,
                self.metadata_column,
            )
            if column is not None
        )
        inputs = (
            (self.input_column,)
            if self.input_column is not None
            else tuple(field.source for field in self.fields)
        )
        if any(not column for column in metadata) or set(inputs).intersection(metadata):
            raise ValueError("input_metadata_overlap")
        if len(set(metadata)) != len(metadata):
            raise ValueError("metadata_column_overlap")
        if (
            (self.input_parse_json and self.input_column is None)
            or (self.expected_parse_json and self.expected_column is None)
            or (self.tags_parse_json and self.tags_column is None)
            or (self.metadata_parse_json and self.metadata_column is None)
        ):
            raise ValueError("parse_flag_without_column")
        if self.option_aliases and self.expected_column is None:
            raise ValueError("aliases_without_expectations")
        return self
