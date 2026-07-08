# License Strategy

Companion doc to constitution's Licensing section. Concrete details for contributors and cohort.

## Licenses

- **All code**: Apache 2.0. Applies to `forge-client-obsidian`, `forge-service`, `forge-runtime`, forge-music, `forge-mcp` (future), and any other Forge implementation code.
- **Documentation and specifications**: CC-BY-4.0. Applies to constitution, protocols (cowork-forge-protocol, cc-prompt-queue), intuitions, deliverables docs, blog posts, README files.
- **Test fixtures and example content**: same license as containing repo.

## Rationale

- **Apache 2.0 for code**: broad compatibility, explicit patent grant, permissive enough for downstream commercial use. MIT considered but Apache's patent grant matters for a project touching LLM tooling.
- **CC-BY-4.0 for docs**: allows redistribution with attribution, encourages citation of the constitution and protocol methodology as research artifacts, doesn't restrict commercial use of derivative documentation.

## Hosted service model

`forge-service` code is open (Apache 2.0). The default hosted instance is a convenience offered by the project maintainer at project cost. Users may:

- Consume the default hosted instance (free at cohort scale).
- Self-host `forge-service` on their own infrastructure using the open source.
- BYOK for LLM calls (bring your own Anthropic API key) if self-hosting.

If usage of the default instance grows to require sustained hosting cost, a paid tier for high-volume access may be introduced. The code stays open regardless.

## Cohort content

Cohort's own vaults, notes, music, simulations, and creative work are theirs. Forge's license applies only to Forge's implementation, not to what cohort produces with it. Cohort may license their own work under whatever they choose.

## Third-party dependencies

- **music21** (BSD-3): forge-music depends on music21. Compatible with Apache 2.0.
- **Pyodide** (MPL-2.0): forge-runtime bundles Pyodide. Compatible; MPL requires source availability for MPL-licensed files.
- **Obsidian API**: forge-client-obsidian is an Obsidian plugin. Obsidian itself is proprietary; plugins interface via a public API and are separately licensed.
- **Anthropic SDK / API**: forge-service uses Anthropic APIs. Consumers of forge-service accept Anthropic's terms of use through their own configuration.

## Contribution model

Contributions welcome under Apache 2.0 (inbound = outbound; contributions land under the same license as the project). No copyright assignment; contributors retain their copyright and grant the project rights via Apache 2.0.

## Not covered here

- Trademarks and naming rights (deferred; may need attention if a competitive fork emerges).
- Enterprise support terms (n/a today).
- SLA on hosted service (best-effort at cohort scale; no formal SLA).

## Related

- Constitution: `~/projects/forge/docs/specs/constitution.md` (Licensing section)
- Third-party attribution ships in each repo's `NOTICE` or `THIRD_PARTY.md` file (to be created per repo as needed).
