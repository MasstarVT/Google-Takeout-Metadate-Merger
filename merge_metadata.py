# Python script to merge metadata from Google Photos JSON files into media files.
#
# This script handles JPG, JPEG, PNG, WEBP, HEIC, GIF, MP4, MKV, FLV, MOV, and MP files.
# It also handles RAW files (NEF, CR2, ARW, DNG) by updating their file system
# "Date modified" to match the JSON data, but it does NOT modify their internal
# EXIF data, as this can be risky without specialized tools.
#
# It recursively searches through all subfolders to find and process files.
# It reads metadata (like creation date and GPS) from .json files and writes
# it into the corresponding media files (for non-RAW files). It updates the
# file's "Date modified" for ALL supported file types.
#
# --- REQUIREMENTS ---
# 1. Python Libraries: You need to install 'piexif', 'mutagen', and 'pillow-heif'.
#    Run this command in your terminal:
#    pip install piexif mutagen pillow-heif
#
# --- HOW TO USE ---
# 1. Save this script as a Python file (e.g., merge_metadata.py).
# 2. Place this script in the root folder of your photo collection.
# 3. IMPORTANT: It's highly recommended to back up your files before running
#    this script, as it will overwrite the original files.
# 4. Run the script from your terminal: python merge_metadata.py

import os
import json
import re
import shutil
import piexif
import mutagen
import logging
from datetime import datetime, timezone
from PIL import Image, ImageFile
import pillow_heif

# Allow loading of truncated images, which can prevent errors with corrupted files.
ImageFile.LOAD_TRUNCATED_IMAGES = True

# Register the HEIF opener with Pillow
pillow_heif.register_heif_opener()

def to_deg(value, loc):
    """Converts a decimal degree value to degrees, minutes, seconds."""
    if value < 0:
        loc_value = loc[1]
    elif value > 0:
        loc_value = loc[0]
    else:
        loc_value = ""
    abs_value = abs(value)
    deg = int(abs_value)
    t1 = (abs_value - deg) * 60
    min = int(t1)
    sec = round((t1 - min) * 60, 5)
    return (deg, 1), (min, 1), (int(sec*100000), 100000), loc_value.encode('utf-8')

def set_gps_location(exif_dict, lat, lon):
    """Creates and sets the GPS EXIF data for JPG files."""
    lat_deg = to_deg(lat, ["N", "S"])
    lon_deg = to_deg(lon, ["E", "W"])

    exif_dict['GPS'] = {
        piexif.GPSIFD.GPSVersionID: (2, 0, 0, 0),
        piexif.GPSIFD.GPSLatitudeRef: lat_deg[3],
        piexif.GPSIFD.GPSLatitude: lat_deg[:3],
        piexif.GPSIFD.GPSLongitudeRef: lon_deg[3],
        piexif.GPSIFD.GPSLongitude: lon_deg[:3],
    }
    return exif_dict

def find_json_for_media(media_filepath, all_json_files):
    """
    Finds the corresponding JSON file for a given media file. This version
    is robust against various Google Takeout naming conventions, including:
    - Edited files ("-edited")
    - Numbered/duplicate files ("(1)")
    - Videos with .jpg JSONs ("video.mp4" -> "video.jpg.json")
    - Truncated metadata suffixes ("...supplemental-metad.json")
    """
    media_filename = os.path.basename(media_filepath)
    base_name, ext = os.path.splitext(media_filename)
    base_name_lower = base_name.lower()
    ext_lower = ext.lower()

    media_dir = os.path.dirname(media_filepath)
    json_map_local = {os.path.basename(f).lower(): f for f in all_json_files if os.path.dirname(f) == media_dir}

    # --- 1. Deconstruct the filename to find its core parts ---
    core_name_lower = base_name_lower
    number_part = ""
    
    edited_match = re.search(r'(.+?)([-_]edited)$', core_name_lower)
    if edited_match:
        core_name_lower = edited_match.group(1).strip()
        logging.info(f"  - '{media_filename}' is an edited file. Targeting original's JSON...")

    numbered_match = re.search(r'(.+?)(\(\d+\))$', core_name_lower)
    if numbered_match:
        core_name_lower = numbered_match.group(1).strip()
        number_part = numbered_match.group(2)

    # --- 2. Build target base names to search for ---
    
    # For videos, the JSON might use .jpg instead of the video extension.
    base_ext_combinations = [ext_lower]
    if ext_lower in ['.mp4', '.mov', '.mkv', '.flv', '.mp']:
        base_ext_combinations.append('.jpg')

    # Create a list of possible base names for the JSON file.
    # e.g., for "photo(1).mp4", this would include "photo(1).mp4" and "photo(1).jpg"
    target_bases = [f"{core_name_lower}{number_part}{combo_ext}" for combo_ext in base_ext_combinations]
    
    # Also add the base name without any extension for simpler JSONs like "photo(1).json"
    target_bases.append(f"{core_name_lower}{number_part}")

    # --- 3. Find Match: Exact, then Prefix ---

    # A. Check for exact, full matches first (most reliable)
    for base in target_bases:
        # e.g., photo(1).jpg.supplemental-metadata.json
        full_candidate = f"{base}.supplemental-metadata.json"
        if full_candidate in json_map_local:
            return json_map_local[full_candidate]
        # e.g., photo(1).jpg.json
        simple_candidate = f"{base}.json"
        if simple_candidate in json_map_local:
            return json_map_local[simple_candidate]

    # B. If no exact match, check for prefix matches (handles truncated suffixes)
    # We sort the json_map by key length, descending. This makes "foo.jpg.supplemental.json"
    # match before "foo.jpg.json" or "foo.jpg.supple.json", which is more specific and correct.
    sorted_json_names = sorted(json_map_local.keys(), key=len, reverse=True)

    for base in target_bases:
        for json_name in sorted_json_names:
            if json_name.startswith(base + '.'): # Ensure it's a full prefix match
                return json_map_local[json_name]

    # --- 4. Fallback: Deep search by title in JSON content ---
    target_filename_for_search = f"{core_name_lower}{number_part}{ext}"
    
    logging.info(f"  - No filename match for '{media_filename}'. Starting deep search for title '{target_filename_for_search}'...")
    for json_path in json_map_local.values():
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if data.get('title') == target_filename_for_search:
                logging.info(f"  - Deep search SUCCESS: Found match in '{os.path.basename(json_path)}' by title.")
                return json_path
        except (json.JSONDecodeError, IOError):
            continue

    return None

