"""Composition adapters for existing Jev and authored-fixture provider ports."""

from dataclasses import dataclass

from deykit.application.dataset_support import fail, validated_model
from deykit.application.errors import ServiceFailure
from deykit.application.fixtures import FixtureService
from deykit.contracts.codec import load_record
from deykit.contracts.errors import ServiceError
from deykit.contracts.json_value import JsonError
from deykit.contracts.ports import (
    ChoiceCompiler,
    Clock,
    ProjectSource,
    ProviderTransport,
    ResourceKey,
    StoredRecord,
)
from deykit.contracts.records import ChoiceDefinition, FixtureSet, ProviderProfile
from deykit.providers.choice import JevChoiceCompiler
from deykit.providers.credentials import Credentials, credentials_for
from deykit.providers.fixtures import FixtureInvalid, FixtureTransportFactory, validate_fixture_set
from deykit.providers.jev import JevProvider
from deykit.providers.profiles import ProviderProfiles, validate_provider_profile
from deykit.runner.ports import Backend


@dataclass(frozen=True)
class LiveBackend:
    provider: JevProvider

    @property
    def compiler(self) -> ChoiceCompiler:
        return JevChoiceCompiler()

    def preflight(
        self, decision_id: str, dataset_id: str, definition: ChoiceDefinition | None = None
    ) -> ServiceError | None:
        if definition is not None and len(definition.questions[0].options) > 255:
            return ServiceError(code="preflight_failed", reason="unsupported_option_count")
        return self.provider.preflight()

    def for_case(self, case_id: str) -> ProviderTransport:
        return self.provider


@dataclass(frozen=True)
class FixtureBackend:
    factory: FixtureTransportFactory

    @property
    def compiler(self) -> ChoiceCompiler:
        return JevChoiceCompiler()

    def preflight(
        self, decision_id: str, dataset_id: str, definition: ChoiceDefinition | None = None
    ) -> ServiceError | None:
        if definition is not None and len(definition.questions[0].options) > 255:
            return ServiceError(code="preflight_failed", reason="unsupported_option_count")
        fixture = self.factory.fixture_set
        if fixture.decision_id != decision_id or fixture.dataset_id != dataset_id:
            return ServiceError(code="preflight_failed", reason="fixture_context_mismatch")
        return None

    def for_case(self, case_id: str) -> ProviderTransport:
        return self.factory.for_case(case_id)


class ProviderBackends:
    def __init__(
        self, source: ProjectSource, clock: Clock, credentials: Credentials | None = None
    ) -> None:
        self.source = source
        self.fixtures = FixtureService(source, clock)
        self.credentials = credentials

    @staticmethod
    def _fixture_set_record(stored: StoredRecord, fixture_set_id: str) -> FixtureSet:
        try:
            fixture_set = load_record(FixtureSet, stored.body)
            if fixture_set.id != fixture_set_id:
                raise ValueError
            validate_fixture_set(fixture_set)
            return fixture_set
        except (JsonError, ValueError, FixtureInvalid) as error:
            reason = error.code if isinstance(error, JsonError) else getattr(error, "reason", None)
            fail(reason or "invalid_fixture_set", "preflight_failed")

    @staticmethod
    def _provider_profile_record(stored: StoredRecord, provider_id: str) -> ProviderProfile:
        try:
            profile = load_record(ProviderProfile, stored.body)
            if profile.id != provider_id:
                raise ValueError
            return validate_provider_profile(profile)
        except (JsonError, ValueError, ServiceFailure):
            fail("invalid_provider_profile", "preflight_failed")

    @staticmethod
    def _captured_record(
        records: tuple[StoredRecord, ...], key: ResourceKey, reason: str
    ) -> StoredRecord:
        stored = next((record for record in records if record.key == key), None)
        if stored is None:
            fail(reason, "preflight_failed")
        return stored

    def profile_captured(
        self,
        provider_id: str | None,
        fixture_set_id: str | None,
        records: tuple[StoredRecord, ...],
    ) -> ProviderProfile:
        """Resolve only the profile bytes from the planner's already captured epoch."""
        if fixture_set_id is not None:
            fixture_record = self._captured_record(
                records, ResourceKey("fixtures", fixture_set_id), "fixture_set_missing"
            )
            fixture = self._fixture_set_record(fixture_record, fixture_set_id)
            if provider_id is not None:
                profile_record = self._captured_record(
                    records, ResourceKey("providers", provider_id), "invalid_provider_profile"
                )
                return self._provider_profile_record(profile_record, provider_id)
            return ProviderProfile(
                id="fixture-" + fixture.content_hash[:32],
                adapter="fixture",
                requested_model=fixture.model_identity,
                destination="fixture:jev-choice",
            )
        if provider_id is None:
            fail("provider_required", "preflight_failed")
        profile_record = self._captured_record(
            records, ResourceKey("providers", provider_id), "invalid_provider_profile"
        )
        return self._provider_profile_record(profile_record, provider_id)

    def resolve_captured(
        self,
        profile: ProviderProfile,
        fixture_set_id: str | None,
        records: tuple[StoredRecord, ...],
    ) -> Backend:
        """Build a planner backend from the exact fixture record captured with its plan."""
        profile = validated_model(ProviderProfile, profile, "invalid_provider_profile")
        if fixture_set_id is not None:
            fixture_record = self._captured_record(
                records, ResourceKey("fixtures", fixture_set_id), "fixture_set_missing"
            )
            fixture = self._fixture_set_record(fixture_record, fixture_set_id)
            try:
                return FixtureBackend(FixtureTransportFactory(fixture, profile))
            except FixtureInvalid as error:
                fail(error.reason, "preflight_failed")
        if profile.adapter != "jev":
            fail("fixture_set_required", "preflight_failed")
        try:
            return LiveBackend(JevProvider(profile, self.credentials or credentials_for(profile)))
        except ValueError:
            fail("invalid_provider_profile", "preflight_failed")

    def profile(self, provider_id: str | None, fixture_set_id: str | None) -> ProviderProfile:
        if fixture_set_id is not None:
            fixture = self.fixtures.read(fixture_set_id).fixture_set
            if provider_id is not None:
                return self.fixtures.read_profile(provider_id)
            return ProviderProfile(
                id="fixture-" + fixture.content_hash[:32],
                adapter="fixture",
                requested_model=fixture.model_identity,
                destination="fixture:jev-choice",
            )
        if provider_id is None:
            fail("provider_required", "preflight_failed")
        try:
            return ProviderProfiles(self.source).read(provider_id)
        except (LookupError, ValueError):
            fail("invalid_provider_profile", "preflight_failed")

    def resolve(self, profile: ProviderProfile, fixture_set_id: str | None) -> Backend:
        profile = validated_model(ProviderProfile, profile, "invalid_provider_profile")
        if fixture_set_id is not None:
            try:
                return FixtureBackend(
                    FixtureTransportFactory(self.fixtures.read(fixture_set_id).fixture_set, profile)
                )
            except FixtureInvalid as error:
                fail(error.reason, "preflight_failed")
        if profile.adapter != "jev":
            fail("fixture_set_required", "preflight_failed")
        try:
            return LiveBackend(JevProvider(profile, self.credentials or credentials_for(profile)))
        except ValueError:
            fail("invalid_provider_profile", "preflight_failed")
