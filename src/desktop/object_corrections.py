"""Publish immutable mask unions, connected corrections and object deletions."""
import csv
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace

import cv2
import numpy as np

from src.block3_feature_extractor import TopologicalFeatureExtractor
from src.partition_geometry import dataset_path, checked_imwrite
from src.tile_edits import tile_artifact_path
from src.default_settings import MASK_EDITOR_DEFAULTS, MASK_EDITOR_DEFAULTS_VERSION
from .i18n import tr
from .mask_connection import MaskBatchCorrection, MaskCorrection, MaskCrop
from .project import atomic_json, timestamp
from .storage_names import readable_name, version_path


def correction_context(dataset, tile_name, identifiers, rows, *, editable=True, keep_separate=False):
    """Load exact native-grid selection, foreign masks and active ownership."""
    from . import service
    from .object_merging import exact_objects
    from .result_tile import find_result_tile_record, resolve_tile_image
    objects = exact_objects(dataset, tile_name, rows)
    selected = [o for o in objects if int(o['row']['Object_ID']) in identifiers]
    if len(selected) != len(identifiers) or not selected:
        raise ValueError(tr('Select one or more masks from one tile.'))
    record = find_result_tile_record(selected[0]['row'], service.tile_records(dataset))
    path, space = resolve_tile_image(dataset, record)
    if space != 'native' or any(o['entry']['measurement_space'] != 'source_pixels' for o in selected):
        raise ValueError(tr('Exact object masks are unavailable or inconsistent. Recalculate measurements.'))
    shape = tuple(selected[0]['entry']['tile_shape'])
    if editable and shape[0]*shape[1] > MASK_EDITOR_DEFAULTS['max_editor_pixels']:
        raise ValueError(tr('Mask editing is limited to 32 MP native tiles.'))
    image = cv2.imdecode(np.frombuffer(path.read_bytes(), np.uint8), cv2.IMREAD_GRAYSCALE)
    if image is None or image.shape != shape:
        raise ValueError(tr('Mask and tile dimensions do not match.'))
    origin=(0,0)
    pixel_um = None
    if editable:
        try:
            run = json.loads((Path(dataset['results_dir'])/'measurement_run.json').read_text(encoding='utf8'))
            pixel_um = run['settings'].get('pixel_size_um')
        except (OSError, ValueError, KeyError):
            pass
        valid_path = tile_artifact_path(dataset['path'], record, 'valid_mask')
        valid = cv2.imdecode(np.frombuffer(valid_path.read_bytes(), np.uint8), cv2.IMREAD_GRAYSCALE)
        if valid is None or valid.shape != shape: raise ValueError(tr('Mask and tile dimensions do not match.'))
        canvas=shape
        if keep_separate:
            model = MaskBatchCorrection(objects, identifiers, valid > 0, image)
            return dict(model=model, objects=objects, selected=selected, path=path,
                        origin=origin, tile_shape=shape, pixel_um=pixel_um)
    else:
        # Ordinary unions retain their previous oversized-tile support and
        # allocate only the selected bounding crop, not full native canvases.
        boxes=[]
        for obj in selected:
            ys,xs=np.nonzero(obj['mask']);x,y=obj['origin']
            boxes.append((x+int(xs.min()),y+int(ys.min()),x+int(xs.max())+1,y+int(ys.max())+1))
        left,top=min(b[0] for b in boxes),min(b[1] for b in boxes)
        right,bottom=max(b[2] for b in boxes),max(b[3] for b in boxes)
        origin=(left,top);canvas=(bottom-top,right-left);image=image[top:bottom,left:right]
    union, manual = (np.zeros(canvas,bool) for _ in range(2))
    other=np.zeros(canvas,bool) if editable else None
    for obj in objects:
        ys, xs = np.nonzero(obj['mask']); x, y = obj['origin']
        is_selected = int(obj['row']['Object_ID']) in identifiers
        if not editable and not is_selected: continue
        target = union if is_selected else other
        target[ys+y-origin[1], xs+x-origin[0]] = True
        if is_selected and obj['entry'].get('manual_added_mask'):
            my, mx = np.nonzero(obj['manual_added']); manual[my+y-origin[1], mx+x-origin[0]] = True
    model = MaskCorrection(union, valid > 0, other, image) if editable else SimpleNamespace(mask=union,original=union,gray=image)
    return dict(model=model, objects=objects, selected=selected, path=path, manual=manual,
                origin=origin, tile_shape=shape, pixel_um=pixel_um)


