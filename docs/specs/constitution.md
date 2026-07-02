# Forge — Core Invariants and Discipline (V2a v12)

## Mission

Forge is a **constructionist environment**. People learn — and create
their most meaningful work — by making artifacts they care about, in a
medium that lets them tinker freely. The system exists to make that
possible at every scale: a beginner making their first parametric
greeting, a student composing a 12-bar blues, a researcher orchestrating
a multi-note simulation.

The building blocks are **notes** — markdown files with frontmatter
and one or more facets. Notes come in two shapes: an **action note**
that computes a result, and a **data note** that stores literal
content. Both must be:

- **Concrete** — every note produces a visible, immediately legible
  artifact (text, score, image, simulation, computed value). The user
  sees what they made.
- **Parametric** — every note exposes inputs the user can tweak and
  re-run. Variation is cheap.
- **Composable** — notes call notes; small things become bigger
  things; the call graph is visible to author and reader, not hidden.
- **Personally meaningful** — users author for what *they* want to
  build, not for a curriculum's prescribed exercises.

The environment itself must have:

- A **low floor** — the cost to author and run a first note is small.
  A beginner can be productive within minutes.
- A **high ceiling** — the cost to author the hundredth note stays
  small. Complex work composes from simple parts without combinatorial
  pain.
- **Wide walls** — many directions to play (music, simulation, math,
  image, text, anything code can do), not a single linear curriculum.

**Every design decision is evaluated against the play loop.** Does this
make adding a note cheaper or more expensive? Does this make tweaking
a value cheaper or more expensive? Does this make sharing a creation
cheaper or more expensive? If a feature costs the user more than it
gives, it is the wrong feature — even if it is elegant.

**The LLM is in service of the play loop, not the other way around.**
The LLM lowers the entry barrier (free Description → structured Recipe)
and is allowed to be slow or fuzzy *at transpile time*. At runtime, the
system is deterministic, debuggable, and cheap — so users iterate without
waiting and without per-click LLM cost. Architectural guarantees below
serve this principle.

**The canonical form is Recipe** (V2 paradigm; supersedes the V1
canonical-English / E-- design). Every V2 action note has a Description
facet (free prose capturing intent + mechanics + inputs) and a Recipe
facet (a structured grammar that compiles deterministically to Python).
The Recipe uses chips ([[note]] references, control flow, `{{ ... }}`
value slots) so the call graph is legible without specifying mechanism.
The LLM is invoked only at `/generate` time (Description → Recipe) and
at `/resolve-slot` time (`{{ ... }}` → Python expression) — never to
decide program structure at runtime. After Recipe is in hand, the
deterministic transpiler emits Python; the LLM is out of the runtime
path. This is the load-bearing implementation choice that makes the
runtime determinism + cheap-tweak properties above realizable. Legacy
V1 action notes (English + Python facets) remain valid; the engine
accepts both shapes during the V1 → V2 migration period.

The clauses that follow (Purpose, Core abstractions, A/B/F/D/C-series)
are the invariants and disciplines that make this mission realizable.
When a decision is unclear, the mission is the yardstick.

## Vocabulary

Adopted from V2 specification §1, June 2026. These terms are
authoritative throughout this document and the engine. The V2a v12
sweep amendment (2026-07-03) migrated remaining "snippet" occurrences
in A-series, B-series, Data, Snapshots, and Cultural sections to V2
vocabulary. `snippet_id` and `AmbiguousSnippetResolutionError` retain
V1 naming as engine-code identifiers; source-side renames are
tracked separately.

1. **Note** — the file unit. A `.md` file with frontmatter and one or
   more facets. The umbrella term covering both shapes below.
2. **Action note** — a note that returns a computed result. Replaces
   the V1 term "action snippet."
3. **Data note** — a note that returns literal data. Replaces the V1
   term "data snippet."
4. **Description** — free-prose facet capturing intent + mechanics +
   design notes + parameter documentation. Required on every V2 action
   note. Replaces the V1 "English facet."
5. **Recipe** — structured-recipe facet that compiles to Python.
   Required on every V2 action note. Uses chip-call syntax
   (`Let X = Y.`, `Call [[chip]] with k=v.`, `Return X.`,
   `If/Otherwise`, `For each/Repeat`, `{{...}}` slots).
6. **Python** — the compiled-from-Recipe Python facet. Always present
   at compute time; visible to the cohort when toggled, editable by
   engineers. The canonical facet (the one that actually runs) is
   determined by which layer was last hand-edited; the implicit-
   locking state machine (S9) routes accordingly.
7. **Chip** — a palette UX construct. The chip palette displays
   clickable entries that insert wikilinks + Recipe-grammar shapes
   into the active note. Each chip in the palette references a note
   (library note per §12, or vault note per §13). "Chip" is NOT the
   model concept for callable primitives — the model concept is the
   note that the chip references. Per V2a v11.2 amendment closing
   the chip-as-model-concept conflation.
8. **Chip palette** — the UI affordance for inserting chips +
   control-flow into a Recipe. Not a model concept.
9. **Library** — the union of engine primitives + vault notes that
   are callable.
10. **Cohort author** — composes notes from existing chips. Writes
    Description + Recipe. Never writes Python directly.
11. **Engineer** — extends the library by adding library notes (per
    §12) in `forge/forge/<domain>/lib.py`.
12. **Library note** — a callable action note shipped by the engine.
    The Python source lives in `forge/forge/<domain>/lib.py`; the
    note's facets are served read-only via the plugin's library-note
    view (Description from the function's docstring, Recipe from a
    synthetic signature, Python from the function source). Library
    notes are virtual at the vault level (no `.md` file materializes;
    the view renders directly from the `lib.py` introspection). They
    are callable from any Recipe via wikilink.
13. **Vault note** — a callable action note authored by the cohort.
    Full V2 shape (Description + Recipe + Python) with implicit-
    locking state machine per S9. Callable from any Recipe via
    wikilink. Distinct from library notes only in authorship (cohort
    vs engine) and editability (read-write vs read-only).

Every chip in the palette MUST correspond to a note (library or
vault). There are no chips without backing notes. The conflation of
chip-as-model-concept and chip-as-palette-entry shipped in V2a v11.0
was the prior framing; V2a v11.2 separates them.

The terms above are the V2 paradigm. V1 vocabulary ("snippet,"
"English facet") remains valid in the engine source and in legacy
content (e.g., `forge-music/blues/*.md`) and SHOULD be migrated to V2
on a per-vault basis. V1 and V2 notes coexist in the same vault; the
engine accepts both shapes.

## Purpose

Forge is a research environment for AI-augmented creative work. Humans
articulate intent in English; LLMs help realize it in Python; the system
runs the Python and renders the result. Forge optimizes for expressivity
and improv, accepting that reproducibility and other architectural
guarantees are traded away for flexibility and creative range.

The work in Forge is meant to feel less like writing a deterministic
program and more like improvising at an instrument: each unfrozen
performance may differ, each iteration explores a different realization,
the artifacts are alive rather than fixed. Snapshots and freezing exist
so that the user can stabilize parts of the DAG at will, locking
specific improvisations in place while the rest stays live.

## Core abstractions

