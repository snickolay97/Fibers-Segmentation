import os
import unittest
from unittest.mock import patch

import numpy as np

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from src.desktop.i18n import get_language, set_language
from src.desktop.qt import QtCore, QtWidgets
from src.desktop.result_statistics import StatisticsDialog, class_counts_by_tile, feature_matrix, log_histogram_edges


class FeatureStatisticsTests(unittest.TestCase):
    def test_constant_decimal_has_undefined_correlation(self):
        rows = np.array([[.1, 1, 7], [.1, 2, 6], [.1, 3, 5]])

        np.testing.assert_allclose(feature_matrix(rows, correlation=True),
                                   [[np.nan, np.nan, np.nan],
                                    [np.nan, 1, -1],
                                    [np.nan, -1, 1]])
        np.testing.assert_allclose(feature_matrix(rows, correlation=False),
                                   [[0, 0, 0], [0, 1, -1], [0, -1, 1]])

    def test_single_feature_uses_sample_covariance(self):
        rows = np.array([[1], [2], [3]])

        np.testing.assert_allclose(feature_matrix(rows, correlation=False), [[1]])

    def test_log_intervals_keep_small_large_and_constant_areas(self):
        for values in (np.array([40., 100., 200., 454239.]), np.array([114., 114.])):
            edges = log_histogram_edges(values, 30)
            self.assertEqual(len(edges), 31)
            np.testing.assert_allclose(edges[1:] / edges[:-1], edges[1] / edges[0])
            counts, _ = np.histogram(values, bins=edges)
            self.assertEqual(counts.sum(), len(values))
            self.assertGreater(np.count_nonzero(counts), 1 if np.ptp(values) else 0)

    def test_counts_use_manual_keys_per_tile_and_keep_unclassified_separate(self):
        rows = [dict(Tile_Name='a', Object_ID=1, Class_ID=1),
                dict(Tile_Name='b', Object_ID=1, Class_ID=0),
                dict(Tile_Name='b', Object_ID=2, Class_ID=1)]
        labels = {'a/1': {'Manual_Class': 'particle'}, 'b/1': {'Manual_Class': 'fiber'},
                  'outside/1': {'Manual_Class': 'particle'}}
        counts = class_counts_by_tile(rows, labels)
        self.assertEqual(counts[None], {'particle': 1, 'fiber': 1, None: 1})
        self.assertEqual(counts['a'], {'particle': 1})
        self.assertEqual(counts['b'], {'fiber': 1, None: 1})

    def test_results_plot_changes_scale_and_selects_another_image_and_tile(self):
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        self.addCleanup(set_language, get_language())
        set_language('en')
        rows = [dict(Tile_Name='tile', Object_ID=i, Area=value)
                for i, value in enumerate((40, 114, 454239, 0), 1)]
        first = dict(id='first', name='First')
        second = dict(id='second', name='Second', last_csv='file.csv', results_current=True)
        dialog = StatisticsDialog(['Area'], rows, None, dataset=first, project_datasets=[first, second])
        try:
            axes = dialog.figure.axes[0]
            self.assertEqual(axes.get_xscale(), 'log')
            self.assertEqual(sum(bar.get_height() for bar in axes.patches), 3)
            self.assertIn('omitted: 1', dialog.summary.text())
            dialog.histogram_scale.setCurrentIndex(dialog.histogram_scale.findData('linear'))
            axes = dialog.figure.axes[0]
            self.assertEqual(axes.get_xscale(), 'linear')
            self.assertEqual(sum(bar.get_height() for bar in axes.patches), 4)
            dialog.kind.setCurrentIndex(dialog.kind.findText('Classes by image'))
            second_rows = [dict(Tile_Name='a', Object_ID=1), dict(Tile_Name='b', Object_ID=1)]
            with (patch('src.desktop.service.read_results', return_value=(['Area'], second_rows)) as read,
                  patch('src.desktop.service.get_object_labels',
                        return_value={'labels': {'a/1': {'Manual_Class': 'fiber'}}})):
                dialog.class_source.setCurrentIndex(dialog.class_source.findData('second'))
                self.assertIn('1 of 2', dialog.summary.text())
                dialog.class_tile.setCurrentIndex(dialog.class_tile.findData('a'))
                self.assertIn('1 of 1', dialog.summary.text())
                self.assertEqual([bar.get_width() for bar in dialog.figure.axes[0].patches], [0, 1, 0, 0, 0, 0])
                read.assert_called_once_with(second)
        finally:
            dialog.deleteLater()
            QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
            app.processEvents()

    def test_zoom_and_chart_colors_preserve_view_and_counts(self):
        from types import SimpleNamespace
        from matplotlib.colors import to_hex
        from src.desktop.qt import QtGui

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        dialog = StatisticsDialog(['Area'], [dict(Area=value) for value in (20, 50, 100)], None)
        try:
            axes = dialog.figure.axes[0]
            initial = axes.get_xlim()
            dialog._wheel_zoom(SimpleNamespace(inaxes=axes, step=1, xdata=50, ydata=.5))
            zoomed = axes.get_xlim()
            self.assertGreater(zoomed[0], initial[0])
            self.assertLess(zoomed[1], initial[1])
            with patch.object(QtWidgets.QColorDialog, 'getColor', return_value=QtGui.QColor('#9d3471')):
                dialog._choose_color('data_color', 'Data color…')
            axes = dialog.figure.axes[0]
            self.assertEqual(axes.get_xlim(), zoomed)
            self.assertEqual(sum(bar.get_height() for bar in axes.patches), 3)
            self.assertEqual(to_hex(axes.patches[0].get_facecolor()), '#9d3471')
            dialog.show_settings.setChecked(False)
            self.assertTrue(dialog.settings.isHidden())
            dialog.toolbar.home()
            np.testing.assert_allclose(axes.get_xlim(), initial)
        finally:
            dialog.deleteLater()
            QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
            app.processEvents()
