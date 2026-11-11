# SoLoData

Previously named FiBreath. Existing projects and panel layouts remain compatible. The repository keeps its existing name, Fibers-Segmentation.

[SoLoData release notes](docs/SOLODATA_RELEASE_2026-11-11_RU.md).

A local Windows application for microscopy TIFF processing, tile review, YOLO segmentation import, feature extraction, and manual object classification for Random Forest datasets. [Additional guide](README_RU.md).

## Start

Double-click **launch_app.cmd**. The launcher checks the configured interpreter, the project environment and PATH. Qt uses PyQt6 or PySide6. Processing works offline. The app reopens the last successfully selected project. If that project cannot be opened, the default project opens with an explanation. An explicit `--project` takes precedence.

Alternatively, from the project directory:

```powershell
& ".venv\Scripts\python.exe" -B app.py
```

On another computer, install Python 3.10+ and create a local environment:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe app.py
```

This release includes source code and a Windows launcher. An independent bundled EXE is not included.

## Workflow

1. Create or open a project. Add TIFF images and check the sources to process.
2. In **Preparation**, select the TIFF, channel, slice/frame, filters and tile size. Calibration defaults to supported TIFF metadata per source, with a manual option. Hover over **?**, click it or press **F1** for help. Preview the whole image before preparing the checked TIFF batch.
3. Select a prepared **Dataset**. In **Tiles**, inspect the overview, model/native crops, ownership masks, and polygons. Exclude or restore tiles by ID, then mark the review complete.

Completely black tiles are excluded automatically during preparation/import and when **Tiles** first checks an existing private dataset. Only exact zeros in valid native pixels count as black: even a single value of 1 remains active, including 16-bit data. Padding and reduced model previews do not decide exclusion. The list explains automatic exclusions, and maps keep the tile ID with an orange **EXCLUDED** label. **Restore** manually includes a selected tile and remembers that choice for the same input version. **Check black tiles** repeats the check. Source images, masks, annotations and excluded model PNGs are retained. Measurements require recalculation after the active tile set changes; historical measurement files remain intact.

4. In **Segmentation**, import YOLO polygons and click **Measure using selected mode**, or use **Measure with automatic fallback** for tiles with missing TXT. An empty TXT means zero objects. After calculation, inspect the selected tile in **Native**, **Model**, **Objects** or **YOLO polygons**. In Objects, click parts or check their IDs and choose **Merge selected parts** to correct a split.
5. In **Object labeling → Object gallery**, inspect each saved crop and assign its type with one of six buttons or keys 1–6. The type saves immediately and the next object opens. **Open object's tile** highlights its measured mask. **Export training CSV** exports reviewed targets.
6. **Model training** evaluates the reviewed labels.
7. The final **Results** page contains **Charts**, the **Feature table**, and CSV, Excel and ML exports. **Export visible rows** uses this page’s own table filters.

**Results** also offers an Excel copy of the full measurement table, an ML ZIP with aligned predictor, target and metadata CSVs for manually typed objects, and feature statistics for the current dataset. The Charts tab includes histograms, scatter and box plots, sample covariance and Pearson correlation.

In **Results → Charts**, drag inside the plot to pan and use the wheel to zoom. Drag the divider to change the chart height or collapse **Chart settings**. **Chart colors** controls the data, background and matrix palette. The separate chart window can be moved and resized.

**Dataset** selects an existing prepared tile dataset in the current project. It is empty until preparation finishes or existing tiles are opened. **Open tiles… / Open prepared tiles** opens one dataset folder previously created by this pipeline, containing model PNGs plus `native`, `valid_masks`, and `overview/*_tiles_coords.json` (v3). Select the individual folder, for example `data/2_sliced_tiles_1500/FL01_G3_RGB_Red`, rather than its parent. This skips TIFF filtering and slicing.

New project asks for a folder name and parent directory, then creates `<parent>/<name>/project.json`. Each project keeps its own `sources`, `previews`, `runs` (tiles, raw crops and animations), imported `datasets`, `annotations`, `measurements` (including object crops) and `jobs`. Add TIFF copies exact source bytes in a cancellable background job; allow enough disk space for large files. The default project is empty at `data/projects/default/project.json`; startup does not import TIFFs. New preparation settings create another run. Opening prepared tiles copies that dataset into the project; exclusion/restoration changes only the private copy and keeps native crops and metadata.

Folder examples: `sources/FL01_G3_RGB_Red.tif`, `runs/Preparation_001/tiles/FL01_G3_RGB_Red`, `previews/FL01_G3_RGB_Red/Preview_001`, `annotations/FL01_G3_RGB_Red/Labels_001`, and `measurements/FL01_G3_RGB_Red/Measurement_001`. UUIDs are internal JSON identities. Legacy managed directories are renamed with an exact project backup and rollback journal in `backups/Storage_layout_001`; measurements and manual labels retain their identities and bytes. Required v3 `native`, `valid_masks` and `overview` folders are preserved. Temporary staging folders are removed after an operation.

**TIFF slice/frame** is the zero-based Z-depth, time T or image I index, separate from channel. Index 3 selects the fourth slice. A plain 2D or RGB TIFF has one plane, so 0 is read-only. No stack projection or merging is performed.

**From TIFF metadata** displays the selected source calibration read-only and resolves each processing source separately. It accepts positive, finite and equal X/Y sizes (relative tolerance 1e-6) from OME PhysicalSizeX/Y or ImageJ units plus reciprocal X/YResolution. OME's default physical unit is µm; 400 nm/px converts to 0.4 µm/px. Print DPI, objective magnification, unsupported units and unequal X/Y pixels are not used automatically. **Manual / source pixels** applies one entered value to the whole batch; 0 keeps pixel units. Each run/measurement records its resolved calibration and origin; older results and the immutable factory catalog are unchanged. See the [OME schema](https://www.openmicroscopy.org/Schemas/Documentation/Generated/OME-2015-01/ome_xsd.html) and [tifffile metadata documentation](https://www.cgohlke.com/docs/tifffile/).

## Help and safe settings

### Project database and backups

**Help → Project database…** checks the local SQLite metadata catalog and browses saved datasets/history in pages of 100 rows. **Refresh catalog** creates or updates it; **Rebuild catalog** preserves an old damaged catalog under `backups/Database_catalog_001` before replacing the index. Maintenance is disabled during processing.

`project.json` remains authoritative. Saving a project also updates its derived `project.sqlite3` catalog in a transaction; a catalog failure does not cancel the JSON save. Read-only opening of an older project creates no database. SQL queries verify the JSON SHA-256 and refuse stale catalog data. TIFFs, tiles, scientific CSVs, masks, manual labels and models remain in their existing files. Catalog freshness does not establish measurement freshness or image availability.

**Back up project metadata…** creates matching JSON/SQLite snapshots with a `METADATA_ONLY.txt` notice. For a complete backup, stop processing, close SoLoData and copy the **entire project folder** to another disk. Older absolute scientific paths may need relocation before a copied project can be used elsewhere. Work on a local disk; sharing a live SQLite file through a network drive or cloud synchronization is not supported collaboration.

Developer diagnostics: `python tools/project_database.py --project <project.json> status`; `sync`, `rebuild`, `list datasets --status ready`, `list history --action assign_object_class`, and `backup <new-directory>` are also available. Maintenance commands use the desktop project lock. [Database research and implementation report](docs/DATABASE_RESEARCH_2026-11-11_RU.md).

**Help** opens a searchable application guide and the pipeline parameter reference. **F1** opens help for the focused parameter or current page. Use the clickable **?** badges or a field’s **Explain this parameter** context action for the same article.

The start page walks through a first run with one TIFF. Each workflow chapter starts with practical instructions and links to related guides and parameters. Search accepts several words, for example `empty TXT` or `Excel ML`.

The reference shows a comparison table above the detailed guide. Select a row to read the article below, or browse the linked index grouped by processing stage. Each article shows where to find the setting and gives a practical check alongside units, validation rules and related controls. Factory defaults come from the immutable version 3 catalog. Help displays a snapshot of the form, including unsaved edits.

Use **Help → Restore saved settings** to return the form to the last successfully saved project settings. **Restore factory defaults** restores the full baseline for future processing; a field's right-click **Use factory default** restores just that parameter. These controls update settings rather than completed runs or annotations.

**Settings…** in the top bar collects all processing options and the starting values for both editors. Search by name or key, compare with factory values and save the project draft. A separate checkbox remembers processing settings for new projects. The editor tabs apply their values when an editor opens.

Invalid edits are highlighted in red and explained with the allowed range and factory value. They cannot be saved or used to start processing; closing the window keeps the valid saved settings. If an older project already contains invalid settings, startup first backs up its exact original bytes in a unique `.recovery` subfolder, then repairs only the invalid fields. Valid choices and project data are preserved, and changes are recorded in history; unsupported settings are retained in the backup and recorded when removed.

## Filters and workspace

The **Ruler** measures a straight segment or a polyline. In polyline mode, click to add vertices and double-click or press **Enter** to finish. Right-click a segment to change its color. The ruler and contour menus set color and line width (1–12 screen pixels). Shift aligns a segment and Esc clears the measurement. Length is shown in source pixels when the transform is known and in micrometres when calibrated. Use Native for precise endpoints.

In **Preparation → Choose filters**, enable or disable each step and edit its parameters:

| Step | Setting | Default parameters |
|---|---|---|
| Bilateral denoising | `enable_bilateral` | Diameter 9; intensity sigma 45; spatial sigma 15 |
| White top-hat | `enable_tophat` | Radius 85; 171 × 171 elliptical kernel, followed by min–max normalization |
| Gamma correction | `enable_gamma` | Gamma 1.2; exponent `1/gamma` |
| Morphological closing | `enable_closing` | 17 × 17 elliptical kernel; protective mask only |
| Protective dilation | `enable_dilation` | 5 × 5 elliptical kernel; protective mask only |

All five steps are enabled by default, including when opening an older project without these switches. Turning a step off retains its parameter values. Closing and dilation affect the protective routing mask, rather than the filtered grayscale image or a physical diameter mask. Protective Otsu thresholding still runs on the current grayscale when filters are disabled. Existing prepared tiles retain their saved processing settings; changing these controls applies to preview and new preparation jobs.

Drag panel headers to rearrange the workspace. Double-click a header to detach its panel or dock it again. **Panels** shows or hides panels; **Reset panel layout** restores the default arrangement. Layouts are saved between sessions.

Image panels, separate windows and full screen use the same icon toolbar. Buttons grow as the view widens and wrap in narrow panes. Drag to pan and use the wheel or zoom icons to change magnification. Use the enlarge icon or double-click to open an image window and **F11** for full screen. In **Contour**, the next edge follows the pointer. Click or drag vertices to measure a path, rectangle, ellipse or a copy of an outline. A simple closed shape reports perimeter, area and the diameter of a circle with that area. Imported YOLO outlines have their own color and width controls. Object crops use the calibration saved with their measurement version.

In **Preparation** or **Segmentation**, select **Compare side by side → Open comparison window**. The two-image icon in any viewer also opens **Compare with file…**. Equal-sized images can be overlaid, with the second image at 0–100% opacity. The views align at the pixel origin. Use matching acquisition coordinates and orientation when comparing channels.

The slider icon opens **Brightness and contrast**, with direct black/white levels and reset. These are display adjustments. The save icon exports a separate TIFF, PNG or JPEG. **Save displayed image** includes the current display and visible overlays at the decoded resolution. **Export saved file** uses the full saved file, copies its bytes in the same format, and uses the first frame on format conversion. TIFF and PNG can preserve 16-bit grayscale values from saved files. JPEG is lossy and 8-bit.

Numeric fields have visible **+** and **−** buttons using their established steps and limits; morphology kernels still step by 2. The wheel never changes numeric parameters, dropdown selections, sliders or dials, even when focused; it scrolls the surrounding form. Scrolling inside an open dropdown still works; the image wheel continues to zoom. **Fit to window** hides scrollbars; zoom shows them only where the image exceeds the viewport. Dragging then pans the image without artificial blank margins.

Resize panels using the separators between them. In Tiles, drag the horizontal divider above tile details/actions down to give the image more height, or up to show more controls. Its position is saved. Return a detached panel by dragging its title into the workspace and releasing at the highlighted location; it can dock beside another panel or in tabs. The title buttons detach/return, maximize/restore a floating window, and close. Double-clicking the title also returns the panel. Separate original-image windows support maximize/restore. **Reset panel layout** remains available as a recovery action.

**1:1** opens the saved image at original resolution in a separate window, with an Actual pixels mode. The Preparation tabs open a native-pixel region viewer. In Tiles, Overview requests a detailed boundary map. Direct original-file windows above 32 MP use the Windows image viewer to limit application memory.

In **Object labeling**, select an object and choose **Open object's tile**. Its exact measured mask, ID and frame are highlighted in gold. **Highlight object** toggles the overlay. Native pixels are preferred; a labelled model fallback uses the matching coordinate scale. New measurements save exact masks and coordinates in `verification_masks/object_locations.json`, separately from predictors. Old grayscale crops require a unique exact foreground-intensity match; ambiguous matches request recalculation. The overlay does not change pixels or features.

The application has a SoLoData window/taskbar icon. Create its Windows launcher shortcut with `powershell -NoProfile -ExecutionPolicy Bypass -File tools/create_shortcut.ps1`; the generated `SoLoData.lnk` sits beside `launch_app.cmd`. Recreate the shortcut after moving the application directory. The editable icon is `src/desktop/assets/solodata.svg`; `tools/build_icon.py` rebuilds PNG/ICO assets.

## Straight-corridor search and tile editing

**Drawing cursor** in both the tile and mask editors offers Crosshair, Dot, Arrow and Precision target. The pointer changes independently of brush or eraser size. In the tile editor, **Compare with original…** opens the original alongside a snapshot of applied edits, including unsaved edits.

In **Preparation → Straight corridor search**, set **Initial search window end** to the exclusive right/bottom edge in source pixels. For a 1500 px tile, **Automatic** gives `[1125, 1462)`. Enter 1400 for `[1125, 1400)` and up to 100 px of right/down travel. The start is 75% of the model side rounded down. At 1500 px, the manual end accepts 1126–1500 px and the left/up shift limit is 750 px.

The two sliders or pixel fields set how far to move that first window. At 1500 px, each full trial step is 22 px. A manual limit of 30 px adds trials at 22 and 30 px if needed. Factory shift settings are **Automatic** left/up and 0 right/down. If the straight search fails, Dijkstra uses the configured first window. The settings apply to new preparation runs.

In **Tiles**, open **Model** or **Native** with **1:1**, then choose **Edit tile**. The original-resolution viewer from **Object labeling → Open object’s tile** also offers editing.

**Brush (B) → Pick intensity** samples the current native value from a valid pixel. Drag to paint that intensity or enter it manually. The brush radius is 0–150 source pixels (factory 3). Radius 0 makes a one-pixel line. The pipette preserves 8/16-bit values, and painting stays inside the valid region. Ctrl+Z restores a stroke. Saved edits record manually synthesized signal, including its sample, intensity and path. Later versions retain that flag. Recalculate and review the changed measurement mask before assigning classes or training.

- **Cut by line** extends a straight line to the tile edges. Click the side to remove or choose **Smaller side** by valid pixel count. Check the highlighted side and click **Apply** to fill it with zero padding. The straight and freehand erasers remove only the stroke footprint.
- **Local background** uses white top-hat inside a rectangle. In **Brightness (gamma)**, choose **Draw rectangle** to select any region directly, **Last background region** to reuse the filter rectangle, or **Whole tile**. Preview the correction and click **Apply**. Gamma 1.00 is neutral and higher values brighten dark and midrange tones. The eraser starts at radius 60 px from the immutable editor defaults catalog.

Use **Undo** and **Show original** before saving. **Save tile** publishes an active edited version with matching native/model images, validity and an edit record. Tile images shows that version. Recalculate measurements after editing, review the new object identities and assign types before exporting or training. Random Forest uses the numerical features of those reviewed objects. Saved older measurements and model reports retain their recorded input versions.

**Use saved edit…** activates a previously exported `edit.json` after source/scale checks. A native export or a model export at one source pixel per model pixel is supported. Redo edits from older reduced-model exports on native pixels. **Restore prepared tile** selects the prepared image again. Rebuild a cached overview when its warning says it predates active edits. The 1:1 editing window opens native source pixels even when launched from Model.

The cleanup threshold is an absolute brightness floor on the 8-bit processing image. The local Otsu factor multiplies the Otsu cutoff computed inside each candidate contour. For local Otsu T > 10, the final cutoff is `max(floor, int(T × factor))`. Pixels strictly above it enter the measurement mask. At fixed T=80, floor 25 and factor 0.70 give 56, while factor 0.45 gives 36. A weak middle at brightness 40 and background at 38 both survive the lower cutoff. Inspect the same native region and verification masks after changing these controls or applying local gamma.

## Manual classes and training export

**Segmentation → Objects → Merge selected parts** takes the pixelwise union of two or more exact masks from one active tile. It recalculates all six predictors and calibrated area in a new immutable Measurement version. Gaps retain their existing pixels; tile intensities and YOLO files stay intact. Overlaps count once. Disconnected pieces can be one reviewed object, so topology and shape features reflect the remaining gaps. Unchanged object types carry forward; the new merged object starts unclassified. **Undo last merge** reactivates the complete parent measurement and its labels while retaining the merged version on disk. Old results without exact binary locations and stale results require recalculation. A full measurement run creates fresh segmentation without these merge decisions.

The **Object gallery** displays real verification crops saved during feature extraction. Select a card to inspect the larger image and choose its type with one of the six class buttons or keys **1–6**; both actions save and advance. **←/→** move between visible objects, and **U** finds the next unclassified object. Gallery filters select a tile, search objects/classes, or show only unclassified objects; the feature table has separate search and class filters.

Under **More class controls**, the class selector and **Save class / Save and next** remain available. Choosing **Unclassified** and saving removes a previous target. Keyboard shortcuts **1–6** correspond to the class IDs **0–5** below; stored IDs remain zero-based.

| Stable ID | CSV target key | Class |
|---|---|---|
| 0 | particle | Particle |
| 1 | fiber | Fiber |
| 2 | self_crossed_tube | Self-crossed tube |
| 3 | crossed_tubes | Crossed tubes |
| 4 | agglomeration | Agglomeration |
| 5 | adhered_objects | Adhered objects |

Manual targets are saved in `manual_object_labels.sqlite3` beside the selected measurement version. Each assignment updates one target and its audit event in one transaction, without rewriting the feature CSV or project JSON. Old `manual_object_labels.json` files are validated and imported on first save; their original bytes are preserved. Targets remain bound to the dataset, measurement, tile, object and CSV digest. A new extraction starts without previous targets; mask corrections retain targets only for unchanged objects, and undo restores the parent version.

**More class controls → Export label snapshot (JSON)…** writes the latest targets for compatible older readers on a separate project copy. Keep the target database, `manual_object_labels_storage.json` and original JSON in full project backups. A missing/damaged target database must be restored from backup; the old JSON is not silently reused. The separate `project.sqlite3` catalog remains rebuildable metadata.

**Export training CSV** exports assigned objects by default, with numeric scientific features, `Manual_Class_ID`, `Manual_Class`, `Reviewed`, and source/measurement references. CSV target keys and IDs remain stable.

The numerical predictors are `Area`, `Aspect_Ratio`, `Solidity`, `Euler_Number`, `Endpoints`, and `Branch_Points`. `Area_um2` is included when calibrated. `Manual_Class_ID` is the training target. Original YOLO `Class_ID`/`Class_Name`, source identifiers, and measurement references remain in the CSV as metadata and are excluded from the predictor list.

**Model training** uses reviewed objects from project datasets or a reviewed `.xlsx` or `.csv` training table. Select the object classes and set the forest tree count. Preview the 80/20 split and check class counts. Whole TIFFs or experiments stay together in the default evaluation. Stratified objects provides a same-source check, including on a single TIFF. Optional K-fold tuning compares Gini and entropy within the training partition. Data charts show class counts, predictor distributions, Pearson correlation and impurity curves. With a holdout, compare the baseline, tree and forest using macro-F1, class recall and the confusion matrix. Completed reports retain the data snapshot and predictions in `model_evaluations`. **Save selected model** exports a fitted object classifier as a `.joblib` file.

**Split gallery** shows the saved objects in training, the held-out test and each validation fold. Open **Review new objects…** to run a saved tree or forest on unclassified measured objects from selected tiles. The project keeps the prediction snapshot and review decisions under `object_predictions`, separate from manual training labels.

The class catalog is shared with YOLO. IDs 0–4 retain the original numbering: `Sphere` means particle and `Curve` means fiber. Adhered objects is the additional class 5. `Class_Catalog_Version=2` records this mapping. Earlier manual labels are interpreted using their saved class key and migrated to these IDs on the next save; read-only viewing and export preserve the old label file.

## Measurements and execution

**Segmentation → Pixel segmentation…** trains a separate pixel forest from reviewed exact masks. Choose the datasets, foreground classes and number of trees. Particle and fiber start selected. The model uses candidate background away from measured masks and produces a class PNG and color overlay for an active native tile. Models and predictions are stored in `pixel_segmentation` under the project. The output is a semantic map with no independent test score.

Large complete objects may be reduced to fit a model tile. v3 measurements use the native crop at source scale. `Area` is measured in source pixels; calibrated `Area_um2 = Area × (µm/px)²`. `Aspect_Ratio` is major/minor mask axis and is dimensionless. It is not curved fiber skeleton length divided by thickness. `Endpoints` counts skeleton endpoints; `Branch_Points` retains the definition of branching pixels.

In **Preparation**, inspect the tabs in order. **Source channel** shows the selected TIFF channel and plane. **Filtering** shows the grayscale result of the enabled filters. **Protective mask** marks white regions to protect during tiling. Full-image filtering, top-hat normalization and Otsu run on the entire plane. The quick display PNGs have a 2400-pixel limit. **View at source resolution** or **1:1** opens the main view at one source pixel per physical display pixel. Pan and zoom through the TIFF as the visible pixels load, or click the reduced navigation map to jump. The first full-resolution request for Filtering or Protective mask may run the filters again and store two full-size TIFFs. Completed matching previews are reused.

**Combine TIFF channels…** uses one plane of the selected TIFF. Enable channels and set their display colors, brightness gains (0–1600%) and opacities (0–100%). The tool adds the colored contributions and clips each RGB component. The preview is sampled for responsiveness. **Save full-resolution composite…** exports RGB8 at the source width and height. TIFF can retain supported physical pixel sizes. PNG and JPEG are available for images up to 32 MP.

In **Tiles**, use **Overview** to find the crop, **Model** to check the fixed-size model canvas, **Native** to inspect source-scale pixels, **Ownership** to check valid pixels and **Polygons** to see imported YOLO outlines. **1:1** in Overview requests the detailed boundary map. The individual tile tabs decode the saved grid directly up to 32 MP. Click **Edit selected tile…** above the image to open the editor and find **Drawing cursor** below the tool selector.

**Settings → Appearance** controls the starting cursor in both editors and the interface scale. Automatic grows text and controls with the main window. Fixed scales range from 100% to 200%, in addition to Windows scaling. The brightness and contrast tool shifts and stretches a clipped linear display interval. Gamma is nonlinear, while bilateral and white top-hat use neighboring pixels. Display levels apply to the view and displayed-image export.

Long operations run in a separate process. **Stop** requests cancellation at a safe checkpoint; the current indivisible filter operation can take time to finish. Incomplete outputs are not presented as complete measurements. Project settings, stages, annotation versions, and current results survive reopening. A second window cannot mutate the same project. Changed annotations or active tiles block export of stale results. Zero detected objects produce a new CSV with headers.

## Connected masks and noise removal

In **04 Segmentation → Objects**, select masks and open **Connect ends / Edit mask**. The editor zooms to the selection. Suggested endpoint pairs use distance and outward direction; choose another pair in the lists or with **Pick ends A / B**. **Follow image signal** finds a minimum-cost path in the cyan search rectangle; **Straight connection** draws directly. Inspect the pink preview, then **Add previewed connection**. Changing ends, method, width or search margin requires another preview. Only the bridge is thickened.

Use **Brush (B)** and **Eraser (E)** for freehand corrections. **Pan (H)**, wheel zoom, **Zoom to selection**, **Show original mask**, and **Ctrl+Z / Undo mask stroke** support inspection. Widths are odd **1–101 native px**, search margin **4–256 px**. The mask-editor factory catalog v1 sets connection width **3**, brush width **7**, and margin **48**. Routing is limited to **1,000,000 ROI pixels**, the editor to **32 MP**. Additions cannot leave active ownership or touch an unselected mask, even diagonally.

**Select all masks (Ctrl+A)** checks all objects on the current tile. **Edit masks separately** keeps each object ID and lets an eraser stroke affect all checked masks. In **Brush target**, choose one ID for a freehand continuation or **Across touched masks** to stamp the brush where its center passes over each checked mask. Additions must avoid other masks and padding. A save creates one measurement version and requires every edited mask to remain nonempty and 8-connected. Recheck the manual classes of changed objects.

**Save connected mask** requires one nonempty 8-connected component. It publishes a new Measurement version, recalculates all six predictors and calibrated area, and requires review of the new object’s manual class. Otsu does not split the accepted mask again in that version. Paths, widths, input hashes and manual additions are recorded; additions remain pink in Objects after reopening and later unions. Native/model intensities and YOLO files stay unchanged. Grayscale crops preserve actual intensities, so a binary bridge can look dark there. The bridge is a manual reconstruction, not observed biological evidence.

**Delete selected masks** removes selected noise objects from the current CSV, masks, crops, labels, charts and training export. **Undo last mask change** restores the complete parent, even after deleting every object. Other IDs and labels remain intact. Original versions stay on disk. A full new measurement starts segmentation afresh: removed noise can return and manual bridges are not blindly transferred to changed inputs. Ordinary **Merge selected parts** still groups exact masks with their gaps. **? / F1** explains controls, factory values, limits and recovery.

## Verification

```powershell
$env:QT_QPA_PLATFORM='offscreen'
& ".venv\Scripts\python.exe" -B -m unittest discover -s test -p 'test_*.py' -v
& .\launch_app.ps1 -SmokeTest
```

The complete application guide, parameter reference, settings recovery and keyboard shortcuts are available offline through **Help / F1**. See the [SoLoData release notes](docs/SOLODATA_RELEASE_2026-11-11_RU.md) for the current publication. Scientific images, derived examples, local audit reports and verification artifacts remain local and are excluded from this public repository.
