"""Preserve historical YOLO semantics and accept the additional user class."""
from pathlib import Path
import tempfile
import unittest

from src.block3_feature_extractor import CLASS_MAP, TopologicalFeatureExtractor
from src.desktop.object_labels import CLASS_BY_KEY


class SharedObjectClassTests(unittest.TestCase):
    def test_original_yolo_ids_and_manual_meanings_agree(self):
        expected = (
            (0, 'particle', 'Sphere'),
            (1, 'fiber', 'Curve'),
            (2, 'self_crossed_tube', 'Self-intersecting curve'),
            (3, 'crossed_tubes', 'Intersecting curves'),
            (4, 'agglomeration', 'Agglomeration'),
            (5, 'adhered_objects', 'Adhered objects'),
        )
        for ident, key, original_name in expected:
            self.assertEqual(CLASS_MAP[ident], original_name)
            self.assertEqual(CLASS_BY_KEY[key]['id'], ident)

    def test_all_six_classes_are_accepted_as_yolo_polygons(self):
        with tempfile.TemporaryDirectory() as directory:
            labels = Path(directory) / 'tile.txt'
            labels.write_text(''.join(f'{ident} 0.1 0.1 0.7 0.1 0.1 0.8\n' for ident in range(6)), encoding='utf-8')
            parsed = TopologicalFeatureExtractor._parse_yolo(str(labels), 100, 200)
            self.assertEqual([ident for ident, _ in parsed], list(range(6)))
            for _, polygon in parsed:
                self.assertEqual(polygon.reshape(-1, 2).tolist(), [[10, 20], [70, 20], [10, 160]])

    def test_unknown_source_class_remains_invalid_annotation(self):
        with tempfile.TemporaryDirectory() as directory:
            labels = Path(directory) / 'tile.txt'
            for ident in (-1, 6):
                labels.write_text(f'{ident} 0.1 0.1 0.7 0.1 0.1 0.8\n', encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'Unknown annotation class'):
                    TopologicalFeatureExtractor._parse_yolo(str(labels), 100, 200)


if __name__ == '__main__':
    unittest.main()
