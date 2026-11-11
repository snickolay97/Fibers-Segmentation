"""Interactive plots for the selected measurement table."""
from collections import Counter, defaultdict
from pathlib import Path
import textwrap

import numpy as np

from .i18n import get_language, register_translations, tr
from .help import attach_help, image_help_button
from .input_safety import install_parameter_wheel_guard
from .object_labels import CANONICAL_MANUAL_CLASSES, CLASS_BY_KEY, RF_PREDICTORS, object_key
from .parameter_inputs import ParameterSpinBox
from .qt import QtCore, QtGui, QtWidgets


_TEXT = {
    'Chart settings': ('Настройки графика', 'הגדרות תרשים'),
    'Chart colors': ('Цвета графика', 'צבעי התרשים'),
    'Data color…': ('Цвет данных…', 'צבע הנתונים…'),
    'Chart background…': ('Фон графика…', 'רקע התרשים…'),
    'Matrix palette': ('Палитра матрицы', 'לוח צבעים למטריצה'),
    'Cool–warm': ('Холодная — тёплая', 'קר — חם'),
    'Red–blue': ('Красная — синяя', 'אדום — כחול'),
    'Purple–orange': ('Фиолетовая — оранжевая', 'סגול — כתום'),
    'Brown–teal': ('Коричневая — бирюзовая', 'חום — טורקיז'),
    'Reset chart colors': ('Сбросить цвета графика', 'איפוס צבעי התרשים'),
    'Drag to pan · wheel to zoom · drag the divider to resize the chart': (
        'Перетаскивание — панорама · колесо — масштаб · разделитель меняет размер графика',
        'גרירה להזזה · גלגלת לזום · גרירת המפריד לשינוי גודל התרשים'),
    'Classes by image': ('Классы по снимкам', 'מחלקות לפי תמונה'),
    'Histogram scale': ('Шкала гистограммы', 'סולם היסטוגרמה'),
    'Automatic (log for area)': ('Автоматически (логарифм для площади)', 'אוטומטי (לוגריתמי עבור שטח)'),
    'Linear intervals': ('Линейные интервалы', 'מרווחים ליניאריים'),
    'Logarithmic intervals': ('Логарифмические интервалы', 'מרווחים לוגריתמיים'),
    'Non-positive values omitted: {count}': ('Пропущено значений ≤ 0: {count}', 'ערכים שאינם חיוביים הושמטו: {count}'),
    'Measured image': ('Снимок с измерениями', 'תמונה עם מדידות'),
    'Current image': ('Текущий снимок', 'התמונה הנוכחית'),
    'Whole image': ('Весь снимок', 'כל התמונה'),
    'Manual classes for the selected image and tile': (
        'Ручные классы для выбранного снимка и тайла', 'מחלקות ידניות של התמונה והאריח שנבחרו'),
    'Manually classified: {reviewed} of {total} · Unclassified: {unassigned}': (
        'Размечено вручную: {reviewed} из {total} · Без класса: {unassigned}',
        'סווגו ידנית: {reviewed} מתוך {total} · ללא סיווג: {unassigned}'),
    'Current measurements or manual labels could not be read for this image.': (
        'Не удалось прочитать актуальные измерения или ручные метки этого снимка.',
        'לא ניתן לקרוא מדידות עדכניות או תוויות ידניות עבור תמונה זו.'),
}
register_translations({key: pair[0] for key, pair in _TEXT.items()},
                      hebrew={key: pair[1] for key, pair in _TEXT.items()})

_HISTOGRAM, _SCATTER, _BOX, _COVARIANCE, _CORRELATION, _CLASS_COUNTS = range(6)
_AREA_UNITS = {'Area': 'px²', 'Area_um2': 'µm²'}
_CHART_COLORS = ('#0072b2', '#ffffff', 'coolwarm')


def numeric_features(fields, rows):
    """Return the scientific feature columns, with missing values represented by NaN."""
    columns = [name for name in (*RF_PREDICTORS, 'Area_um2') if name in fields]
    values = np.full((len(rows), len(columns)), np.nan)
    for j, name in enumerate(columns):
        for i, row in enumerate(rows):
            try:
                values[i, j] = float(row[name])
            except (KeyError, TypeError, ValueError):
                continue
    return columns, values


