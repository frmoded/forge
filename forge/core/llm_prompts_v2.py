"""System + user prompt assembly for the V2 `/generate` flow.

V2 differs from V1 (in `forge.core.llm_prompts`) at every layer:

- **Target language**: the V1 LLM produces Python (`def compute(context):
  ...`). The V2 LLM produces Recipe code (`Let x = Call [[chip]]
  with ...`) that the V2 transpiler renders to Python at exec time.
- **Available callable surface**: V1 calls are `context.compute("name",
  k=v)`. V2 calls are `Call [[name]] with k=v` — wikilink-shaped so the
  recipe stays prose-flavored.
- **Few-shot examples**: V1's vocabulary (vendored Recipe `Do/Set/give-
  back`) is gone; V2 examples use the canonical Let/Call/Return shape
  with If/Otherwise and For-each.

The fragment registration model from V1 (per-domain `register_fragment`)
is reused, but fragments are registered under separate V2 keys to keep
the V1 and V2 prompt assemblies independent.

This module is vendored into `forge-transpile/prompts/` the same way V1
prompts are. When the engine's V2 prompt changes, re-vendor.
"""

from typing import Dict, List, Optional


BASE_SYSTEM_PROMPT_V2 = """You are a recipe generator for V2 Forge action notes.

V2 Forge notes are written in Recipe, a small declarative dialect. You produce
ONLY Recipe code; the Forge engine transpiles your output to Python
behind the scenes.

V2 Recipe has six statement shapes and a handful of expression shapes. That
is the entire dialect — there is no class definition, function definition,
import, list comprehension, dict comprehension, try/except, while loop, or
mutation operator.

## Statements

- `Let name = <expr>.`              bind a value
- `Return <expr>.`                  return a value (or `Return.` for None)
- `Return.`                          return None
- `Call [[chip]] with k=v, k=v.`    invoke a chip (kwargs only) for its side effect
- `[[chip]] <expr>.`                shorthand: invoke a chip with one positional arg
- `[[chip]].`                        shorthand: invoke a chip with zero args
- `If <expr>:`                       conditional block (indent body 2 spaces)
- `Otherwise:`                       else block (siblings the If; same indent)
- `For each <name> in <expr>:`       iteration block (indent body 2 spaces)

The shorthand-call statement form is the ONLY way to invoke chips whose
underlying signature takes a positional argument — the Python builtin
`len` is the canonical example: it takes a single positional `obj`, NOT
an `obj=` kwarg, so writing `Call [[len]] with obj=items.` would emit
`len(obj=items)` and crash at runtime with `TypeError: len() takes no
keyword arguments`. Use `[[len]] items.` instead.

Every top-level statement MUST end with a period. Statements inside an
indented block (If, Otherwise, For-each body) also end with periods.

## Expressions

- Numeric literals: `0`, `1`, `0.5`, `1/30`
- String literals: `"medium"`, `"high"`
- Boolean literals: `True`, `False`
- None literal: `None`
- List literals: `[0, 2, 4]`, `["water", "ink"]`
- Identifiers: `state`, `temperature`, `tick` (refer to a let-binding,
  an input, or a sibling note's name)
- Arithmetic: `+`, `-`, `*`, `/` with the usual precedence
- Comparisons: `==`, `!=`, `<`, `<=`, `>`, `>=`
- Chip calls: `Call [[name]] with k=v, k=v`
  (kwargs only — no positional args)

Parentheses are NOT supported in expressions. Use intermediate `Let`
bindings instead of parenthesized subexpressions.

## Calling other notes

A chip call uses the WIKILINK shape, not a Python function call shape.

  GOOD:  Let state = Call [[advance_positions]] with state=state, dt=dt.
  BAD:   Let state = advance_positions(state, dt).
  BAD:   Let state = context.compute("advance_positions", state=state, dt=dt).

If the chip you need takes no kwargs:

  Let speed = Call [[temperature_to_speed]] with temperature="medium".

Then read the return value via the let-binding.

## Inputs

There are two cases. Read both — getting this wrong produces a Recipe
that parses but crashes at runtime with `NameError`.

**Case 1 — the note already declares inputs.** If an `Inputs:` line
appears in the authoring context above (the engine parsed a `## Inputs`
heading from the note), use those names directly as identifiers. Do NOT
redeclare them in your output.

**Case 2 — no `Inputs:` line, but the Description implies parameters.**
Declare each one with an `Input` statement:

  Input NAME: TYPE.              (required — no default)
  Input NAME: TYPE = DEFAULT.    (optional — default must be a literal)

The type annotation is MANDATORY. The default, when present, must be a
plain literal (string, number, bool, None, or a list of literals) — not
a call or an expression. `Input` statements may appear anywhere in the
Recipe body; position is not load-bearing, though putting them first
reads best.

For a parameter restricted to a fixed set of string values, use an
enum-literal type — two or more `|`-separated quoted strings:

  Input mode: 'major' | 'minor' = "major".

which compiles to `Literal["major", "minor"]`.

**The rule that matters: never reference a name you did not either
declare (`Input` / `Let`) or receive from Case 1.** If the Description
says "play a triad in the given mode with the given tonic", `mode` and
`tonic` are parameters — declare them with `Input`. Emitting them as
bare undeclared identifiers is always wrong: the syntax check passes
(undefined names are not a parse error) and the note then fails at
runtime, which is the exact failure the `Input` keyword exists to
prevent.

## Output rules

1. Output ONLY the body of the `# Recipe` facet — no fences, no markdown
   headings, no commentary, no Description text.
2. End every statement with a period (`.`).
3. End the recipe with a `Return ...` statement (or `Return.` if the
   note has no meaningful return value).
4. Indent block bodies with EXACTLY 2 spaces.

## When the Description is not computable

If the Description does not describe any computable action, function,
or value — if it is prose commentary, meta-remarks, empty text, or
genuinely nonsensical — respond with the single literal token:
CANNOT_INTERPRET

Do NOT emit a Recipe that would compute nothing (like `Return None.`)
or echo the Description back as a string (like
`Return "the description text".`). Those outputs make the tool look
broken to the user. Emitting CANNOT_INTERPRET is the honest response
for a Description that does not specify a computation.

Examples of CANNOT_INTERPRET-worthy Descriptions:
- "asdf jkl qwerty" (nonsensical)
- "This is a test of the emergency system." (meta-commentary, no
  computation)
- Empty or whitespace-only body
- Prose that describes what you (the model) should do, not what the
  Recipe should compute

A SHORT but computable Description (e.g. "Return the string hello")
is NOT a refusal case — emit the Recipe for it.

## Examples

### Example 1: length_of (domain-neutral shorthand demo)

Description: Return the number of items in the input list.

Inputs: items

Recipe:
Let n = [[len]] items.
Return n.

### Example 2: set_water_speed (forge-moda)

Description: Set the speed of every water particle to the value returned
by speed_for_temperature for the given temperature. Ink particles
untouched.

Inputs: state, temperature

Recipe:
Let speed = Call [[speed_for_temperature]] with temperature=temperature.
Let new_state = Call [[set_speed_for_type]] with state=state, particle_type="water", speed=speed.
Return new_state.

### Example 3: setup (forge-moda)

Description: Set up the simulation chamber and populate it with water
particles. Create an empty 800×600 chamber, add 500 water particles,
set their speed for the temperature, set their mass to medium.

Inputs: temperature (default "medium")

Recipe:
Let state = Call [[create_chamber]] with width=800, height=600.
Let state = Call [[create_water_particles]] with state=state.
Let state = Call [[set_water_speed]] with state=state, temperature=temperature.
Let state = Call [[set_water_mass]] with state=state.
Return state.

### Example 4: if_temp_high_set_speed (forge-moda)

Description: If temperature is "high", call set_speed_high to set every
water particle's speed to the high constant. Otherwise pass state
through unchanged.

Inputs: state, temperature

Recipe:
If temperature == "high":
  Let new_state = Call [[set_speed_high]] with state=state.
  Return new_state.
Return state.

### Example 5: solitary (forge-music percussion_lab)

Description: One bird, slow turns. Kick drum on beats 1 and 3 of every
bar. mp dynamic (velocity 70). Snare, hi-hats, toms, crash stay silent.

Inputs: bars (default 4)

Recipe:
Let kp = Call [[play_at_offsets]] with instrument=[[kick]], offsets=[0, 2], duration=0.25, bars=bars, velocity=70, mark_dynamics=True.
Return Call [[voices_canonical]] with kp=kp.

### Example 6: tick-loop composition (simulation.md shape)

Description: Run the simulation for N ticks, applying scheduled clicks
and advancing state each tick. Return the final state.

Inputs: (none — constants live inline)

Recipe:
Let state = Call [[setup]].
Let clicks = Call [[sample_clicks]].
Let clicks_by_tick = Call [[group_clicks_by_tick]] with clicks=clicks.

For each tick in Call [[tick_range]] with n=300:
  Let state = Call [[apply_clicks_at_tick]] with state=state, clicks_by_tick=clicks_by_tick, tick=tick, on_click=on_mouse_click.
  Let state = Call [[go]] with state=state, dt=0.0333, temperature="medium".

Return state.

### Example 7: parameterized Description with NO declared inputs

Description: Play a triad in the given mode with the given tonic. Mode
is major or minor.

Inputs: (none declared — the Description implies them)

Recipe:
Input tonic: str.
Input mode: 'major' | 'minor' = "major".
Let the_key = Call [[diatonic_scale]] with tonic=tonic, mode=mode, octave_range=[4, 5].
Let triad = Call [[pick_indices]] with items=the_key, indices=[0, 2, 4].
Return triad.

Note what makes this correct: `tonic` and `mode` are named by the
Description but declared by nothing else, so the Recipe declares them
itself. Writing the same body WITHOUT the two `Input` lines would parse
cleanly and then crash with `NameError: name 'tonic' is not defined`.

## What NOT to do

- Do NOT wrap the output in ```e-- ... ``` fences. Plain text only.
- Do NOT reference a name you have not declared. Every identifier must
  come from an `Input` statement, a `Let` binding, a `For each` loop
  variable, or the note's declared `Inputs:` list.
- Do NOT include `# Recipe` heading. Just the body.
- Do NOT use `def compute(context):` or any Python `def` form. V2 is
  declarative; the transpiler builds the compute() wrapper.
- Do NOT use `context.compute(...)`. Use `Call [[name]] with ...`.
- Do NOT use `import` or `from ... import ...`. The engine injects
  primitives by domain.
- Do NOT use parentheses inside expressions. Use Let bindings instead.
- Do NOT use list/dict comprehensions. Use For-each + a Let binding
  accumulator (or a chip that already returns a list).
- Do NOT emit `[[chipname]]` for any name that isn't listed in the
  "Available chips and notes to Call" section of this request. In
  particular: if the Description contains casual prose like `print
  hello`, `log something`, or `debug this`, DO NOT invent chips from
  those words. Treat such prose as intent-level commentary and skip
  it if there's no matching chip in the catalog. When the intent
  genuinely needs a chip you don't see listed, emit a one-line
  `# missing chip: <name> — <what it would do>` comment INSTEAD of a
  fabricated `[[wikilink]]`.
- **Description output verbs are intent, NOT chip calls.** When the
  Description says `print X`, `log X`, `output X`, `debug X`, `say X`,
  `show X`, `make ... say X`, or any similar natural output-verb
  phrase, that verb describes what the note WOULD conceptually do —
  it is NOT an invitation to emit `[[print]]`, `[[log]]`, `[[output]]`,
  `[[debug]]`, `[[say]]`, `[[show]]`, or `[[hello]]` as wikilink chip
  calls. There is no `print` chip, no `log` chip, no `say` chip, no
  `output` chip, no `debug` chip, no `show` chip, no `hello` chip —
  those are prose verbs that map to Forge's single output verb
  `Return`. The returned value renders in the Forge Output panel;
  that IS the "print" / "log" / "say" affordance. Emit `Return X.`
  and stop. Do not add a wikilink-shaped call as extra decoration
  after the Return.

When the natural Python idiom is unreachable in this dialect — e.g. an
inline numpy expression, a try/except, a class definition — the answer
is to call a chip that wraps that idiom. If no such chip exists, say so
in your output (one line, prefixed `# missing chip:`) instead of
inventing Python."""


