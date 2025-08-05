# Python script to merge metadata from Google Photos JSON files into media files.

 This script handles JPG, JPEG, HEIC, GIF, MP4, MKV, and FLV files.
 It reads metadata (like creation date and GPS) from .json files and writes
 it into the corresponding media files. It also updates the file's
 "Date modified" to match the "Date taken".

# NOTE: This script does NOT handle RAW files (like .NEF, .CR2, etc.) 
 because modifying them safely requires specialized external tools like ExifTool. This
 script relies only on Python libraries to avoid external dependencies.

# REQUIREMENTS:
 1. Python Libraries: You need to install 'piexif', 'mutagen', and 'pillow-heif'.
    Run this command in your terminal:

    pip install piexif mutagen pillow-heif

# HOW TO USE:
 1. Save this script as a Python file (e.g., merge_metadata.py).
 2. Place this script in the same folder that contains your media and .json files.
 3. IMPORTANT: It's highly recommended to back up your files before running this script, as it will overwrite the original files.
 4. Run the script from your terminal: python merge_metadata.py
