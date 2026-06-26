"""V2-spec E-- (v2-spike). Separate from the legacy `forge/forge/e_minus_minus/`
module (which uses the Set/Do/Give-back dialect synced 2026-06-05). This
module implements the V2 spec's Let/Call/Return dialect described in
v2-spec.md §5-§6 and validated by the v2-spike-mini-solitary prompt.

Public surface:
  detect_recipe_shape(snippet_body)  -> bool
  parse(emm_source)              -> Module AST
  transpile(module_ast)          -> str  (Python source)
"""

from .detect import (
    InputDecl,
    detect_recipe_shape,
    extract_recipe_body,
    extract_inputs_declarations,
)
from .parser import Module, parse
from .transpiler import transpile

__all__ = [
    "InputDecl",
    "detect_recipe_shape",
    "extract_recipe_body",
    "extract_inputs_declarations",
    "Module",
    "parse",
    "transpile",
]
