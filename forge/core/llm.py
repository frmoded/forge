import hashlib
import os
import re
from anthropic import Anthropic
from forge.core.executor import extract_section, extract_python
from forge.core.registry import SnippetRegistry
from forge.core.llm_prompts import build_system_prompt
# Side-effect import: registers the music-domain fragment with llm_prompts.
# Each new domain (arch, moda, ...) gets a parallel import here.
import forge.music.llm_prompt  # noqa: F401

_client = None

# In-memory cache: sha256(LLM prompt) → generated code.
# Hashing the prompt itself captures every input the model sees (snippet_id,
# description, inputs, english, dep signatures) and ignores the body's python
# section, which is the OUTPUT of generation and would otherwise self-invalidate
# the cache as soon as the client writes the generated code back to disk.
# Cache lives only as long as the server process; restart drops it.
_GENERATION_CACHE: dict[str, str] = {}


def generate_snippet_code(snippet_id: str, registry: SnippetRegistry, recursive: bool = False) -> dict[str, str]:
  """Return {snippet_id: generated_code} for snippet and optionally its dependencies."""
  results: dict[str, str] = {}
  _generate(snippet_id, registry, recursive, results, visited=set())
  return results


def _generate(snippet_id: str, registry: SnippetRegistry, recursive: bool, results: dict[str, str], visited: set[str]) -> None:
  if snippet_id in visited:
    return
  visited.add(snippet_id)

  snippet = registry.get(snippet_id)
  if snippet is None:
    raise KeyError(f"snippet '{snippet_id}' not found")

  # Builtin snippets ship with python in the package — LLM generation would
  # waste tokens regenerating working code, and the client has no user-vault
  # file to write the result back to. Skip generation and dep recursion;
  # non-builtin callers still embed builtin dep SIGNATURES (description /
  # inputs) in their own prompt via _call_llm.
  if snippet.get("source") == "builtin":
    import logging
    logging.getLogger(__name__).info("snippet '%s' skipped (builtin)", snippet_id)
    return

  # Edit-mode "python" (or the legacy alias `locked: true`): the user has
  # explicitly switched the snippet's edit-mode to Python — they're hand-
  # tuning the python facet and don't want LLM regeneration. Same shape as
  # the builtin skip — no LLM, no result, deps not walked. The plugin
  # pre-checks edit_mode before /generate so the user gets a clear notice;
  # this is defense-in-depth.
  meta = snippet["meta"]
  if meta.get("edit_mode") == "python" or meta.get("locked") is True:
    import logging
    logging.getLogger(__name__).info("snippet '%s' skipped (edit_mode=python)", snippet_id)
    return

  body = snippet["body"]
  deps = _find_deps(body)

  if recursive:
    for dep_id in deps:
      _generate(dep_id, registry, recursive, results, visited)

  import logging
  import time
  log = logging.getLogger(__name__)
  start = time.perf_counter()

  prompt = _build_prompt(snippet_id, meta, body, deps, registry if recursive else None)
  cache_key = hashlib.sha256(prompt.encode("utf-8")).hexdigest()

  # Diagnostic short-hashes to help spot what changed between runs. eng/py
  # show whether the user's input/output drifted; key reflects the full prompt.
  english = extract_section(body, "english") or ""
  python = extract_python(body) or ""
  diag = (
    f"key={cache_key[:8]} eng={_short_hash(english)} py={_short_hash(python)} "
    f"prompt_len={len(prompt)} cache_size={len(_GENERATION_CACHE)}"
  )

  cached = _GENERATION_CACHE.get(cache_key)
  if cached is not None:
    elapsed_ms = (time.perf_counter() - start) * 1000
    log.info("snippet '%s' generated via cache (%.1fms) [%s]", snippet_id, elapsed_ms, diag)
    results[snippet_id] = cached
    return

  code = _call_llm(snippet_id, prompt)
  _GENERATION_CACHE[cache_key] = code
  results[snippet_id] = code
  elapsed_ms = (time.perf_counter() - start) * 1000
  log.info("snippet '%s' generated via LLM (%.0fms) [%s]", snippet_id, elapsed_ms, diag)


_CANONICALIZE_SYSTEM_PROMPT = """You are summarizing Forge snippets back to their canonical English description.

Forge snippets are Python functions (entrypoint `compute(context, ...)`).
You are given the python facet of a snippet — your job is to write the
English facet that describes what it does, in the voice an author would
use when first writing the snippet.

Length matches code complexity:
- A one-line `print(...)` snippet gets one literal sentence.
- A three-line composition gets two sentences.
- A 50-line music generator gets a paragraph or two.

Voice: literal and direct. State what the code does. Do NOT add:
- "purely as a sanity check", "minimal example", "demo", "hello world"
  framing, or other meta-commentary about what KIND of snippet it is.
- Hedging like "It takes no inputs and produces no musical output" —
  if it has no inputs, just don't mention inputs.
- Background reasoning the code itself doesn't reveal.

Style:
- Plain prose, no headings, no bullet markers, no code blocks.
- Reference dependencies via [[wikilinks]] when the python calls
  context.compute("name") — write as [[name]].
- Mention key, time signature, tempo, instrument choices when the code
  sets them. Skip them when the code doesn't.

Output ONLY the English text. No surrounding fences, no commentary."""


