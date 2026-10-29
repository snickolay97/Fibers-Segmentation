# SoLoData

Previously named FiBreath. Existing projects, language preferences and panel layouts remain compatible. The repository keeps its existing name, Fibers-Segmentation.

[SoLoData release notes](docs/SOLODATA_RELEASE_2026-10-29_RU.md).

A local Windows application for microscopy TIFF processing, tile review, YOLO segmentation import, feature extraction, and manual object classification for Random Forest datasets. English is the default interface language; Russian and Hebrew are available from the language selector. [Русская инструкция](README_RU.md).

## Start

Double-click **launch_app.cmd**. On this computer, the launcher finds the installed scientific Python environment `bm-336546`. Qt uses PyQt6 or PySide6. Processing works offline.

Alternatively, from the project directory:

```powershell
& "$env:USERPROFILE\anaconda3\envs\bm-336546\python.exe" -B app.py
```

On another computer, install Python 3.10+ and create a local environment:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe app.py
```

This release includes source code and a Windows launcher. An independent bundled EXE is not included.

To choose Hebrew for one launch, append `--language he`, for example:

```powershell
& "$env:USERPROFILE\anaconda3\envs\bm-336546\python.exe" -B app.py --language he
```

The selector also supports English (`en`) and Russian (`ru`). Hebrew uses a right-to-left workspace; numeric controls, image coordinates, file identifiers and technical tables keep left-to-right reading. Language changes preserve scientific parameter keys, class IDs and CSV columns.

## Workflow

1. Create or open a project. Add TIFF images and check the sources to process.
2. In **Preparation**, choose channel, stack plane, filters, tile size, and optional µm/px calibration. Hover over **?** for a short explanation; click it or press **F1** for detailed help. Preview a small crop, then prepare the selected TIFFs.
3. Select a prepared **Dataset**. In **Tiles**, inspect the overview, model/native crops, ownership masks, and polygons. Exclude or restore tiles by ID, then mark the review complete.
4. In **Segmentation**, import YOLO polygons or use **Detect objects and assign types**. This button uses existing annotation files and automatically detects objects only where a TXT is missing. An empty TXT still means no annotated objects. The calculation opens **Results** when complete.
5. In **Results → Object gallery**, select a saved object crop and assign its type with one of six buttons. The class saves immediately and the next object opens. Use the **Feature table** to inspect or export scientific values, and **Export training CSV** for reviewed targets.

**Dataset** selects an existing prepared tile dataset in the current project. It is empty until preparation finishes or existing tiles are opened. **Open tiles… / Open prepared tiles** opens one dataset folder previously created by this pipeline, containing model PNGs plus `native`, `valid_masks`, and `overview/*_tiles_coords.json` (v3). Select the individual folder, for example `data/2_sliced_tiles_1500/FL01_G3_RGB_Red`, rather than its parent. This skips TIFF filtering and slicing.

Prepared runs, annotation versions, measurements, and logs are saved in the project's workspace. New preparation settings create a separate run. The default project is `data/ui_projects/default/project.json`; startup adds headers of local TIFFs without starting processing. Opening prepared tiles reads them; explicitly excluding/restoring a tile moves its model PNG while retaining native crops and metadata.

## Help and safe settings

**Help** opens a searchable guide covering 12 application topics and a reference for all 28 pipeline settings. **F1** opens help for the focused parameter or current page; clickable **?** badges and a field's right-click **Explain this parameter** action provide the same context. Hover explanations remain available.

The reference shows **Factory default** and **Current value** separately, with units, valid ranges, examples, and the effect of changing each parameter. Factory defaults are an immutable version 1 installation baseline, independent of project values or edits to `config.py`. The help window reads settings without applying changes or starting processing.

Use **Help → Restore saved settings** to return the form to the last successfully saved project settings. **Restore factory defaults** restores the full baseline for future processing; a field's right-click **Use factory default** restores just that parameter. These controls update settings rather than completed runs or annotations.

Invalid edits are highlighted in red and explained with the allowed range and factory value. They cannot be saved or used to start processing; closing the window or changing language keeps the valid saved settings. If an older project already contains invalid settings, startup first backs up its exact original bytes in a unique `.recovery` subfolder, then repairs only the invalid fields. Valid choices and project data are preserved, and changes are recorded in history; unsupported settings are retained in the backup and recorded when removed.

## Filters and workspace

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

Every image preview supports dragging to pan and the wheel or **+/−** to zoom. Use the full-screen icon, double-click the image, or focus the image and press **F11** to enlarge it. **Esc** or **F11** returns to the workspace. These controls work for source/filter previews, protective and ownership masks, tile/overview images, polygons, and the selected object crop. Viewing controls do not change image files or measurement scale.

## Manual classes and training export

The **Object gallery** displays real verification crops saved during feature extraction. Select a card to inspect the larger image and choose its type with one of the six class buttons or keys **1–6**; both actions save and advance. **←/→** move between visible objects, and **U** finds the next unclassified object. Gallery filters select a tile, search objects/classes, or show only unclassified objects; the feature table has separate search and class filters.

Under **More class controls**, the class selector and **Save class / Save and next** remain available. Choosing **Unclassified** and saving removes a previous target. Keyboard shortcuts **1–6** correspond to the class IDs **0–5** below; stored IDs remain zero-based.

| Stable ID | CSV target key | English class |
|---|---|---|
| 0 | particle | Particle |
| 1 | fiber | Fiber |
| 2 | self_crossed_tube | Self-crossed tube |
| 3 | crossed_tubes | Crossed tubes |
| 4 | agglomeration | Agglomeration |
| 5 | adhered_objects | Adhered objects |

Manual targets are saved in `manual_object_labels.json` beside the selected measurement version. They are identified by dataset, measurement, tile, and object. Scientific values and original YOLO classes stay intact. A new extraction creates a new object version and starts without manual targets; previous labels remain in the previous results directory. Annotation/tile changes require recalculation before assignment or training export.

**Export training CSV** exports assigned objects by default, with numeric scientific features, `Manual_Class_ID`, `Manual_Class`, `Reviewed`, and source/measurement references. CSV target keys and IDs remain the same across all interface languages.

The numerical predictors are `Area`, `Aspect_Ratio`, `Solidity`, `Euler_Number`, `Endpoints`, and `Branch_Points`. `Area_um2` is included when calibrated. `Manual_Class_ID` is the training target. Original YOLO `Class_ID`/`Class_Name`, source identifiers, and measurement references remain in the CSV as metadata and are excluded from the predictor list. Passing a class as an input would reveal the answer to the model. Random Forest training and inference are not implemented; this workflow prepares their dataset.

The class catalog is shared with YOLO. IDs 0–4 retain the original numbering: `Sphere` means particle and `Curve` means fiber. Adhered objects is the additional class 5. `Class_Catalog_Version=2` records this mapping. Earlier manual labels are interpreted using their saved class key and migrated to these IDs on the next save; read-only viewing and export preserve the old label file.

## Measurements and execution

Large complete objects may be reduced to fit a model tile. v3 measurements use the native crop at source scale. `Area` is measured in source pixels; calibrated `Area_um2 = Area × (µm/px)²`. `Aspect_Ratio` is major/minor mask axis and is dimensionless. It is not curved fiber skeleton length divided by thickness. `Endpoints` counts skeleton endpoints; `Branch_Points` retains the definition of branching pixels.

Crop previews are approximate: enabled top-hat normalization and protective Otsu are calculated on the preview crop, while full preparation uses the complete source image. Each preparation run saves its settings independently. Protective masks preserve their complete connected components. Expert annotations are needed to evaluate biological detection accuracy.

Long operations run in a separate process. **Stop** requests cancellation at a safe checkpoint; the current indivisible filter operation can take time to finish. Incomplete outputs are not presented as complete measurements. Project settings, stages, annotation versions, and current results survive reopening. A second window cannot mutate the same project. Changed annotations or active tiles block export of stale results. Zero detected objects produce a new CSV with headers.

## Verification

```powershell
$env:QT_QPA_PLATFORM='offscreen'
& "$env:USERPROFILE\anaconda3\envs\bm-336546\python.exe" -B -m unittest discover -s test -p 'test_*.py' -v
& .\launch_app.ps1 -SmokeTest
```

The complete application guide, parameter reference, settings recovery and keyboard shortcuts are available offline through **Help / F1**. See the [SoLoData release notes](docs/SOLODATA_RELEASE_2026-10-29_RU.md) for the current publication. Scientific images, derived examples, local audit reports and verification artifacts remain local and are excluded from this public repository.
