"""Geometry helpers for the optional second ring of pie-menu commands."""

import math


def outer_ring_positions(outer_flags, radius, button_size, icon_size,
                         pack_outer=False, pack_inner=False):
    """Return command centers in command order, using each command's ring.

    The gap between rings is 60% of the rendered icon size. Packed
    buttons start at the top with a four-pixel gap between adjacent buttons.
    Otherwise the outer ring is evenly spaced and staggered half a slot.
    """
    outer_count = sum(outer_flags)
    inner_count = len(outer_flags) - outer_count
    ring_indices = {False: 0, True: 0}
    positions = []
    for is_outer in outer_flags:
        ring_count = outer_count if is_outer else inner_count
        ring_radius = radius + button_size + icon_size * 0.6 if is_outer else radius
        step = 2 * math.pi / ring_count
        start = -math.pi / 2 + (step / 2 if is_outer and ring_count > 1 else 0)
        if (pack_outer if is_outer else pack_inner):
            # Convert the desired center-to-center chord into an angle. Cap
            # at one complete ring so large command lists never wrap twice.
            step = min(step, 2 * math.asin(min(1, (button_size + 4) / (2 * ring_radius))))
            start = -math.pi / 2
        angle = start + ring_indices[is_outer] * step
        positions.append((ring_radius * math.cos(angle),
                          ring_radius * math.sin(angle)))
        ring_indices[is_outer] += 1
    return positions
