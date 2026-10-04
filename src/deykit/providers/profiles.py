"""Local provider profile operations over the authoritative project source port."""

from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.ports import CommitReceipt, ProjectSource, ResourceKey, SourceChange
from deykit.contracts.records import ProviderProfile
from deykit.providers.jev import validate_profile


class ProviderProfiles:
    """Configuration operations deliberately have no transport or credential dependency."""

    def __init__(self, source: ProjectSource) -> None:
        self._source = source

    def read(self, profile_id: str) -> ProviderProfile:
        record = self._source.read(ResourceKey("providers", profile_id))
        if record is None:
            raise LookupError("Provider profile does not exist.")
        profile = load_record(ProviderProfile, record.body)
        if profile.id != profile_id:
            raise ValueError("Stored provider profile identity is inconsistent.")
        return validate_profile(profile)

    def list(self) -> tuple[ProviderProfile, ...]:
        with self._source.consistent_read():
            return tuple(self.read(profile_id) for profile_id in self._source.list_ids("providers"))

    def configure(
        self,
        profile: ProviderProfile,
        *,
        expected_etag: str | None,
        operation_id: str,
    ) -> CommitReceipt:
        validate_profile(profile)
        return self._source.commit(
            operation_id,
            (
                SourceChange(
                    ResourceKey("providers", profile.id),
                    dump_record(profile),
                    expected_etag,
                ),
            ),
        )
