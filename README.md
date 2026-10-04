# Deykit

Deykit is a local typed decision debugger under development. The first implementation
step provides exact JSON/hash handling, strict versioned evidence records, shared
provider/storage contracts and an installable Python foundation.

```sh
uv sync --locked
uv run deykit --version
uv run deykit --help
```

Project authoring, providers, bounded execution and the browser application are being
implemented in subsequent milestone tasks. This foundation makes no live model quality
or provider compatibility claim.

See [development and verification](guide/development.md) and
[architecture contracts](architecture/contracts.md). Licensed under [MIT](LICENSE).
