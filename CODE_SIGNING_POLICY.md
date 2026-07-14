# Code signing policy

Swim Balham is applying to the SignPath Foundation open-source code-signing program. The current `v1.0.0` release is unsigned. If approved, future Windows release binaries will use **free code signing provided by SignPath.io, certificate by SignPath Foundation**.

## Project roles

- Committer and reviewer: [Zak Mobariz (`@zmobariz`)](https://github.com/zmobariz)
- Signing approver: [Zak Mobariz (`@zmobariz`)](https://github.com/zmobariz)

These roles will be expanded if additional trusted maintainers join the project.

## Release process

1. Source changes are committed to the public GitHub repository.
2. GitHub Actions runs the automated tests and builds `SwimBalham.exe` from the tagged source.
3. GitHub records build provenance through an artifact attestation and publishes a SHA-256 checksum.
4. If the SignPath application is approved, only artifacts produced from the public release workflow will be submitted for signing.
5. The signed binary and checksum will be published on the corresponding GitHub Release.

The SignPath private key is managed by SignPath and is not available to project maintainers or stored in the repository.

## Security and privacy

Maintainer access to GitHub and SignPath must use multi-factor authentication. Signing requests are limited to binaries built from this repository's open-source code and release workflow.

Swim Balham has no analytics or telemetry. Its network connections and local data handling are documented in the [Privacy Policy](PRIVACY.md). Vulnerabilities should be reported according to the [Security Policy](SECURITY.md).
