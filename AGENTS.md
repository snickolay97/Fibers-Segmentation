# SoLoData project guidance

## Scope and source of truth

This directory contains a local Windows microscopy application and its image-processing pipeline. The sibling `../Presentanion` (intentional existing spelling) contains the canonical bilingual slide decks. Communicate with the owner in Russian unless asked otherwise. Follow the current user request before repository preferences.

Read `README.md`, `README_RU.md`, and the relevant source before changing behavior. Existing review documents describe different historical versions; source and reproducible tests establish current behavior. Do not describe proposals as implemented features or historical benchmark numbers as new measurements.

## Entry points and architecture

- `app.py`, `launch_app.cmd`, `launch_app.ps1`: desktop startup. `main.py`: command-line pipeline.
- `src/app_settings.py`: validated per-run `PipelineSettings`. `src/config.py`: defaults and some historical/experimental constants.
- `src/image_io.py`: TIFF axes, explicit channel/plane selection, native pixels and uint8 processing view. uint16 processing uses a right shift by 8, not percentile normalization.
- `src/block1_preprocessor.py`: bilateral filter, white top-hat with min-max normalization, reciprocal-gamma LUT. A separate protective mask uses modified Otsu, a lower threshold, closing, and dilation.
- `src/block2_slicer.py`: v3 adaptive tiling. Straight corridor search with backward-moving windows, directed `MCP_Geometric` routing, whole-component allocation, exact pixel ownership, native/model tiles and metadata.
- `src/partition_geometry.py`, `src/tile_scale.py`, `src/overview_reconstructor.py`, `src/tile_manager.py`: geometry, scale mappings, overviews and explicit tile exclusions.
- `src/block3_feature_extractor.py`: YOLO polygon import or explicitly selected automatic detection, local thresholding, component decomposition, six geometric/topological features, CSV and verification masks.
- `src/desktop/`: Qt interface, project persistence, worker process, provenance, localization, manual object labels and training export.
- `src/object_classes.py`: shared stable class catalog. `src/desktop/object_classifier.py` is a manual classification UI, not a trained classifier.
- `test/test_*.py`: unittest regression suite. `test/Fiber Detection.py` is a historical experiment, not the automated test entry point.

## Scientific invariants

1. Distinguish the grayscale processing image, protective routing mask, annotation polygon, and thresholded measurement mask. Closing/dilation change dimensions; the protective mask is not a physical diameter mask.
2. Current preprocessing defaults: bilateral d=9, sigmaColor=45, sigmaSpace=15; top-hat radius=85 (171x171 ellipse); gamma=1.2 with exponent 1/gamma. Modified global Otsu ignores bin 0; protective threshold is `max(10, int(0.25*T))`; closing=17x17, buffer=5x5.
3. Default model tile size is 1500. Search offsets derive from target size: 0.75N to floor(0.975N), backoff floor(0.015N), minimum floor(0.25N). Only straight-corridor windows move backward. Directed routing runs in the original window with offsets (1,-1),(1,0),(1,1).
4. Obstacles have infinite route cost. Final ownership preserves whole 8-connected protective components and assigns every source pixel exactly once. This is a guarantee about the protective mask, not unknown biological truth.
5. v3 retains native crops for measurements even when an oversized crop is resized to a fixed model canvas. Respect valid masks, source coordinates, scale metadata, exclusions, and stale-result checks.
6. Current predictors: `Area`, `Aspect_Ratio`, `Solidity`, `Euler_Number`, `Endpoints`, `Branch_Points`. `Aspect_Ratio` is equivalent-ellipse major/minor axis ratio, not fiber centerline length/diameter. `Branch_Points` counts branch pixels, not merged graph junctions. Degenerate minor axes currently return 1.0; document this limitation rather than silently changing feature semantics.
7. `Area` uses source pixels in v3. With calibration s in micrometres/pixel, `Area_um2=Area*s*s`; the current training exporter adds `Area_um2` alongside the six core predictors. Do not infer physical units without calibration.
8. Six stable targets: particle=0, fiber=1, self_crossed_tube=2, crossed_tubes=3, agglomeration=4, adhered_objects=5. Keep IDs and CSV keys stable across UI languages.
9. Random Forest training/inference and class-specific diameter/length measurement are future modules. Current code prepares manual labels and a training CSV. Exclude target/class columns and source identifiers from predictor inputs. Group future train/test splits by source image or experiment.
10. Search GIFs show actual attempted windows and reveal the accepted route. They do not show the priority-queue exploration frontier.
11. MCP checks occupied route vertices but permits diagonal corner crossing between two 8-connected obstacle pixels. The later `_allocate_components` stage repairs ownership for whole components; it does not recompute the seam. Do not attribute the final preservation guarantee to the route alone. A local reproducible counterexample is in `../Presentanion/presentation_source/reproduce_corner_case.py`.
12. Min–max normalization changes a value range, not a distribution into a Gaussian. Gamma=1 is an identity control. Gamma=1.2 raises faint background as well as faint signal and can change subsequent Otsu/local masks; improved segmentation is unproven without expert ground truth. The 2026-10-24 four-crop comparison measures protective coverage, not accuracy.