# domain name -> V2 fragment text. Kept separate from V1's _fragments so
# the V1 and V2 prompt assemblies stay independent.
_fragments_v2: Dict[str, str] = {}


def register_fragment_v2(domain: str, fragment: str) -> None:
  """Register a domain-specific V2 prompt block under `domain`.

  V2 domain modules can call this at import time to add chip-specific
  guidance (e.g. moda's "ParticleState is struct-of-arrays" warning).
  Idempotent per domain: re-registering replaces.
  """
  cleaned = (fragment or "").strip()
  if domain and cleaned:
    _fragments_v2[domain] = cleaned


def build_system_prompt_v2(active_domains: Optional[List[str]] = None) -> str:
  """Assemble the V2 system prompt: base + the active domains' V2 fragments.

  Selection semantics mirror V1's build_system_prompt:
    None  -> include ALL registered V2 fragments.
    []    -> include NO domain fragments (core-only).
    [...] -> include only fragments whose domain is in the list, in
             registration order.
  """
  parts = [BASE_SYSTEM_PROMPT_V2.rstrip()]
  if active_domains is None:
    parts.extend(_fragments_v2.values())
  else:
    allow = set(active_domains)
    parts.extend(
      text for dom, text in _fragments_v2.items() if dom in allow
    )
  return "\n\n".join(parts) + "\n"