def correct_objects(project, dataset_id, tile_name, object_ids, expected_signature, operations,
                    progress=None, cancelled=None, *, keep_separate=False):
    if type(keep_separate) is not bool:
        raise ValueError(tr('Invalid mask stroke.'))
    return change_objects(project,dataset_id,tile_name,object_ids,expected_signature,
                          operations=operations,action='correct_objects',progress=progress,cancelled=cancelled,
                          keep_separate=keep_separate)


def delete_objects(project, dataset_id, tile_name, object_ids, expected_signature, progress=None, cancelled=None):
    return change_objects(project,dataset_id,tile_name,object_ids,expected_signature,
                          action='delete_objects',progress=progress,cancelled=cancelled)


def _replacement(row, pixels, manual, gray, x, y, fields, old_run):
    """Recompute scientific features and format exact, manual and review crops."""
    mask = np.pad(pixels.astype(np.uint8)*255, 2)
    manual = np.pad(manual.astype(np.uint8)*255, 2)
    gray = np.pad(gray, 2)
    gray[mask == 0] = 0
    row = dict(row)
    row.update(TopologicalFeatureExtractor._extract_geometry(mask),
               **TopologicalFeatureExtractor._extract_topology(mask))
    if 'Area_um2' in fields:
        scale = old_run['settings']['pixel_size_um']
        if scale is None or not np.isfinite(scale) or scale <= 0:
            raise ValueError('Invalid measurement calibration')
        row['Area_um2'] = row['Area']*scale*scale
    return dict(row=row, mask=mask, manual=manual, gray=gray, origin=[x-2, y-2])


