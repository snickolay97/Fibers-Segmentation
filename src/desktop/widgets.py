"""Reusable, responsive image and CSV widgets for the local desktop UI."""

import csv
import os
from pathlib import Path
import tempfile

from .qt import QtCore, QtGui, QtWidgets, Signal, show_centered_window
from .i18n import tr, get_language, register_translations
from .help import attach_help, help_label, image_help_button, install_image_help
from .image_comparison import compare_with_file
from .image_controls import ImageActionStrip, describe, tool_icon
from .image_export import export_from_viewer
from .image_levels import ImageLevelsDialog, display_image, grayscale_image
from .image_polygon import ImagePolygon
from .image_ruler import ImageRuler
from .object_labels import CANONICAL_MANUAL_CLASSES


_IMAGE_POOL = QtCore.QThreadPool()
_IMAGE_POOL.setMaxThreadCount(1)
MAX_NATIVE_VIEW_PIXELS = 32_000_000
register_translations({'Enlarge image…': 'Открыть изображение в окне…', 'Close image': 'Закрыть'},
                      hebrew={'Enlarge image…': 'פתיחת תמונה בחלון…', 'Close image': 'סגירה'})


def image_pool():
    """Serialize native preview decoding to keep memory use bounded."""
    return _IMAGE_POOL


class _ImageSignals(QtCore.QObject):
    ready = Signal(int, object, object)
    failed = Signal(int, str)


class _ImageTask(QtCore.QRunnable):
    """Decode pixels off the GUI thread and return a detached QImage."""

    def __init__(self, token, filename, maximum=2400, *, full_when_safe=False):
        super().__init__()
        self.token, self.filename, self.maximum = token, filename, maximum
        self.full_when_safe = full_when_safe
        self.signals = _ImageSignals()
        self.cancelled = False

    def run(self):
        try:
            if self.cancelled:
                self.signals.failed.emit(self.token, "Cancelled")
                return
            from PIL import Image
            import numpy as np
            # These are user-selected scientific outputs. Native canvases can
            # legitimately exceed Pillow's generic web-image size threshold.
            Image.MAX_IMAGE_PIXELS = None
            with Image.open(self.filename) as source:
                original_size = source.size
                if self.full_when_safe and source.width * source.height <= MAX_NATIVE_VIEW_PIXELS:
                    self.maximum = None
                if source.mode == "I" or source.mode.startswith("I;16"):
                    pixels = np.asarray(source, dtype=np.uint16)
                    if self.maximum is not None and max(original_size) > self.maximum:
                        import cv2
                        scale = self.maximum / max(original_size)
                        size = tuple(max(1, round(length * scale)) for length in original_size)
                        pixels = cv2.resize(pixels, size, interpolation=cv2.INTER_AREA)
                    image = grayscale_image(pixels)
                else:
                    if self.maximum is not None:
                        source.thumbnail((self.maximum, self.maximum), Image.Resampling.LANCZOS)
                    rgb = source.convert("RGB")
                    width, height = rgb.size
                    image = QtGui.QImage(
                        rgb.tobytes(), width, height, width * 3, QtGui.QImage.Format.Format_RGB888
                    ).copy()
            if self.cancelled:
                self.signals.failed.emit(self.token, "Cancelled")
            else:
                self.signals.ready.emit(self.token, image, original_size)
        except Exception as exc:
            self.signals.failed.emit(self.token, str(exc))


class _ExpandedImageDialog(QtWidgets.QDialog):
    """A second view of an existing scene; never owns or decodes the image."""

    def __init__(self, owner, fullscreen):
        super().__init__(owner)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.auto_fit = True
        name = Path(owner.filename).name or owner.caption.text()
        self.setWindowTitle(owner._text('Image') + ' — ' + name)
        self.resize(1050, 760)
        self.view = QtWidgets.QGraphicsView(owner.scene, self)
        owner._configure_view(self.view)
        self.view.setBackgroundBrush(owner.view.backgroundBrush())
        self.caption = QtWidgets.QLabel(owner.caption.text())
        self.caption.setWordWrap(True)
        self.caption.setObjectName('muted')
        controls = owner._image_actions(self, self.view, expanded=True)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(self.view, 1)
        caption_row = QtWidgets.QHBoxLayout()
        caption_row.addWidget(self.caption, 1)
        if owner._object_highlight is not None:
            highlight = QtWidgets.QCheckBox(owner._text('Highlight object'))
            highlight.setChecked(owner.highlight_toggle.isChecked())
            highlight.toggled.connect(owner.highlight_toggle.setChecked)
            owner.highlight_toggle.toggled.connect(highlight.setChecked)
            caption_row.addWidget(attach_help(highlight, 'result_tile'))
        caption_row.addWidget(image_help_button(self, 'image_viewer', owner.language))
        layout.addLayout(caption_row)
        layout.addWidget(owner.ruler.label(self))
        layout.addWidget(owner.polygon.label(self))
        layout.addWidget(controls)
        self.f11_shortcut = QtGui.QShortcut(QtGui.QKeySequence('F11'), self)
        self.f11_shortcut.activated.connect(self.close if fullscreen else self._toggle_fullscreen)
        self.escape_shortcut = QtGui.QShortcut(QtGui.QKeySequence('Esc'), self)
        self.escape_shortcut.activated.connect(self._escape)
        install_image_help(self, 'image_viewer', owner.language)
        self.fit_timer = QtCore.QTimer(self)
        self.fit_timer.setSingleShot(True)
        self.fit_timer.timeout.connect(self._apply_fit)
        self.finished.connect(lambda _result: self.view.setScene(None))

    def fit(self):
        self.auto_fit = True
        self._apply_fit()

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _escape(self):
        owner = self.parent()
        if owner.polygon.active:
            owner.polygon.clear()
        elif owner.ruler.active:
            owner.ruler.clear()
        else:
            self.close()

    def _apply_fit(self):
        scene = self.view.scene()
        owner = self.parent()
        if self.auto_fit and scene is not None and owner._pixmap_item is not None:
            bounds = owner._pixmap_item.boundingRect()
            self.view.fitInView(bounds, QtCore.Qt.AspectRatioMode.KeepAspectRatio)
            owner._update_pan_bounds(self.view)
            self.view.centerOn(bounds.center())

    def showEvent(self, event):
        super().showEvent(event)
        self.fit_timer.start(0)
        self.view.setFocus(QtCore.Qt.FocusReason.OtherFocusReason)

    def closeEvent(self, event):
        self.fit_timer.stop()
        self.view.setScene(None)
        super().closeEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'fit_timer'):
            self.fit_timer.start(0)