def canonicalize_python(snippet_id: str, registry: SnippetRegistry) -> str:
  """Reverse direction: given a snippet's current python facet, ask the LLM
  for a canonical English description. Returned text is plain prose, ready
  to be written into the snippet's `# English` section by the caller."""
  snippet = registry.get(snippet_id)
  if snippet is None:
    raise KeyError(f"snippet '{snippet_id}' not found")

  python = extract_python(snippet["body"]) or ""
  if not python.strip():
    raise ValueError(
      f"snippet '{snippet_id}' has no Python facet to canonicalize")

  meta = snippet["meta"]
  description = (meta.get("description") or "").strip()
  inputs = meta.get("inputs") or []

  user_lines = [
    f'Snippet id: {snippet_id}',
  ]
  if description:
    user_lines.append(f"Frontmatter description: {description}")
  if inputs:
    user_lines.append(f"Inputs: {', '.join(str(i) for i in inputs)}")
  user_lines.append("Python facet:")
  user_lines.append("```python")
  user_lines.append(python)
  user_lines.append("```")
  user_lines.append(
    "Return the canonical English description for this snippet, suitable "
    "as the body of the # English section."
  )
  prompt = "\n".join(user_lines)

  import logging
  import time
  log = logging.getLogger(__name__)
  start = time.perf_counter()
  client = _get_client()
  message = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=2048,
    system=_CANONICALIZE_SYSTEM_PROMPT,
    messages=[{"role": "user", "content": prompt}],
  )
  elapsed_ms = (time.perf_counter() - start) * 1000
  text = message.content[0].text.strip()
  log.info(
    "snippet '%s' canonicalized via LLM (%.0fms) [out_len=%d]",
    snippet_id, elapsed_ms, len(text),
  )
  return text


def _build_prompt(snippet_id, meta, body, deps, registry):
  """Assemble the user prompt sent to the LLM. Pulled out so the cache can
  hash exactly what the model will see."""
  description = meta.get("description", "").strip()
  inputs = meta.get("inputs") or []
  english = extract_section(body, "english") or ""

  lines = [f'Generate Python code for the Forge snippet "{snippet_id}".']
  if description:
    lines.append(f"Description: {description}")
  if inputs:
    lines.append(f"Inputs: {', '.join(str(i) for i in inputs)}")
  if english:
    lines.append(f"Behavior: {english}")
  if deps and registry:
    dep_lines = []
    for dep_id in deps:
      dep = registry.get(dep_id)
      if dep:
        dep_desc = dep["meta"].get("description", "").strip()
        dep_inputs = dep["meta"].get("inputs") or []
        sig = f"context.compute(\"{dep_id}\"{', ' + ', '.join(f'{i}=...' for i in dep_inputs) if dep_inputs else ''})"
        dep_lines.append(f"  - {dep_id}: {dep_desc}  →  {sig}")
    if dep_lines:
      lines.append("Available snippets to call:\n" + "\n".join(dep_lines))

  return "\n".join(lines)


def _call_llm(snippet_id, prompt):
  client = _get_client()
  message = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=8192,
    system=build_system_prompt(),
    messages=[{"role": "user", "content": prompt}],
  )
  if message.stop_reason == "max_tokens":
    import logging
    logging.getLogger(__name__).warning(
      "generation hit max_tokens for snippet '%s' — output may be truncated", snippet_id,
    )
  return message.content[0].text.strip()


def _short_hash(s: str) -> str:
  """First 8 hex chars of sha256(s) — enough to spot drift in logs."""
  return hashlib.sha256(s.encode("utf-8")).hexdigest()[:8]


_ID_CHARS = r"[\w./-]+"  # word chars (letters/digits/_), slash, period, hyphen


def _find_deps(body):
  """Find snippet IDs referenced via [[wiki-links]] or context.compute() calls.

  Only matches IDs made of valid identifier characters (\\w / . -). Prose
  wikilinks like [[<vault_name>/...]] or f-string fragments like
  [[{vault_name}/...]] (which the install builtin has in its English and
  return message) are skipped — they aren't real refs and would otherwise
  cause a recursive /generate to fail with a 404 on a phantom dep."""
  deps = []
  seen = set()
  for m in re.finditer(rf'\[\[({_ID_CHARS})(?:\|[^\]]*)?\]\]', body):
    dep = m.group(1).strip()
    if dep and dep not in seen:
      deps.append(dep)
      seen.add(dep)
  for m in re.finditer(rf'context\.compute\(\s*["\']({_ID_CHARS})["\']', body):
    dep = m.group(1).strip()
    if dep and dep not in seen:
      deps.append(dep)
      seen.add(dep)
  return deps


def _get_client():
  global _client
  if _client is None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
      raise RuntimeError("ANTHROPIC_API_KEY is not set")
    _client = Anthropic(api_key=api_key)
  return _client
