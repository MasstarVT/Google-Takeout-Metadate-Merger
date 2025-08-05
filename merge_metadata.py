# Python script to merge metadata from Google Photos JSON files into media files.
#
# This script handles JPG, JPEG, PNG, WEBP, HEIC, GIF, MP4, MKV, FLV, and MP files.
# It recursively searches through all subfolders to find and process files.
# It reads metadata (like creation date and GPS) from .json files and writes
# it into the corresponding media files. It also updates the file's
# "Date modified" to match the "Date taken".
#
# NOTE: This script does NOT handle RAW files (like .NEF, .CR2, etc.) because
# modifying them safely requires specialized external tools like ExifTool. This
# script relies only on Python libraries to avoid external dependencies.
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
    Finds the corresponding JSON file for a given media file from a list of all JSON files.
    """
    media_filename = os.path.basename(media_filepath)
    base_name, ext = os.path.splitext(media_filename)

    # Create a map for quick lookups, storing full paths
    json_map = {os.path.basename(f): f for f in all_json_files}

    search_candidates = []
    # Exact match first
    search_candidates.append(f"{media_filename}.json")
    search_candidates.append(f"{base_name}.json")

    # Handle numbered files like 'image(1).jpg' -> 'image.jpg(1).json'
    match = re.match(r'(.+?)\s*\(\d+\)$', base_name)
    if match:
        original_base = match.group(1).strip()
        numbered_part = base_name[len(original_base):]
        search_candidates.append(f"{original_base}{ext}{numbered_part}.json")

    # Handle edited files like 'image-edited.jpg' -> 'image.jpg.json'
    if base_name.lower().endswith(('-edited', '_edited')):
        original_base = re.sub(r'[-_]edited$', '', base_name, flags=re.IGNORECASE)
        search_candidates.append(f"{original_base}{ext}.json")
        search_candidates.append(f"{original_base}.json")

    for candidate in search_candidates:
        if candidate in json_map:
            return json_map[candidate]

    # Broader search for cases where the JSON name is a subset of the media name
    # e.g., media='Screenshot_20210216-201518_Reddit.jpg', json='Screenshot_20210216-201518.jpg.json'
    media_dir = os.path.dirname(media_filepath)
    for json_path in all_json_files:
        if os.path.dirname(json_path) == media_dir:
            json_filename = os.path.basename(json_path)
            # Check if the json filename (without its own .json ext) is a prefix of the media filename
            json_base, _ = os.path.splitext(json_filename)
            if media_filename.startswith(json_base):
                return json_path

    # Final fallback for supplemental files
    for json_path in all_json_files:
        if os.path.dirname(json_path) == media_dir:
            json_filename = os.path.basename(json_path)
            if json_filename.startswith(media_filename) or json_filename.startswith(base_name):
                 return json_path

    return None

def delete_empty_folders(root_dir):
    """Walks through a directory and removes any empty subfolders."""
    deleted_folders_count = 0
    # Walk the directory tree from the bottom up
    for dirpath, dirnames, filenames in os.walk(root_dir, topdown=False):
        # Don't try to delete the root directory itself
        if os.path.abspath(dirpath) == os.path.abspath(root_dir):
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

    # --- Setup Logging ---
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, mode='w'), # 'w' to overwrite the log each run
            logging.StreamHandler()
        ]
    )
    logging.info(f"Log file created at: {os.path.abspath(log_file)}")
    # ---

    if not os.path.exists(completed_directory):
        os.makedirs(completed_directory)
        logging.info(f"Created folder: '{completed_directory}'")

    logging.info(f"Starting recursive metadata merge in directory: {os.path.abspath(root_directory)}")
    processed_files = 0
    skipped_files = 0
    processed_media_basenames = set() 

    supported_extensions = ('.jpg', '.jpeg', '.mp4', '.mkv', '.heic', '.gif', '.flv', '.png', '.webp', '.mp')
    raw_extensions = ('.nef', '.cr2', '.arw', '.dng')
    
    all_media_files = []
    all_json_files = []
    all_raw_files = []
    
    for dirpath, dirnames, filenames in os.walk(root_directory):
        # Skip the 'Completed' directory during the initial file scan
        if os.path.abspath(dirpath).startswith(os.path.abspath(completed_directory)):
            continue
            
        for filename in filenames:
            full_path = os.path.join(dirpath, filename)
            # Use os.path.splitext for a more reliable way to get the extension
            _, ext = os.path.splitext(filename)
            ext = ext.lower()
            if ext in supported_extensions:
                all_media_files.append(full_path)
            elif ext in raw_extensions:
                all_raw_files.append(full_path)
            elif ext == '.json':
                all_json_files.append(full_path)

    if not all_media_files:
        logging.info(f"No supported files found ({', '.join(supported_extensions)}).")
    
    if all_raw_files:
        logging.info(f"\nFound {len(all_raw_files)} RAW files. They will be skipped to prevent data corruption, as modifying them safely requires external tools outside of Python.")

    logging.info(f"Found {len(all_media_files)} supported files to process.")

    for media_filepath in all_media_files:
        filename = os.path.basename(media_filepath)
        json_filepath = find_json_for_media(media_filepath, all_json_files)

        if json_filepath:
            logging.info(f"\nProcessing '{media_filepath}' with JSON '{os.path.basename(json_filepath)}'...")
            try:
                with open(json_filepath, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)

                if 'photoTakenTime' in metadata and 'timestamp' in metadata['photoTakenTime']:
                    timestamp = int(metadata['photoTakenTime']['timestamp'])
                    dt_object = datetime.fromtimestamp(timestamp)
                    _, file_ext = os.path.splitext(filename)
                    file_ext = file_ext.lower().replace('.', '')


                    # --- Attempt to write internal metadata (EXIF, video tags) ---
                    try:
                        if file_ext in ['jpg', 'jpeg', 'heic', 'png', 'webp']:
                            exif_dict = {}
                            try:
                                if file_ext in ['heic', 'png', 'webp']:
                                    with Image.open(media_filepath) as image:
                                        exif_dict = piexif.load(image.info.get('exif', b''))
                                else: # For JPG/JPEG
                                    exif_dict = piexif.load(media_filepath)
                            except Exception:
                                logging.info(f"  - No valid EXIF data in '{filename}'. Creating new EXIF data.")
                                exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}
                            
                            date_str = dt_object.strftime("%Y:%m:%d %H:%M:%S")
                            exif_dict['Exif'][piexif.ExifIFD.DateTimeOriginal] = date_str.encode('utf-8')
                            exif_dict['Exif'][piexif.ExifIFD.DateTimeDigitized] = date_str.encode('utf-8')
                            exif_dict['0th'][piexif.ImageIFD.DateTime] = date_str.encode('utf-8')
                            logging.info(f"  - Found and set EXIF date to: {date_str}")
                            
                            if 'geoData' in metadata and 'latitude' in metadata['geoData'] and metadata['geoData']['latitude'] != 0.0:
                                lat = metadata['geoData']['latitude']
                                lon = metadata['geoData']['longitude']
                                exif_dict = set_gps_location(exif_dict, lat, lon)
                                logging.info(f"  - Found and set GPS to: Lat {lat}, Lon {lon}")
                            
                            for ifd_name in exif_dict:
                                if ifd_name == 'thumbnail':
                                    continue
                                keys_to_delete = [tag for tag, value in exif_dict[ifd_name].items() if isinstance(value, int)]
                                if keys_to_delete:
                                    for key in keys_to_delete:
                                        del exif_dict[ifd_name][key]
                            
                            exif_dict['thumbnail'] = None
                            exif_bytes = piexif.dump(exif_dict)
                            
                            if file_ext in ['jpg', 'jpeg']:
                                 piexif.insert(exif_bytes, media_filepath)
                            elif file_ext in ['heic', 'png', 'webp']:
                                with Image.open(media_filepath) as image:
                                    image.save(media_filepath, exif=exif_bytes)

                        elif file_ext in ['mp4', 'mkv', 'gif', 'flv', 'mp']:
                            video = mutagen.File(media_filepath)
                            if video is not None:
                                utc_dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                                date_str_iso = utc_dt.isoformat()
                                
                                if video.tags is None:
                                    video.add_tags()
                                
                                tag_key = 'creation_time' if file_ext == 'flv' else 'DATE_RECORDED'
                                video.tags[tag_key] = date_str_iso
                                video.save()
                                logging.info(f"  - Found and set {file_ext.upper()} internal creation date to: {date_str_iso}")
                            else:
                                logging.warning(f"  - Could not write internal metadata for '{filename}' (unsupported by mutagen).")

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
                    
                    # Add the base name of the processed file to a set for later cleanup
                    base_name_for_cleanup, _ = os.path.splitext(filename)
                    # Normalize names like 'IMG_1234(1)' or 'IMG_1234-edited' to get the true base
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
    
    logging.info("\n--------------------")
    logging.info("      COMPLETE      ")
    logging.info("--------------------")
    logging.info(f"Processed: {processed_files} files")
    logging.info(f"Skipped:   {skipped_files + len(all_raw_files)} files (including RAW files)")

    if processed_media_basenames:
        logging.info("\n")
        while True:
            prompt_message = f"Do you want to delete all JSON files corresponding to the {len(processed_media_basenames)} successfully processed media items? (yes/no): "
            delete_choice = input(prompt_message).lower().strip()
            if delete_choice in ['yes', 'y', 'no', 'n']:
                break
            else:
                logging.warning("Invalid input. Please enter 'yes' or 'no'.")

        if delete_choice in ['yes', 'y']:
            deleted_count = 0
            logging.info("\nDeleting related JSON files...")
            # Re-iterate through all found JSON files to find all matches
            for json_path in all_json_files:
                json_filename = os.path.basename(json_path)
                # Check if this JSON file belongs to any of the processed media
                for base_name in processed_media_basenames:
                    if json_filename.startswith(base_name):
                        try:
                            os.remove(json_path)
                            logging.info(f"  - Deleted '{os.path.basename(json_path)}' from '{os.path.dirname(json_path)}'")
                            deleted_count += 1
                            # Once deleted, break inner loop to avoid trying to delete it again
                            break 
                        except OSError as e:
                            logging.error(f"  - Error deleting '{json_path}': {e}")
            logging.info(f"\nSuccessfully deleted {deleted_count} JSON files.")
        else:
            logging.info("\nSkipping JSON file deletion.")

    # --- Clean up empty folders ---
    logging.info("\n")
    while True:
        cleanup_choice = input("Do you want to delete any empty folders that are left? (yes/no): ").lower().strip()
        if cleanup_choice in ['yes', 'y', 'no', 'n']:
            break
        else:
            logging.warning("Invalid input. Please enter 'yes' or 'no'.")
    
    if cleanup_choice in ['yes', 'y']:
        logging.info("\nChecking for empty folders to delete...")
        delete_empty_folders(root_directory)
    else:
        logging.info("\nSkipping empty folder cleanup.")


if __name__ == '__main__':
    main()
