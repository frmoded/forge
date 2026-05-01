import os
import re
from anthropic import Anthropic
from forge.core.executor import extract_section, extract_python
from forge.core.registry import SnippetRegistry

_client = None

_SYSTEM_PROMPT = """You are a code generator for the Forge snippet system.

Forge snippets are Python functions. Follow these conventions exactly:
- Every snippet's entrypoint must be named `compute`.
- Snippets with no inputs:      def compute(context): ...
- Snippets with named inputs:   def compute(context, param1, param2): ...
- Call another snippet:         context.compute("snippet_id", param=value)
- Read an input parameter:      context.get("key", default)
- Side-effect output:           print(...)
- Return the result value at the end of the function.

Available modules (already in scope, do NOT import them): random, math, numpy

Output ONLY valid Python code. No markdown fences, no explanation, no comments."""


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

  meta = snippet["meta"]
  body = snippet["body"]
  deps = _find_deps(body)

  if recursive:
    for dep_id in deps:
      _generate(dep_id, registry, recursive, results, visited)

  results[snippet_id] = _call_llm(snippet_id, meta, body, deps, registry if recursive else None)


def _call_llm(snippet_id, meta, body, deps, registry):
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

  prompt = "\n".join(lines)
  client = _get_client()
  message = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    system=_SYSTEM_PROMPT,
    messages=[{"role": "user", "content": prompt}],
  )
  return message.content[0].text.strip()


def _find_deps(body):
  """Find snippet IDs referenced via [[wiki-links]] or context.compute() calls."""
  deps = []
  seen = set()
  for m in re.finditer(r'\[\[([^\]|#]+?)(?:\|[^\]]*)?\]\]', body):
    dep = m.group(1).strip()
    if dep not in seen:
      deps.append(dep)
      seen.add(dep)
  for m in re.finditer(r'context\.compute\(\s*["\']([^"\']+)["\']', body):
    dep = m.group(1).strip()
    if dep not in seen:
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
