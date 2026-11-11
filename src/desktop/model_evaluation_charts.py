"""Plots from the frozen evaluation snapshot and the saved holdout results."""

from collections import Counter

import numpy as np

from . import model_chart_text, model_evaluation_text
from .i18n import get_language, tr
from .input_safety import install_parameter_wheel_guard
from .model_evaluation import CLASS_IDS
from .qt import QtCore, QtGui, QtWidgets
from .result_statistics import draw_feature_matrix, feature_matrix


MODEL_COLORS = {'dummy': '#727d88', 'tree': '#0072b2', 'forest': '#009e73'}


class _ChartsDialog(QtWidgets.QDialog):
    def __init__(self, parent, title):
        super().__init__(parent)
        self.setWindowTitle(tr(title))
        self.resize(920, 640)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
        layout = QtWidgets.QVBoxLayout(self)
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setUsesScrollButtons(True)
        self._help_center = None
        help_button = QtWidgets.QPushButton('?')
        help_button.setFixedWidth(30)
        help_button.setToolTip(tr('Help for this chart'))
        help_button.setAccessibleName(tr('Help for this chart'))
        help_button.clicked.connect(self._show_help)
        self.tabs.setCornerWidget(help_button)
        layout.addWidget(self.tabs)
        shortcut = QtGui.QShortcut(QtGui.QKeySequence('F1'), self)
        shortcut.activated.connect(self._show_help)

    def _show_help(self):
        from .help_center import HelpCenter
        if self._help_center is None:
            self._help_center = HelpCenter(parent=self)
        page = self.tabs.currentWidget()
        topic = page.property('helpKey') if page is not None else None
        self._help_center.open_topic(topic or 'training_charts')
        self._help_center.raise_()
        self._help_center.activateWindow()

    def _chart(self, title, caption, controls=None, *, help_topic='training_charts'):
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
        from matplotlib.figure import Figure

        page = QtWidgets.QWidget()
        page.setProperty('helpKey', help_topic)
        layout = QtWidgets.QVBoxLayout(page)
        label = QtWidgets.QLabel(caption)
        label.setWordWrap(True)
        layout.addWidget(label)
        if controls is not None:
            layout.addLayout(controls)
        canvas = FigureCanvasQTAgg(Figure(layout='constrained'))
        layout.addWidget(NavigationToolbar2QT(canvas, page))
        layout.addWidget(canvas, 1)
        self.tabs.addTab(page, tr(title))
        return canvas.figure

    def _message(self, title, message):
        label = QtWidgets.QLabel(tr(message))
        label.setWordWrap(True)
        label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.tabs.addTab(label, tr(title))


def _class_axis(axes, classes):
    # Use stable numeric class IDs on the axes. The accompanying Qt caption
    # displays localized names with correct bidirectional text shaping.
    axes.margins(y=.15)
    axes.set(xticks=classes, xlabel='ID', ylabel='n')
    axes.set_ylim(bottom=0)
    axes.yaxis.get_major_locator().set_params(integer=True)