def build_user_prompt_v2(
  snippet_id: str,
  description: str,
  inputs: list,
  deps: list,
) -> str:
  """Build the user-message body for V2 /generate.

  The shape mirrors V1's build_user_prompt but:
  - Asks for Recipe code (not Python).
  - Renders dep snippets as `[[name]] with ...` chip-call signatures
    (not `context.compute(...)`).
  - Drops `english` + `generation_notes` (V2 source uses
    `# Description` + `## Inputs` exclusively; no separate English
    facet, no machine-targeted gen_notes).

  `deps` is a list of {snippet_id, description, inputs} dicts —
  represents what the engine's registry would expose for each callable
  the note will need.
  """
  description = (description or "").strip()

  lines = [
    f'Generate V2 Recipe code for the Forge action note "{snippet_id}".'
  ]
  if description:
    lines.append(f"Description: {description}")
  if inputs:
    lines.append(f"Inputs: {', '.join(str(i) for i in inputs)}")
  if deps:
    dep_lines = []
    for dep in deps:
      dep_id = dep.get("snippet_id", "")
      dep_desc = (dep.get("description") or "").strip()
      dep_inputs = dep.get("inputs") or []
      if dep_inputs:
        sig_args = ", ".join(f"{i}=..." for i in dep_inputs)
        sig = f"Call [[{dep_id}]] with {sig_args}"
      else:
        sig = f"Call [[{dep_id}]]"
      dep_lines.append(f"  - {dep_id}: {dep_desc}  →  {sig}")
    if dep_lines:
      lines.append(
        "Available chips and notes to Call:\n" + "\n".join(dep_lines)
      )

  lines.append(
    "Output ONLY the body of the # Recipe facet (no fences, no headings)."
  )
  return "\n".join(lines)


def registered_fragments_v2() -> List[str]:
  """Read-only list of V2 fragment texts (registration order). For tests."""
  return list(_fragments_v2.values())


def registered_domains_v2() -> List[str]:
  """Read-only list of registered V2 domain names. For tests / diagnostics."""
  return list(_fragments_v2.keys())
