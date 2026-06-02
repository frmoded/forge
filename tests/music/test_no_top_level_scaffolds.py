"""v0.3.3+: lock in deletion of inert top-level scaffolds.

The forge-music vault had two top-level files (form.md,
twelve_bar_blues_progression.md) that pre-dated the v0.3.x blues/
subdirectory. The v0.2.28 Phase A audit confirmed they were inert in
production — no qualified `forge-music/form` or `forge-music/
twelve_bar_blues_progression` references exist in any production code
path (only a throwaway spike script + docs + historical feedback). The
user initially chose to keep them; this drain deletes them per Case A
of that audit.

This test scans the real vault on disk and asserts the deletion held.
A future content drain that accidentally re-introduces a top-level
`form.md` or `twelve_bar_blues_progression.md` will fail this test
before shipping.

Tests skip cleanly on fresh clones without ~/projects/forge-music/ via
the existing `music_vault` fixture.
"""
import os


def test_no_top_level_form_md(music_vault):
    """Top-level forge-music/form.md must not exist; the canonical
    `form` snippet is blues/form.md."""
    path = os.path.join(music_vault, "form.md")
    assert not os.path.exists(path), (
        f"top-level {path} should be deleted; the blues subdir version "
        "is canonical"
    )


def test_no_top_level_twelve_bar_blues_progression_md(music_vault):
    """Top-level forge-music/twelve_bar_blues_progression.md must not
    exist; the canonical version is blues/twelve_bar_blues_progression.md."""
    path = os.path.join(music_vault, "twelve_bar_blues_progression.md")
    assert not os.path.exists(path), (
        f"top-level {path} should be deleted; the blues subdir version "
        "is canonical"
    )


def test_blues_subdir_versions_still_exist(music_vault):
    """The blues/ subdir versions must remain (this is what gets resolved
    when snippets reference [[form]] or [[twelve_bar_blues_progression]]
    from inside the subdir per v0.2.26 caller-scoped resolution)."""
    form_path = os.path.join(music_vault, "blues", "form.md")
    progression_path = os.path.join(
        music_vault, "blues", "twelve_bar_blues_progression.md",
    )
    assert os.path.exists(form_path), (
        f"blues/form.md must exist; it's the canonical form snippet"
    )
    assert os.path.exists(progression_path), (
        f"blues/twelve_bar_blues_progression.md must exist; it's the "
        "canonical progression data snippet"
    )
