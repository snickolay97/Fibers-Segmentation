"""
Biomedical Image Analysis Pipeline - Main Entry Point

Available Execution Modes:
-------------------------
1. 'filter_and_slice':
   - Runs Preprocessor (Block 1) and Smart Slicer (Block 2).
   - Generates the High-Resolution Tile Index Map and coordinates JSON.
   - Generates animations in data/animations/ if ENABLE_ANIMATIONS = True.

2. 'manage_tiles':
   - Moves unwanted out-of-channel or scale-bar tiles into 'excluded_tiles/' subfolders.

3. 'extract_features':
   - Runs Block 3 on verified in-channel tiles to extract geometric & topological descriptors.

4. 'end_to_end':
   - Executes full workflow: filtering -> slicing -> feature extraction.
"""

from src.pipeline_manager import BiomedicalPipelineManager

def main():
    print("Initializing Biomedical Pipeline Manager...")
    manager = BiomedicalPipelineManager()

    # --- EXECUTION MODE SELECTOR ---
    # Options: 'filter_and_slice', 'manage_tiles', 'extract_features', 'end_to_end'
    selected_mode = 'filter_and_slice'

    # Target dataset for tile exclusion mode
    DATASET_NAME = 'FL01_G3_RGB_Red'

    # Ranges & IDs of tiles to isolate (outside microchannel or artifacts)
    TILES_TO_EXCLUDE = [
        "1-9",
        "14-20, 82, 83, 95-97, 110, 111",
        "153-159, 167-175, 180-205"
    ]

    print(f"Starting pipeline in mode: '{selected_mode}'\n" + "=" * 50)

    if selected_mode == 'manage_tiles':
        manager.run(mode=selected_mode, dataset_name=DATASET_NAME, exclude_specs=TILES_TO_EXCLUDE)
    else:
        manager.run(mode=selected_mode)

if __name__ == "__main__":
    main()