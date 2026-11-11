"""The last workflow page contains current tables, charts and exports."""
from . import segmentation_text
from .help import attach_help, install_image_help
from .i18n import get_language, register_translations, tr
from .qt import QtCore, QtWidgets, show_centered_window
from .widgets import CsvTable


register_translations({'Open charts in a separate window…': 'Открыть графики в отдельном окне…'})


class AnalysisPage(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._fields, self._rows, self._plot, self._dirty = [], [], None, True
        self._dataset, self._labels, self._project_datasets = {}, {}, ()
        self._chart_window = None
        layout = QtWidgets.QVBoxLayout(self); layout.setContentsMargins(0,8,0,0)
        self.summary = QtWidgets.QLabel(); layout.addWidget(self.summary)
        self.tabs = QtWidgets.QTabWidget(); layout.addWidget(self.tabs,1)
        self.chart_container = QtWidgets.QWidget()
        self.chart_layout = QtWidgets.QVBoxLayout(self.chart_container); self.chart_layout.setContentsMargins(0,0,0,0)
        self.open_charts = QtWidgets.QPushButton(tr('Open charts in a separate window…'))
        self.open_charts.setEnabled(False)
        self.open_charts.clicked.connect(self.show_charts_window)
        self.chart_layout.addWidget(attach_help(self.open_charts, 'feature_statistics'),
                                    alignment=QtCore.Qt.AlignmentFlag.AlignLeading)
        self.empty = QtWidgets.QLabel(tr('No current objects to plot.')); self.chart_layout.addWidget(self.empty)
        self.table = CsvTable()
        self.tabs.addTab(self.chart_container,tr('Charts')); self.tabs.addTab(self.table,tr('Feature table'))
        self.tabs.currentChanged.connect(self.ensure_plot)
        self.actions = QtWidgets.QHBoxLayout(); layout.addLayout(self.actions)

    def set_data(self, dataset, fields, rows, labels, *, project_datasets=()):
        self._fields, self._rows, self._dirty = list(fields), list(rows), True
        self._dataset, self._labels = dict(dataset or {}), labels
        self._project_datasets = tuple(project_datasets)
        self.open_charts.setEnabled(bool(self._rows))
        if dataset and dataset.get('last_csv') and fields:
            self.table.load_csv(dataset['last_csv']); self.table.set_manual_labels(labels)
        else:
            self.table.clear()
        count, labeled = len(rows), labels.get('assigned',0)
        self.summary.setText(tr('Objects: {objects} · Labeled: {labeled} · Unlabeled: {unlabeled}',
                                objects=count,labeled=labeled,unlabeled=count-labeled))
        if self.isVisible(): self.ensure_plot()

    def ensure_plot(self, *_):
        if not self._dirty or not self.isVisible() or self.tabs.currentIndex() != 0: return
        state = None
        if self._plot is not None:
            state = self._plot.view_state()
            self.chart_layout.removeWidget(self._plot); self._plot.deleteLater(); self._plot = None
        self.empty.setVisible(not self._rows)
        if self._rows:
            self._plot = self._create_chart()
            self._plot.setWindowFlags(QtCore.Qt.WindowType.Widget)
            self.chart_layout.addWidget(self._plot,1)
            if state:
                self._plot.apply_view_state(state)
            self._plot.show()
        self._dirty = False

    def _create_chart(self):
        from .result_statistics import StatisticsDialog

        return StatisticsDialog(self._fields, self._rows, self, dataset=self._dataset, labels=self._labels,
                                project_datasets=self._project_datasets)

    def show_charts_window(self):
        if not self._rows:
            return
        if self._chart_window is not None:
            self._chart_window.raise_()
            self._chart_window.activateWindow()
            return self._chart_window
        dialog = self._create_chart()
        if name := self._dataset.get('name'):
            dialog.setWindowTitle(tr('Feature statistics') + ' — ' + name)
        original = self._plot
        if original is not None:
            dialog.copy_view_from(original)
        self._chart_window = dialog
        dialog.finished.connect(lambda _: self._close_charts_window(dialog, original))
        install_image_help(dialog, 'feature_statistics', get_language())
        dialog.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
        show_centered_window(dialog)
        return dialog

    def _close_charts_window(self, dialog, original):
        self._chart_window = None
        if original is not None and self._plot is original:
            original.copy_view_from(dialog)