class DataChartsDialog(_ChartsDialog):
    def __init__(self, parent, payload, group_names, class_name):
        super().__init__(parent, 'Data charts…')
        snapshot = payload['snapshot']
        rows, features = snapshot['rows'], snapshot['features']
        targets = [row['target'] for row in rows]
        classes = payload.get('training_options', {}).get('class_ids') or CLASS_IDS
        class_key = ' · '.join(f'{label} — {class_name(label)}' for label in classes)

        values = np.asarray([row['values'] for row in rows], dtype=float).reshape(len(rows), len(features))
        # Use only the predictors and rows frozen by this preview or report.
        # The same complete rows contribute to every coefficient in the table.
        values = values[np.isfinite(values).all(axis=1)]
        if len(values) >= 2:
            caption = tr('Reviewed objects: {count}. Pearson r measures linear association. A dash marks an undefined coefficient.',
                         count=len(values))
            figure = self._chart('Pearson correlation', caption)
            matrix = feature_matrix(values, correlation=True)
            draw_feature_matrix(figure, figure.add_subplot(), features, matrix, correlation=True)
        else:
            self._message('Pearson correlation', 'Insufficient finite data')

        caption = tr('Counts include all reviewed objects in the preview. A zero means the class is absent.')
        figure = self._chart('Class counts', caption + '\n' + class_key)
        axes = figure.add_subplot()
        counts = Counter(targets)
        bars = axes.bar(classes, [counts[label] for label in classes], color='#0072b2')
        axes.bar_label(bars, padding=3)
        _class_axis(axes, classes)

        plan = payload['plan']
        if plan is None:
            self._message('Train and test counts', 'No valid split is available. See Split plan for the reason.')
        else:
            caption = tr('Blue shows training counts and orange shows test counts.')
            if plan.get('split_mode') == 'object':
                caption += '\n' + tr('Same-source object test. Scores apply to these TIFFs.')
            if plan['demo']:
                caption += '\n' + tr('Demonstration only. No independent test groups.')
            figure = self._chart('Train and test counts', caption + '\n' + class_key)
            axes = figure.add_subplot()
            # Count the actual snapshot indices assigned to each split. Fixed
            # class positions make missing classes and imbalances visible.
            positions = np.asarray(classes)
            for split, offset, color in [('train', -.19, '#0072b2'), ('test', .19, '#e69f00')]:
                counts = Counter(targets[index] for index in plan[split])
                title = split.capitalize()
                # Matplotlib draws labels without bidirectional shaping. Keep
                # the exported Hebrew legend readable using the stable keys;
                # the Qt caption above the graph carries the localized labels.
                if get_language() != 'he':
                    title = tr(title)
                bars = axes.bar(positions + offset, [counts[label] for label in classes],
                                width=.38, color=color, label=title)
                axes.bar_label(bars, padding=3)
            _class_axis(axes, classes)
            axes.legend(loc='lower center', bbox_to_anchor=(.5, 1.01), ncols=2, frameon=False)

        self._feature_histograms(rows, features, group_names, class_key)
        self._impurity()
        install_parameter_wheel_guard(self)

    def _feature_histograms(self, rows, features, group_names, class_key):
        feature = QtWidgets.QComboBox()
        feature.addItems(features)
        source = QtWidgets.QComboBox()
        source.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        source.setMinimumContentsLength(12)
        source.addItem(tr('All groups'))
        for group, name in sorted(group_names.items()):
            source.addItem(name, group)
        controls = QtWidgets.QHBoxLayout()
        controls.addWidget(feature)
        controls.addWidget(source, 1)
        caption = tr('Feature histograms use the same bin edges for all classes in the selected group.')
        figure = self._chart('Features by class', caption + '\n' + class_key, controls)

        def draw():
            figure.clear()
            axes = figure.add_subplot()
            groups = {}
            selected = source.currentData()
            for row in rows:
                value = row['values'][feature.currentIndex()]
                if np.isfinite(value) and (selected is None or row['group'] == selected):
                    groups.setdefault(row['target'], []).append(value)
            if groups:
                # Shared edges make bin counts comparable between classes.
                # Keep colors keyed to class ID across group selections.
                pooled = [value for values in groups.values() for value in values]
                bins = np.histogram_bin_edges(pooled, bins=25)
                for label, values in sorted(groups.items()):
                    axes.hist(values, bins=bins, histtype='step', color=f'C{label}', label=str(label))
                axes.legend(title='ID')
            axes.set(xlabel=feature.currentText(), ylabel='n')
            figure.canvas.draw_idle()

        feature.currentIndexChanged.connect(draw)
        source.currentIndexChanged.connect(draw)
        draw()

    def _impurity(self):
        caption = tr('Imagine a group of 10 objects. At p = 0.2 there are 2 particles and 8 fibers. The curves show three ways to describe the class mix.')
        figure = self._chart('Impurity criteria', caption, help_topic='tree_impurity')
        axes = figure.add_subplot()
        p = np.linspace(0, 1, 201)
        gini = 2 * p * (1 - p)
        # H = −sum(p_k log2(p_k)), using the limit 0 log2(0) = 0.
        # Avoid evaluating logarithms at the two pure-node endpoints.
        entropy = np.zeros_like(p)
        q = p[1:-1]
        entropy[1:-1] = -q * np.log2(q) - (1 - q) * np.log2(1 - q)
        # The majority-class error is a reference curve from the tutorial.
        # It is the fraction misclassified when a leaf predicts one class.
        error = 1 - np.maximum(p, 1 - p)
        axes.plot(p, gini, label=r'Gini $= 1 - \sum_k p_k^2$')
        axes.plot(p, entropy, label=r'Entropy $= -\sum_k p_k \log_2 p_k$ (bit)')
        axes.plot(p, error, '--', color='#49596b', label=r'Error $= 1 - \max_k p_k$')
        axes.set(xlabel='p', xlim=(0, 1), ylim=(0, 1.05))
        axes.legend(loc='upper right')


