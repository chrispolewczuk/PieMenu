import math
import unittest

from piemenu.layout import outer_ring_positions


class OuterRingLayoutTests(unittest.TestCase):
    def test_empty_menu(self):
        self.assertEqual(outer_ring_positions([], 80, 32, 24), [])

    def test_inner_only_starts_at_top(self):
        positions = outer_ring_positions([False] * 3, 80, 32, 24)
        self.assertEqual(len(positions), 3)
        self.assertAlmostEqual(positions[0][0], 0)
        self.assertAlmostEqual(positions[0][1], -80)
        for x, y in positions:
            self.assertAlmostEqual(math.hypot(x, y), 80)

    def test_assignments_preserve_command_order(self):
        flags = [True, False, True, False, False, True]
        positions = outer_ring_positions(flags, 80, 32, 24)
        self.assertEqual(len(positions), len(flags))
        for is_outer, (x, y) in zip(flags, positions):
            expected = 80 + 32 + 24 * 0.6 if is_outer else 80
            self.assertAlmostEqual(math.hypot(x, y), expected)

    def test_outer_only_does_not_require_inner_commands(self):
        positions = outer_ring_positions([True] * 4, 80, 32, 24)
        self.assertEqual(len(positions), 4)
        for x, y in positions:
            self.assertAlmostEqual(math.hypot(x, y), 80 + 32 + 24 * 0.6)

    def test_gap_scales_with_icon_size(self):
        for icon_size in (16, 24, 80):
            positions = outer_ring_positions([False, True], 80, 32, icon_size)
            self.assertAlmostEqual(
                math.hypot(*positions[-1]) - 80 - 32, icon_size * 0.6)

    def test_single_outer_command_starts_at_top(self):
        x, y = outer_ring_positions([True], 80, 32, 24)[0]
        self.assertAlmostEqual(x, 0)
        self.assertAlmostEqual(y, -(80 + 32 + 24 * 0.6))

    def test_outer_ring_is_evenly_spaced_and_staggered(self):
        positions = outer_ring_positions([True] * 8, 80, 32, 24, pack_outer=False)
        step = 2 * math.pi / 8
        angles = [math.atan2(y, x) for x, y in positions]
        self.assertAlmostEqual(angles[0], -math.pi / 2 + step / 2)
        for index in range(len(angles)):
            difference = angles[(index + 1) % len(angles)] - angles[index]
            self.assertAlmostEqual(difference % (2 * math.pi), step)

    def test_each_ring_has_distinct_positions(self):
        positions = outer_ring_positions([False, True] * 12, 80, 32, 24)
        self.assertEqual(len({(round(x, 6), round(y, 6))
                              for x, y in positions}), 24)

    def test_packed_outer_buttons_start_at_top_and_sit_next_to_each_other(self):
        positions = outer_ring_positions([True] * 4, 80, 32, 24, pack_outer=True)
        self.assertAlmostEqual(positions[0][0], 0)
        self.assertLess(positions[0][1], 0)
        for first, second in zip(positions, positions[1:]):
            self.assertAlmostEqual(math.dist(first, second), 32 + 4)

    def test_packed_spacing_does_not_depend_on_outer_command_count(self):
        few = outer_ring_positions([True] * 3, 80, 32, 24, pack_outer=True)
        more = outer_ring_positions([True] * 8, 80, 32, 24, pack_outer=True)
        self.assertEqual(few, more[:3])

    def test_spacing_mode_does_not_change_inner_ring(self):
        flags = [False, True, False, True, False]
        packed = outer_ring_positions(flags, 80, 32, 24, pack_outer=True)
        even = outer_ring_positions(flags, 80, 32, 24, pack_outer=False)
        for index, is_outer in enumerate(flags):
            if not is_outer:
                self.assertEqual(packed[index], even[index])

    def test_crowded_packed_ring_does_not_wrap_more_than_once(self):
        positions = outer_ring_positions([True] * 80, 80, 32, 24, pack_outer=True)
        self.assertEqual(len({(round(x, 6), round(y, 6))
                              for x, y in positions}), 80)

    def test_packed_inner_ring_works_without_outer_commands(self):
        positions = outer_ring_positions([False] * 4, 80, 32, 24, pack_inner=True)
        self.assertAlmostEqual(positions[0][0], 0)
        self.assertAlmostEqual(positions[0][1], -80)
        for first, second in zip(positions, positions[1:]):
            self.assertAlmostEqual(math.dist(first, second), 36)

    def test_inner_packing_does_not_change_outer_ring(self):
        flags = [False, True, False, True, False]
        packed = outer_ring_positions(flags, 80, 32, 24, pack_inner=True)
        equally = outer_ring_positions(flags, 80, 32, 24)
        for index, is_outer in enumerate(flags):
            if is_outer:
                self.assertEqual(packed[index], equally[index])

    def test_default_inner_spacing_matches_native_pie(self):
        count = 5
        positions = outer_ring_positions([False] * count, 80, 32, 24)
        for index, (x, y) in enumerate(positions):
            angle = -math.pi / 2 + index * 2 * math.pi / count
            self.assertAlmostEqual(x, 80 * math.cos(angle))
            self.assertAlmostEqual(y, 80 * math.sin(angle))


if __name__ == "__main__":
    unittest.main()