"""Tests for forge.core.lib — domain-agnostic library primitives.

Drain 2026-07-26-1000: `nth` + `pick_indices`.
"""
import pytest

from forge.core.lib import nth, pick_indices


class TestNth:
  def test_first_element(self):
    assert nth(["a", "b", "c"], 0) == "a"

  def test_middle_element(self):
    assert nth([10, 20, 30], 1) == 20

  def test_last_element_positive_index(self):
    assert nth([1, 2, 3], 2) == 3

  def test_negative_index_from_end(self):
    """Python semantics: -1 is last, -2 is second-to-last."""
    assert nth([1, 2, 3], -1) == 3
    assert nth([1, 2, 3], -2) == 2

  def test_out_of_range_raises_index_error(self):
    with pytest.raises(IndexError):
      nth([1, 2, 3], 5)

  def test_empty_list_raises_index_error(self):
    """Do NOT silently return None."""
    with pytest.raises(IndexError):
      nth([], 0)

  def test_works_with_tuples(self):
    assert nth((10, 20, 30), 1) == 20


class TestPickIndices:
  def test_pick_alternating(self):
    assert pick_indices(["a", "b", "c", "d", "e"], [0, 2, 4]) == ["a", "c", "e"]

  def test_pick_single(self):
    assert pick_indices([1, 2, 3], [1]) == [2]

  def test_pick_empty_indices(self):
    """No indices → empty result, not error."""
    assert pick_indices([1, 2, 3], []) == []

  def test_pick_reordered(self):
    """Indices order determines result order."""
    assert pick_indices(["a", "b", "c"], [2, 0, 1]) == ["c", "a", "b"]

  def test_pick_repeated_indices(self):
    """Same index twice → same element twice."""
    assert pick_indices(["a", "b"], [0, 0, 1]) == ["a", "a", "b"]

  def test_pick_negative_indices(self):
    """Python semantics propagate."""
    assert pick_indices([10, 20, 30], [-1, -2]) == [30, 20]

  def test_out_of_range_raises_index_error(self):
    with pytest.raises(IndexError):
      pick_indices([1, 2, 3], [5])

  def test_pick_from_empty_list_with_indices_raises(self):
    with pytest.raises(IndexError):
      pick_indices([], [0])