class PerformanceChartsDialog(_ChartsDialog):
    def __init__(self, parent, report, class_name):
        super().__init__(parent, 'Performance charts…')
        if report.get('split_mode') == 'object':
            scope = QtWidgets.QLabel(tr('Same-source object test. Scores apply to these TIFFs.'))
            scope.setWordWrap(True)
            self.layout().insertWidget(0, scope)
        scored = {key: result for key, result in report['models'].items() if 'macro_f1' in result}
        if not scored:
            self._message('Macro-F1', 'No test scores are available for this evaluation.')
            return

        model_key = ' · '.join(f'{key} — {tr(key)}' for key in scored)
        caption = tr('Higher macro-F1 is better. The displayed test score averages F1 across the classes present in the test set.')
        figure = self._chart('Macro-F1', caption + '\n' + model_key, help_topic='confusion_matrix')
        axes = figure.add_subplot()
        # Use saved holdout scores, never the CV scores used to choose a model.
        bars = axes.bar(list(scored), [result['macro_f1'] for result in scored.values()],
                        color=[MODEL_COLORS[key] for key in scored])
        axes.bar_label(bars, fmt='%.3f', padding=3)
        axes.set(ylabel='Macro-F1', ylim=(0, 1.10), yticks=np.linspace(0, 1, 6))

        self._recall(scored, report['classes'], class_name, model_key)
        self._importance(report['models'].get('forest', {}).get('permutation_importance'))

    def _recall(self, scored, classes, class_name, model_key):
        caption = tr('Recall is the fraction of correctly predicted objects within each true class. n is the test support.')
        class_key = ' · '.join(f'{label} — {class_name(label)}' for label in classes)
        figure = self._chart('Per-class recall', '\n'.join((caption, model_key, class_key)),
                             help_topic='confusion_matrix')
        axes = figure.add_subplot()
        positions = np.arange(len(classes))
        width = .8 / len(scored)
        for index, (key, result) in enumerate(scored.items()):
            matrix = np.asarray(result['confusion'])
            support = matrix.sum(axis=1)
            present = support > 0
            # A row is an actual class. Recall is diagonal / row total.
            # Omit undefined bars (n=0), while keeping their class tick.
            shift = (index - (len(scored) - 1) / 2) * width
            bars = axes.bar(positions[present] + shift, matrix.diagonal()[present] / support[present],
                            width=width, color=MODEL_COLORS[key], label=key)
            axes.bar_label(bars, fmt='%.2f', padding=2, fontsize=8)
        # All models share the same holdout and therefore the same row totals.
        axes.set_xticks(positions, [f'{label}\n(n={n})' for label, n in zip(classes, support)])
        axes.set(ylim=(0, 1.10), yticks=np.linspace(0, 1, 6))
        axes.legend()

    def _importance(self, importance):
        if not importance:
            self._message('Permutation importance', 'Permutation importance was not recorded for this evaluation.')
            return
        caption = tr('Random Forest on the test set. Bars show mean macro-F1 decrease after shuffling a feature, with ±1 standard deviation over shuffles.')
        figure = self._chart('Permutation importance', caption, help_topic='permutation_importance')
        axes = figure.add_subplot()
        ordered = sorted(importance, key=lambda item: item['mean'])
        # Preserve negative scores: a feature permutation can improve the
        # measured test score, especially on a small holdout. Error bars
        # describe variability across shuffles on this particular holdout.
        axes.barh([item['feature'] for item in ordered], [item['mean'] for item in ordered],
                  xerr=[item['std'] for item in ordered], capsize=4, color=MODEL_COLORS['forest'])
        axes.axvline(0, color='#333333', linewidth=1)
        axes.set_xlabel('Δ Macro-F1')
