"""Unit tests for forge.core.llm_prompts_v2 — V2 /generate prompt assembly.

Locks in the contract the forge-transpile service relies on when the
hosted /generate is invoked with `dialect="emm"`. Drift in field
ordering, header phrasing, or dep-line shape would change LLM output.
"""

from forge.core import llm_prompts_v2 as p


# ---------------------------------------------------------------------------
# build_system_prompt_v2 — base + fragments
# ---------------------------------------------------------------------------

def setup_function(_):
  """Clear V2 fragments between tests so registration order is
  deterministic per-test."""
  p._fragments_v2.clear()


def test_build_system_prompt_v2_base_only_when_no_fragments():
  out = p.build_system_prompt_v2()
  assert out.startswith("You are a recipe generator for V2 Forge action notes.")
  # End of base prompt — final clause spans a newline in source.
  assert "instead of\ninventing Python." in out
  assert out.rstrip().endswith("inventing Python.")


def test_build_system_prompt_v2_contains_statement_inventory():
  out = p.build_system_prompt_v2()
  # Spot-check every statement shape so a refactor doesn't silently
  # drop one.
  assert "Let name = <expr>." in out
  assert "Return <expr>." in out
  assert "Call [[chip]] with k=v, k=v." in out
  # v0.2.200 — shorthand-call statement form. Required for positional-
  # only callables like the Python builtin `print` (takes `*objects`,
  # NOT `text=` kwarg). Without this teaching the LLM defaulted to
  # `Call [[print]] with text="..."` which transpiled to
  # `print(text="...")` and crashed at runtime.
  assert "[[chip]] <expr>." in out
  assert "[[chip]]." in out
  assert "If <expr>:" in out
  assert "Otherwise:" in out
  assert "For each <name> in <expr>:" in out


def test_build_system_prompt_v2_warns_about_print_kwarg_form():
  """v0.2.200 regression guard: the prompt must explicitly tell the LLM
  that `Call [[print]] with text="..."` crashes with TypeError. Without
  this guard the LLM happily reproduced the bad form from Example 1
  (since fixed) — a tutorial vault smoke caught it for hello_world."""
  out = p.build_system_prompt_v2()
  assert "print" in out
  assert "TypeError" in out
  assert "[[print]]" in out


def test_build_system_prompt_v2_example_1_uses_shorthand_not_kwarg_form():
  """Example 1 must show the shorthand statement form, not the
  `Call [[fn]] with kwarg=...` form, for a callable that takes
  POSITIONAL args. Pre-v0.2.200 Example 1 taught the kwarg form and the
  LLM reproduced it verbatim — `print(text=)` crashes. (The Statements
  section is allowed to MENTION the bad form as a counterexample so the
  LLM knows what NOT to do — we only assert on the Example 1 recipe
  body here.)

  Updated 2026-08-12 (drain 1830, vendoring reconcile): Example 1 is now
  `length_of` using `[[len]] items.` rather than `hello_world` using
  `[[print]] "Hello, world!".`. The canonical copy of this prompt moved
  to forge-transpile (see forge-transpile/prompts/__init__.py), and its
  version had already swapped the positional-args exemplar from `print`
  to `len`. The INVARIANT under test is unchanged — Example 1 teaches
  shorthand, never the kwarg form — only the exemplar differs."""
  out = p.build_system_prompt_v2()
  # Extract Example 1's Recipe block.
  ex1_marker = "### Example 1: length_of"
  ex2_marker = "### Example 2:"
  assert ex1_marker in out
  assert ex2_marker in out
  block = out[out.index(ex1_marker):out.index(ex2_marker)]
  assert '[[len]] items.' in block
  assert 'Call [[len]] with obj=' not in block


def test_build_system_prompt_v2_contains_few_shot_examples():
  out = p.build_system_prompt_v2()
  # Each example's signature line, so we catch regressions if an
  # example is dropped.
  assert "Example 1: length_of" in out
  assert "Example 2: set_water_speed" in out
  assert "Example 3: setup" in out
  assert "Example 4: if_temp_high_set_speed" in out
  assert "Example 5: solitary" in out
  assert "Example 6: tick-loop composition" in out
  # Example 7 added by drain 2026-08-12-1650 (Input-keyword grammar);
  # reached the engine copy via the drain-1830 reconcile.
  assert "Example 7: parameterized Description with NO declared inputs" in out


def test_build_system_prompt_v2_warns_against_python_idioms():
  out = p.build_system_prompt_v2()
  assert "Do NOT use `def compute(context):`" in out
  assert "Do NOT use `context.compute(...)`." in out
  assert "Do NOT use `import`" in out


