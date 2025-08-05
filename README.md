# Python script to merge metadata from Google Photos JSON files into JPG and MP4 files.
#
# This script reads metadata (like creation date) from .json
# files and writes it into the EXIF data of corresponding .jpg files or the
# metadata tags of .mp4 files. It also updates the file's "Date modified"
# to match the "Date taken".
#
# REQUIREMENTS:
# You need to install the 'piexif' and 'mutagen' libraries.
# You can install them by running:
# pip install piexif mutagen
#
# HOW TO USE:
# 1. Save this script as a Python file (e.g., merge_metadata.py).
# 2. Place this script in the same folder that contains your media and .json files.
#    Alternatively, you can modify the 'media_directory' variable below to point
#    to the correct folder.
# 3. IMPORTANT: It's highly recommended to back up your files before running
#    this script, as it will overwrite the original files.
# 4. Run the script from your terminal: python merge_metadata.py
