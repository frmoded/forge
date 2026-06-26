"""v2-migration §4 — parser extensions: If/Otherwise + arithmetic + comparisons.

Per v2-spec §5.2, the V2 dialect supports If X: / Otherwise: blocks and
simple arithmetic + comparisons. The v2-spike parser shipped without
these; this drain fills the gap so factorial (and other recursion/
conditional notes) migrate cleanly.
"""

import pytest

from forge.recipe import parse, transpile
from forge.recipe.parser import (
    BinaryOp,
    ForEachStmt,
    IfStmt,
    LetStmt,
    NumberLit,
    ReturnStmt,
)


class TestIfStmt:
  def test_if_simple(self):
    m = parse(
      "If n <= 1:\n"
      "  Return 1.\n"
    )
    assert len(m.statements) == 1
    s = m.statements[0]
    assert isinstance(s, IfStmt)
    assert isinstance(s.condition, BinaryOp)
    assert s.condition.op == "<="
    assert len(s.then_body) == 1
    assert s.else_body == []

  def test_if_otherwise(self):
    m = parse(
      "If x > 0:\n"
      "  Return x.\n"
      "Otherwise:\n"
      "  Return 0.\n"
    )
    assert len(m.statements) == 1
    s = m.statements[0]
    assert isinstance(s, IfStmt)
    assert len(s.then_body) == 1
    assert len(s.else_body) == 1


class TestArithmetic:
  def test_subtraction(self):
    m = parse("Let r = n - 1.")
    s = m.statements[0]
    assert isinstance(s.value, BinaryOp)
    assert s.value.op == "-"

  def test_multiplication(self):
    m = parse("Let r = n * 2.")
    s = m.statements[0]
    assert isinstance(s.value, BinaryOp)
    assert s.value.op == "*"

  def test_addition_in_kwarg(self):
    m = parse("Let r = Call [[f]] with x=a + 1.")
    s = m.statements[0]
    # ChipCall with kwargs[0].value = BinaryOp(a + 1)
    assert isinstance(s.value.kwargs[0].value, BinaryOp)
    assert s.value.kwargs[0].value.op == "+"


class TestComparisons:
  def test_le(self):
    m = parse("Let r = n <= 1.")
    assert m.statements[0].value.op == "<="

  def test_eq(self):
    m = parse("Let r = a == b.")
    assert m.statements[0].value.op == "=="

  def test_lt(self):
    m = parse("Let r = a < b.")
    assert m.statements[0].value.op == "<"


class TestTranspileAndExec:
  def test_if_otherwise_transpile(self):
    py = transpile(parse(
      "If n <= 1:\n"
      "  Return 1.\n"
      "Otherwise:\n"
      "  Return n.\n"
    ))
    assert "if (n <= 1):" in py
    assert "return 1" in py
    assert "else:" in py
    assert "return n" in py

  def test_factorial_executes(self):
    """End-to-end: V2 factorial migrates faithfully."""
    from forge.recipe import InputDecl
    inputs = [InputDecl(name="n", default=5, has_default=True, doc="")]
    py = transpile(parse(
      "If n <= 1:\n"
      "  Return 1.\n"
      "Return n * Call [[factorial]] with n=n - 1.\n"
    ), inputs=inputs)
    # Provide a self-call shim.
    scope = {}
    def factorial(n):
      sub_scope = {"factorial": factorial}
      exec(py, sub_scope)
      return sub_scope["compute"](context=None, n=n)
    scope["factorial"] = factorial
    exec(py, scope)
    # Stamp the shim now that compute exists.
    assert scope["compute"](context=None, n=5) == 120
    assert scope["compute"](context=None, n=1) == 1
    assert scope["compute"](context=None, n=3) == 6
