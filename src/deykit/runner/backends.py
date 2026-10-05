"""Composition adapters for existing Jev and authored-fixture provider ports."""

from dataclasses import dataclass

from deykit.application.dataset_support import fail, validated_model
from deykit.application.fixtures import FixtureService
from deykit.contracts.errors import ServiceError
from deykit.contracts.ports import ChoiceCompiler, Clock, ProjectSource, ProviderTransport
from deykit.contracts.records import ChoiceDefinition, ProviderProfile
from deykit.providers.choice import JevChoiceCompiler
from deykit.providers.credentials import Credentials, credentials_for
from deykit.providers.fixtures import FixtureInvalid, FixtureTransportFactory
from deykit.providers.jev import JevProvider
from deykit.providers.profiles import ProviderProfiles
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