def change_objects(project, dataset_id, tile_name, object_ids, expected_signature, *, action='merge_objects',
                   operations=None, progress=None, cancelled=None, keep_separate=False):
    from . import service
    from .object_labels import _measurement, _load_document, LABELS_FILENAME, object_key
    from .object_merging import exact_objects
    dataset = project.get_dataset(dataset_id)
    service._check_cancel(cancelled)
    if not service.results_are_current(dataset):
        raise ValueError(tr('Current measurements are required for merging.'))
    if dataset.get('measurement_signature') != expected_signature:
        raise ValueError(tr('Measurements changed. Reload the tile before merging.'))
    minimum = 2 if action == 'merge_objects' else 1
    if (not isinstance(object_ids,list) or len(object_ids) < minimum or
            any(type(i) is not int or i <= 0 for i in object_ids) or len(set(object_ids)) != len(object_ids)):
        raise ValueError(tr('Merge at least two objects from one tile.' if minimum == 2 else 'Select one or more masks from one tile.'))
    output, source, fields, rows, indexed, identity = _measurement(dataset)
    labels = _load_document(output, indexed, identity)
    keys = {object_key(tile_name,i) for i in object_ids}
    if not keys <= indexed.keys(): raise ValueError(tr('Select one or more masks from one tile.'))
    old_run = json.loads((output/'measurement_run.json').read_text(encoding='utf8'))
    deleting = action == 'delete_objects'
    replacements = []
    changed_ids = object_ids
    added_pixels, removed_pixels = 0, 0
    if deleting:
        objects = exact_objects(dataset,tile_name,rows)
        selected = [o for o in objects if int(o['row']['Object_ID']) in object_ids]
        removed_pixels = sum(np.count_nonzero(o['mask']) for o in selected)
    else:
        context = correction_context(dataset,tile_name,object_ids,rows,editable=action == 'correct_objects',
                                     keep_separate=keep_separate)
        model, objects, selected = context['model'],context['objects'],context['selected']
        if action == 'correct_objects':
            if not isinstance(operations,list) or not 1 <= len(operations) <= 500:
                raise ValueError(tr('Invalid mask stroke.'))
            for operation in operations:
                service._check_cancel(cancelled); model.apply(operation)
            validated = model.validate()
        if keep_separate:
            changed_ids = validated
            for obj in selected:
                service._check_cancel(cancelled)
                ident = int(obj['row']['Object_ID'])
                if ident not in changed_ids:
                    continue
                crop = model.crops[ident]
                left, top, right, bottom = crop.box
                original = model.original_crop(ident)
                added = crop.pixels & ~original.raster(crop.box)
                removed = original.pixels & ~crop.raster(original.box)
                manual = MaskCrop(*obj['origin'], obj['manual_added']).raster(crop.box)
                manual = (manual | added) & crop.pixels
                added_pixels += np.count_nonzero(added)
                removed_pixels += np.count_nonzero(removed)
                replacements.append(_replacement(obj['row'], crop.pixels, manual,
                    model.gray[top:bottom, left:right], left, top, fields, old_run))
        else:
            ys, xs = np.nonzero(model.mask)
            left, top, right, bottom = int(xs.min()),int(ys.min()),int(xs.max())+1,int(ys.max())+1
            region = np.s_[top:bottom, left:right]
            added = model.mask & ~model.original
            added_pixels = np.count_nonzero(added)
            removed_pixels = np.count_nonzero(model.original & ~model.mask)
            manual = (context['manual'] | added) & model.mask
            new_id = max(int(o['row']['Object_ID']) for o in objects)+1
            merged = dict(selected[0]['row'],Object_ID=str(new_id))
            if len({o['row']['Class_ID'] for o in selected}) != 1:
                merged.update(Class_ID='-1',Class_Name='Unknown')
            replacements.append(_replacement(merged, model.mask[region], manual[region], model.gray[region],
                left+context['origin'][0], top+context['origin'][1], fields, old_run))
    keys = {object_key(tile_name, i) for i in changed_ids}
    if keep_separate:
        edited_rows = {object_key(tile_name, replacement['row']['Object_ID']): replacement['row']
                       for replacement in replacements}
        new_rows = [edited_rows.get(object_key(r['Tile_Name'], r['Object_ID']), r) for r in rows]
    else:
        new_rows = [r for r in rows if object_key(r['Tile_Name'],r['Object_ID']) not in keys]
        new_rows.extend(replacement['row'] for replacement in replacements)
    target = version_path(Path(project.workspace)/'measurements'/readable_name(dataset['name']),'Measurement')
    target.parent.mkdir(parents=True,exist_ok=True)
    parent = {k:deepcopy(dataset.get(k)) for k in ('results_dir','last_csv','measurement_signature','objects','measured_at')}
    operation = dict(method='separate_mask_edits' if keep_separate else
        {'merge_objects':'pixelwise_union','correct_objects':'manual_mask','delete_objects':'delete_masks'}[action],
        tile_name=tile_name,object_ids=sorted(object_ids),time=timestamp(),source_csv_sha256=identity['csv_sha256'],
        input_masks=[dict(object_id=int(o['row']['Object_ID']),sha256=o['mask_sha256']) for o in selected],
        added_pixels=int(added_pixels), removed_pixels=int(removed_pixels))
    if keep_separate:
        operation['changed_object_ids'] = changed_ids
    elif not deleting:
        operation['object_id'] = new_id
    if action == 'correct_objects':
        operation.update(strokes=deepcopy(operations),editor_defaults_version=MASK_EDITOR_DEFAULTS_VERSION,
                         editor_defaults=dict(MASK_EDITOR_DEFAULTS))
    with tempfile.TemporaryDirectory(prefix='.merge_',dir=target.parent) as temporary:
        staged = Path(temporary)/'measurement'; staged.mkdir()
        def copy_checked(src,dst):
            service._check_cancel(cancelled); return shutil.copy2(src,dst)
        shutil.copytree(output/'verification_masks',staged/'verification_masks',copy_function=copy_checked)
        verification = staged/'verification_masks'
        manifest = json.loads((verification/'object_locations.json').read_text(encoding='utf8'))
        manifest['objects'] = [e for e in manifest['objects'] if not(e['tile_name'] == tile_name and e['object_id'] in changed_ids)]
        for obj in selected:
            if int(obj['row']['Object_ID']) not in changed_ids:
                continue
            dataset_path(verification,obj['entry']['mask']).unlink()
            if obj['entry'].get('manual_added_mask'): dataset_path(verification,obj['entry']['manual_added_mask']).unlink()
            for file in dataset_path(verification,tile_name).glob(f"obj_{int(obj['row']['Object_ID']):03d}_*.png"): file.unlink()
        for replacement in replacements:
            service._check_cancel(cancelled)
            row = replacement['row']
            ident = int(row['Object_ID'])
            mask_path = Path('object_locations')/tile_name/f'obj_{ident:03d}.png'
            (verification/mask_path).parent.mkdir(parents=True,exist_ok=True)
            checked_imwrite(verification/mask_path,replacement['mask'])
            entry = dict(tile_name=tile_name,object_id=ident,origin_xy=replacement['origin'],tile_shape=list(context['tile_shape']),
                         mask=mask_path.as_posix(),measurement_space='source_pixels')
            if replacement['manual'].any():
                manual_path = mask_path.with_name(f'obj_{ident:03d}_manual.png')
                checked_imwrite(verification/manual_path,replacement['manual']); entry['manual_added_mask'] = manual_path.as_posix()
            manifest['objects'].append(entry)
            review_dir = dataset_path(verification,tile_name); review_dir.mkdir(exist_ok=True)
            mode = old_run.get('settings',{}).get('mask_save_mode','gray_3filter')
            checked_imwrite(review_dir/f"obj_{ident:03d}_{row['Class_Name']}.png",
                            replacement['gray'] if mode == 'gray_3filter' else replacement['mask'])
        atomic_json(verification/'object_locations.json',manifest)
        with (staged/source.name).open('w',encoding='utf8',newline='') as handle:
            writer=csv.DictWriter(handle,fieldnames=fields); writer.writeheader(); writer.writerows(new_rows)
        run = deepcopy(old_run)
        run.update(time=timestamp(),operation=action,parent_measurement=parent,merge=operation)
        if action == 'correct_objects':
            run['contains_manual_mask_edits'] = True
            run['mask_corrections'] = run.get('mask_corrections',[])+[operation]
        summary = dict(status='completed',objects=len(new_rows),csv_path=str(target/source.name),tile_name=tile_name,
                       mask_operation=action,deleted_count=len(selected) if deleting else 0)
        if keep_separate:
            summary['changed_object_ids'] = changed_ids
        elif not deleting:
            summary['object_id'] = new_id
        run['summary'] = summary
        from .provenance import runtime_provenance
        run['runtime'] = runtime_provenance(); signature = service.fingerprint(run)
        atomic_json(staged/'measurement_run.json',run)
        atomic_json(staged/'object_merges.json',dict(schema_version=1,parent_measurement=parent,operation=operation,
                                                   source_rows=[o['row'] for o in selected]))
        labels.update(measurement_signature=signature,measurement_reference=dataset_id+':'+signature,
                      csv_sha256=hashlib.sha256((staged/source.name).read_bytes()).hexdigest(),
                      labels={k:v for k,v in labels['labels'].items() if k not in keys},object_count=len(new_rows),updated_at=timestamp())
        labels['assigned_count'] = len(labels['labels']); atomic_json(staged/LABELS_FILENAME,labels)
        service._check_cancel(cancelled)
        if not service.results_are_current(dataset) or dataset.get('measurement_signature') != expected_signature:
            raise ValueError(tr('Measurements changed. Reload the tile before merging.'))
        os.replace(staged,target)
    prior = deepcopy(dataset)
    try:
        dataset.update(results_dir=str(target),last_csv=str(target/source.name),measurement_signature=signature,
                       objects=len(new_rows),measured_at=run['time'],results_current=True,status='completed')
        project.add_history(action,dataset_id=dataset_id,merge=operation)
    except Exception:
        dataset.clear(); dataset.update(prior); raise
    return summary