**S1.** A *note* is a markdown file with frontmatter and one or more
facets. Notes come in two shapes:

- An **action note** (V2: Description + Recipe + optional Python;
  V1: English + Python) returns a computed result.
- A **data note** has stored content (either inline body or a sibling
  asset file referenced by `content_ref`) and returns the deserialized
  value.

Identified by `<vault_name>/<note_id>`.

**S2.** A *vault* is a directory containing notes and a `forge.toml`
manifest declaring name, version, description, and optional dependencies
on other vaults.

**S3.** The *registry* is a JSON catalog mapping vault names to versioned
tarball URLs with SHA-256 integrity hashes.

**S4.** The *built-in vault* (`forge`) is bundled inside the engine and
contains platform machinery (install, registry/lookup, etc.).

**S5.** A *data note* is a note whose stored content (rather than
executable Python) is the value it represents. Content lives inline in
the body for text content types, or in a sibling asset file referenced
by `content_ref` for binary content types. Data notes have no
Description / Recipe / Python facets. They may be hand-authored by
users, captured from compute results, or system-generated by Forge as
snapshots.

**S6.** A *snapshot* is a system-generated data note capturing the
most recent computed value on a specific edge of the DAG (a
caller-callee pair). Forge writes snapshots automatically; users do
not author them directly. Snapshots are the storage mechanism Forge
uses to implement edge-level freezing.

**S7.** *Infrastructure files vs. notes.* Markdown files whose basename
starts with an underscore (`_`) are treated as vault **infrastructure
files**, not notes. They are excluded from note-registry discovery,
from chip-palette auto-derivation, from the Forge-click compute
surface, and from the static dependency analyzer. Examples:
`_chips.md` (chip palette curation), `_meta/*.md` files (vault
metadata), future `_config.md`, `_aliases.md`, etc. The `_` prefix is
a syntactically-explicit convention so authors know which files are
"real content" vs which are "tooling configuration" without reading
frontmatter. Infrastructure files MAY still be valid data notes in
shape (with frontmatter + body), and may be read by tooling (engine,
plugin, registry) via explicit-name lookups — they're simply not
auto-discovered as part of the note inventory. Auto-discovery rules in
registry-building, chip-palette construction, and any future discovery
surfaces MUST honor this exclusion.

**S8.** *Facet structure for V2 action notes.* A V2 action note has
three facets, in this order in the markdown body:

1. `# Description` — required. Free prose describing intent +
   mechanics + design notes. Optionally contains a `## Inputs`
   sub-section listing parameters with descriptions. The Description
   is the load-bearing facet for `/generate` (LLM reads it to produce
   Recipe) and for cohort comprehension.
2. `# Recipe` — required for V2 action notes. Structured grammar that
   compiles to Python via the forge-transpile service. Uses chip-call
   syntax (per Vocabulary item 5).
3. `# Python` — required in the source file. All three facets are
   always visible + always editable per the S9 uniform-visibility
   contract (V2a v11.3). When hand-edited, takes precedence over
   Recipe per the implicit-locking state machine (S9). New V2
   templates seed Python with `def compute(context): return None` so
   the section is populated from note creation.

A V1 action note has two facets (`# English` + `# Python`) and uses
frontmatter `inputs: []` for parameter declaration. V1 notes remain
valid; the engine accepts both shapes. New action notes SHOULD be
authored as V2.

**S9.** *Implicit-locking state machine for V2 action notes.* Three
SHA-256 hashes in frontmatter (`description_hash`, `recipe_hash`,
`python_hash`) track which facets have been hand-edited since the
last synced state. The **canonical facet** — the source-of-truth
facet, the one whose content actually drives what Forge-click runs —
is whichever was most recently hand-edited:

- All three hashes match stored: **synced** state; running Python
  produces output matching all three facets.
- Description hash drifted: cohort is editing Description; Recipe
  regenerates from Description on next `/generate`; Python then
  recompiles from Recipe on next Forge-click.
- Recipe hash drifted: cohort is editing Recipe; Python recompiles
  from Recipe on next Forge-click; Description stays as documentation
  of the prior intent.
- Python hash drifted: engineer is editing Python directly; Python
  runs as-is (no transpile), Recipe + Description treated as
  documentation (they no longer drive runtime; the engineer's Python
  is authoritative).

**Uniform-visibility contract (V2a v11.3, preserved in v11.4).** All three facets
(`# Description`, `# Recipe`, `# Python`) are always visible and
always editable in the source markdown — there is no toggle to hide
Python and no default that presents fewer than three sections. The
V2a v11.0 "Toggle Python visibility" command is retired; new-note
templates seed Python with a `def compute(context): return None`
stub so the section is populated from creation. Rationale: Python
IS what the engine runs; hiding it from cohort by default was a
false-modesty design choice that made "which layer is running?"
harder to answer at a glance. Cohort authoring stays through the
Description/Recipe path; Python's visibility does not push cohort
into engineer mode.

**Tri-state visibility (V2a v11.4).** V11.4 supersedes v11.3's
binary source/reference suffix with a tri-state
source/derived/stale contract. Each facet's state is auto-annotated
by the CM6 view plugin with a state suffix and body decoration:

- `— source`, full color: this facet drives runtime; content is
  authoritative.
- `— derived`, 60% opacity: this facet was auto-produced from the
  current source and its stored `<facet>_derived_from_source_hash`
  matches the canonical's current hash (recently forged).
- `— stale`, 40% opacity: this facet's content does not reflect
  current source. Either upstream of canonical in the D→R→P chain
  (upstream never regenerates automatically), or downstream with a
  stored `derived_from_source_hash` that no longer matches — cohort
  edited source after last forge.

State computation is symmetric-by-construction: `facet === canonical`
is source; upstream of canonical is inherently stale; downstream
compares `<facet>_derived_from_source_hash` against `<canonical>_hash`.

Frontmatter schema additions (v11.4):
- `description_derived_from_source_hash` (rare; only when a future
  reverse-derivation path is added).
- `recipe_derived_from_source_hash` — stamped when Recipe is
  auto-produced from Description (`/generate`).
- `python_derived_from_source_hash` — stamped when Python is
  auto-produced from Description or Recipe (Forge-click transpile).

Suffix widgets are view-only CM6 decorations. On-disk `# Description`
/ `# Recipe` / `# Python` heading text stays clean.

Cohort norm: forge after editing to normalize downstream from stale
back to derived. Direct edits to any facet promote it to source; other
facets recompute state on next render.

CM6 decorations + status bar surface the canonical layer to the
cohort. A confirmation modal protects against unintended overwrite
when `/generate` would clobber a hand-edited Recipe. The hash-driven
locking replaces the V1 explicit-lock mechanism (`lock` / `unlock`
commands, removed v0.2.197).

**S10.** *Engineer-mode action notes — third operational shape between
V1 and full-V2.*

Some action notes carry Python logic that V2 Recipe grammar cannot
express: lambdas, comprehensions, music21 object construction with
bound method references, complex try/except, dynamic attribute access,
etc. These notes need to be authored as V2-shaped (so they participate
in the V2 ecosystem — Description for cohort comprehension, Recipe
heading for the chip palette + display contract) while remaining
engineer-owned operationally (the canonical layer is Python, hand-
authored, and runs as-is on Forge-click).

