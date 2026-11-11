"""Capture current Qt workflows on real microscopy crops in a private demo.

This authoring helper never mutates production datasets or assigns expert
biological labels. All screenshots are real QWidget.grab() results. Editor
previews remain unsaved unless a separate immutable demo version is requested.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time

import cv2
import numpy as np
from PIL import Image

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[1]
PRESENTATION = ROOT.parent/'Presentanion'
SOURCE = ROOT/'Archive/Presentations/Build_history/revision_2026-10-30/ui/input/G3_real_crop_y7000_x7000_2048.tif'
ASSETS = PRESENTATION/'presentation_source/assets/ui_quality_2026_11_08'
META = PRESENTATION/'presentation_source/ui_quality_2026_11_08.json'
sys.path.insert(0,str(ROOT))
temporary_root = ROOT/'data/validation/Presentation_capture/Temporary'
temporary_root.mkdir(parents=True, exist_ok=True)
tempfile.tempdir = str(temporary_root)

from src.app_settings import PipelineSettings
from src.desktop import service
from src.desktop.branding import configure_application_branding
from src.desktop.i18n import set_language
from src.desktop.main_window import MainWindow
from src.desktop.project import Project
from src.desktop.qt import QtCore, QtGui, QtWidgets, configure_font
from src.desktop.storage_names import new_version
from src.desktop.tile_edit import TileEdit, TileEditContext
from src.desktop.widgets import ImageViewer, image_pool
from src.overview_reconstructor import HighResOverviewReconstructor
from src.partition_geometry import (find_dataset_manifest, read_manifest,
                                    restore_ownership, ownership_boundary)
from src.tile_edits import tile_artifact_path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pump(seconds=.20):
    until=time.monotonic()+seconds
    while time.monotonic()<until:
        APP.processEvents(); time.sleep(.01)


def wait_for(predicate, seconds=40):
    until=time.monotonic()+seconds
    while not predicate() and time.monotonic()<until:
        APP.processEvents();time.sleep(.01)
    if not predicate():
        raise RuntimeError('Timed out waiting for current UI data')
    pump(.15)


def capture(widget, name, **provenance):
    pump(.35)
    path=ASSETS/name
    if not widget.grab().save(str(path)):
        raise RuntimeError('Could not save screenshot '+str(path))
    with Image.open(path) as image:
        size=list(image.size)
    MANIFEST['assets'].append(dict(path=path.relative_to(PRESENTATION/'presentation_source').as_posix(),
                                  sha256=sha(path),size=size,**provenance))
    print('Captured',name,flush=True)


def wait_images(window):
    wait_for(lambda:not any(v._loading for v in window.findChildren(ImageViewer)))
    pump(.25)


def stage(window,index):
    window.sidebar.setCurrentRow(index)
    pump(.20)
    wait_images(window)
    wait_for(lambda:window.process is None)


def editor(window,dataset,record,name):
    context=TileEditContext(window.project.workspace,dataset['id'],dataset['path'],record,'native',
                            expected_revision=record.get('edit_reference'))
    path=tile_artifact_path(dataset['path'],record,'native_filename')
    dialog=ImageViewer.open_image_window(path,window,language='en',caption=name,original=True,tile_editor=context)
    dialog.resize(1560,1000)
    wait_for(lambda:not dialog.viewer._loading)
    dialog.tile_editor.start.click()
    wait_for(lambda:dialog.tile_editor.edit is not None)
    dialog.viewer.fit();pump(.25)
    return dialog,context


def main():
    ASSETS.mkdir(parents=True,exist_ok=True)
    qa_parent=PRESENTATION/'_build/Interface_capture'
    qa=new_version(qa_parent,'Capture')
    project=Project.create(qa/'project.json',name='Microscopy demo')
    settings=PipelineSettings(target_size=1500,overview_size=2400,save_raw_tiles=True,enable_animations=False)
    project.settings=settings.to_dict();project.save()
    sources=service.add_sources(project,[SOURCE,
        PRESENTATION/'Raw Examples/FL01_G3_RGB_Red_tile_259.tif',
        PRESENTATION/'Raw Examples/FL01_G3_RGB_Red_tile_91.tif'])
    primary=sources[0]
    preview=service.preview(project,source_id=primary['id'])
    summary=service.prepare(project,source_ids=[primary['id']])
    if summary.get('failed'):
        raise RuntimeError(str(summary))
    dataset=project.get_dataset(summary['datasets'][0])
    service.mark_reviewed(project,dataset['id'])
    extraction=service.extract(project,dataset['id'],labels_mode='auto')
    project.save()
    MANIFEST.update(project_path=project.path,source=str(SOURCE),source_sha256=sha(SOURCE),
        source_scope=dict(original_source='FL01_G3_RGB_Red.tif',bounds_xyxy=[7000,7000,9048,9048],
                          processing='standalone real 2048x2048 crop, not the original full TIFF'),
        settings=settings.to_dict(),preview=preview,preparation=summary,extraction=extraction,
        labels='No expert biological labels were assigned; source classes are Unknown in automatic mode.')

    prefs=QtCore.QSettings(str(qa/'screen_preferences.ini'),QtCore.QSettings.Format.IniFormat)
    window=MainWindow(project,language='en',preferences=prefs)
    window.labels_mode.setCurrentIndex(window.labels_mode.findData('auto'))
    window.resize(1920,1080);window.show();window.show_log.setChecked(False)
    # The dataset and previews were generated by the same current application services.
    window.preview_source_combo.setCurrentIndex(window.preview_source_combo.findData(primary['id']))
    window.input_preview.set_image(preview['input_path'])
    window.filtered_preview.set_image(preview['filtered_path'])
    window.protective_preview.set_image(preview['mask_path'])
    window.labels_mode.setCurrentIndex(window.labels_mode.findData('auto'))
    stage(window,0)
    for row in range(1,window.source_table.rowCount()):
        window.source_table.item(row,0).setCheckState(QtCore.Qt.CheckState.Unchecked)
    window.source_table.selectRow(0)
    capture(window,'01_sources.png',role='Sources page',state='three real demo TIFFs imported into private project')

    stage(window,1)
    window._settings_fields['straight_shift_left'].setMinimumWidth(125)
    window.preview_tabs.setCurrentIndex(1);window.filtered_preview.fit();pump(.25)
    capture(window,'02_preparation_filtered.png',role='Preparation page',state='completed whole demo-TIFF filtered preview')
    window.preview_tabs.setCurrentIndex(2);window.protective_preview.fit();pump(.25)
    capture(window,'02_preparation_protection.png',role='Preparation page',state='completed protective-mask preview')

    stage(window,2)
    tilespace=window._workspaces['tiles']
    tilespace.resizeDocks([tilespace.panels['browser'],tilespace.panels['images']],[350,1230],QtCore.Qt.Orientation.Horizontal)
    window.tile_tabs.setCurrentIndex(0);window.overview_view.fit();pump(.3)
    capture(window,'03_tiles_overview.png',role='Tiles page',state='actual saved overview with native ownership boundaries')
    records=service.tile_records(window.selected_dataset())
    with Path(window.selected_dataset()['last_csv']).open(encoding='utf-8-sig',newline='') as handle:
        rows=list(csv.DictReader(handle))
    counts={r['id']:sum(Path(r['filename']).stem==row['Tile_Name'] for row in rows) for r in records}
    # Native0004 is also the independently reproduced object-mask example.
    record=next((r for r in records if r['id']==1 and not r['excluded']),max(records,key=lambda r:counts[r['id']]))
    window._select_tile_id(record['id']);window.tile_tabs.setCurrentIndex(2)
    wait_images(window);window.native_view.fit();pump(.2)
    capture(window,'03_tiles_native.png',role='Tiles page',tile_id=record['id'],state='prepared native source-scale pixels')

    # Save native-resolution overview evidence. These PNGs come from the actual renderer.
    map_path=HighResOverviewReconstructor().reconstruct_dataset(dataset['path'],target_dim=2048)
    map_asset=ASSETS/'overview_exact_boundaries.png';map_asset.write_bytes(Path(map_path).read_bytes())
    MANIFEST['assets'].append(dict(path=map_asset.relative_to(PRESENTATION/'presentation_source').as_posix(),
        sha256=sha(map_asset),role='source-resolution overview',state='processed grayscale with final ownership boundaries'))
    if dataset.get('raw_path'):
        raw_map=HighResOverviewReconstructor().reconstruct_dataset(dataset['raw_path'],target_dim=2048)
        raw_asset=ASSETS/'overview_raw_boundaries.png';raw_asset.write_bytes(Path(raw_map).read_bytes())
        MANIFEST['assets'].append(dict(path=raw_asset.relative_to(PRESENTATION/'presentation_source').as_posix(),
            sha256=sha(raw_asset),role='raw source-resolution overview',state='raw grayscale with the same prepared ownership boundaries'))

    stage(window,3)
    workspace=window._workspaces['segmentation']
    workspace.resizeDocks([workspace.panels['settings'],workspace.panels['image']],[470,1120],QtCore.Qt.Orientation.Horizontal)
    review=window.segmentation_review;review.select_tile(record['id']);review.tabs.setCurrentIndex(2)
    wait_for(lambda:bool(review._objects) and not review.objects_view._loading)
    review.objects_view.fit();pump(.3)
    capture(window,'04_segmentation_objects.png',role='Segmentation page',tile_id=record['id'],
            state='exact measured masks and IDs, no expert biological labels')
    selected=[int(o['row']['Object_ID']) for o in review._objects
              if float(o['row']['Area']) in (1421,1019)]
    assert len(selected)==2,'Expected the independently reproduced split candidate'
    review.select_ids(selected);pump(.2)
    capture(window,'04_segmentation_merge_selection.png',role='Segmentation page',tile_id=record['id'],
            selected_ids=selected,state='two components of one candidate contour; merge selection preview, biological belonging unconfirmed')
    review.merge_button.click();wait_for(lambda:window.process is None)
    wait_for(lambda:bool(review._objects) and len(review._objects)==counts[record['id']]-1)
    capture(window,'04_segmentation_merged.png',role='Segmentation page',tile_id=record['id'],
            state='manual union of selected masks in a new version; no synthetic bridge, unclassified merged object')
    merged_rows=service.read_results(window.selected_dataset())[1]
    merged_row=next(r for r in merged_rows if r['Tile_Name']==Path(record['filename']).stem and int(r['Object_ID'])>35)
    MANIFEST['merge_example']=dict(source_object_ids=selected,merged_object_id=int(merged_row['Object_ID']),
        area_px=float(merged_row['Area']),euler_number=float(merged_row['Euler_Number']),
        caveat='Manual union of two masks from one automatic candidate; unconfirmed biological identity, no added bridge pixels.')
    review.undo_button.click();wait_for(lambda:window.process is None)
    wait_for(lambda:bool(review._objects) and len(review._objects)==counts[record['id']])
    review.select_ids([])

    stage(window,4)
    window.object_gallery.tile_filter.setCurrentIndex(window.object_gallery.tile_filter.findData(Path(record['filename']).stem))
    window.object_gallery.select_object(Path(record['filename']).stem,selected[0])
    pump(.25)
    # Trigger and wait for every currently visible thumbnail. No gray placeholders are delivered.
    deadline=time.monotonic()+15
    while time.monotonic()<deadline:
        APP.processEvents();pump(.10)
        for row in window.object_gallery.visible_rows:
            window.object_gallery._thumbnail(window.object_gallery._key(row))
        if (not window.object_gallery._tasks and
                all(window.object_gallery._key(r) in window.object_gallery._cache for r in window.object_gallery.visible_rows)):
            break
    pump(.8)
    capture(window,'05_object_labeling.png',role='Object labeling page',state='unclassified real objects; six stable type controls')

    stage(window,5)
    capture(window,'06_model_training.png',role='Model training page',state='configuration without invented expert labels or scores')

    stage(window,6);window.analytics.tabs.setCurrentIndex(0);window.analytics.ensure_plot();pump(.8)
    capture(window,'07_results_histogram.png',role='Results page',state='Area histogram of current demo measurements')
    if window.analytics._plot is not None:
        window.analytics._plot.kind.setCurrentIndex(1)
        window.analytics._plot.x.setCurrentText('Area');window.analytics._plot.y.setCurrentText('Aspect_Ratio')
        pump(.5)
        capture(window,'07_results_scatter.png',role='Results page',state='Area vs equivalent-ellipse Aspect_Ratio for current demo objects')

    capture_editors(window,window.selected_dataset(),record)
    window.close();window.deleteLater();image_pool().waitForDone(10000)
    APP.processEvents();QtCore.QCoreApplication.sendPostedEvents(None,QtCore.QEvent.Type.DeferredDelete)
    META.write_text(json.dumps(MANIFEST,indent=2,ensure_ascii=False),encoding='utf8')
    print('Saved',META,flush=True)


def capture_editors(window,dataset,record):
    dialog,context=editor(window,dataset,record,'Native tile · source-scale editing')
    edit=dialog.tile_editor
    capture(dialog,'08_editor_original.png',role='Tile editor',tile_id=record['id'],state='original pixels, no edits')
    edit.mode.setCurrentIndex(edit.mode.findData('cut'))
    height,width=edit.edit.pixels.shape
    line=((int(width*.75),0),(int(width*.75),height-1))
    edit._cut_line=line;edit._cut_side=-1
    edit._paint_cut(line);edit._update_hint();edit._sync();pump(.15)
    capture(dialog,'08_editor_cut_preview.png',role='Tile editor',tile_id=record['id'],
            state='unsaved cut-side preview',line_xy=line,side=-1)
    edit._cancel_pending()
    edit.mode.setCurrentIndex(edit.mode.findData('gamma'))
    edit.gamma_scope.setCurrentIndex(edit.gamma_scope.findData('rectangle'))
    # A real native region around the independently reproduced object.
    box=(435,417,min(width,737),min(height,539))
    if box[2]<=box[0] or box[3]<=box[1]:box=(width//4,height//4,width//2,height//2)
    edit._gamma_rectangle=box;edit.gamma_slider.setValue(200)
    wait_for(lambda:edit._gamma_preview_key is not None and edit._task is None)
    capture(dialog,'08_editor_local_gamma.png',role='Tile editor',tile_id=record['id'],
            state='unsaved gamma preview in selected rectangle',gamma=2.0,bounds_ltrb=box)
    dialog.viewer._keep_manual_transform()
    dialog.viewer.view.fitInView(QtCore.QRectF(385,370,400,220),QtCore.Qt.AspectRatioMode.KeepAspectRatio)
    dialog.viewer.view.centerOn(585,480)
    capture(dialog,'08_editor_local_gamma_detail.png',role='Tile editor',tile_id=record['id'],
            state='unsaved local-gamma preview, zoomed real native region',gamma=2.0,bounds_ltrb=box)
    edit._cancel_pending();edit.mode.setCurrentIndex(edit.mode.findData('paint'))
    pixels=edit.edit.pixels;valid=edit.edit.valid
    ys,xs=np.nonzero(valid & (pixels>100))
    roi=pixels[417:539,435:737]
    sy,sx=np.unravel_index(np.argmax(roi),roi.shape)
    sample=(int(sx+435),int(sy+417))
    with QtCore.QSignalBlocker(edit.paint_intensity):edit.paint_intensity.setValue(int(pixels[sample[1],sample[0]]))
    edit._paint_sample=list(sample);edit.pick_button.setChecked(False);edit._update_hint();edit._sync()
    capture(dialog,'08_editor_pipette_brush.png',role='Tile editor',tile_id=record['id'],
            state='sampled native intensity; no synthetic stroke applied',sample_xy=sample,intensity=int(pixels[sample[1],sample[0]]))
    edit._points=[(614,488),(627,494)];edit._paint_guide('paint')
    capture(dialog,'08_editor_brush_preview.png',role='Tile editor',tile_id=record['id'],
            state='unsaved manual brush guide only; synthetic continuation preview, not observed evidence',
            points_xy=edit._points,radius_px=edit.paint_radius.value(),sample_xy=sample,intensity=int(pixels[sample[1],sample[0]]))
    edit._cancel_gesture()
    # Reproduce the editor LUT on the exact same stored pixels, without publishing changes.
    original=pixels.copy();whole=edit.edit.gamma_preview(2.0);local=edit.edit.gamma_preview(2.0,box)
    arrays={'noise_stored_native.png':original,'noise_gamma2_whole.png':whole,'noise_gamma2_local.png':local}
    for name,array in arrays.items():
        path=ASSETS/name;Image.fromarray(array).save(path)
        MANIFEST['assets'].append(dict(path=path.relative_to(PRESENTATION/'presentation_source').as_posix(),
            sha256=sha(path),role='reproduced native tone transform',state='same stored input; editor reciprocal gamma2',bounds_ltrb=box))
        detail=Image.fromarray(array[387:569,405:767]).resize((1086,546),Image.Resampling.NEAREST)
        detail_path=ASSETS/name.replace('.png','_detail.png');detail.save(detail_path)
        MANIFEST['assets'].append(dict(path=detail_path.relative_to(PRESENTATION/'presentation_source').as_posix(),
            sha256=sha(detail_path),role='same real intensity region enlarged 3x',native_bounds_ltrb=[405,387,767,569],
            state='nearest-neighbor enlargement, same 0..255 display scale'))
    bkg=(original>0)&(original<=25)&valid
    MANIFEST['tone_example']=dict(tile_id=record['id'],native_path=str(tile_artifact_path(dataset['path'],record,'native_filename')),
        native_sha256=sha(tile_artifact_path(dataset['path'],record,'native_filename')),editor_gamma=2.0,local_bounds_ltrb=box,
        low_intensity_selection='valid pixels with stored intensity 1..25; a descriptive subset, not an expert noise mask',
        selected_pixels=int(bkg.sum()),mean_stored=float(original[bkg].mean()) if bkg.any() else None,
        mean_gamma2=float(whole[bkg].mean()) if bkg.any() else None,
        caveat='Gamma raises faint background and faint signal; no expert segmentation-accuracy claim. No editor operation was saved.')
    dialog.close();pump(.2)


def capture_merge_details():
    """Add close UI evidence using the already prepared private demo version."""
    MANIFEST.update(json.loads(META.read_text(encoding='utf8')))
    project=Project.load(MANIFEST['project_path'])
    qa=Path(project.workspace)
    prefs=QtCore.QSettings(str(qa/'detail_preferences.ini'),QtCore.QSettings.Format.IniFormat)
    window=MainWindow(project,language='en',preferences=prefs)
    window.labels_mode.setCurrentIndex(window.labels_mode.findData('auto'))
    window.resize(1920,1080);window.show();window.show_log.setChecked(False);stage(window,3)
    workspace=window._workspaces['segmentation']
    workspace.resizeDocks([workspace.panels['settings'],workspace.panels['image']],[470,1120],QtCore.Qt.Orientation.Horizontal)
    review=window.segmentation_review;review.select_tile(1);review.tabs.setCurrentIndex(2)
    wait_for(lambda:bool(review._objects) and not review.objects_view._loading)
    review.select_ids([18,19])
    def focus():
        review.objects_view._keep_manual_transform()
        review.objects_view.view.fitInView(QtCore.QRectF(385,370,400,220),QtCore.Qt.AspectRatioMode.KeepAspectRatio)
        review.objects_view.view.centerOn(585,480)
        pump(.25)
    focus()
    capture(window,'04_merge_selection_detail.png',role='manual correction detail',state='two exact masks selected; unsaved selection',source_object_ids=[18,19])
    review.merge_button.click();wait_for(lambda:window.process is None)
    wait_for(lambda:len(review._objects)==34 and not review.objects_view._loading)
    focus()
    capture(window,'04_merge_result_detail.png',role='manual correction detail',state='new immutable union object; no synthetic bridge pixels',source_object_ids=[18,19],merged_id=36)
    review.undo_button.click();wait_for(lambda:window.process is None)
    window.close();window.deleteLater();image_pool().waitForDone(10000);APP.processEvents()
    QtCore.QCoreApplication.sendPostedEvents(None,QtCore.QEvent.Type.DeferredDelete)
    for name,frames,box,states in (
        ('manual_merge_demo.gif',['04_merge_selection_detail.png','04_merge_result_detail.png'],[780,245,1905,1018],
         ['two selected masks','manual union as one object; gap pixels unchanged']),
        ('editor_gamma_region_demo.gif',['08_editor_pipette_brush.png','08_editor_local_gamma_detail.png'],[13,13,1533,720],
         ['stored native pixels','unsaved editor gamma2 preview in the selected rectangle']),
    ):
        images=[]
        for source in frames:
            with Image.open(ASSETS/source) as image:
                images.append(image.crop(box).convert('RGB'))
        path=ASSETS/name
        images[0].save(path,save_all=True,append_images=images[1:],duration=[1600,1900],loop=0,disposal=2)
        MANIFEST['assets'].append(dict(path=path.relative_to(PRESENTATION/'presentation_source').as_posix(),
            sha256=sha(path),role='actual UI state comparison animation',source_frames=frames,crop_ltrb=box,
            states=states,frame_count=2,duration_ms=[1600,1900]))
    MANIFEST['capture_script_sha256']=sha(Path(__file__))
    MANIFEST['assets']=list({asset['path']:asset for asset in MANIFEST['assets']}.values())
    assert sha(SOURCE)==MANIFEST['source_sha256'],'Read-only source changed'
    META.write_text(json.dumps(MANIFEST,indent=2,ensure_ascii=False),encoding='utf8')
    print('Added merge detail screenshots and actual UI GIFs',flush=True)


def capture_numeric_table():
    """Capture the actual final Results table without changing scientific input."""
    MANIFEST.update(json.loads(META.read_text(encoding='utf8')))
    project=Project.load(MANIFEST['project_path'])
    qa=Path(project.workspace)
    prefs=QtCore.QSettings(str(qa/'table_preferences.ini'),QtCore.QSettings.Format.IniFormat)
    window=MainWindow(project,language='en',preferences=prefs)
    window.resize(1920,1080);window.show();window.show_log.setChecked(False);stage(window,6)
    window.analytics.tabs.setCurrentIndex(1)
    csv=window.analytics.table
    wait_for(lambda:len(csv.rows)==59 and csv.table.rowCount()==59)
    table=csv.table
    # Presentation view changes only: the genuine table is horizontally scrolled
    # to its measurement fields. Every scientific value and row is unchanged.
    widths={'Area':125,'Aspect_Ratio':215,'Solidity':215,'Euler_Number':130,
            'Endpoints':170,'Branch_Points':140}
    for name,width in widths.items():
        table.setColumnWidth(csv.headers.index(name),width)
    csv.select_object('G3_real_crop_y7000_x7000_2048_tile_0001',18)
    table.setHorizontalScrollMode(QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel)
    table.horizontalScrollBar().setValue(table.horizontalScrollBar().maximum())
    table.verticalScrollBar().setValue(0);pump(.5)
    selected=next(row for row in csv.rows if row.get('Tile_Name')=='G3_real_crop_y7000_x7000_2048_tile_0001' and str(row.get('Object_ID'))=='18')
    visible=[name for i,name in enumerate(csv.headers) if table.columnViewportPosition(i)+table.columnWidth(i)>0 and table.columnViewportPosition(i)<table.viewport().width()]
    capture(window,'07_results_table.png',role='Results page, Feature table tab',
            state='59 actual unclassified objects; numeric columns horizontally scrolled into view',
            visible_columns=visible,selected_object=selected,scientific_values_unchanged=True)
    window.close();window.deleteLater();image_pool().waitForDone(10000);APP.processEvents()
    QtCore.QCoreApplication.sendPostedEvents(None,QtCore.QEvent.Type.DeferredDelete)
    MANIFEST['capture_script_sha256']=sha(Path(__file__))
    MANIFEST['assets']=list({asset['path']:asset for asset in MANIFEST['assets']}.values())
    assert sha(SOURCE)==MANIFEST['source_sha256'],'Read-only source changed'
    META.write_text(json.dumps(MANIFEST,indent=2,ensure_ascii=False),encoding='utf8')
    print('Added numeric Results table screenshot',flush=True)


def capture_presentation_boundaries():
    """Enlarge display marks over exact saved source-scale ownership maps."""
    MANIFEST.update(json.loads(META.read_text(encoding='utf8')))
    project=Project.load(MANIFEST['project_path'])
    dataset=project.datasets[0]
    bases=[('raw',Path(dataset['raw_path'])),('exact',Path(dataset['path']))]
    inputs={}
    geometry=[]
    for kind,base in bases:
        coordinate_path=find_dataset_manifest(base)
        manifest=read_manifest(coordinate_path)
        inputs[str(coordinate_path)]=sha(coordinate_path)
        h,w=manifest['image_shape']
        owners=np.zeros((h,w),np.int32)
        restore_ownership(base,manifest,owners)
        assert (owners>0).all(),'Demonstration requires complete exact pixel ownership'
        first_path=base/manifest['tiles'][0]['native_filename']
        sample=cv2.imread(str(first_path),cv2.IMREAD_UNCHANGED)
        shape=(h,w) if sample.ndim==2 else (h,w,sample.shape[2])
        canvas=np.zeros(shape,dtype=sample.dtype)
        records=[]
        for rec in manifest['tiles']:
            tile_path=base/rec['native_filename'];valid_path=base/rec['valid_mask']
            inputs[str(tile_path)]=sha(tile_path);inputs[str(valid_path)]=sha(valid_path)
            tile=cv2.imread(str(tile_path),cv2.IMREAD_UNCHANGED)
            valid=cv2.imread(str(valid_path),cv2.IMREAD_GRAYSCALE)>0
            x1,y1,x2,y2=[rec[k] for k in ('x1','y1','x2','y2')]
            assert tile is not None and valid.shape==(y2-y1,x2-x1)
            canvas[y1:y2,x1:x2][valid]=tile[:y2-y1,:x2-x1][valid]
            records.append(rec)
        assert canvas.dtype==np.uint8,'This documented demonstration has 8-bit source values'
        original=cv2.cvtColor(canvas,cv2.COLOR_GRAY2BGR) if canvas.ndim==2 else canvas.copy()
        result=original.copy()
        edge=ownership_boundary(owners).astype(np.uint8)
        # The six-pixel band is a presentation annotation. Its underlying
        # one-pixel transitions and all scientific ownership arrays are intact.
        band=cv2.dilate(edge,np.ones((6,6),np.uint8),anchor=(3,3))>0
        display_mask=band.astype(np.uint8)*255
        result[band]=(0,225,255)
        labels=[]
        for rec in records:
            x1,y1,x2,y2=[rec[k] for k in ('x1','y1','x2','y2')]
            local=(owners[y1:y2,x1:x2]==rec['id']).astype(np.uint8)
            distance=cv2.distanceTransform(cv2.copyMakeBorder(local,1,1,1,1,cv2.BORDER_CONSTANT),cv2.DIST_L2,3)[1:-1,1:-1]
            yy,xx=np.unravel_index(np.argmax(distance),distance.shape)
            text='#{:04d}'.format(rec['id']);font=cv2.FONT_HERSHEY_SIMPLEX;scale=2.2
            (tw,th),baseline=cv2.getTextSize(text,font,scale,3)
            at=(x1+int(xx)-tw//2,y1+int(yy)+th//2)
            tx,ty=at
            assert np.all(owners[max(0,ty-th-5):min(h,ty+baseline+5),max(0,tx-5):min(w,tx+tw+5)]==rec['id'])
            cv2.putText(display_mask,text,at,font,scale,255,9,cv2.LINE_AA)
            cv2.putText(result,text,at,font,scale,(0,0,0),9,cv2.LINE_AA)
            cv2.putText(result,text,at,font,scale,(0,255,0),3,cv2.LINE_AA)
            labels.append(dict(tile_id=rec['id'],text=text,baseline_xy=list(at),glyph_height_native_px=th))
        assert np.array_equal(result[display_mask==0],original[display_mask==0]),'Pixels outside display marks changed'
        name='overview_{}_boundaries_presentation.png'.format(kind)
        path=ASSETS/name
        encoded=cv2.imencode('.png',result)[1].tobytes()
        if path.exists():
            assert path.read_bytes()==encoded,'Refusing to overwrite an existing presentation asset'
        else:
            path.write_bytes(encoded)
        MANIFEST['assets'].append(dict(path=path.relative_to(PRESENTATION/'presentation_source').as_posix(),
            sha256=sha(path),size=[w,h],role='presentation overview with enlarged display annotations',
            state=('raw grayscale' if kind=='raw' else 'processed grayscale')+' with exact final ownership geometry; display boundaries and IDs enlarged only',
            scientific_geometry_unchanged=True,source_intensities_unchanged_outside_display_overlay=True,
            ownership_sha256=hashlib.sha256(owners.tobytes()).hexdigest(),
            boundary_rule='src.partition_geometry.ownership_boundary, lower/right pixel of every label transition',
            boundary_display=dict(color_rgb=[255,225,0],dilation_kernel_native_px=[6,6],anchor_xy=[3,3],purpose='display enlargement only'),
            id_display=dict(color_rgb=[0,255,0],font='OpenCV Hershey Simplex',font_scale=2.2,stroke_native_px=3,black_outline_native_px=9,labels=labels),
            coordinate_manifest=str(coordinate_path),native_dataset=str(base)))
        geometry.append(owners)
        print('Rendered',name,flush=True)
    assert np.array_equal(geometry[0],geometry[1]),'Raw and processed ownership must match'
    assert all(sha(Path(path))==value for path,value in inputs.items()),'Scientific input changed'
    MANIFEST['presentation_boundary_inputs_sha256']=inputs
    MANIFEST['capture_script_sha256']=sha(Path(__file__))
    MANIFEST['assets']=list({asset['path']:asset for asset in MANIFEST['assets']}.values())
    assert sha(SOURCE)==MANIFEST['source_sha256'],'Read-only source changed'
    META.write_text(json.dumps(MANIFEST,indent=2,ensure_ascii=False),encoding='utf8')
    print('Added two presentation boundary assets; scientific source values and ownership unchanged',flush=True)


if __name__=='__main__':
    APP=QtWidgets.QApplication([]);configure_font();configure_application_branding(APP);set_language('en')
    APP.setApplicationName('SoLoData')
    MANIFEST=dict(created_for='2026-11-08 presentation quality revision',capture='current Qt widgets, private project',assets=[])
    if '--details-only' in sys.argv:
        capture_merge_details()
    elif '--table-only' in sys.argv:
        capture_numeric_table()
    elif '--boundaries-only' in sys.argv:
        capture_presentation_boundaries()
    else:
        main()
