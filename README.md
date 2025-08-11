
# Google Takeout Metadata Merger

A Python script to merge metadata from Google Photos Takeout JSON files into your media files. This tool updates EXIF data (date taken, GPS) for images and sets the filesystem date for all supported media types, helping you restore original metadata after exporting from Google Photos.

## Features
- Supports JPG, JPEG, PNG, WEBP, HEIC, GIF, MP4, MKV, FLV, MOV, MP, and RAW files (NEF, CR2, ARW, DNG)
- Recursively processes all subfolders
- Updates EXIF metadata (date taken, GPS) for images
- Updates filesystem "Date modified" for all supported files
- Moves processed files to a `Completed` folder
- Optionally deletes processed JSON files and empty folders

## Requirements
- Python 3.7+
- Install required libraries:
    ```sh
    pip install piexif mutagen pillow-heif
    ```

## Usage
1. **Backup your files!** This script will overwrite metadata and move files.
2. Place `merge_metadata.py` in the root folder of your Google Takeout photo collection.
3. Open a terminal in that folder.
4. Run the script:
     ```sh
     python merge_metadata.py
     ```
5. Follow the prompts to optionally delete processed JSON files and empty folders.

## Notes
- RAW files: Only the filesystem date is updated (EXIF is not changed for safety).
- A log file (`metadata_merge.log`) is created in the root folder for troubleshooting.
- Processed files are moved to a `Completed` subfolder, preserving the folder structure.

## Disclaimer
- Use at your own risk. Always back up your files before running this script.

## License
MIT