def test_build_system_prompt_v2_includes_registered_fragments():
  p.register_fragment_v2("music", "MUSIC GUIDANCE BLOCK")
  p.register_fragment_v2("moda", "MODA GUIDANCE BLOCK")
  out = p.build_system_prompt_v2()
  assert "MUSIC GUIDANCE BLOCK" in out
  assert "MODA GUIDANCE BLOCK" in out


def test_build_system_prompt_v2_filters_to_active_domains():
  p.register_fragment_v2("music", "MUSIC")
  p.register_fragment_v2("moda", "MODA")
  out = p.build_system_prompt_v2(active_domains=["music"])
  assert "MUSIC" in out
  assert "MODA" not in out


def test_build_system_prompt_v2_empty_active_domains_excludes_all():
  p.register_fragment_v2("music", "MUSIC")
  out = p.build_system_prompt_v2(active_domains=[])
  assert "MUSIC" not in out


def test_register_fragment_v2_is_idempotent_per_domain():
  p.register_fragment_v2("music", "ORIGINAL")
  p.register_fragment_v2("music", "UPDATED")
  out = p.build_system_prompt_v2()
  assert "UPDATED" in out
  assert "ORIGINAL" not in out


# ---------------------------------------------------------------------------
# build_user_prompt_v2 — field ordering + dep rendering
# ---------------------------------------------------------------------------

def test_build_user_prompt_v2_minimal_shape():
  out = p.build_user_prompt_v2(
    snippet_id="forge-tutorial/hello_world",
    description="Print Hello, world!.",
    inputs=[],
    deps=[],
  )
  assert out.startswith(
    'Generate V2 Recipe code for the Forge action note '
    '"forge-tutorial/hello_world".'
  )
  assert "Description: Print Hello, world!." in out
  # Empty inputs/deps don't surface their headings.
  assert "Inputs:" not in out
  assert "Available chips and notes to Call:" not in out
  assert "Output ONLY the body" in out


def test_build_user_prompt_v2_renders_inputs():
  out = p.build_user_prompt_v2(
    snippet_id="forge-moda/set_water_speed",
    description="Set water speed by temperature.",
    inputs=["state", "temperature"],
    deps=[],
  )
  assert "Inputs: state, temperature" in out


def test_build_user_prompt_v2_renders_deps_as_chip_call_signatures():
  out = p.build_user_prompt_v2(
    snippet_id="forge-moda/setup",
    description="Set up the chamber.",
    inputs=["temperature"],
    deps=[
      {
        "snippet_id": "create_water_particles",
        "description": "Adds 500 water particles.",
        "inputs": ["state"],
      },
      {
        "snippet_id": "create_chamber",
        "description": "Build empty chamber.",
        "inputs": ["width", "height"],
      },
    ],
  )
  # Dep lines use wikilink+with syntax, NOT context.compute().
  assert "[[create_water_particles]] with state=..." in out
  assert "[[create_chamber]] with width=..., height=..." in out
  assert "context.compute" not in out


def test_build_user_prompt_v2_renders_chipless_dep():
  out = p.build_user_prompt_v2(
    snippet_id="forge-moda/canonical_demo",
    description="Print a greeting.",
    inputs=[],
    deps=[
      {"snippet_id": "print", "description": "Builtin print.", "inputs": []},
    ],
  )
  # No "with" suffix when dep takes no inputs.
  assert "[[print]]" in out
  assert "[[print]] with" not in out


def test_build_user_prompt_v2_strips_description_whitespace():
  out = p.build_user_prompt_v2(
    snippet_id="x",
    description="  weird whitespace  \n",
    inputs=[],
    deps=[],
  )
  assert "Description: weird whitespace" in out


def test_build_user_prompt_v2_no_description_omits_field():
  out = p.build_user_prompt_v2(
    snippet_id="x",
    description="",
    inputs=[],
    deps=[],
  )
  assert "Description:" not in out


# ---------------------------------------------------------------------------
# registered_* introspection helpers
# ---------------------------------------------------------------------------

def test_registered_fragments_v2_returns_in_order():
  p.register_fragment_v2("music", "M-FRAG")
  p.register_fragment_v2("moda", "X-FRAG")
  assert p.registered_fragments_v2() == ["M-FRAG", "X-FRAG"]


def test_registered_domains_v2_returns_in_order():
  p.register_fragment_v2("music", "X")
  p.register_fragment_v2("moda", "Y")
  assert p.registered_domains_v2() == ["music", "moda"]
