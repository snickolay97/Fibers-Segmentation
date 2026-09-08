"""
Biomedical Image Analysis Pipeline - Main Entry Point

This script serves as the master control center for the modular Directed Acyclic Graph (DAG) pipeline.
It initializes the Orchestrator (BiomedicalPipelineManager) which seamlessly connects the independent
processing blocks:

Available Modules in the Architecture:
--------------------------------------
- Block 1 (Global Preprocessor): Applies Bilateral, Top-Hat, and Gamma filters to massive raw .tif images.
- Block 2 (Smart Slicer): Uses Dijkstra's algorithm to topographically slice images into 1500x1500 tiles without cutting fibers.
- Block 3 (Feature Extractor): Isolates objects, calculates geometry (Area, Solidity), and extracts graph topology (Euler, Endpoints).
- Block 4 & 5 (Upcoming): Random Forest Classification and Physical parameter calculations (Microns, True Length).
"""

from src.pipeline_manager import BiomedicalPipelineManager

def main():
    # Instantiate the Orchestrator.
    # It automatically loads directory paths and constants from src/config.py
    print("Initializing the Biomedical Pipeline Manager...")
    manager = BiomedicalPipelineManager()

    """
    PIPELINE EXECUTION MODES:
    -------------------------
    Uncomment the mode you want to run. 

    Mode A: 'filter_and_slice'
        - Triggers Block 1 & Block 2.
        - Use this when you have a new massive raw .tif image in '1_raw_large_images'.
        - Output: Perfectly sliced 1500x1500 .png tiles ready for manual SAM annotation.

    Mode B: 'extract_features'
        - Triggers Block 3 only.
        - Use this AFTER you have annotated the tiles in SAM/CVAT and placed the .txt labels in '3_sam_labels'.
        - Output: 'topological_features.csv' containing dry mathematical metrics for Machine Learning.

    Mode C: 'end_to_end' (Production Mode)
        - Triggers Block 1, Block 2, and Block 3 consecutively.
        - Use this for fully autonomous inference on unannotated images. 
        - Outputs sliced tiles and automatically finds objects (assigning them the 'Unknown' class) to calculate math.
    """

    # Select your desired mode here:
    selected_mode = 'end_to_end'

    print(f"Starting pipeline in mode: '{selected_mode}'\n" + "="*50)
    manager.run(mode=selected_mode)

if __name__ == "__main__":
    main()