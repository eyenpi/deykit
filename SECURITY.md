# Security

Deykit is a local application, not a multi-user hosted service. Keep the service
on loopback. A project can contain sensitive example inputs, saved responses and
reports; treat backups and exports accordingly. Credentials belong in environment
variables or an approved OS keyring, never project files. Raw report/inspection
content is an explicit opt-in, not permission to share it publicly.

For a vulnerability, use GitHub's **Security → Report a vulnerability** when
private reporting is enabled. If unavailable, request a private contact channel
from the repository owner without posting exploit details, credentials or
sensitive project data in a public issue. Do not upload a complete private project.

Include affected versions, platform, a minimal sanitized reproduction, expected
behavior and impact. No response-time or supported-version guarantee is currently
offered. Maintainers should enable private vulnerability reporting when making
the repository public; see the [public repository checklist](guide/public-repository.md).