class ImageViewer(QtWidgets.QWidget):
    """Pan/zoom preview; clicked coordinates refer to the original image."""

    clicked = Signal(float, float)
    loaded = Signal(str, object)
    failed = Signal(str)
    tile_saved = Signal(str, int, object)
    display_levels_changed = Signal(object)

    def __init__(self, parent=None, empty_text="Select an image to preview", *, maximum=2400, full_when_safe=False):
        super().__init__(parent)
        self._preview_maximum = maximum
        self._full_when_safe = full_when_safe
        self.resolution_action = None
        self.language = get_language()
        self._empty_message = empty_text
        self._loading, self._error = False, None
        self._token = 0
        self._tasks = {}
        self._filename = ""
        self._export_source = None
        self._tile_editor = None
        self._original_size = (0, 0)
        self._press_position = None
        self._fit_pending = False
        self._auto_fit = True
        self._fit_timer = QtCore.QTimer(self)
        self._fit_timer.setSingleShot(True)
        self._fit_timer.timeout.connect(self._apply_auto_fit)
        self._polygons = []
        self._overlay_items = []
        self._object_highlight = None
        self._object_highlight_items = []
        self._fullscreen_dialog = None
        self._host_window = None
        self._levels_dialog = None
        self._comparison_window = None
        self._base_image = None
        self._levels = None
        self._exports = {}
        self._middle_pan = None
        self._press_positions = {}
        self._pending_click = None
        self._click_timer = QtCore.QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.timeout.connect(self._deliver_click)
        self.scene = QtWidgets.QGraphicsScene(self)
        self.ruler = ImageRuler(self)
        self.polygon = ImagePolygon(self)
        self.view = QtWidgets.QGraphicsView(self.scene, self)
        self._configure_view(self.view)
        self.view.setMinimumSize(230, 160)
        self.caption = QtWidgets.QLabel(self._text(empty_text))
        self.caption.setWordWrap(True)
        self.caption.setObjectName("muted")
        caption_row = QtWidgets.QHBoxLayout()
        caption_row.addWidget(self.caption, 1)
        self.highlight_toggle = QtWidgets.QCheckBox(self._text('Highlight object'))
        attach_help(self.highlight_toggle, 'result_tile')
        self.highlight_toggle.setChecked(True)
        self.highlight_toggle.hide()
        self.highlight_toggle.toggled.connect(self._toggle_object_highlight)
        caption_row.addWidget(self.highlight_toggle)
        self._view_help = image_help_button(self, 'image_viewer', self.language)
        caption_row.addWidget(self._view_help)
        attach_help(self.view, 'image_viewer')
        self._pixmap_item = None
        self._actions = self._image_actions(self, self.view)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view, 1)
        layout.addLayout(caption_row)
        layout.addWidget(self.ruler.label(self))
        layout.addWidget(self.polygon.label(self))
        layout.addWidget(self._actions)
        self.f11_shortcut = QtGui.QShortcut(QtGui.QKeySequence('F11'), self)
        self.f11_shortcut.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.f11_shortcut.activated.connect(self.open_fullscreen)
        # Qt can deliver viewport callbacks during construction/destruction.
        # Subscribe only after every handler attribute exists.
        self.view.viewport().installEventFilter(self)
        self.view.installEventFilter(self)

    def _configure_view(self, view):
        view.setLayoutDirection(QtCore.Qt.LayoutDirection.LeftToRight)
        view.setRenderHints(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
        view.setDragMode(QtWidgets.QGraphicsView.DragMode.ScrollHandDrag)
        view.setTransformationAnchor(QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        view.setResizeAnchor(QtWidgets.QGraphicsView.ViewportAnchor.AnchorViewCenter)
        view.setMouseTracking(True)
        view.viewport().setMouseTracking(True)
        view.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        view.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        attach_help(view, 'image_viewer')

    def _image_actions(self, parent, view, *, expanded=False):
        def button(attribute, title, icon, help_key, callback):
            control = QtWidgets.QToolButton(parent)
            control.clicked.connect(callback)
            control.setProperty('imageIcon', icon)
            control.setProperty('imageActionTitle', title)
            attach_help(control, help_key)
            setattr(parent, attribute, control)
            return control

        original_title = ('Original resolution…' if self._preview_maximum is not None and self._filename
                          else 'Actual pixels · 1:1')
        zoom_out = button('zoom_out_button', 'Zoom out', 'zoom_out', 'image_zoom', lambda: self._zoom_view(view, 1 / 1.3))
        zoom_in = button('zoom_in_button', 'Zoom in', 'zoom_in', 'image_zoom', lambda: self._zoom_view(view, 1.3))
        fit = button('fit_button', 'Fit to window', 'fit', 'image_fit', parent.fit)
        fit.setProperty('showActionText', True)
        actual = button('original_button', original_title, None, 'image_original',
                        lambda: self._open_resolution(view))
        actual.setText('1:1')
        enlarge = button('fullscreen_button', 'Enlarge image…', 'enlarge', 'image_fullscreen',
                         parent._toggle_fullscreen if expanded else self.open_enlarged)
        enlarge.setObjectName('imageFullScreen')
        ruler = attach_help(self.ruler.button(parent), 'image_ruler')
        polygon = attach_help(self.polygon.button(parent), 'image_contour')
        for attribute, control, icon in (('ruler_button', ruler, 'ruler'), ('polygon_button', polygon, 'contour')):
            setattr(parent, attribute, control)
            control.setProperty('imageIcon', icon)
            control.setProperty('showActionText', True)
        levels = button('levels_button', 'Brightness and contrast', 'levels', 'image_levels',
                        lambda: self.open_levels(parent))
        save = button('image_save_button', 'Save image…', 'save', 'image_export', lambda: None)
        menu = QtWidgets.QMenu(save)
        parent.save_displayed_action = menu.addAction('', lambda: export_from_viewer(self, parent, saved_file=False))
        parent.save_file_action = menu.addAction('', lambda: export_from_viewer(self, parent, saved_file=True))
        save.setMenu(menu)
        save.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
        compare = button('compare_file_button', 'Compare with file…', 'compare', 'image_comparison',
                         lambda: self.open_file_comparison(parent))
        controls = [zoom_out, zoom_in, fit, actual, enlarge, ruler, polygon, levels, save, compare]
        if expanded:
            controls.append(button('exit_button', 'Close image', 'close', 'image_fullscreen', parent.close))
        strip = ImageActionStrip(controls, parent)
        strip.setEnabled(self._pixmap_item is not None and not self._loading)
        self._translate_actions(parent, strip)
        self._action_icons(strip)
        return strip

    def set_view_help(self, key):
        # The contextual button resolves the current key when clicked.
        attach_help(self._view_help, key)
        attach_help(self.view, key)

    def _open_resolution(self, view):
        if self.resolution_action:
            return self.resolution_action()
        if self._preview_maximum is not None and self._filename:
            return self.open_original()
        return self._actual_size(view)

    def _translate_actions(self, parent, strip):
        for button in strip.buttons:
            title = button.property('imageActionTitle')
            if title:
                describe(button, self._text(title))
                if title == 'Close image':
                    button.setText(self._text(title) + ' · Esc')
                elif title != 'Actual pixels · 1:1' and button is not parent.original_button:
                    button.setText(self._text(title))
        parent.save_displayed_action.setText(self._text('Save displayed image…'))
        parent.save_file_action.setText(self._text('Export saved file…'))
        parent.save_file_action.setEnabled(bool(self._export_source))

    @staticmethod
    def _action_icons(strip):
        for button in strip.buttons:
            icon = button.property('imageIcon')
            if icon:
                button.setIcon(tool_icon(button, icon))

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QtCore.QEvent.Type.PaletteChange, QtCore.QEvent.Type.StyleChange) and hasattr(self, '_actions'):
            self._action_icons(self._actions)

    def _update_pan_bounds(self, view):
        item = getattr(self, '_pixmap_item', None)
        if item is None:
            return
        # Limit scrolling to the image bounds so Fit needs no extra pan space.
        view.setSceneRect(item.boundingRect())

    @classmethod
    def open_image_window(cls, filename, parent=None, *, language=None, caption=None,
                          polygons=None, original=False, tile_editor=None, ruler_scale=None, start_editor=False):
        """Open an image in a separate viewer.

        Original mode displays the saved image at its native resolution.
        Original-mode requests above 32 MP are delegated to the system viewer
        and return None.
        """
        filename = Path(filename)
        if original and tile_editor is not None and tile_editor.space == 'model' and tile_editor.record.get('native_filename'):
            from dataclasses import replace
            from src.tile_edits import tile_artifact_path
            native_file = tile_artifact_path(tile_editor.dataset_dir, tile_editor.record, 'native_filename')
            if native_file.is_file():
                filename = native_file
                tile_editor = replace(tile_editor, space='native')
                caption = tr('Native source pixels for editing', language=language)
                polygons = None
                ruler_scale = (1.0, 1.0, ruler_scale[2] if ruler_scale else None)
            else:
                tile_editor = None
        if not filename.is_file():
            return None
        if original:
            from PIL import Image
            Image.MAX_IMAGE_PIXELS = None
            try:
                with Image.open(filename) as source:
                    too_large = source.width * source.height > MAX_NATIVE_VIEW_PIXELS
            except Exception:
                # Let the asynchronous decoder show the normal localized error;
                # an exception must never escape a Qt clicked callback.
                too_large = False
            if too_large:
                opened = QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(filename.resolve())))
                if not opened:
                    QtWidgets.QMessageBox.warning(parent, tr('Original resolution…', language=language),
                        tr('Could not open the original file in the system image viewer.', language=language))
                return None
        dialog = QtWidgets.QDialog(parent)
        dialog.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.setWindowTitle(tr('Original resolution' if original else 'Image', language=language)
                              + ' — ' + filename.name)
        dialog.resize(1100, 820)
        viewer = cls(dialog, maximum=None if original else 2400)
        viewer.retranslate(language)
        viewer._host_window = dialog
        dialog.viewer = viewer
        dialog.setLayoutDirection(QtCore.Qt.LayoutDirection.RightToLeft if viewer.language == 'he'
                                  else QtCore.Qt.LayoutDirection.LeftToRight)
        layout = QtWidgets.QVBoxLayout(dialog)
        layout.addWidget(viewer)
        if original and tile_editor is not None:
            from .tile_editor import TileEditor
            dialog.tile_editor = TileEditor(dialog, viewer, tile_editor)
            attach_help(viewer.view, 'tile_editor')
            layout.addWidget(dialog.tile_editor)
            dialog.tile_editor.saved.connect(lambda directory: viewer.tile_saved.emit(
                tile_editor.dataset_id, int(tile_editor.record['id']), directory))
            if start_editor:
                viewer.loaded.connect(lambda *_: dialog.tile_editor.start.click())
            owner = parent
            while owner is not None:
                if hasattr(owner, 'process'):
                    dialog.tile_editor.setEnabled(owner.process is None)
                    break
                owner = owner.parentWidget()
        install_image_help(dialog, 'tile_editor' if hasattr(dialog, 'tile_editor') else 'image_viewer', viewer.language)
        if original and tile_editor is None:
            viewer.loaded.connect(lambda *_: viewer.actual_size())
        viewer.set_image(filename, caption, ruler_scale=ruler_scale)
        if polygons:
            # Loading is asynchronous; set overlays after the image is ready.
            viewer.loaded.connect(lambda *_: viewer.set_polygons(polygons))
        dialog.finished.connect(lambda _result: viewer.clear())
        show_centered_window(dialog)
        return dialog

    def open_original(self, *, start_editor=False):
        if self._filename and not self._loading:
            dialog = self.open_image_window(self._filename, self, language=self.language,
                                          polygons=list(self._polygons), original=True,
                                          tile_editor=self._tile_editor, ruler_scale=self.ruler.scale,
                                          start_editor=start_editor)
            if dialog is not None:
                dialog.viewer.view.setBackgroundBrush(self.view.backgroundBrush())
                dialog.viewer.tile_saved.connect(self.tile_saved)
            return dialog
        return None

    def actual_size(self):
        self._actual_size(self.view)

    def _actual_size(self, view):
        if self._pixmap_item is not None:
            if view is not self.view:
                self._fullscreen_dialog.auto_fit = False
            else:
                self._keep_manual_transform()
            center = view.mapToScene(view.viewport().rect().center())
            view.resetTransform()
            view.scale(1 / view.devicePixelRatioF(), 1 / view.devicePixelRatioF())
            self._update_pan_bounds(view)
            view.centerOn(center)

    def open_levels(self, parent):
        if self._base_image is None or self._loading:
            return
        if self._levels_dialog is None:
            dialog = ImageLevelsDialog(self, parent)
            self._levels_dialog = dialog
            dialog.finished.connect(lambda *_: setattr(self, '_levels_dialog', None))
            dialog.open_window()
        else:
            self._levels_dialog.raise_()
            self._levels_dialog.activateWindow()

    def _close_levels(self):
        if self._levels_dialog is not None:
            self._levels_dialog.close()

    def set_display_levels(self, levels):
        self._levels = levels
        self._refresh_display()
        self.display_levels_changed.emit(levels)

    def replace_display_pixels(self, image):
        """Update the unadjusted view after a tile edit without resetting pan."""
        self._base_image = image
        self._refresh_display()

    def _refresh_display(self):
        if self._pixmap_item is not None and self._base_image is not None:
            self._pixmap_item.setPixmap(QtGui.QPixmap.fromImage(display_image(self._base_image, self._levels)))

    def export_frame(self):
        if self._pixmap_item is None or self._loading:
            return None
        if len(self.scene.items()) > 1:
            return self.render_image_layers()
        return self._pixmap_item.pixmap().toImage()

    def comparison_frame(self):
        return self.render_image_layers(), self.original_size

    def render_image_layers(self, size=None, *, bounds=None):
        """Rasterize visible image overlays on the decoded grid, cropped to the image."""
        if bounds is None:
            bounds = self._pixmap_item.boundingRect()
        frame = QtGui.QImage(size or bounds.size().toSize(), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
        frame.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(frame)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        self.scene.render(painter, QtCore.QRectF(frame.rect()), bounds, QtCore.Qt.AspectRatioMode.IgnoreAspectRatio)
        painter.end()
        return frame

    def image_export_finished(self, error):
        task, destination = self._exports.pop(self.sender())
        parent = self._fullscreen_dialog or self
        if error:
            QtWidgets.QMessageBox.warning(parent, self._text('Save image…'),
                                          self._text('Could not save image: {message}', message=error))
        else:
            QtWidgets.QToolTip.showText(parent.mapToGlobal(parent.rect().center()),
                                       self._text('Image saved to {path}', path=str(destination)), parent)

    def set_export_source(self, filename):
        self._export_source = filename
        self.save_file_action.setEnabled(bool(filename))

    def open_file_comparison(self, parent):
        return compare_with_file(self, parent)

    def open_fullscreen(self):
        if self._host_window is not None and self._pixmap_item is not None and not self._loading:
            if self._host_window.isFullScreen():
                if self._host_window.property('restoreMaximized'):
                    self._host_window.showMaximized()
                else:
                    self._host_window.showNormal()
            else:
                self._host_window.setProperty('restoreMaximized', self._host_window.isMaximized())
                self._host_window.showFullScreen()
            return self._host_window
        return self._open_expanded(fullscreen=True)

    def open_enlarged(self):
        if self._host_window is not None and self._pixmap_item is not None and not self._loading:
            if self._host_window.isFullScreen():
                return self.open_fullscreen()
            if self._host_window.isMaximized():
                self._host_window.showNormal()
            else:
                self._host_window.showMaximized()
            return self._host_window
        return self._open_expanded(fullscreen=False)

    def _open_expanded(self, fullscreen):
        if self._pixmap_item is None or self._loading:
            return None
        self._cancel_click()
        if self._fullscreen_dialog is not None:
            if fullscreen:
                self._fullscreen_dialog.showFullScreen()
            self._fullscreen_dialog.raise_()
            self._fullscreen_dialog.activateWindow()
            return self._fullscreen_dialog
        dialog = _ExpandedImageDialog(self, fullscreen)
        self._fullscreen_dialog = dialog
        dialog.view.viewport().installEventFilter(self)
        dialog.view.installEventFilter(self)
        dialog.finished.connect(lambda _result, current=dialog: self._fullscreen_finished(current))
        if fullscreen:
            dialog.showFullScreen()
        else:
            show_centered_window(dialog)
        return dialog

    def close_fullscreen(self):
        dialog = getattr(self, '_fullscreen_dialog', None)
        if dialog is not None:
            try:
                dialog.close()
            except RuntimeError:
                self._fullscreen_dialog = None

    def _fullscreen_finished(self, dialog):
        if self._levels_dialog is not None and self._levels_dialog.parentWidget() is dialog:
            self._close_levels()
        self._cancel_click()
        if self._middle_pan is not None and self._middle_pan[0] is dialog.view:
            self._stop_middle_pan()
        try:
            dialog.view.viewport().removeEventFilter(self)
            dialog.view.removeEventFilter(self)
        except RuntimeError:
            pass
        if self._fullscreen_dialog is dialog:
            self._fullscreen_dialog = None
        try:
            if self.view.isVisible():
                self.view.setFocus(QtCore.Qt.FocusReason.OtherFocusReason)
        except RuntimeError:
            pass

    def _cancel_click(self):
        timer = getattr(self, '_click_timer', None)
        if timer is not None:
            try:
                timer.stop()
            except RuntimeError:
                pass
        self._pending_click = None
        positions = getattr(self, '_press_positions', None)
        if positions is not None:
            positions.clear()

    def _deliver_click(self):
        pending, self._pending_click = self._pending_click, None
        if pending is not None and pending[0] == self._token and self._pixmap_item is not None and not self._loading:
            self.clicked.emit(pending[1], pending[2])

    def _text(self, text, **values):
        return tr(text, language=self.language, **values)

    def retranslate(self, language=None):
        self.close_fullscreen()
        self._close_levels()
        self.language = language or get_language()
        self.ruler.changed.emit()
        self._translate_actions(self, self._actions)
        if self._loading:
            self.caption.setText(self._text('Loading preview…'))
        elif self._error:
            self.caption.setText(self._text('Could not open image: {message}', message=self._error))
        elif self._pixmap_item is None:
            self.caption.setText(self._text(self._empty_message))
        self._draw_polygons()

    @property
    def original_size(self):
        return self._original_size

    @property
    def filename(self):
        return self._filename

    @property
    def ruler_active(self):
        return self.ruler.active

    @property
    def measurement_active(self):
        return self.ruler.active or self.polygon.active

    def set_ruler_scale(self, source_per_x, source_per_y=None, pixel_um=None):
        """Set source pixels per saved-file pixel on each axis and optional µm/source px."""
        self.ruler.set_scale(source_per_x, source_per_y, pixel_um)

    def clear(self, message="Select an image to preview"):
        self.close_fullscreen()
        self._close_levels()
        self._stop_middle_pan()
        self._cancel_click()
        self._auto_fit = True
        self._fit_pending = False
        self._stop_fit_timer()
        self._actions.setEnabled(False)
        self._base_image = self._levels = None
        for task, _ in self._tasks.values():
            task.cancelled = True
        self._token += 1
        self.ruler.set_active(False)
        self.polygon.set_active(False)
        self.ruler.scale = None
        self.scene.clear()
        self._reset_object_highlight()
        self._pixmap_item = None
        self._overlay_items = []
        self._polygons = []
        self._original_size = (0, 0)
        self._filename = ""
        self._export_source = None
        self._tile_editor = None
        self._empty_message, self._loading, self._error = message, False, None
        self.caption.setText(self._text(message))
        self.ruler.changed.emit()

    def set_image(self, filename, caption=None, *, tile_editor=None, ruler_scale=None, preserve_view=False):
        self.close_fullscreen()
        self._close_levels()
        self._stop_middle_pan()
        self._cancel_click()
        self._stop_fit_timer()
        self._actions.setEnabled(False)
        self._base_image = self._levels = None
        for task, _ in self._tasks.values():
            task.cancelled = True
        if not filename or not Path(filename).is_file():
            self.clear("Image is missing")
            return
        self._token += 1
        self._filename = str(filename)
        self._export_source = self._filename
        self._tile_editor = tile_editor
        self.ruler.set_active(False)
        self.polygon.set_active(False)
        self.ruler.scale = ruler_scale
        # For another revision of the same tile, leave its old base frame
        # visible during decoding, while invalidating the old overlays and
        # click targets. Other selections clear immediately.
        if preserve_view and self._pixmap_item is not None:
            for item in (*self._overlay_items, *self._object_highlight_items):
                self.scene.removeItem(item)
        else:
            self._auto_fit = True
            self.scene.clear()
            self._pixmap_item = None
            self._original_size = (0, 0)
        self._reset_object_highlight()
        self._polygons = []
        self._overlay_items = []
        self._loading, self._error = True, None
        self.caption.setText(self._text("Loading preview…"))
        self.ruler.changed.emit()
        task = _ImageTask(self._token, str(filename), maximum=self._preview_maximum,
                          full_when_safe=self._full_when_safe)
        task.signals.ready.connect(self._image_ready)
        task.signals.failed.connect(self._image_failed)
        self._tasks[self._token] = (task, caption)
        image_pool().start(task)

    def set_grayscale_pixels(self, pixels, caption, ruler_scale=None):
        """Display a grayscale buffer without an intermediate file."""
        self.set_image_frame(grayscale_image(pixels), caption, ruler_scale=ruler_scale)

    def set_image_frame(self, image, caption, *, ruler_scale=None, original_size=None):
        self.clear()
        self.ruler.scale = ruler_scale
        self._tasks[self._token] = (None, caption)
        self._image_ready(self._token, image, original_size or (image.width(), image.height()))

    def _image_ready(self, token, image, original_size):
        task, caption = self._tasks.pop(token, (None, None))
        # A selection can change while decoding. Only the newest request may
        # replace the scene or its source-coordinate mapping.
        if token != self._token:
            return
        replace_in_place = self._pixmap_item is not None and original_size == self._original_size
        self._base_image = image
        pixmap = QtGui.QPixmap.fromImage(display_image(image))
        if replace_in_place:
            self._pixmap_item.setPixmap(pixmap)
        else:
            self.scene.clear()
            self._pixmap_item = self.scene.addPixmap(pixmap)
        self._loading, self._error = False, None
        self._original_size = original_size
        self.scene.setSceneRect(self._pixmap_item.boundingRect())
        self._draw_polygons()
        self.caption.setText(caption or f"{Path(self._filename).name}  ·  {original_size[0]} × {original_size[1]} px")
        self._actions.setEnabled(True)
        original_available = self.resolution_action or (self._preview_maximum is not None and self._filename)
        self.original_button.setProperty('imageActionTitle', 'Original resolution…'
                                         if original_available else 'Actual pixels · 1:1')
        self._translate_actions(self, self._actions)
        self.ruler.changed.emit()
        if not replace_in_place or self._auto_fit:
            self.fit()
        self.loaded.emit(self._filename, original_size)

    def _image_failed(self, token, message):
        self._tasks.pop(token, None)
        if token != self._token:
            return
        self.close_fullscreen()
        self._actions.setEnabled(False)
        self.scene.clear()
        self._pixmap_item = None
        self._loading, self._error = False, message
        self.caption.setText(self._text("Could not open image: {message}", message=message))
        self.ruler.changed.emit()
        self.failed.emit(message)

    def set_caption(self, caption):
        """Update a caption without opening the same image again."""
        if self._loading:
            task, _ = self._tasks[self._token]
            self._tasks[self._token] = (task, caption)
        elif not self._error:
            self.caption.setText(caption)

    def set_polygons(self, polygons):
        """Set annotations with a class ID and normalized model-canvas points."""
        self._polygons = list(polygons)
        self._draw_polygons()
        self.polygon.changed.emit()

    def _reset_object_highlight(self):
        self._object_highlight = None
        self._object_highlight_items = []
        self.highlight_toggle.hide()

    def _toggle_object_highlight(self, visible):
        for item in self._object_highlight_items:
            item.setVisible(visible)

    def set_object_highlight(self, highlight):
        """Overlay exact foreground pixels without changing the tile image."""
        import numpy as np
        if self._pixmap_item is None:
            return
        for item in self._object_highlight_items:
            if item.scene() is self.scene:
                self.scene.removeItem(item)
        self._object_highlight = highlight
        mask = highlight['mask']
        h, w = mask.shape
        rgba = np.zeros((h, w, 4), dtype=np.uint8)
        rgba[mask] = (255, 196, 48, 110)
        image = QtGui.QImage(rgba.tobytes(), w, h, 4*w, QtGui.QImage.Format.Format_RGBA8888).copy()
        item = self.scene.addPixmap(QtGui.QPixmap.fromImage(image))
        cw, ch = highlight['coordinate_size']
        bounds = self._pixmap_item.boundingRect()
        sx, sy = bounds.width()/cw, bounds.height()/ch
        transform = QtGui.QTransform.fromScale(sx, sy)
        item.setTransform(transform)
        x, y = highlight['origin']
        item.setPos(x*sx, y*sy)
        ys, xs = np.nonzero(mask)
        pen = QtGui.QPen(QtGui.QColor('#ffc430'), 2)
        pen.setCosmetic(True)
        frame = self.scene.addRect((x+int(xs.min())-5)*sx, (y+int(ys.min())-5)*sy,
                                   (int(xs.max()-xs.min())+11)*sx, (int(ys.max()-ys.min())+11)*sy, pen)
        label = self.scene.addSimpleText(highlight.get('label', self._text('Highlight object')))
        label.setBrush(QtGui.QColor('#ffc430'))
        label.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        label.setPos(frame.rect().right()+8, frame.rect().top())
        self._object_highlight_items = [item, frame, label]
        for overlay in self._object_highlight_items:
            overlay.setZValue(1.5)
        self.highlight_toggle.setText(self._text('Highlight object'))
        self.highlight_toggle.show()
        self._toggle_object_highlight(self.highlight_toggle.isChecked())

    def _draw_polygons(self):
        """Draw normalized annotation points over the current display pixmap."""
        for item in self._overlay_items:
            if item.scene() is self.scene:
                self.scene.removeItem(item)
        self._overlay_items = []
        if self._pixmap_item is None or self._loading:
            return
        bounds = self._pixmap_item.boundingRect()
        colors = ["#3be2b9", "#ffce55", "#cf99ff", "#ff8e8e", "#7fc8ff"]
        for polygon in self._polygons:
            class_id = int(polygon.get("class_id", -1))
            color = self.polygon.displayed_color or QtGui.QColor(colors[class_id % len(colors)])
            points = QtGui.QPolygonF([
                QtCore.QPointF(float(x) * bounds.width(), float(y) * bounds.height())
                for x, y in polygon.get("points", [])
            ])
            pen = QtGui.QPen(color, self.polygon.displayed_width)
            pen.setCosmetic(True)
            fill = QtGui.QColor(color)
            fill.setAlpha(25)
            item = self.scene.addPolygon(points, pen, QtGui.QBrush(fill))
            item.setToolTip(self._text('Class {id}', id=class_id))
            item.setZValue(1)
            self._overlay_items.append(item)

    def fit(self):
        self._auto_fit = True
        self._fit_pending = True
        self._apply_auto_fit()
        self._queue_auto_fit()

    def _queue_auto_fit(self):
        # Let Qt finish assigning the viewport its new size before fitting.
        timer = getattr(self, '_fit_timer', None)
        if timer is not None and getattr(self, '_auto_fit', False) and getattr(self, '_pixmap_item', None) is not None:
            self._fit_pending = True
            try:
                timer.start(0)
            except RuntimeError:
                pass

    def _apply_auto_fit(self):
        view, item = getattr(self, 'view', None), getattr(self, '_pixmap_item', None)
        if not getattr(self, '_auto_fit', False) or view is None or item is None:
            return
        try:
            if view.isVisible():
                view.fitInView(item.boundingRect(), QtCore.Qt.AspectRatioMode.KeepAspectRatio)
                self._update_pan_bounds(view)
                view.centerOn(item.boundingRect().center())
                self._fit_pending = False
        except RuntimeError:
            pass

    def _stop_fit_timer(self):
        timer = getattr(self, '_fit_timer', None)
        if timer is not None:
            try:
                timer.stop()
            except RuntimeError:
                pass

    def _keep_manual_transform(self):
        """Keep zoom or pan through subsequent resize events until Fit is chosen."""
        self._auto_fit = False
        self._fit_pending = False
        self._stop_fit_timer()

    def zoom(self, factor):
        self._zoom_view(self.view, factor)

    def _zoom_view(self, view, factor, anchor=None):
        if self._pixmap_item is not None:
            scale = view.transform().m11()
            ceiling = getattr(self, '_zoom_ceiling', 40)
            if 0.02 <= scale * factor <= max(ceiling, scale if factor < 1 else ceiling):
                if view is self.view:
                    self._keep_manual_transform()
                elif self._fullscreen_dialog is not None:
                    self._fullscreen_dialog.auto_fit = False
                center = view.viewport().rect().center()
                anchor = center if anchor is None else anchor
                before = view.mapToScene(anchor)
                view.scale(factor, factor)
                self._update_pan_bounds(view)
                view.centerOn(view.mapToScene(center) + before - view.mapToScene(anchor))

    def _stop_middle_pan(self):
        pan, self._middle_pan = self._middle_pan, None
        if pan is not None:
            view, _, cursor = pan
            if cursor is None:
                view.viewport().unsetCursor()
            else:
                view.viewport().setCursor(cursor)

    def _handle_middle_pan(self, view, event):
        kind = QtCore.QEvent.Type
        middle = QtCore.Qt.MouseButton.MiddleButton
        if event.type() in (kind.MouseButtonPress, kind.MouseButtonDblClick) and event.button() == middle:
            if (self._pixmap_item is not None and not self._loading
                    and not event.buttons() & QtCore.Qt.MouseButton.LeftButton):
                self._stop_middle_pan()
                self._cancel_click()
                viewport = view.viewport()
                cursor = viewport.cursor() if viewport.testAttribute(QtCore.Qt.WidgetAttribute.WA_SetCursor) else None
                self._middle_pan = view, event.position().toPoint(), cursor
                viewport.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
            return True
        if self._middle_pan is None or self._middle_pan[0] is not view:
            return False
        if event.type() in (kind.Hide, kind.UngrabMouse):
            self._stop_middle_pan()
        elif event.type() == kind.MouseButtonRelease and event.button() == middle:
            self._stop_middle_pan()
            return True
        elif event.type() == kind.MouseMove:
            if not event.buttons() & middle:
                self._stop_middle_pan()
                return False
            _, previous, cursor = self._middle_pan
            current = event.position().toPoint()
            delta = current - previous
            if not delta.isNull():
                if view is self.view:
                    self._keep_manual_transform()
                else:
                    self._fullscreen_dialog.auto_fit = False
                horizontal, vertical = view.horizontalScrollBar(), view.verticalScrollBar()
                horizontal.setValue(horizontal.value() - delta.x())
                vertical.setValue(vertical.value() - delta.y())
                self._middle_pan = view, current, cursor
            return True
        return False

    def eventFilter(self, watched, event):
        embedded = getattr(self, 'view', None)
        if embedded is None:
            return False
        dialog = getattr(self, '_fullscreen_dialog', None)
        try:
            view = embedded if watched is embedded.viewport() else None
            fullscreen = getattr(dialog, 'view', None)
            ruler = getattr(self, 'ruler', None)
            polygon = getattr(self, 'polygon', None)
            if (polygon is not None and watched in (embedded, fullscreen)
                    and event.type() in (QtCore.QEvent.Type.ShortcutOverride, QtCore.QEvent.Type.KeyPress)
                    and polygon.handle_key(event)):
                return True
            if (ruler is not None and watched in (embedded, fullscreen)
                    and event.type() in (QtCore.QEvent.Type.ShortcutOverride, QtCore.QEvent.Type.KeyPress)
                    and ruler.handle_key(event)):
                return True
            if fullscreen is not None and watched is fullscreen.viewport():
                view = fullscreen
        except RuntimeError:
            # A native viewport can outlive its Python wrapper during deferred
            # deletion. An exception escaping a Qt callback aborts PyQt apps.
            return False
        if view is not None:
            # Pan before the drawing tools see mouse motion.
            if self._handle_middle_pan(view, event):
                return True
            if event.type() in (QtCore.QEvent.Type.Resize, QtCore.QEvent.Type.Show):
                if view is embedded:
                    self._queue_auto_fit()
                self._update_pan_bounds(view)
            if event.type() == QtCore.QEvent.Type.Wheel and getattr(self, '_pixmap_item', None) is not None:
                self._zoom_view(view, 1.18 if event.angleDelta().y() > 0 else 1 / 1.18, event.position().toPoint())
                return True
            if polygon is not None and polygon.handle(view, event):
                return True
            if ruler is not None and ruler.handle(view, event):
                return True
            if event.type() == QtCore.QEvent.Type.MouseButtonDblClick and event.button() == QtCore.Qt.MouseButton.LeftButton:
                self._cancel_click()
                if view is self.view:
                    self.open_enlarged()
                else:
                    self.close_fullscreen()
                return True
            if event.type() == QtCore.QEvent.Type.MouseButtonPress:
                if event.button() == QtCore.Qt.MouseButton.LeftButton:
                    self._press_positions[view] = event.position().toPoint()
            elif event.type() == QtCore.QEvent.Type.MouseMove:
                origin = self._press_positions.get(view)
                if origin is not None and (event.position().toPoint() - origin).manhattanLength() >= 5:
                    if view is embedded:
                        self._keep_manual_transform()
                    elif dialog is not None:
                        dialog.auto_fit = False
            elif event.type() == QtCore.QEvent.Type.MouseButtonRelease and event.button() == QtCore.Qt.MouseButton.LeftButton:
                press_position = self._press_positions.pop(view, None)
                position = event.position().toPoint()
                if (press_position is not None and (position - press_position).manhattanLength() < 5
                        and self._pixmap_item is not None and not self._loading):
                    point = view.mapToScene(position)
                    rect = self._pixmap_item.boundingRect()
                    if rect.contains(point):
                        self._pending_click = (self._token,
                            point.x() * self._original_size[0] / rect.width(),
                            point.y() * self._original_size[1] / rect.height())
                        # Distinguish a selection from the first half of a
                        # double-click, which opens the image instead.
                        self._click_timer.start(QtWidgets.QApplication.doubleClickInterval())
        return super().eventFilter(watched, event)

    def hideEvent(self, event):
        self.close_fullscreen()
        self._stop_middle_pan()
        self._cancel_click()
        self._stop_fit_timer()
        super().hideEvent(event)

    def closeEvent(self, event):
        self.close_fullscreen()
        self._close_levels()
        self._stop_middle_pan()
        self._cancel_click()
        self._stop_fit_timer()
        super().closeEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        self._queue_auto_fit()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._queue_auto_fit()

class _FilterComboBox(QtWidgets.QComboBox):
    def findData(self, data, role=QtCore.Qt.ItemDataRole.UserRole, flags=None):
        # Qt's QVariant search cannot compare Python tuple payloads on every
        # binding. Keep the source/manual filter identity portable.
        if isinstance(data, (tuple, list)):
            for index in range(self.count()):
                value = self.itemData(index, role)
                if isinstance(value, (tuple, list)) and tuple(value) == tuple(data):
                    return index
            return -1
        return super().findData(data, role) if flags is None else super().findData(data, role, flags)


class CsvTable(QtWidgets.QWidget):
    """Read-only scientific features with a separate overlay of manual targets."""

    row_selected = Signal(object)
    MANUAL_HEADERS = ('Manual_Class_ID', 'Manual_Class', 'Reviewed')
    HEADER_LABELS = {
        'Class_Name':'Source class', 'Class_ID':'Source class ID', 'Tile_Name':'Tile',
        'Object_ID':'Object', 'Large_Image':'Source dataset', 'Area':'Area, px²',
        'Aspect_Ratio':'AR (major / minor axis)', 'Solidity':'Solidity',
        'Euler_Number':'Euler number', 'Endpoints':'Skeleton endpoints',
        'Branch_Points':'Branch pixels', 'Measurement_Space':'Measurement space',
        'Source_Pixels_Per_Output_Pixel':'Source px / model px', 'Area_um2':'Area, µm²',
        'Manual_Class_ID':'Manual class ID', 'Manual_Class':'Manual class', 'Reviewed':'Reviewed'}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.language = get_language()
        self.headers, self.rows, self.visible_rows = [], [], []
        self._source_headers, self._source_rows = [], []
        self._manual_enabled = False
        self.source_path = None
        self.class_filter = _FilterComboBox()
        self.search = QtWidgets.QLineEdit()
        self.count = QtWidgets.QLabel()
        attach_help(self.class_filter, 'result_class_filter')
        attach_help(self.search, 'result_search')
        self.table = QtWidgets.QTableWidget()
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.class_filter.currentIndexChanged.connect(self.apply_filter)
        self.search.textChanged.connect(self.apply_filter)
        top = QtWidgets.QHBoxLayout()
        top.addWidget(self.class_filter)
        top.addWidget(help_label('result_class_filter'))
        top.addWidget(self.search, 1)
        top.addWidget(help_label('result_search'))
        top.addWidget(self.count)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(top)
        layout.addWidget(self.table, 1)
        self.retranslate(self.language)

    def _text(self, text, **values):
        return tr(text, language=self.language, **values)

    def retranslate(self, language=None):
        self.language = language or get_language()
        self.search.setPlaceholderText(self._text('Search by tile, object or class'))
        self._refresh_classes()
        self.apply_filter()

    @staticmethod
    def _object_key(row):
        return str(row.get('Tile_Name', '')) + '/' + str(row.get('Object_ID', ''))

    def _manual_name(self, key):
        if not key:
            return self._text('Unclassified')
        entry = next((item for item in CANONICAL_MANUAL_CLASSES if item['key'] == key), None)
        return self._text(entry['label_en']) if entry else str(key)

    def _refresh_classes(self):
        selected = self.class_filter.currentData()
        self.class_filter.blockSignals(True)
        self.class_filter.clear()
        self.class_filter.addItem(self._text('All classes'), None)
        for name in sorted({str(row.get('Class_Name') or 'Unknown') for row in self.rows}):
            label = self._text('Source: {class_name}', class_name=self._text(name)) if self._manual_enabled else self._text(name)
            self.class_filter.addItem(label, name)
        if self._manual_enabled:
            self.class_filter.addItem(self._text('Unclassified'), ('manual', None))
            for definition in CANONICAL_MANUAL_CLASSES:
                self.class_filter.addItem(self._text('Manual: {class_name}',
                    class_name=self._manual_name(definition['key'])), ('manual', definition['key']))
        found = self.class_filter.findData(selected)
        self.class_filter.setCurrentIndex(max(0, found))
        self.class_filter.blockSignals(False)

    def clear(self):
        self.headers, self.rows, self.visible_rows = [], [], []
        self._source_headers, self._source_rows = [], []
        self._manual_enabled = False
        self.source_path = None
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self._refresh_classes()
        self.apply_filter()

    def load_csv(self, filename):
        with open(filename, encoding='utf-8-sig', newline='') as handle:
            reader = csv.DictReader(handle)
            self._source_headers = reader.fieldnames or []
            self._source_rows = list(reader)
        self.headers = list(self._source_headers)
        self.rows = [dict(row) for row in self._source_rows]
        self._manual_enabled = 'Manual_Class' in self.headers
        self.source_path = str(filename)
        self._refresh_classes()
        self.apply_filter()

    def set_manual_labels(self, report_or_labels):
        """Add persisted targets to the view without changing scientific data."""
        selected = self.selected_row()
        report = report_or_labels or {}
        labels = report.get('labels', report)
        self._manual_enabled = True
        self.headers = [name for name in self._source_headers if name not in self.MANUAL_HEADERS]
        position = self.headers.index('Object_ID')+1 if 'Object_ID' in self.headers else len(self.headers)
        self.headers[position:position] = ['Manual_Class', 'Manual_Class_ID', 'Reviewed']
        self.rows = []
        for source in self._source_rows:
            row = dict(source)
            row.update(Manual_Class_ID='', Manual_Class='', Reviewed=False)
            label = labels.get(self._object_key(row), {})
            row.update({name:label[name] for name in self.MANUAL_HEADERS if name in label})
            self.rows.append(row)
        self._manual_rows_by_key = {self._object_key(row): row for row in self.rows}
        self._refresh_classes()
        self.apply_filter()
        if selected:
            self.select_object(selected.get('Tile_Name'), selected.get('Object_ID'))

    apply_manual_labels = set_manual_labels

    def update_manual_label(self, key, label):
        """Update one visible row; filtered views keep their existing semantics."""
        row = getattr(self, '_manual_rows_by_key', {}).get(key)
        if row is None:
            return
        row.update(Manual_Class_ID='', Manual_Class='', Reviewed=False)
        row.update({name: label[name] for name in self.MANUAL_HEADERS if label and name in label})
        if self.search.text().strip() or self.class_filter.currentData() is not None:
            self.apply_filter()
            return
        position = getattr(self, '_visible_indexes_by_key', {}).get(key)
        if position is None:
            return
        for column in range(len(self.headers)):
            item = self.table.item(position, column)
            if item is not None:
                item.setData(QtCore.Qt.ItemDataRole.UserRole, row)
        for name in self.MANUAL_HEADERS:
            if name not in self.headers:
                continue
            item = self.table.item(position, self.headers.index(name))
            if item is None:
                continue
            value = row.get(name, '')
            if name == 'Manual_Class':
                value = self._manual_name(value)
                item.setForeground(QtGui.QColor('#20a585') if label else QtGui.QBrush())
                font = item.font(); font.setBold(bool(label)); item.setFont(font)
            elif name == 'Reviewed':
                value = self._text('Yes') if label else ''
            item.setText(str(value))

    def selected_row(self):
        selected = self.table.selectedItems()
        return selected[0].data(QtCore.Qt.ItemDataRole.UserRole) if selected else None

    def select_object(self, tile_name, object_id):
        key = str(tile_name) + '/' + str(object_id)
        for index, row in enumerate(self.visible_rows):
            if self._object_key(row) == key:
                self.table.selectRow(index)
                self.table.scrollToItem(self.table.item(index, 0))
                return True
        return False

    def navigate(self, direction):
        if direction not in ('previous', 'next', 'unlabeled'):
            raise ValueError('Unknown object navigation direction')
        if not self.visible_rows:
            return None
        current = self.selected_row()
        position = next((i for i, row in enumerate(self.visible_rows)
                         if current and self._object_key(row) == self._object_key(current)), -1)
        if direction == 'unlabeled':
            order = list(range(position+1, len(self.visible_rows))) + list(range(0, position+1))
            target = next((i for i in order if not self.visible_rows[i].get('Manual_Class')), None)
            if target is None:
                return None
        else:
            target = 0 if position < 0 else max(0, min(len(self.visible_rows)-1,
                                                     position + (-1 if direction == 'previous' else 1)))
        row = self.visible_rows[target]
        self.select_object(row.get('Tile_Name'), row.get('Object_ID'))
        return row

    def apply_filter(self, *_):
        """Rebuild localized display rows while retaining raw CSV values and IDs."""
        selected = self.selected_row()
        chosen = self.class_filter.currentData()
        query = self.search.text().strip().casefold()
        def matches(row):
            if isinstance(chosen, (list, tuple)) and len(chosen) == 2 and chosen[0] == 'manual':
                if (row.get('Manual_Class') or None) != chosen[1]:
                    return False
            elif chosen is not None and row.get('Class_Name') != chosen:
                return False
            values = ' '.join(str(value) for value in row.values())
            values += ' ' + self._manual_name(row.get('Manual_Class')) + ' ' + self._text(str(row.get('Class_Name', '')))
            return not query or query in values.casefold()
        self.visible_rows = [row for row in self.rows if matches(row)]
        self._visible_indexes_by_key = {self._object_key(row): i for i, row in enumerate(self.visible_rows)}
        self.table.setSortingEnabled(False)
        self.table.clear()
        self.table.setColumnCount(len(self.headers))
        self.table.setHorizontalHeaderLabels([self._text(self.HEADER_LABELS.get(name, name)) for name in self.headers])
        self.table.setRowCount(len(self.visible_rows))
        for row_index, row in enumerate(self.visible_rows):
            for column, name in enumerate(self.headers):
                value = row.get(name, '')
                if name == 'Manual_Class':
                    value = self._manual_name(value)
                elif name == 'Reviewed':
                    value = self._text('Yes') if str(value).casefold() in ('true','1','yes') else ''
                elif name == 'Class_Name':
                    value = self._text(str(value))
                item = QtWidgets.QTableWidgetItem(str(value))
                item.setData(QtCore.Qt.ItemDataRole.UserRole, row)
                if name == 'Manual_Class' and row.get('Manual_Class'):
                    item.setForeground(QtGui.QColor('#20a585'))
                    font=item.font(); font.setBold(True); item.setFont(font)
                self.table.setItem(row_index, column, item)
        self.table.resizeColumnsToContents()
        self.count.setText(self._text('Objects: {visible} / {total}', visible=len(self.visible_rows), total=len(self.rows)))
        if selected:
            self.select_object(selected.get('Tile_Name'), selected.get('Object_ID'))

    def _selection_changed(self):
        selected = self.selected_row()
        if selected is not None:
            self.row_selected.emit(selected)

    def export_filtered(self, filename):
        """Export the displayed subset without altering the scientific source CSV."""
        destination = Path(filename).resolve()
        if self.source_path:
            from .object_labels import validate_export_destination
            destination = validate_export_destination(
                dict(results_dir=str(Path(self.source_path).resolve().parent), last_csv=self.source_path),
                destination)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8-sig', newline='',
                                             prefix='.csv_export_', suffix='.tmp',
                                             dir=destination.parent, delete=False) as handle:
                temporary = Path(handle.name).resolve()
                if temporary.parent != destination.parent:
                    raise ValueError('CSV export must stay inside its selected destination directory')
                writer = csv.DictWriter(handle, fieldnames=self.headers)
                writer.writeheader()
                writer.writerows(self.visible_rows)
            os.replace(temporary, destination)
        finally:
            if temporary is not None and temporary.is_file():
                temporary.unlink()
        return len(self.visible_rows)
