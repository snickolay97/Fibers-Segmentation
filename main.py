"""Run the standalone microscopy pipeline with the mode selected in main().

Use filter_and_slice to prepare TIFFs, manage_tiles to exclude selected
model tiles, extract_features to measure a prepared dataset, or end_to_end
to prepare and measure in one run.
"""

from src.pipeline_manager import BiomedicalPipelineManager

def main():
    """Run the selected workflow with the manager's default per-run settings."""
    print("Initializing Biomedical Pipeline Manager...")
    manager = BiomedicalPipelineManager()

    selected_mode = 'filter_and_slice'

    # Exclusion IDs belong to a specific preparation. Read them from its overview.
    DATASET_NAME = 'FL01_G3_RGB_Red'
    TILES_TO_EXCLUDE = []

    print(f"Starting pipeline in mode: '{selected_mode}'\n" + "=" * 50)

    if selected_mode == 'manage_tiles':
        manager.run(mode=selected_mode, dataset_name=DATASET_NAME, exclude_specs=TILES_TO_EXCLUDE)
    else:
        manager.run(mode=selected_mode)

if __name__ == "__main__":
    main()