The convention:

1. **Frontmatter signal**: `edit_mode: python` MUST appear in the
   frontmatter.
2. **Facet structure**: Description + Recipe + Python all present
   (V2-shaped per S8), where Recipe body is a single HTML comment
   indicating engineer-mode (e.g., `<!-- engineer-mode: this note's
   logic lives in # Python. The frontmatter carries edit_mode: python
   so Forge-click runs the Python directly instead of transpiling
   Recipe → Python. -->`).
3. **Routing precedence**: the engine's action-code resolver MUST
   check the `edit_mode: python` frontmatter signal BEFORE V2-shape
   detection. The short-circuit ensures engineer-mode notes never
   route through Recipe transpilation regardless of whether their
   shape would otherwise classify as V2 (per v0.2.222 retrospective —
   ordering bug had `resolve_action_code` hitting V2 detect first,
   transpiling stub Recipes to empty Python and overwriting the
   canonical).

Engineer-mode is the legitimate operational shape for action notes
whose Python uses constructs outside V2 Recipe's expressive range.
It is NOT a workaround for V1 notes that haven't been migrated —
those keep `# English` + `# Python` shape. It is NOT a Path Y escape
hatch (Path Y delivery via v0.2.197-205 implicit-locking handles
cohort-authored Python edits correctly per S9).

Engineer-mode is engineer-authored. Cohort users can READ the
Description but should not edit the Python; if they want behavior
changes, the right path is to request engine work or fork the note
with their own Python facet.

The implicit-locking state machine (S9) is bypassed entirely for
engineer-mode notes — the engine treats the Python facet as
canonical without hash comparison. This is intentional: hash drift
would surface false-positive "Python canonical" status when the
Recipe is just a stub that the cohort might edit by accident; the
short-circuit prevents the stale state machine from firing.

## Architectural guarantees

These are structural and behavioral properties the engine guarantees by
construction (independent of what users write inside their notes).

**A1.** Every action note has an English facet (intent) and a
Python facet. Every data note has a `content_type` declaration and
either an inline body (text content types) or a `content_ref`
pointing to a sibling asset file (binary content types).

**A2.** Action note Python facets define a top-level `compute`
function whose first parameter is `context`. Additional parameters
are bound by name from the engine's input dict at compute time; the
engine invokes the function as `fn(context, *args, **inputs)` where
`inputs` is the kwargs dict derived per B5.2. Any of the following
shapes are valid: `def compute(context)`, `def compute(context, x, y)`,
`def compute(context, name)`, `def compute(context, *args, **kwargs)`,
etc. The function returns a value, which must be wire-serializable
per C7 unless the note declares `snapshot_capture: false`.

**A3.** `context.compute(snippet_id, *args, **kwargs)` invokes another
note and returns its value. For action notes, this runs Python;
for data notes, this deserializes the body. The caller does not
need to know which.

**A4.** Note resolution order: authoring vault → declared library
vaults (in manifest order) → built-in vault. Bare references match by
this order; qualified references (`vault/note`) dispatch directly.

**A4.1.** *Caller-scoped sibling resolution.* When
`context.compute(bare_id)` runs from a note whose qualified ID
has a subdirectory component (e.g. `forge-music/blues/song`), the
resolver applies the following ordered probes:

1. **Caller's own directory**: `{caller_vault}/{caller_dir}/{bare_id}`.
   Match wins immediately.
2. **Sibling subdirs within the caller's vault**: `{caller_vault}/*/{bare_id}`,
   excluding the caller's own directory probed in (1). If exactly one
   sibling subdir contains `{bare_id}`, match wins. If two or more
   sibling subdirs each contain a `{bare_id}` note, the resolver
   raises `AmbiguousSnippetResolutionError(bare_id, [candidates...])`,
   naming every candidate qualified path; the author must qualify
   the call explicitly to disambiguate.
3. **Fall through to A4** resolution order if (1) and (2) yield no
   match.

Qualified references (per A4) are unaffected — they dispatch directly
to the named vault. This refinement lets notes within one library
subdirectory reference siblings in the same vault by bare ID (e.g.
`[[chorus]]` from `forge-music/blues/song` resolves to
`forge-music/blues/chorus` via probe 1; `[[solitary]]` from
`forge-music/percussion/murmuration` resolves to
`forge-music/percussion_lab/solitary` via probe 2 when there's no
`forge-music/percussion/solitary`). The caller's directory takes
priority over siblings; ambiguous bare references across siblings
are an authoring error to be resolved by explicit qualification.

**Rationale for probe 2** (added V2a v8 per forge-music v0.3.9
percussion-lab decomposition): authors commonly refactor a single
subdir into a content cluster + lab cluster (e.g. `percussion/`
holds shipping pieces, `percussion_lab/` holds the section notes
the pieces compose from). Without probe 2, every cross-cluster
call must be qualified or every lab note must live in the same
directory as its caller — both raise the cost of intra-vault
composability against the Mission's "composable" property. Probe 2
preserves bare-ID composability across same-vault siblings while
keeping caller-locality as the primary tie-breaker.

**A5.** Vaults are distributed via per-vault GitHub repositories, with
tagged tarballs and SHA-256 integrity verification at install time.

**A5.1.** *Library-vault subdirectory convention.* When the installer
fetches a library vault into a user's vault, it places it at
`<user-vault>/<library-name>/` — the subdirectory name matches the
library's manifest `name`. The engine treats any top-level
subdirectory of a vault that contains its own `forge.toml` as a
library vault, indexes its notes under the library's namespace,
and walks them in the parent vault's declared `dependencies` order
when resolving bare references (per A4). This is a fixed convention,
not user-configurable: renaming the subdirectory breaks resolution
because the engine looks up the library by directory name + manifest.
Shadow files (a same-bare-id note at the user-vault root) override
the library version by A4 order; deleting the shadow restores the
library version with no copy needed.

**A5.2.** *Role tagging on library notes.* Library notes carry
an optional `role: root | leaf` frontmatter field that the installer
consumes at install-time, not at view-time or compute-time. `root`
marks a note that the installer should copy to the user-vault root
as the user's editable entry point (e.g. `setup`, `go`, an event
handler); `leaf` marks a library-internal note that stays in the
subdirectory and only becomes user-editable if the user explicitly
customizes it (creating a shadow). Notes without a role field
default to library-internal behavior (no auto-copy). The engine does
not consult `role` for resolution — A4 alone determines which copy
wins. `role` is purely an installer affordance.

**A5.3.** *Bundled distribution (V1).* For closed beta, a fixed set
of vaults (the "bundled libraries" — currently `forge-moda` and
`forge-music`) ships inside the plugin at
`<plugin>/assets/vaults/<library-name>/`. The engine mounts these
at startup and treats them per A5.1 (library-subdirectory
convention) without an install step. A user vault declares its use
of a bundled library by listing the corresponding domain in
`forge.toml` (per B9); the plugin extracts the bundle into the
user's vault root as editable `.md` files only when the domain is
declared. Registry-fetched distribution per A5 remains the path
for v1.1+ vaults not in the bundle. Bundled-vault content updates
ship via plugin releases; user-edited copies in the vault root take
precedence via A4 shadowing.

