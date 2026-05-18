"""Single end-to-end run of the 25-block MoDa chain.

Mirrors the demo lifecycle: init (setup), 30 go ticks, a click, 30 more
go ticks. Asserts no out-of-bounds particles, ink present, exact
particle count, no exceptions, and kinetic-energy conservation (the
collision block swaps headings only, never speeds).
"""
import numpy as np


def test_full_lifecycle(run_block):
    # 1. /moda/init equivalent
    s = run_block("setup", "medium")
    assert len(s.ids) == 500 and (s.types == "water").all()

    ke_initial = float((s.speeds ** 2).sum())

    # 2. 30 ticks of go @ medium
    for _ in range(30):
        s = run_block("go", s, 1.0 / 30.0, "medium")
    assert s.tick == 30

    # 3. simulate a click
    s = run_block("on_mouse_click", s, 400.0, 300.0)
    assert len(s.ids) == 550
    assert (s.types == "ink").sum() == 50

    # 4. 30 more ticks
    for _ in range(30):
        s = run_block("go", s, 1.0 / 30.0, "medium")
    assert s.tick == 60

    # 5. assertions
    assert len(s.ids) == 550
    assert (s.types == "ink").sum() == 50
    assert (s.types == "water").sum() == 500

    in_bounds = (
        (s.xs >= 0) & (s.xs <= s.width) & (s.ys >= 0) & (s.ys <= s.height)
    )
    assert in_bounds.all(), (
        f"{(~in_bounds).sum()} particles out of bounds")

    # KE: water speed is re-pinned by ask_water_particles every tick
    # (medium -> 50), ink stays at the medium constant, and collisions
    # swap headings only. So total KE is exactly the steady-state value
    # and must match a fresh medium-state's KE within 1%.
    ke_now = float((s.speeds ** 2).sum())
    ke_ref = 550 * (50.0 ** 2)  # 500 water + 50 ink, all at speed 50
    assert abs(ke_now - ke_ref) / ke_ref < 0.01, (
        f"KE drifted: now={ke_now:.1f} ref={ke_ref:.1f}")
    # sanity: initial setup KE was 500 water @ 50
    assert ke_initial == 500 * (50.0 ** 2)