## Development and verification

Use Python 3.10+ with the versions in `requirements.txt`. On Windows, resolve the scientific environment from `%USERPROFILE%/anaconda3/envs/bm-336546/python.exe`, as the launcher does. Use the bundled artifact runtime for slide work, not a replacement installation.

Typical checks from this directory:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
& "$env:USERPROFILE\anaconda3\envs\bm-336546\python.exe" -B -m unittest discover -s test -p 'test_*.py' -v
& .\launch_app.ps1 -SmokeTest
```

If sandbox ACLs prevent temporary-file creation, run tests with `tempfile.tempdir` set to a dedicated writable local temporary directory. Record that workaround separately from project defects. For targeted changes, run the relevant test modules before broadening checks. Scientific validation against expert masks is distinct from software regression tests.

Preserve existing user changes; the checkout may already be dirty. Do not reset or overwrite unrelated files. Do not regenerate full TIFF datasets, replace annotations, move tiles, or retrain models merely to update documentation. Use new output directories for experiments. Keep intermediate renders, caches and sample exports separate from canonical deliverables.

## In-app help maintenance

The built-in Help is the application manual, not only a list of parameter defaults. Every future application update that changes a feature, workflow, control, parameter, shortcut, export, validation rule, error or recovery behavior must update the relevant in-app Help topics in the same change. Keep English, Russian and Hebrew content equivalent, including contextual question-mark links, search terms, units, valid ranges, worked examples and limitations. Verify the affected Help pages alongside the behavior being changed.

Factory settings must come from the versioned, immutable defaults catalog shared by runtime settings and Help. A user's project settings must never become the factory reference. When changing factory defaults, explicitly update the catalog version, reference explanations, translations and regression checks. Keep current editable values visibly separate from factory values. Invalid drafts must not be saved as working project settings or prevent the application from starting; preserve an exact backup before repairing saved settings.

## Documentation and presentations

The canonical files are `../Presentanion/Fibers_Pipeline_EN.pptx` and `../Presentanion/Fibers_Pipeline_RU.pptx`. They must carry equivalent content, identical slide order, formulas, numerical examples, images and layout, differing only in language. The intended format is a 20–30 minute main talk with a detailed appendix and speaker notes. Preserve the original files in an archive before replacing them. Keep bilingual source data and a reproducible build script.

For each mathematical method, explain symbols, purpose, the exact project convention, a worked example, limitations, and a primary literature/documentation link. Clearly separate literature-derived formulas from project heuristics such as the 0.25 threshold factor or kernel choices. Use real source images and reproducible processing examples. Mark any simulated example as simulated. Never invent accuracy, calibration, biological labels, or benchmark results.

Detailed current audit: `docs/PIPELINE_AUDIT_2026-10-22_RU.md` and `docs/FEATURES_GEOMETRY_2026-10-22_RU.md`. The tutorial and bibliography are in `../Presentanion/PROJECT_EXPLANATION_RU.md`. Shared bilingual content, authoring scripts and all slide assets live in `../Presentanion/presentation_source/`; read its README for rebuild commands. The 2026-10-24 revision has 31 main slides and 24 hidden appendix slides, including a diagonal-contact counterexample and gamma comparison without ground-truth claims. This file is a compact working map; keep long derivations in those documents.

AGENTS.md conventions: https://learn.chatgpt.com/docs/agent-configuration/agents-md