**A5.4.** *Inlined-asset version stamping (added 2026-06-10 per
v0.2.98; relocated from B10 to A5.4 in V2a v10 — this is a
distribution/packaging guarantee, sibling to A5.1-A5.3, not engine
compute behavior).* When the runtime distribution channel does not
deliver the plugin's `assets/` tree alongside `main.js` (BRAT being
the canonical example — it pulls only `main.js`, `manifest.json`,
`styles.css`, `data.json`), the plugin MUST:

1. Inline the required assets into `main.js` at build time and
   ship a runtime restore step on plugin onload that writes any
   missing files to disk under `<plugin-dir>/assets/`.
2. Stamp each inlined-assets bundle with the plugin's manifest
   version via a `.bundle-version` sentinel file written at the
   end of every successful restore.
3. Force-overwrite the entire inlined-asset tree on every plugin
   onload where the sentinel version does not match the bundle's
   embedded version. Skip-if-exists guards on individual files
   are FORBIDDEN — they cause silent staleness when a BRAT update
   replaces `main.js` but leaves the previously-restored asset
   tree untouched.

The skip-if-exists antipattern silently broke every plugin update
between v0.2.91 (first inlined-assets ship) and v0.2.98 (sentinel
introduction). Any future asset-bundling mechanism MUST follow
this stamp + force-overwrite pattern; per-file existence checks
are not a substitute.

**A6.** The plugin renders structured output values by their tagged
shape (`{type, content}`). Current formats: `musicxml` (rendered via
Verovio inline). Future formats added as needed.

**A7.** For every edge (caller_note, callee_note) traversed
during a compute, Forge automatically captures the value the caller
received and stores it as a snapshot. If a snapshot already exists for
that edge, it is overwritten with the latest. Capture is automatic;
users do not invoke it. Capture requires the return value to be
wire-serializable per F3. A non-serializable return on a
capture-eligible note raises at return time, naming the note
and the offending type. Notes that declare `snapshot_capture:
false` (per C7) are not captured; the edge has no snapshot and
cannot be frozen.

**A8.** An edge may be in one of two states: *live* (default) or
*frozen*. When frozen, calling the callee from the caller returns the
captured snapshot value rather than recomputing. Freeze state is
per-edge: different callers of the same callee can have different
freeze states.

**A9.** Transitive freezing: if edge X→Y is frozen, Y is not invoked
when called from X — its snapshot is returned directly. Any
dependencies Y has on Z are not traversed for this call. Freezing one
edge short-circuits the entire subgraph below it from the caller's
perspective.

## Engine behavior (no purity guarantees)

These are how the engine behaves; behavior depends on what the user
writes.

**B1.** `compute(note, args)` runs the note's Python facet (for
action notes) or returns the deserialized body (for data notes).
Whatever Python the author wrote runs. The engine does not verify,
sandbox, or constrain behavior beyond Python's own semantics.

**B2.** Action note Python has the full powers of Python: imports,
network calls, file I/O, randomness without explicit seeds, LLM calls,
mutation of inputs, side effects on the world. The author chooses what
their note does and accepts the consequences.

**B3.** Compute is **not** guaranteed to be deterministic. Same inputs
may produce different outputs, especially for notes that call LLMs,
sample randomly, or read external state. This is a feature for
exploratory and improvisational work.

**B4.** Snapshot capture (A7) happens regardless of the note's
determinism. For non-deterministic notes, the most recent
computation is what's captured. Repeat invocations may overwrite the
snapshot with successively different values until the edge is frozen.

**B5.** Generation: `/generate` produces a Python facet from the
note's English facet, augmented by read-only access to the vault's
note inventory. For each note in scope, the LLM may consult the
note's name, signature, and either its English facet (action
notes) or its `description` and `content_type` (data notes).

The LLM may use this information either to call notes explicitly
referenced in the English facet of the note being authored, or to
call notes it discovers while implementing the Python facet. Other
notes are treated as black boxes characterized by their declared
intent and signature; the LLM does not see other notes' Python
facets or their computed outputs at authoring time.

Generation does not execute notes at authoring time. The LLM's
decisions about which notes to call are based on what's documented
(English) and declared (signatures), not on what the notes actually
compute.

**B5.1.** *`generation_notes` frontmatter field.* A note's
frontmatter may carry a `generation_notes` field — a free-text block
consumed by `/generate` as additional authoring context for that
specific note. The field captures machine-targeted guidance (data
shapes the LLM should expect, idiomatic patterns specific to the
domain, carve-out semantics, edge cases) that would clutter the English
facet if written there. The English facet stays human-readable; the
machine-targeted hints live in `generation_notes`.

`generation_notes` is part of the note's authoring contract with
the LLM, not part of its public interface. It is visible to `/generate`
only when authoring *that* note's Python facet; it is not exposed
when the note appears in another note's authoring inventory (per
B5). Consumers of the note see only its name, signature, and
English facet (or `description` for data notes) — implementation
hints stay implementation-side. The runtime ignores the field; the
plugin's rendered view does not display it prominently.

**B5.2.** *Input derivation.* The engine determines which inputs to
request from the user at compute time by parsing the note's
Python signature and taking the union of (frontmatter-declared
`inputs`) and (positional / keyword-only params other than
`context`). The Python signature is the source of truth for what
`compute` actually needs; frontmatter `inputs` is a declarative
hint that informs `/generate`'s authoring context (per B5) and
provides UI ordering. When the LLM produces Python with params not
declared in frontmatter, the engine still surfaces them to the
user via the input modal — the note's runtime contract
self-describes via its signature, not its frontmatter. Inputs are
delivered to `compute` as kwargs (via `**inputs` unpacking, per
A2); declared parameters bind by name. The `context` parameter is
always supplied by the engine and never surfaced to the user.

**B6.** The Python produced by `/generate` is then static code. It
does not re-invoke `/generate` at runtime. Runtime LLM calls inside
Python are allowed and explicit, distinct from the `/generate`
mechanism.

**B7.** After /generate produces a Python facet, Forge performs static
analysis on the result to extract direct dependencies (calls to
`context.compute(...)` with literal-string note IDs). These
dependencies are written as a `Dependencies` section in the note's
body, formatted as wikilinks. The section is delimited by a
clearly-marked header indicating it is system-maintained. The section
is updated at /generate time and on explicit user command; drift
between the section and the current Python facet may occur if the user
edits the Python directly. Drift is detected and surfaced by clients
but not automatically resolved by Forge.

**B7.1.** *Canonical E-- call syntax in English facets.* When an
action note's English facet is in canonical E-- form (the
canonical form per the Mission preamble; the post-migration default,
opt-in during the migration), calls to other notes are written as
`[[<snippet_id>]](<arg-list>)`, where:

- `<snippet_id>` is a wikilink target identifying the callee
  (qualified per A4 if needed for disambiguation; bare otherwise).
- `<arg-list>` is a parenthesized, comma-separated list of arguments,
  positional and/or keyword. Keyword arguments use `name=expression`
  syntax. The arguments correspond to the callee's declared `inputs`
  frontmatter.
- Each argument is itself an expression per the E-- grammar (literal,
  variable, nested call, `{{ ... }}` value slot, list, dict, or
  parenthesized group).