def class_counts_by_tile(rows, labels):
    """Count saved manual targets per tile and for the whole measurement."""
    counts = defaultdict(Counter, {None: Counter()})
    for row in rows:
        tile = row.get('Tile_Name')
        try:
            label = labels.get(object_key(tile, row.get('Object_ID')), {}).get('Manual_Class')
        except ValueError:
            label = None
        label = label if label in CLASS_BY_KEY else None
        counts[None][label] += 1
        if tile:
            counts[tile][label] += 1
    return dict(counts)


def log_histogram_edges(values, bins):
    """Use equal multiplicative steps and keep both extremes in the histogram."""
    low, high = float(values.min()), float(values.max())
    if low == high:
        low, high = low / 2 or low, min(high * 2, np.finfo(float).max)
    # Closely spaced values can yield repeated edges after float rounding.
    return np.unique(np.geomspace(low, high, bins + 1))


def feature_matrix(data, correlation):
    """Calculate sample covariance or Pearson r for at least two complete rows."""
    # Each row is an object and each column a feature. ddof=1 divides by n−1.
    covariance = np.atleast_2d(np.cov(data, rowvar=False, ddof=1))
    # A repeated decimal can acquire a tiny numerical variance when its
    # computed mean is rounded. Mark exactly constant columns explicitly.
    constant = np.all(data == data[0], axis=0)
    covariance[constant, :] = 0
    covariance[:, constant] = 0
    if not correlation:
        return covariance
    # Pearson r divides covariance by both sample standard deviations. If
    # either feature is constant, the denominator is zero and r is undefined.
    deviation = np.sqrt(covariance.diagonal())
    denominator = np.outer(deviation, deviation)
    result = np.divide(covariance, denominator, out=np.full_like(covariance, np.nan),
                       where=denominator > 0)
    return np.clip(result, -1, 1)


def draw_feature_matrix(figure, axes, columns, matrix, correlation, cmap='coolwarm'):
    """Draw a table with a signed color scale and blanks for undefined cells."""
    finite = matrix[np.isfinite(matrix)]
    # Center both scales at zero. The Pearson scale is fixed across datasets,
    # while covariance has units and the range depends on the observed values.
    limit = 1 if correlation or not finite.size else float(np.max(np.abs(finite))) or 1
    heatmap = axes.imshow(np.ma.masked_invalid(matrix), cmap=cmap, vmin=-limit, vmax=limit)
    axes.set_xticks(range(len(columns)), columns, rotation=35, ha='right')
    axes.set_yticks(range(len(columns)), columns)
    for (i, j), value in np.ndenumerate(matrix):
        axes.text(j, i, f'{value:.3g}' if np.isfinite(value) else '—',
                  ha='center', va='center', fontsize=8,
                  bbox=dict(facecolor='white', alpha=.8, edgecolor='none', pad=1))
    figure.colorbar(heatmap, ax=axes)