def delete_empty_folders(root_dir):
    """Walks through a directory and removes any empty subfolders."""
    deleted_folders_count = 0
    # Walk the directory tree from the bottom up
    for dirpath, dirnames, filenames in os.walk(root_dir, topdown=False):
        # Don't try to delete the root directory itself or the completed directory
        if os.path.abspath(dirpath) == os.path.abspath(root_dir) or "Completed" in dirpath:
            continue
            
        if not dirnames and not filenames:
            try:
                os.rmdir(dirpath)
                logging.info(f"  - Deleted empty folder: '{dirpath}'")
                deleted_folders_count += 1
            except OSError as e:
                logging.error(f"  - Error deleting folder '{dirpath}': {e}")
    if deleted_folders_count > 0:
        logging.info(f"\nSuccessfully deleted {deleted_folders_count} empty folders.")
    else:
        logging.info("\nNo empty folders found to delete.")


def main():
    """Main function to process media files in the specified directory."""
    root_directory = '.'
    completed_directory = os.path.join(root_directory, "Completed")
    log_file = os.path.join(root_directory, "metadata_merge.log")

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.FileHandler(log_file, mode='w'), logging.StreamHandler()])
    logging.info(f"Log file created at: {os.path.abspath(log_file)}")

    if not os.path.exists(completed_directory):
        os.makedirs(completed_directory)
        logging.info(f"Created folder: '{completed_directory}'")

    logging.info(f"Starting recursive metadata merge in directory: {os.path.abspath(root_directory)}")
    processed_files = 0
    skipped_files = 0
    processed_media_basenames = set() 

    supported_extensions = ('.jpg', '.jpeg', '.mp4', '.mkv', '.heic', '.gif', '.flv', '.png', '.webp', '.mp', '.nef', '.cr2', '.arw', '.dng', '.mov')
    
    all_media_files, all_json_files = [], []
    for dirpath, _, filenames in os.walk(root_directory):
        if os.path.abspath(dirpath).startswith(os.path.abspath(completed_directory)):
            continue
        for filename in filenames:
            full_path = os.path.join(dirpath, filename)
            _, ext = os.path.splitext(filename)
            ext = ext.lower()
            if ext in supported_extensions:
                all_media_files.append(full_path)
            elif ext == '.json':
                all_json_files.append(full_path)

    if not all_media_files:
        logging.info(f"No supported files found ({', '.join(supported_extensions)}).")
        return
    
    logging.info(f"Found {len(all_media_files)} supported files to process and {len(all_json_files)} JSON files.")
    
    for media_filepath in all_media_files:
        filename = os.path.basename(media_filepath)
        
        # --- Find the matching JSON file ---
        json_filepath = find_json_for_media(media_filepath, all_json_files)
        
        if json_filepath:
            logging.info(f"\nProcessing '{media_filepath}' with JSON '{os.path.basename(json_filepath)}'...")
            try:
                with open(json_filepath, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)

                if 'photoTakenTime' in metadata and 'timestamp' in metadata['photoTakenTime']:
                    timestamp = int(metadata['photoTakenTime']['timestamp'])
                    
                    # --- Update internal metadata (where possible and safe) ---
                    try:
                        _, file_ext_with_dot = os.path.splitext(filename)
                        file_ext = file_ext_with_dot.lower().replace('.', '')
                        if file_ext in ['jpg', 'jpeg', 'heic', 'png', 'webp']:
                            exif_dict = {}
                            try:
                                if file_ext in ['heic', 'png', 'webp']:
                                    with Image.open(media_filepath) as image:
                                        exif_dict = piexif.load(image.info.get('exif', b''))
                                else:
                                    exif_dict = piexif.load(media_filepath)
                            except Exception:
                                exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}
                            
                            dt_object = datetime.fromtimestamp(timestamp)
                            date_str = dt_object.strftime("%Y:%m:%d %H:%M:%S")
                            exif_dict['Exif'][piexif.ExifIFD.DateTimeOriginal] = date_str.encode('utf-8')
                            exif_dict['Exif'][piexif.ExifIFD.DateTimeDigitized] = date_str.encode('utf-8')
                            exif_dict['0th'][piexif.ImageIFD.DateTime] = date_str.encode('utf-8')
                            logging.info(f"  - Found and set EXIF date to: {date_str}")
                            
                            if 'geoData' in metadata and metadata['geoData'].get('latitude'):
                                lat, lon = metadata['geoData']['latitude'], metadata['geoData']['longitude']
                                exif_dict = set_gps_location(exif_dict, lat, lon)
                                logging.info(f"  - Found and set GPS to: Lat {lat}, Lon {lon}")
                            
                            exif_dict['thumbnail'] = None
                            exif_bytes = piexif.dump(exif_dict)
                            
                            if file_ext in ['jpg', 'jpeg']:
                                 piexif.insert(exif_bytes, media_filepath)
                            else:
                                with Image.open(media_filepath) as image:
                                    image.save(media_filepath, exif=exif_bytes)

                        elif file_ext in ['mp4', 'mkv', 'gif', 'flv', 'mp', 'mov']:
                             video = mutagen.File(media_filepath)
                             if video is not None:
                                utc_dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                                date_str_iso = utc_dt.isoformat()
                                if video.tags is None: video.add_tags()
                                tag_key = 'creation_time' if file_ext == 'flv' else 'DATE_RECORDED'
                                video.tags[tag_key] = date_str_iso
                                video.save()
                                logging.info(f"  - Found and set {file_ext.upper()} internal creation date to: {date_str_iso}")
                             else:
                                logging.warning(f"  - Could not write internal metadata for '{filename}' (unsupported by mutagen).")
                        
                        elif file_ext in ['nef', 'cr2', 'arw', 'dng']:
                             logging.info(f"  - Found RAW file. Internal metadata will not be changed for safety.")

                    except Exception as e:
                        logging.warning(f"  - Failed to write internal metadata for '{filename}': {e}")

                    # --- Always update file system date and move file ---
                    os.utime(media_filepath, (timestamp, timestamp))
                    logging.info(f"  - Set file 'Date modified' to match 'Date taken'.")
                    
                    relative_path = os.path.relpath(os.path.dirname(media_filepath), root_directory)
                    destination_dir = os.path.join(completed_directory, relative_path)
                    os.makedirs(destination_dir, exist_ok=True)
                    
                    destination_filepath = os.path.join(destination_dir, filename)
                    shutil.move(media_filepath, destination_filepath)
                    logging.info(f"  - Moved '{filename}' to '{destination_dir}'")
                    
                    base_name_for_cleanup, _ = os.path.splitext(filename)
                    base_name_for_cleanup = re.sub(r'\(\d+\)$', '', base_name_for_cleanup)
                    base_name_for_cleanup = re.sub(r'[-_]edited$', '', base_name_for_cleanup, flags=re.IGNORECASE)
                    processed_media_basenames.add(base_name_for_cleanup)
                    
                    processed_files += 1
                else:
                    logging.info("  - No 'photoTakenTime' found in JSON. Skipping metadata update.")
                    skipped_files += 1
            except Exception as e:
                logging.error(f"  - An unexpected error occurred while processing '{filename}': {e}")
                skipped_files += 1
        else:
            logging.warning(f"\nSkipping '{filename}': No corresponding JSON file found.")
            skipped_files += 1
    
    logging.info("\n" + "-"*20 + "\n      COMPLETE      \n" + "-"*20)
    logging.info(f"Processed: {processed_files} files")
    logging.info(f"Skipped:   {skipped_files} files")

    if processed_media_basenames:
        logging.info("\n")
        delete_choice = input(f"Do you want to delete all JSON files corresponding to the {len(processed_media_basenames)} successfully processed media items? (yes/no): ").lower().strip()
        if delete_choice in ['yes', 'y']:
            deleted_count = 0
            logging.info("\nDeleting related JSON files...")
            for json_path in all_json_files:
                json_filename = os.path.basename(json_path)
                for base_name in processed_media_basenames:
                    if json_filename.startswith(base_name):
                        try:
                            os.remove(json_path)
                            logging.info(f"  - Deleted '{os.path.basename(json_path)}' from '{os.path.dirname(json_path)}'")
                            deleted_count += 1
                            break 
                        except OSError as e:
                            logging.error(f"  - Error deleting '{json_path}': {e}")
            logging.info(f"\nSuccessfully deleted {deleted_count} JSON files.")
        else:
            logging.info("\nSkipping JSON file deletion.")

    logging.info("\n")
    cleanup_choice = input("Do you want to delete any empty folders that are left? (yes/no): ").lower().strip()
    if cleanup_choice in ['yes', 'y']:
        logging.info("\nChecking for empty folders to delete...")
        delete_empty_folders(root_directory)
    else:
        logging.info("\nSkipping empty folder cleanup.")

if __name__ == '__main__':
    main()