This is the **syntactic contract** that Forge tooling depends on. The
static dependency analyzer (B7), the chip palette, the Obsidian graph
view's edge rendering of `# Dependencies` wikilinks, the wikilink-
context-menu freeze affordance, and any future chat-driven authoring
surfaces all read or produce calls in this form. A call written in
canonical form is parser-readable without LLM disambiguation. Tooling
that inserts calls (chip palette, chat) MUST produce text in this
shape; tooling that reads calls (static analysis, freeze affordance)
MUST accept this shape as the canonical input.

Examples:

```
Set result to [[fibonacci]](7).
Do [[print]]("hello world").
Set chord to [[major_chord]](root="C", inversion=2).
Set song to [[compose_blues]](
    bars=12,
    key="E",
    drums=[[shuffle_drums]](feel="laid_back"),
).
```

During the migration from free-English to canonical-E-- facet form
(see Anticipated extensions), free-English facets may still describe
calls in prose. The LLM normalizer translates such prose into canonical
form before the deterministic compiler runs. Post-migration, the
canonical form is the only authored form for new notes, and B5/B6/B7
will be rewritten atomically to describe the new compilation pipeline.

**B7.2.** *Builtin references in canonical form.* Canonical E-- uses
`[[name]](args)` for every function call, including Python builtins
(`print`, `len`, `range`, etc.). When the wikilink target matches a
known Python builtin, the Forge plugin intercepts the Obsidian
wikilink-click and suppresses the default "create unresolved file"
behavior. The user sees a tooltip or Notice naming the builtin; no
stray file lands in the vault. Builtins are NOT Forge notes and
do not require backing `.md` files; the bundled engine knows the
Python globals.

Forge plugin maintains a vetted list of recognized builtin names —
the common Python globals (`print`, `len`, `range`, `str`, `int`,
`float`, `bool`, `list`, `dict`, `set`, `tuple`, `enumerate`,
`zip`, `map`, `filter`, `sorted`, `reversed`, `min`, `max`, `sum`,
`abs`, `round`, `type`, `isinstance`, `getattr`, `setattr`, `hasattr`,
`open`, `input`). Calls to NON-listed names follow the existing
wikilink resolution per A4 + A4.1 — the link is treated as a note
reference. Authors who want to use a less-common builtin can either
qualify it (`[[python:builtin_name]]` or similar — TBD per the
implementation drain) or ship a sibling note that wraps it.

**Rationale**: per the Mission's "low floor" property, every stray
file the user has to clean up raises cost-to-tweak. Canonical
notes that contain `print` references shouldn't pollute the
vault when the user clicks the rendered wikilink. The Forge plugin
knows it's running inside Obsidian and can mediate the click
behavior; the engine's transpile path is unaffected.

**B7.3.** *Value-slot resolution.*

When a note's canonical E-- facet contains a `{{ free-text }}`
value slot, the engine resolves the slot to a Python expression at
**transpile time** via a Forge-hosted `/resolve-slot` endpoint
(parallel to `/generate`, same bearer-token auth). The resolved
expression is spliced into the note's transpiled Python; the
result lands in the note's `# Python` heading — the same cache
surface that legacy free-English notes use. **There is no
separate slot-cache structure visible to users.** `# Python` IS the
cache. The hash-keyed bookkeeping that links a slot text to its
resolution lives transiently in memory during transpile and is
never persisted as a user-facing artifact.

**Cache only when the cache pays for itself.** Slot-free canonical
notes continue transpiling fresh on every compute and DO NOT
write `# Python` — E-- transpile is deterministic, fast, and free,
so caching adds file noise without saving cost. Only slot-bearing
canonical notes persist `# Python` (because the LLM resolution
cost must be amortized). This means in practice: a tutorial that
introduces canonical notes in early chapters ships notes
with `# English` + `# Dependencies` and no `# Python`; the moment
a chapter introduces `{{ }}` slots, those notes begin growing
a `# Python` heading on first compute. The discontinuity is
pedagogically meaningful — the heading appears precisely because
the LLM's answer needs to be remembered.

Cache semantics for slot-bearing canonical notes follow B8
(`edit_mode`). In `english` mode (default), the engine detects
English-facet changes via an `english_hash` frontmatter field
written when `# Python` was last generated, and re-transpiles +
re-resolves on hash mismatch. In `python` mode, `# Python` is
editable and the cached output is used unconditionally — the
user's edits to `# Python` are the override path for any slot
resolution they want to refine. Per the "high ceiling" property,
the Python facet is the natural surface for fine-tuning compiled
output (it's where they'd already go for any other manual Python
correction). For non-programmer cohorts, the override is an
explicitly advanced affordance — the low-floor headline stays at
"write English → get a working value."

**At runtime, the engine MUST NOT hit the LLM.** This is a HARD
RULE per E-- spec §1.2. If a note's `# Python` is missing and
its English contains slots, the engine raises a cache-miss
exception envelope; the plugin batches the missing slots into one
`/resolve-slot` call, the engine splices the resolutions into the
transpiled output on the second pass, the plugin writes the
resulting Python to `# Python`, and re-fires compute. The user-
visible flow is a single Forge-click; the miss + resolution +
write-back are internal.

The resolver is hosted-side responsibility: the engine sees only
the resolved Python expression, never the LLM. Per the Mission's
"low floor" property, students never see an API key or per-
note LLM cost.

**Cache invalidation granularity is note-level.** Editing any
character of the English facet triggers a full re-transpile (and
re-resolution of all slots) on the next compute. Region-level
invalidation (re-resolving only the slot whose text changed,
preserving other slot resolutions) is a deliberate non-commitment
— see Anticipated extensions. The rationale is V1 cohort scale:
notes are short per the Mission preamble, slot counts are
small (1-2 typical), and haiku-pinned slot resolutions are cheap;
the architectural simplification of a single cache surface is
worth more than the marginal cost of re-resolving unchanged slots
on English edits.

See `docs/investigations/slot-resolution-design.md` for the wire-
format details and the in-memory hash contract used by the
transpile-time resolver.

**Cache invalidation on switch-to-English (added 2026-06-10 per
v0.2.90 + v0.2.119 arc).** When the user toggles `edit_mode` from
`python` back to `english` (B8), the plugin MUST delete the
note's `english_hash` frontmatter field as part of the
transition. This forces a cache miss + re-transpile on the next
Forge-click, restoring the engine's English-as-source-of-truth
contract. Without this rule, manual Python edits made during
`python` mode would persist as the cached output even after the
user signaled they want English-driven regeneration. The deletion
is plugin-side (engine never reads `english_hash` for cache
purposes outside this contract); it shares the same field name as
the engine's slot-resolution cache key by construction.

**B8.** Action notes carry an `edit_mode` (`english` or `python`,
defaulting to `english`). In `english` mode, the Python facet is
read-only in the editor and regenerated from English when Forge runs
the note. In `python` mode, the Python facet is editable and
regeneration is skipped; the English facet remains as the canonical
record. An explicit "Sync English to Python" action canonicalizes
English from current Python via a one-shot LLM call (the inverse
direction of B5). Round-trip regeneration is not automatic; mode-flips
and sync are explicit user gestures, never side effects of edits.

