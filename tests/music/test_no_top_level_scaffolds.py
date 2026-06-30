"""v0.3.3+: lock in deletion of inert top-level scaffolds.

Post-v0.7.0 promotion + v0.8.0 Slow Burn rename:
- `form.md` was promoted to `forge.music.lib.form` and deleted from the vault.
- `blues/` was renamed to `slow_burn/`.

The remaining check ensures the canonical `twelve_bar_blues_progression`
data note lives at its post-rename path so caller-scoped resolution from
inside `slow_burn/slow_burn.md` finds it.

Tests skip cleanly on fresh clones without ~/projects/forge-music/ via
the existing `music_vault` fixture.
"""
import os


def test_no_top_level_form_md(music_vault):
    """Top-level forge-music/form.md must not exist; form is now
    promoted to forge.music.lib.form (post-v0.7.0)."""
    path = os.path.join(music_vault, "form.md")
    assert not os.path.exists(path), (
        f"top-level {path} should not exist; form was promoted to lib"
    )


def test_no_top_level_twelve_bar_blues_progression_md(music_vault):
    """Top-level forge-music/twelve_bar_blues_progression.md must not
    exist; the canonical version lives under slow_burn/."""
    path = os.path.join(music_vault, "twelve_bar_blues_progression.md")
    assert not os.path.exists(path), (
        f"top-level {path} should be deleted; the slow_burn subdir version "
        "is canonical"
    )


def test_slow_burn_subdir_progression_exists(music_vault):
    """The slow_burn/ subdir version of twelve_bar_blues_progression
    must remain (this is what caller-scoped resolution finds from
    inside slow_burn/slow_burn.md per v0.2.26)."""
    progression_path = os.path.join(
        music_vault, "slow_burn", "twelve_bar_blues_progression.md",
    )
    assert os.path.exists(progression_path), (
        f"slow_burn/twelve_bar_blues_progression.md must exist; it's the "
        "canonical progression data snippet"
    )