class StatisticsDialog(QtWidgets.QDialog):
    def __init__(self, fields, rows, parent, *, dataset=None, labels=None, project_datasets=()):
        super().__init__(parent)
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
        from matplotlib.figure import Figure

        self.columns, self.values = numeric_features(fields, rows)
        dataset = dataset or {}
        self._dataset_id = dataset.get('id')
        self._class_datasets = {d['id']: dict(d) for d in project_datasets
                                if d['id'] != self._dataset_id and d.get('last_csv') and d.get('results_current')}
        self._class_counts = {self._dataset_id: class_counts_by_tile(rows, (labels or {}).get('labels', {}))}
        self._tile_source = object()
        self.data_color, self.background, self.matrix_palette = _CHART_COLORS
        self.setWindowTitle(tr('Feature statistics'))
        self.resize(950, 700)
        self.figure = Figure(layout='constrained')
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setMinimumHeight(155)
        layout = QtWidgets.QVBoxLayout(self)
        header = QtWidgets.QHBoxLayout()
        self.show_settings = QtWidgets.QToolButton()
        self.show_settings.setText(tr('Chart settings'))
        self.show_settings.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.show_settings.setArrowType(QtCore.Qt.ArrowType.DownArrow)
        self.show_settings.setCheckable(True)
        self.show_settings.setChecked(True)
        header.addWidget(attach_help(self.show_settings, 'feature_statistics'))
        colors = QtWidgets.QToolButton()
        colors.setText(tr('Chart colors'))
        colors.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QtWidgets.QMenu(colors)
        menu.addAction(tr('Data color…'), lambda: self._choose_color('data_color', 'Data color…'))
        menu.addAction(tr('Chart background…'), lambda: self._choose_color('background', 'Chart background…'))
        palettes = menu.addMenu(tr('Matrix palette'))
        for name, palette in (('Cool–warm', 'coolwarm'), ('Red–blue', 'RdBu_r'),
                              ('Purple–orange', 'PuOr'), ('Brown–teal', 'BrBG')):
            palettes.addAction(tr(name), lambda checked=False, value=palette: self._set_palette(value))
        menu.addAction(tr('Reset chart colors'), self._reset_colors)
        colors.setMenu(menu)
        header.addWidget(attach_help(colors, 'feature_statistics'))
        header.addStretch()
        header.addWidget(image_help_button(self, 'feature_statistics', get_language()))
        layout.addLayout(header)
        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        self.splitter.setChildrenCollapsible(False)
        layout.addWidget(self.splitter, 1)
        self.settings = QtWidgets.QScrollArea()
        self.settings.setWidgetResizable(True)
        self.settings.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.settings.setMinimumHeight(54)
        options = QtWidgets.QWidget()
        options_layout = QtWidgets.QVBoxLayout(options)
        options_layout.setContentsMargins(2, 0, 2, 0)
        self.scope = QtWidgets.QLabel()
        self.scope.setWordWrap(True)
        options_layout.addWidget(self.scope)
        self.controls = QtWidgets.QGridLayout()
        self._fields = {}
        self.kind = QtWidgets.QComboBox()
        self.kind.addItems([tr(label) for label in ('Histogram', 'Scatter plot', 'Box plot',
                                                    'Sample covariance', 'Pearson correlation', 'Classes by image')])
        self.x, self.y = QtWidgets.QComboBox(), QtWidgets.QComboBox()
        for selector in (self.x, self.y):
            selector.addItems(self.columns)
        self.y.setCurrentIndex(min(1, len(self.columns) - 1))
        self.bins = ParameterSpinBox()
        self.bins.setRange(1, 200)
        self.bins.setValue(30)
        self.histogram_scale = QtWidgets.QComboBox()
        for title, key in (('Automatic (log for area)', 'auto'), ('Linear intervals', 'linear'),
                           ('Logarithmic intervals', 'log')):
            self.histogram_scale.addItem(tr(title), key)
        self.class_source, self.class_tile = QtWidgets.QComboBox(), QtWidgets.QComboBox()
        for selector in (self.class_source, self.class_tile):
            selector.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            selector.setMinimumContentsLength(14)
        self.class_source.addItem(self._image_title(dataset), self._dataset_id)
        for ident, other in sorted(self._class_datasets.items(), key=lambda item: self._image_title(item[1])):
            self.class_source.addItem(self._image_title(other), ident)
        install_parameter_wheel_guard(self)
        for title, control in ((tr('Plot'), self.kind), ('X', self.x), ('Y', self.y),
                               (tr('Histogram bins'), self.bins), (tr('Histogram scale'), self.histogram_scale),
                               (tr('Measured image'), self.class_source), (tr('Tile'), self.class_tile)):
            control.setParent(options)
            label = QtWidgets.QLabel(title, options)
            label.setBuddy(control)
            self._fields[control] = label
            attach_help(control, 'feature_statistics')
        self.controls.setColumnStretch(1, 1)
        self.controls.setColumnStretch(3, 1)
        options_layout.addLayout(self.controls)
        self.settings.setWidget(options)
        self.splitter.addWidget(self.settings)
        plot_panel = QtWidgets.QWidget()
        plot_layout = QtWidgets.QVBoxLayout(plot_panel)
        plot_layout.setContentsMargins(0, 0, 0, 0)
        self.summary = QtWidgets.QLabel()
        self.summary.setWordWrap(True)
        plot_layout.addWidget(self.summary)
        self.legend = QtWidgets.QLabel()
        self.legend.setWordWrap(True)
        self.legend.hide()
        plot_layout.addWidget(self.legend)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        plot_layout.addWidget(self.toolbar)
        plot_layout.addWidget(self.canvas, 1)
        attach_help(self.canvas, 'feature_statistics')
        self.canvas.setToolTip(tr('Drag to pan · wheel to zoom · drag the divider to resize the chart'))
        self.splitter.addWidget(plot_panel)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.show_settings.toggled.connect(self.settings.setVisible)
        self.show_settings.toggled.connect(lambda shown: self.show_settings.setArrowType(
            QtCore.Qt.ArrowType.DownArrow if shown else QtCore.Qt.ArrowType.RightArrow))
        self.canvas.mpl_connect('scroll_event', self._wheel_zoom)
        for selector in (self.kind, self.x, self.y, self.histogram_scale, self.class_source, self.class_tile):
            selector.currentIndexChanged.connect(self.redraw)
        self.bins.valueChanged.connect(self.redraw)
        self.redraw()
        self.splitter.setSizes([options.sizeHint().height() + 8, 500])
        self.toolbar.pan()

    def view_state(self):
        return dict(kind=self.kind.currentIndex(), x=self.x.currentText(), y=self.y.currentText(),
                    bins=self.bins.value(), scale=self.histogram_scale.currentData(), dataset=self._dataset_id,
                    source=self.class_source.currentData(), tile=self.class_tile.currentData(),
                    colors=(self.data_color, self.background, self.matrix_palette),
                    settings=self.show_settings.isChecked(), sizes=self.splitter.sizes())

    def apply_view_state(self, state):
        self.data_color, self.background, self.matrix_palette = state.get('colors', _CHART_COLORS)
        self.show_settings.setChecked(state.get('settings', True))
        with (QtCore.QSignalBlocker(self.kind), QtCore.QSignalBlocker(self.x),
              QtCore.QSignalBlocker(self.y), QtCore.QSignalBlocker(self.bins),
              QtCore.QSignalBlocker(self.histogram_scale), QtCore.QSignalBlocker(self.class_source),
              QtCore.QSignalBlocker(self.class_tile)):
            self.kind.setCurrentIndex(state['kind'])
            self.x.setCurrentText(state['x'])
            self.y.setCurrentText(state['y'])
            self.bins.setValue(state['bins'])
            self.histogram_scale.setCurrentIndex(self.histogram_scale.findData(state['scale']))
            if state['kind'] == _CLASS_COUNTS and state['dataset'] == self._dataset_id:
                source = self.class_source.findData(state['source'])
                self.class_source.setCurrentIndex(max(0, source))
                self._class_scope()
                if source >= 0:
                    self.class_tile.setCurrentIndex(max(0, self.class_tile.findData(state['tile'])))
        self.redraw()
        if self.show_settings.isChecked() and state.get('sizes') and all(state['sizes']):
            # Preserve the settings pane height rather than the old window ratio.
            height = state['sizes'][0]
            self.splitter.setSizes([height, max(170, self.height() - height - 80)])

    def copy_view_from(self, other):
        # Keep the snapshot behind the displayed bars when a chart is popped out.
        self._class_counts.update(other._class_counts)
        self.apply_view_state(other.view_state())
        if other.figure.axes and self.figure.axes:
            old, new = other.figure.axes[0], self.figure.axes[0]
            new.set(xlim=old.get_xlim(), ylim=old.get_ylim())
            self.toolbar.push_current()
            self.canvas.draw_idle()

    def _choose_color(self, key, title):
        color = QtWidgets.QColorDialog.getColor(QtGui.QColor(getattr(self, key)), self, tr(title))
        if color.isValid():
            setattr(self, key, color.name())
            self.redraw(keep_limits=True)

    def _set_palette(self, palette):
        self.matrix_palette = palette
        self.redraw(keep_limits=True)

    def _reset_colors(self):
        self.data_color, self.background, self.matrix_palette = _CHART_COLORS
        self.redraw(keep_limits=True)

    def _wheel_zoom(self, event):
        if not self.figure.axes or event.inaxes is not self.figure.axes[0] or not event.step:
            return
        axes = event.inaxes
        factor = 1.2 ** -event.step
        for axis, anchor, setter in ((axes.xaxis, event.xdata, axes.set_xlim),
                                     (axes.yaxis, event.ydata, axes.set_ylim)):
            if anchor is None:
                continue
            transform = axis.get_transform()
            low, high, center = transform.transform([*axis.get_view_interval(), anchor])
            zoomed = transform.inverted().transform([center + (low - center) * factor,
                                                     center + (high - center) * factor])
            if np.isfinite(zoomed).all() and zoomed[0] != zoomed[1]:
                setter(zoomed)
        self.toolbar.push_current()
        self.canvas.draw_idle()

    def redraw(self, *_, keep_limits=False):
        kind = self.kind.currentIndex()
        by_class = kind == _CLASS_COUNTS
        self.scope.setText(tr('Manual classes for the selected image and tile' if by_class
                              else 'All measured objects in the selected dataset'))
        shown = [self.kind]
        if by_class:
            shown.extend((self.class_source, self.class_tile))
        elif kind == _HISTOGRAM:
            shown.extend((self.x, self.bins, self.histogram_scale))
        elif kind == _SCATTER:
            shown.extend((self.x, self.y))
        elif kind == _BOX:
            shown.append(self.x)
        for control, label in self._fields.items():
            self.controls.removeWidget(label)
            self.controls.removeWidget(control)
            label.setVisible(control in shown)
            control.setVisible(control in shown)
        for index, control in enumerate(shown):
            row, column = index // 2, 2 * (index % 2)
            self.controls.addWidget(self._fields[control], row, column)
            self.controls.addWidget(control, row, column+1)
        self.legend.hide()
        limits = None
        if keep_limits and self.figure.axes:
            previous = self.figure.axes[0]
            limits = dict(xlim=previous.get_xlim(), ylim=previous.get_ylim())
        self.figure.clear()
        self.figure.set_facecolor(self.background)
        axes = self.figure.add_subplot()
        if by_class:
            self._draw_class_counts(axes)
        else:
            self._draw_features(axes, kind)
        foreground = '#ffffff' if QtGui.QColor(self.background).lightness() < 128 else '#151b20'
        for panel in self.figure.axes:
            panel.set_facecolor(self.background)
            panel.tick_params(colors=foreground)
            panel.xaxis.label.set_color(foreground)
            panel.yaxis.label.set_color(foreground)
            for spine in panel.spines.values():
                spine.set_color(foreground)
        self.toolbar.update()
        self.toolbar.push_current()
        if limits:
            axes.set(**limits)
            self.toolbar.push_current()
        self.canvas.draw_idle()

    def _draw_features(self, axes, kind):
        if not self.columns:
            axes.set_axis_off()
            self.summary.setText(tr('Insufficient finite data'))
            return
        matrix = kind in (_COVARIANCE, _CORRELATION)
        columns = self.columns if matrix else [self.x.currentText()]
        if kind == _SCATTER:
            columns.append(self.y.currentText())
        data = self.values[:, [self.columns.index(name) for name in columns]]
        # Use the same complete observations across the columns of a plot or
        # matrix. The summary reports the actual sample size after filtering.
        data = data[np.isfinite(data).all(axis=1)]
        scale = self.histogram_scale.currentData()
        logarithmic = kind == _HISTOGRAM and (scale == 'log' or (scale == 'auto' and columns[0] in _AREA_UNITS))
        omitted = 0
        if logarithmic:
            positive = data[:, 0] > 0
            omitted = len(data) - int(positive.sum())
            data = data[positive]
        summary = tr('Objects used: {used} / {total}', used=len(data), total=len(self.values))
        if omitted:
            summary += ' · ' + tr('Non-positive values omitted: {count}', count=omitted)
        if len(data) < (2 if matrix else 1):
            axes.set_axis_off()
            summary += ' · ' + tr('Insufficient finite data')
        elif kind == _HISTOGRAM:
            # Counts preserve the number of objects. No density normalization
            # is applied, so summing the bars recovers the displayed sample size.
            edges = log_histogram_edges(data[:, 0], self.bins.value()) if logarithmic else self.bins.value()
            if logarithmic:
                axes.set_xscale('log')
            label = columns[0]
            if label in _AREA_UNITS:
                label += f' [{_AREA_UNITS[label]}]'
            axes.hist(data[:, 0], bins=edges, color=self.data_color)
            axes.set(xlabel=label, ylabel='n')
            summary += ' · ' + tr('Logarithmic intervals' if logarithmic else 'Linear intervals')
        elif kind == _SCATTER:
            # Both coordinates come from the same object. Transparency helps
            # show overlaps, but coincident points may still look like one.
            axes.scatter(*data.T, s=10, alpha=.45, color=self.data_color)
            axes.set(xlabel=columns[0], ylabel=columns[1])
        elif kind == _BOX:
            # Matplotlib's box spans Q1 to Q3, with a median line. Whiskers
            # end at observed values within 1.5 IQR, with farther points shown.
            axes.boxplot(data[:, 0], patch_artist=True, boxprops={'facecolor': self.data_color, 'alpha': .55},
                         medianprops={'color': self.data_color}, whiskerprops={'color': self.data_color},
                         capprops={'color': self.data_color}, flierprops={'markeredgecolor': self.data_color})
            axes.set(xticks=[], ylabel=columns[0])
        else:
            correlation = kind == _CORRELATION
            matrix = feature_matrix(data, correlation)
            draw_feature_matrix(self.figure, axes, columns, matrix, correlation, self.matrix_palette)
        self.summary.setText(summary)

    @staticmethod
    def _image_title(dataset):
        name = Path(dataset['source_path']).name if dataset.get('source_path') else dataset.get('name')
        version = Path(dataset['results_dir']).name if dataset.get('results_dir') else ''
        return ' · '.join(filter(None, (name or tr('Current image'), version)))

    def _class_scope(self):
        ident = self.class_source.currentData()
        if ident not in self._class_counts:
            from .service import get_object_labels, read_results

            dataset = self._class_datasets[ident]
            try:
                fields, rows = read_results(dataset)
                self._class_counts[ident] = (
                    class_counts_by_tile(rows, get_object_labels(dataset, current=True)['labels']) if fields else None)
            except (OSError, ValueError, KeyError):
                self._class_counts[ident] = None
        counts = self._class_counts[ident]
        if ident != self._tile_source:
            with QtCore.QSignalBlocker(self.class_tile):
                self.class_tile.clear()
                self.class_tile.addItem(tr('Whole image'), None)
                if counts:
                    for tile in sorted(key for key in counts if key is not None):
                        self.class_tile.addItem(tile, tile)
            self._tile_source = ident
        return counts

    def _draw_class_counts(self, axes):
        scopes = self._class_scope()
        if scopes is None:
            axes.set_axis_off()
            self.summary.setText(tr('Current measurements or manual labels could not be read for this image.'))
            return
        counts = scopes[self.class_tile.currentData()]
        total = sum(counts.values())
        self.summary.setText(tr('Manually classified: {reviewed} of {total} · Unclassified: {unassigned}',
                                reviewed=total - counts[None], total=total, unassigned=counts[None]))
        classes = CANONICAL_MANUAL_CLASSES
        names = [tr(entry['label_en']) for entry in classes]
        if get_language() == 'he':
            # Qt shapes bidirectional labels. Matplotlib uses stable IDs.
            self.legend.setText(' · '.join(f"{entry['id']} — {name}" for entry, name in zip(classes, names)))
            self.legend.show()
            names = [str(entry['id']) for entry in classes]
        else:
            names = [textwrap.fill(name, 24) for name in names]
        heights = [counts[entry['key']] for entry in classes]
        bars = axes.barh(names, heights, color=self.data_color)
        axes.invert_yaxis()
        foreground = '#ffffff' if QtGui.QColor(self.background).lightness() < 128 else '#151b20'
        axes.bar_label(bars, padding=4, color=foreground)
        axes.set(xlabel='n', xlim=(0, max(1, max(heights) * 1.2)))
        axes.xaxis.get_major_locator().set_params(integer=True)