**Drift detection in `python` mode.** When the user switches to
`python` mode, the plugin snapshots `sha256(English facet)` into a
`locked_english_hash` frontmatter field. On editor refresh, the
plugin recomputes the hash of the current English facet and compares.
If they differ (the user edited English while in python mode), the
plugin shows a yellow-tinted "drifted" indicator on the mode toggle
button + a hover tooltip prompting the user to either run "Sync
English ← Python" to canonicalize from the current Python, or switch
back to `english` mode to regenerate the Python from the new English.
The `locked_english_hash` field is plugin-internal — the engine does
NOT read it; it is distinct from `english_hash` (B7.3, which the
engine uses for slot-resolution cache invalidation). The two fields
coexist by accident of feature timing: `locked_english_hash`
predates the B7.3 unification; both happen to hash the English facet
but serve different consumers. A future consolidation may unify them
under a single field with two consumers; until then, notes in
`edit_mode: python` may carry both fields with the same value.

**Symmetric facet-mutex invariant (added 2026-06-10 per v0.2.83
gestural model + v0.2.87 collapse-active completion; relocated from
B7.3 to B8 in V2a v10 — the invariant governs `edit_mode` facet
visibility, which is B8's concern, not B7.3 slot-caching).** When a
note's `# English` and `# Python` headings are both present in
the body, the facet-mutex maintains the invariant *exactly one
facet visible at any time*. Two gestures trigger a flip:

- *Expand inactive*: unfolding the currently-hidden facet flips
  `edit_mode` to that facet and folds the other.
- *Collapse active*: folding the currently-visible facet flips
  `edit_mode` to the OTHER facet and expands it.

Both gestures produce identical post-mutex state. Both-folded and
both-visible are invalid states; the plugin asserts the invariant
in a 100ms settle-window watchdog and surfaces violations via
`console.warn`. This watchdog is a proactive, self-healing invariant
check — not a caught runtime error — so `console.warn` is intentional
here and sits outside the scope of the console.error-for-caught-errors
discipline (cc-prompt-queue.md Hard rules). The invariant applies only
to note files whose body contains BOTH headings; slot-free
canonical notes (English + Dependencies only, no Python heading)
are exempt.

**B9.** *Note execution namespace and declared domains.* The
runtime sandbox blocks `import` statements; notes cannot pull in
modules at compute time. Instead, the engine pre-injects a fixed set
of names as globals into each note's execution namespace. The base
set — always injected regardless of domain — includes `random`,
`math`, and `numpy`. Domain layers register additional names and
`/generate` prompt fragments under a domain key (e.g. `music`:
music21 modules + composition helpers; `moda`: `Particle` /
`ParticleState`).

A vault **declares the engine domains it relies on** via
`domains = ["..."]` in `forge.toml`. The engine injects a domain's
globals, and includes its `/generate` prompt fragment, **only for
vaults that declare that domain**:

- field present with values → exactly those domains' globals +
  fragments;
- field present but empty (`domains = []`) → core-only: just the
  base globals and the base prompt, no domain extensions;
- field absent → **all registered domains** (back-compat for vaults
  authored before the field; the engine logs a one-line load-time
  warning encouraging an explicit declaration).

The declared dependency is the contract: a vault that uses a
domain-injected name (e.g. `Particle`) without declaring the
corresponding domain fails at compute time with a `NameError`, and
its `/generate` prompt will not carry that domain's guidance. The
implicit version-coupling this clause previously only flagged is now
explicit and declared.

Cross-vault calls are **permissive** in v1: a `context.compute` into
another vault is not blocked at resolve time even if the calling
vault doesn't declare that callee's domain. The active vault's
declared domains govern the whole execution including nested calls;
per-callee-vault re-scoping is a recoverable future refinement, not a
v1 guarantee. `forge-core`'s built-in vault is domain-neutral and
available regardless of declared domains.

## Data notes

**D1.** A data note has frontmatter (`type: data`,
`content_type: <format>`, optional `description`, optional
`read_only` flag, optional structural signature). It has no English
facet. For text content types, the body contains the serialized value
as text. For binary content types, the body is empty and `content_ref`
in frontmatter points to a sibling asset file under
`<vault>/_assets/<snippet_id>.<ext>`. `content_ref` and body content
are mutually exclusive; pairing `content_ref` with a text content
type is a config error.

**D2.** Content types fall into two families:

- *Text* content types (`json`, `yaml`, `text`, `markdown`, `svg`,
  `musicxml`) store the value inline in the note body. Future
  additions: `ifc`, custom DSLs.
- *Binary* content types (`image/jpeg`, `image/png`, `audio/mpeg`,
  `audio/wav`, `video/mp4`) store the value in a sibling asset file
  referenced by `content_ref`.

A data note's `content_type` must be one for which Forge has the
appropriate handler. The bare name `jpeg` is preserved as a
back-compat alias for `image/jpeg`.

**D3.** When `context.compute(...)` resolves to a data note:

- For text content types, the runtime reads the body, deserializes
  per `content_type`, and returns the native Python value (dict for
  json/yaml, str for text/markdown/svg, music21 Stream for musicxml).
- For binary content types, the runtime resolves `content_ref`, reads
  the asset bytes, and returns a `(bytes, content_type)` tuple. The
  caller unpacks at the call site:
  `data, ct = context.compute("snippet_id")`.

No Python execution occurs in either case. Action and text-data calls
are indistinguishable to the caller; binary-data calls require the
unpack idiom by convention. The system prompt teaches the LLM this
idiom directly so generated code uses the right shape.

**D4.** Data notes have signatures expressed in frontmatter — at
minimum, the content type. Optionally, structural metadata (e.g., for
music: tempo, key, instrumentation; for IFC: building level count).
The LLM consumes these as part of B5's authoring context.

**D5.** Data notes are categorized by origin:

- **Hand-authored data notes** are user-created. For text content,
  the user writes the file directly. For binary content, the user
  drags the asset into the New Note modal; Forge copies the file
  to `_assets/` and writes the wrapper `.md` with `content_ref`. They
  live in the user's authoring vault. Forge's runtime does not write
  to them; modifications happen via the user editing the markdown
  file (or replacing the asset file).
- **Captured data notes** are created via the "Save as data
  note" action on a compute result. Forge writes the note
  initially (auto-detecting `content_type`, writing body or sibling
  asset as appropriate), but the artifact is user-owned thereafter.
  This is the standard path from a transient compute result to a
  durable, addressable artifact.
- **System-generated data notes** (snapshots) are written by Forge
  as part of edge capture. They live in `<vault>/.forge/edges/`. Users
  do not author these directly; Forge maintains them automatically.

**D6.** *(Optional / deferred)* Runtime-writable data notes — where
note code mutates the body of another data note at compute time
— are not currently supported. They are mentioned here as a possible
future extension. The architectural cost (concurrency, vault file
rewriting, generated-vs-hand-authored ambiguity) is real and the use
case has not yet justified it.

**D7.** Hand-authored or captured data notes may be marked
`read_only: true` in frontmatter. When set, the editor surfaces a
read-only badge and edits require explicit toggle-off. This is a UI
guard against accidental edits to canonical references that
downstream notes structurally depend on (e.g., a JSON list whose
shape consumers parse). It does not affect runtime behavior. It is
distinct from edge freezing (F1–F9), which operates on caller→callee
edges rather than on notes themselves.

## Snapshots and freezing

**F1.** For every edge (caller, callee) traversed during a compute,
Forge writes a snapshot capturing the value the caller received from
the callee. Snapshots are written automatically; users do not invoke
this directly. (See A7.)

**F2.** Snapshots are stored at
`<vault>/.forge/edges/<caller_id>/<callee_id>.md`. Each file contains:

- Frontmatter: `type: snapshot`, `caller`, `callee`, `state` (live or
  frozen), `captured_at` timestamp, `content_type` matching the
  captured value's wire format.
- Body: the wire-format serialization of the captured value.

Note IDs containing slashes (e.g., `forge-core/hello_registry`)
become subdirectory paths in the storage hierarchy.

**F3.** A snapshot's body is the wire-format serialization of whatever
the callee returned, generated by Forge's serialization machinery.
Reading a snapshot deserializes the body back to a Python value via
the inverse machinery. The engine provides a wire-format codec that
domain layers may extend with additional types as needed. The set of
currently-supported types and their encoded shapes is maintained in
[`wire-format.md`](./wire-format.md), updated alongside codec changes.

If a return value falls outside the supported set, snapshot capture
for that edge is skipped and a warning is logged; compute itself
still succeeds in-process. The edge cannot be frozen until the codec
is extended to handle the value's type.

**F4.** The default edge state is *live*. In the live state, Forge
computes the callee normally on each call and updates the snapshot
afterward. In the *frozen* state, Forge skips computation and returns
the snapshot's stored value.

**F5.** Freezing an edge is a user action (UI gesture in the plugin,
or command). The user identifies the edge — the dependency from a
specific caller to a specific callee — and toggles its state.
Freezing requires that a snapshot already exists for the edge (the
edge has been traversed at least once in a previous compute).

**F6.** Unfreezing an edge returns it to the live state. Subsequent
computes recompute and overwrite the snapshot. The previously-frozen
value is not preserved unless the user has copied it elsewhere (e.g.,
created a hand-authored data note from it).

**F7.** Per-edge granularity: freezing the C→A edge does not affect
B→A. Different callers of the same callee can have different freeze
states.

**F8.** Transitive freezing: if X→Y is frozen, Y is not invoked when
called from X. The snapshot is returned directly. Any dependencies Y
has on other notes are not traversed for this call. Freezing one
edge cuts off the entire subgraph below it from that caller's
perspective.

**F9.** Snapshots persist indefinitely. Forge does not automatically
delete them. Users can manage cleanup via plugin commands when those
tools land.

## Cultural commitments (user discipline)

These are properties Forge encourages but cannot enforce.

**C1.** Notes intended to be reproducible should be written as pure
Python — no LLM calls, no randomness without explicit seeds, no
hidden side effects. The author opts into reproducibility by
disciplining their code.

**C2.** Notes intended to be exploratory or improvisational may
freely use LLM calls, randomness, and full Python expressivity. The
author opts into non-determinism deliberately.

**C3.** English facets (on action notes) are most useful when they
are self-describing about operations — what the note does and how
it uses any references. For data notes, the same role is played by
the optional `description` field in frontmatter — what value is held
and what shape. Thinner English (or thinner descriptions) produces
notes that are harder to regenerate, harder for the LLM to use as
building blocks, and harder for collaborators to understand. The
author chooses how much detail to articulate.

**C4.** External tools that produce notes (Claude Code in a vault,
domain-specific generators, future tooling) are encouraged to follow
the same English-thickness convention. The system does not enforce
this; community practice does.

**C5.** Authors are encouraged to be intentional about side effects in
compute. Network calls, file writes, LLM calls during compute should
be deliberate choices serving the note's purpose, not accidents of
code that should have been pure.

**C6.** Freezing is a tool for stabilizing finished sub-DAGs. Authors
should freeze when they want to stop exploring a part of the work and
commit to its current state. Premature freezing locks in choices not
yet evaluated; over-eager unfreezing loses captured states the author
might want to return to. Both extremes are user-controllable; the
system does not enforce timing.

**C7.** Action notes must return wire-serializable values from
`compute`. The engine attempts capture per A7; failure to serialize
raises a clear error at return time naming the note and the
offending Python type. Authors who deliberately need a non-capturable
return must declare `snapshot_capture: false` in frontmatter — the
engine then skips capture for that note (silently, no warning) and
the edge has no snapshot, no freeze, no replay. The default (field
omitted) is `snapshot_capture: true`. When a note's natural return
type isn't yet wire-serializable, the cleaner move is to extend the
engine's codec (see [`wire-format.md`](./wire-format.md)) rather than
reshape the return or opt out. Domain return types are first-class
once their wire encoding lands.

**C8.** Notes that depend on execution history — by reading their
own prior snapshots, accumulating state across invocations, or any
mechanism beyond their declared inputs — opt out of the
reproducibility and purity discipline of C1. This is intentional and
valuable for exploratory or iterative work (simulation steppers,
conversational state, iterative refinement) but means the note is
no longer a pure function: repeated calls with identical inputs may
return different values because history is part of the computation.
Use deliberately. Document the history-dependency in the English
facet so future readers — and the LLM during regeneration — know
the note's output depends on more than its declared inputs.

The concrete runtime mechanism is `context.read_snapshot()`: it
returns the latest snapshot this note itself produced (a scan of
the note's own outbound edge directory,
`<vault>/.forge/edges/<self_id>/`), or `None` if none exists. It is
a read-only runtime helper and is **independent of edge freezing
(F1–F9)** — it returns the stored snapshot whatever the edge state,
and never writes. Self-only by deliberate scope: it takes no
callee argument (reading *other* notes' snapshots is deferred
until a non-moda use case justifies it). Because Forge captures
snapshots per *edge* keyed by the callee, an entry-point note
(never a callee) reads its *outbound* captures; for a pass-through
note whose return equals its terminal callee's return this is
exactly "my last output", and a note that post-processes before
returning must account for the one-tick lag in its English facet.

**C9.** *Vault-driven authoring affordances.* Vaults may ship data
notes (conventionally prefixed `_*.md` at the vault root or in
installed domain subdirectories) that the plugin reads to surface
domain-specific UI affordances. The plugin's UI shells — sidebar
palettes, menus, modals — are domain-neutral; the content of these
data notes defines what's available. Examples: `_chips.md` defines
a click-to-insert palette of procedural verbs surfaced in a sidebar
chip pane; future conventions (`_templates.md`, `_examples.md`) may
define other affordances. Authors shape the UI by editing markdown,
not plugin code. The plugin reads these files on activate and on an
explicit refresh — it does not file-watch them — so authors get
predictable, palette-refresh-on-demand semantics rather than reactive
churn.

## Current implementation choices

**I1.** Python is the realization language for action notes.

**I2.** Forge is delivered as an Obsidian plugin. In V1 closed beta,
the plugin bundles Pyodide and runs the engine in-process inside
the Obsidian renderer; the user's machine requires no Python install
and no local backend. LLM-driven `/generate` requests go to a hosted
transpile service over HTTPS (authenticated via a shared bearer
token); all other compute paths — `/compute`, note resolution,
snapshot read/write — execute locally inside the plugin process via
Pyodide. A legacy HTTP backend mode (Python uvicorn serving the
engine) remains supported for engine development workflows but is
not exercised on student installs.

**I3.** The plugin's renderer set is fixed at build time: SVG (browser
native), MusicXML (Verovio). New formats added through plugin updates.

