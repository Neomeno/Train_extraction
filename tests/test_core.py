import tempfile
import unittest
from pathlib import Path

from trainclip.cache import AnalysisCache
from trainclip.core import Interval, Sample, clip_ranges, train_events


def samples(*values, fps=2):
    return [Sample(index / fps, confidence) for index, confidence in enumerate(values)]


class EventTests(unittest.TestCase):
    def test_requires_consecutive_hits_and_merges_short_gap(self):
        points = samples(0.8, 0, 0.9, 0.8, 0, 0, 0.9, 0.9)
        result = train_events(points, sample_fps=2, confidence=0.5,
                              min_area_percent=0, consecutive=2, merge_gap=1,
                              duration=4)
        self.assertEqual(result, [Interval(1, 4)])

    def test_does_not_treat_zero_score_as_a_detection(self):
        result = train_events(samples(0, 0, 0), sample_fps=2,
                              confidence=0.1, min_area_percent=0, consecutive=1,
                              merge_gap=0, duration=2)
        self.assertEqual(result, [])

    def test_long_gap_stays_separate(self):
        result = train_events(samples(0.8, 0.8, 0, 0, 0, 0, 0.8, 0.8),
                              sample_fps=2, confidence=0.5, min_area_percent=0,
                              consecutive=2, merge_gap=1, duration=4)
        self.assertEqual(result, [Interval(0, 1), Interval(3, 4)])

    def test_padding_clamps_and_joins_overlaps(self):
        result = clip_ranges([Interval(1, 2), Interval(4, 5), Interval(19, 20)],
                             before=2, after=2, duration=20)
        self.assertEqual(result, [Interval(0, 7), Interval(17, 20)])

    def test_area_filter_and_confidence(self):
        points = [Sample(0, 0.9, 0.1), Sample(0.5, 0.7, 0.8),
                  Sample(1, 0.8, 0.8)]
        result = train_events(points, sample_fps=2, confidence=0.75,
                              min_area_percent=0.5, consecutive=2, merge_gap=0,
                              duration=2)
        self.assertEqual(result, [])


class CacheTests(unittest.TestCase):
    def test_cache_uses_file_identity_and_analysis_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "sample.mp4"
            source.write_bytes(b"video")
            cache = AnalysisCache(Path(folder) / "cache.sqlite")
            try:
                self.assertIsNone(cache.get(source, "model-a"))
                cache.put(source, "model-a", [Sample(1, 0.8, 1.2)])
                self.assertEqual(cache.get(source, "model-a"), [Sample(1, 0.8, 1.2)])
                self.assertIsNone(cache.get(source, "model-b"))
                source.write_bytes(b"changed-video")
                self.assertIsNone(cache.get(source, "model-a"))
            finally:
                cache.close()


if __name__ == "__main__":
    unittest.main()

