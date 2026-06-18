# Release and backport policy

Stable releases use semantic version tags, immutable multi-architecture image digests, SBOM/provenance attestations, keyless Cosign signatures, and generated notes. Security and serious reliability fixes are backported to the current stable major line when practical. Automatic updates consume stable releases only within the installed major version; major upgrades require operator review.