**I4.** Heavy computation (e.g., music engraving prep, geometric
operations) happens server-side in Python; the plugin renders
pre-computed structured outputs without performing domain computation.

**I5.** The bundled LLM provider is Anthropic; configurable to others
via environment variable.

**I6.** Snapshot storage is at
`<vault>/.forge/edges/<caller_id>/<callee_id>.md`. Snapshot content is
wire-format text in the body; metadata in frontmatter.

**I7.** *V1 → V2 migration status.* As of V2a v11.2, the engine and
plugin support both V1 (`# English` + `# Python` + frontmatter inputs)
and full-V2 (`# Description` + `# Recipe` + `# Python` + facet hashes
per S8-S9) action notes. Existing content: forge-tutorial fully V2;
forge-moda fully V2; forge-music fully full-V2 post-v0.7.0 (renamed
`blues/` → `slow_burn/` + `song.md` → `slow_burn.md` in v0.8.0) —
all 5 vault action notes (`slow_burn.md`, `chorus.md`,
`solo_chorus.md`, `percussion/loom.md`, `percussion/murmuration.md`)
are full-V2 with Description + Recipe + Python and implicit-locking
per S9. The 8
prior engineer-mode files (drum_chorus, drums_shuffle, form,
guitar_solo_chorus, vocal_phrase_a, vocal_phrase_b, phase_cell,
phase_shifter) were promoted to library notes per S10 + per the
2026-07-01 brainstorm consistency rule (every chip backs a note —
library or vault; no second-class engineer-mode notes in vault).
They now live as functions in `forge.music.lib` and serve via the
LibraryNoteView read-only path. New action notes SHOULD be authored
as full-V2. Engineer-mode V2 (S10) remains a documented operational
shape for any future case where vault-authored content needs to
escape V2 Recipe grammar, but no current vault notes use it. V1
content is grandfathered indefinitely; the engine does not plan to
drop V1 support, though chip-palette UX defaults bias toward V2
keywords (Let / Return / Call) in V2-contextual editors.

## Deliberate non-commitments

These are things Forge does not currently address. They might be
addressed in future versions; their absence is intentional.

- Reproducibility guarantees on compute outputs.
- Determinism enforcement on note code.
- Cycle detection in the DAG (loops are the user's responsibility).
- Sandboxing of note code.
- Runtime-writable data notes (D6, mentioned as optional future
  extension).
- Multi-user collaboration on a single vault.
- Cloud / hosted execution.
- Streaming output for long-running computations.
- Automatic snapshot eviction or cleanup policies.
- **Backward compatibility for free-English note facets.** As the E-- migration (anticipated extensions below) progresses, free-English English facets that haven't been normalized to canonical E-- may break or require explicit migration. The contract going forward is: the English facet IS canonical E--, possibly with the LLM-normalizer run automatically on free-form input at /generate time. Notes authored before the migration are not guaranteed to keep working as their English facets stand — they need re-running through /generate or hand-editing into canonical form.

## Anticipated extensions

Patterns the architecture admits cleanly, expected to land in future
versions when the use case demands them.

- **Runtime-writable data notes** — if a use case emerges
  justifying the architectural cost.
- **Snapshot eviction policies** — automatic cleanup when storage
  grows.
- **Multi-version snapshots** — keeping a history of past frozen
  values per edge, not just the latest.
- **Snapshot promotion** — converting a system-generated snapshot
  into a hand-authored data note for sharing or version control.
- **Per-vault Python virtualenvs** — vaults declare their Python
  dependencies; the engine manages venv isolation.
- **Cassette-style record-and-replay** for testing — captured LLM
  responses and compute outputs replayed deterministically in test
  mode.
- **Cross-note generation tooling** — external tools (Claude Code,
  domain-specific generators) that create related sets of notes.
  Lives outside Forge core; integrates via the standard note
  contract.
- **Region-level transpilation caching.** B7.3 commits to note-level cache granularity: any English-facet edit triggers a full re-transpile + re-resolution of all slots on the next compute. The architecture admits a finer granularity — caching individual transpiled regions (per-statement, per-slot) and re-running only the changed regions on partial edits. Adoption trigger: evidence that real cohort usage pushes notes to N>3 slots where re-resolving unchanged slots becomes a real cost (LLM dollars, latency, or user-perceived sluggishness). The diagnostic for this trigger is concrete: per-vault slot-count histograms + post-edit re-transpile latency measurements. Until that evidence surfaces, note-level keeps the contract simple, the wire format small (one `# Python` heading, no per-region cache structures), and the user-facing surface minimal (no hash-keyed YAML for students to interpret).
- **E-- as the canonical English facet form (in progress).** Forge is
  migrating the English facet from free-prose-with-LLM-translation to
  canonical E-- (`~/projects/e--/`, vendored into the Forge engine
  package as `forge/forge/e_minus_minus/`). The engine compiles E--
  canonical to Python deterministically; the LLM runs only for
  free-English → canonical normalization (at /generate time) and for
  `{{ ... }}` value-slot resolution (cached per slot text). The
  migration ships as a small number of staged drains post-V1 closed
  beta. Backward compatibility for free-English facets is not
  promised (see Deliberate non-commitments). When Stage-1+Stage-2
  ship, B5/B6/B7 are rewritten atomically to describe the new
  compilation pipeline.

## What Forge promises

- Two-facet authoring on action notes (English + Python) with LLM
  bridging in both directions (English → Python via `/generate`;
  Python → English via explicit canonicalization sync). Inert stored
  content on data notes (no English facet).
- DAG composition via `context.compute`.
- Distribution via vaults and registry.
- Structured output rendering via standard formats.
- Full Python expressivity inside action notes.
- Improvisational, exploratory creative work as a first-class
  workflow.
- Per-edge automatic snapshot capture and per-edge freeze/unfreeze
  semantics for stabilizing parts of the DAG.
- Hand-editable, git-trackable artifacts throughout — notes,
  manifests, snapshots all live as markdown files in the vault.

## What Forge does not promise

- That the same compute returns the same value next time.
- That notes are pure.
- That side effects don't happen.
- That LLM calls don't happen at runtime.
- That dependency graphs don't have cycles.
- That output is reproducible across sessions without freezing.

These trade-offs are accepted as the cost of supporting the kind of
creative work Forge is for: exploratory, improvisational,
LLM-augmented composition where the artifacts are alive rather than
fixed.

## Portability

The vault is markdown files in a directory; you can move it, share
it, version it. Python facets are real Python; English facets are
real prose; data note bodies are real wire-format text; snapshot
files are markdown with frontmatter and serialized values. Anyone
with a Python interpreter and a markdown viewer can inspect, copy,
modify, or fork your work. Snapshots travel with the vault,
preserving whatever frozen states the author has captured.


