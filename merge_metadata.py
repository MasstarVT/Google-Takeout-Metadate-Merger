# Python script to merge metadata from Google Photos JSON files into media files.
#
# This script handles JPG, JPEG, HEIC, GIF, MP4, MKV, and FLV files.
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
# 2. Place this script in the same folder that contains your media and .json files.
# 3. IMPORTANT: It's highly recommended to back up your files before running
#    this script, as it will overwrite the original files.
# 4. Run the script from your terminal: python merge_metadata.py

import os
import json
import re
import shutil
import piexif
import mutagen
from datetime import datetime, timezone
from PIL import Image
import pillow_heif

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

def find_json_for_media(media_filename, all_files, directory):
    """
    Finds the corresponding JSON file for a given media file, handling various
    Google Takeout naming conventions like edited or numbered files.
    """
    base_name, ext = os.path.splitext(media_filename) # e.g., 'photo(1)', '.jpg'

    search_candidates = []
    search_candidates.append(f"{media_filename}.json")
    search_candidates.append(f"{base_name}.json")

    match = re.match(r'(.+?)\s*\(\d+\)$', base_name)
    if match:
        original_base = match.group(1).strip()
        numbered_part = base_name[len(original_base):]
        search_candidates.append(f"{original_base}{ext}{numbered_part}.json")

    if base_name.lower().endswith(('-edited', '_edited')):
        original_base = re.sub(r'[-_]edited$', '', base_name, flags=re.IGNORECASE)
        search_candidates.append(f"{original_base}{ext}.json")
        search_candidates.append(f"{original_base}.json")

    for candidate in search_candidates:
        if candidate in all_files:
            return os.path.join(directory, candidate)
    
    for f in all_files:
        if f.lower().endswith('.json') and f.startswith(media_filename):
            return os.path.join(directory, f)
            
    for f in all_files:
        if f.lower().endswith('.json') and f.startswith(base_name):
            return os.path.join(directory, f)

    return None

def cleanup_duplicate_jsons(directory, all_files):
    """Identifies and offers to delete duplicate JSON files based on '(number)' suffixes."""
    print("\n--- Checking for duplicate JSON files ---")
    json_files = [f for f in all_files if f.lower().endswith('.json')]
    base_filenames = {}
    
    for f in json_files:
        base_name = re.sub(r'\(\d+\)', '', f)
        if base_name not in base_filenames:
            base_filenames[base_name] = []
        base_filenames[base_name].append(f)
        
    duplicate_files_to_delete = []
    for base_name, files in base_filenames.items():
        if len(files) > 1:
            files.sort(key=len)
            duplicates_in_group = files[1:]
            duplicate_files_to_delete.extend(duplicates_in_group)
            print(f"Found duplicate group for '{files[0]}': {', '.join(duplicates_in_group)}")

    if not duplicate_files_to_delete:
        print("No duplicate JSON files found.")
        return all_files

    print(f"\nFound {len(duplicate_files_to_delete)} potential duplicate JSON files.")
    
    while True:
        delete_choice = input("Do you want to delete these duplicate JSON files? (yes/no): ").lower().strip()
        if delete_choice in ['yes', 'y', 'no', 'n']:
            break
        else:
            print("Invalid input. Please enter 'yes' or 'no'.")

    if delete_choice in ['yes', 'y']:
        deleted_count = 0
        print("\nDeleting duplicate JSON files...")
        for json_file_to_delete in duplicate_files_to_delete:
            try:
                os.remove(os.path.join(directory, json_file_to_delete))
                print(f"  - Deleted '{json_file_to_delete}'")
                deleted_count += 1
            except OSError as e:
                print(f"  - Error deleting '{json_file_to_delete}': {e}")
        print(f"\nSuccessfully deleted {deleted_count} duplicate JSON files.")
        return os.listdir(directory)
    else:
        print("\nSkipping duplicate JSON file deletion.")
        return all_files

def main():
    """Main function to process media files in the specified directory."""
    media_directory = '.'
    completed_directory = os.path.join(media_directory, "Completed")

    if not os.path.exists(completed_directory):
        os.makedirs(completed_directory)
        print(f"Created folder: '{completed_directory}'")

    print(f"\nStarting metadata merge in directory: {os.path.abspath(media_directory)}")
    processed_files = 0
    skipped_files = 0
    used_json_files = [] 

    try:
        all_files = os.listdir(media_directory)
    except FileNotFoundError:
        print(f"Error: Directory not found at '{media_directory}'. Please check the path.")
        return

    all_files = cleanup_duplicate_jsons(media_directory, all_files)

    supported_extensions = ('.jpg', '.jpeg', '.mp4', '.mkv', '.heic', '.gif', '.flv')
    media_files = [f for f in all_files if f.lower().endswith(supported_extensions)]
    raw_files = [f for f in all_files if f.lower().endswith(('.nef', '.cr2', '.arw', '.dng'))]

    if not media_files:
        print(f"No supported files found ({', '.join(supported_extensions)}).")
    
    if raw_files:
        print(f"\nFound {len(raw_files)} RAW files. They will be skipped to prevent data corruption,")
        print("as modifying them safely requires external tools outside of Python.")


    print(f"\nFound {len(media_files)} supported files to process.")

    for filename in media_files:
        media_filepath = os.path.join(media_directory, filename)
        json_filepath = find_json_for_media(filename, all_files, media_directory)

        if json_filepath:
            print(f"\nProcessing '{filename}' with JSON '{os.path.basename(json_filepath)}'...")
            try:
                with open(json_filepath, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)

                timestamp = None
                if 'photoTakenTime' in metadata and 'timestamp' in metadata['photoTakenTime']:
                    timestamp = int(metadata['photoTakenTime']['timestamp'])
                    dt_object = datetime.fromtimestamp(timestamp)
                    
                    file_ext = filename.lower().split('.')[-1]

                    # --- Handle JPG/JPEG/HEIC images ---
                    if file_ext in ['jpg', 'jpeg', 'heic']:
                        try:
                            image = Image.open(media_filepath)
                            exif_dict = piexif.load(image.info.get('exif', b''))
                        except Exception as e:
                            print(f"  - Could not load image or EXIF data: {e}. Creating new EXIF data.")
                            exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}
                        
                        date_str = dt_object.strftime("%Y:%m:%d %H:%M:%S")
                        exif_dict['Exif'][piexif.ExifIFD.DateTimeOriginal] = date_str.encode('utf-8')
                        exif_dict['Exif'][piexif.ExifIFD.DateTimeDigitized] = date_str.encode('utf-8')
                        exif_dict['0th'][piexif.ImageIFD.DateTime] = date_str.encode('utf-8')
                        print(f"  - Found and set EXIF date to: {date_str}")
                        
                        if 'geoData' in metadata and 'latitude' in metadata['geoData'] and metadata['geoData']['latitude'] != 0.0:
                            lat = metadata['geoData']['latitude']
                            lon = metadata['geoData']['longitude']
                            exif_dict = set_gps_location(exif_dict, lat, lon)
                            print(f"  - Found and set GPS to: Lat {lat}, Lon {lon}")
                        
                        exif_bytes = piexif.dump(exif_dict)
                        
                        if file_ext in ['jpg', 'jpeg']:
                             piexif.insert(exif_bytes, media_filepath)
                        elif file_ext == 'heic':
                            image.save(media_filepath, exif=exif_bytes)


                    # --- Handle Video/GIF files with Mutagen ---
                    elif file_ext in ['mp4', 'mkv', 'gif', 'flv']:
                        video = mutagen.File(media_filepath)
                        if video is None:
                            print(f"  - Could not process file with mutagen. Skipping.")
                            skipped_files += 1
                            continue
                        
                        utc_dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                        date_str_iso = utc_dt.isoformat()
                        
                        if video.tags is None:
                            video.add_tags()
                        
                        # Use a generic date tag that works for many formats
                        tag_key = 'creation_time' if file_ext == 'flv' else 'DATE_RECORDED'
                        video.tags[tag_key] = date_str_iso
                        video.save()
                        print(f"  - Found and set {file_ext.upper()} creation date to: {date_str_iso}")

                    if timestamp:
                        os.utime(media_filepath, (timestamp, timestamp))
                        print(f"  - Set file 'Date modified' to match 'Date taken'.")
                    
                    shutil.move(media_filepath, os.path.join(completed_directory, filename))
                    print(f"  - Moved '{filename}' to 'Completed' folder.")
                    
                    processed_files += 1
                    used_json_files.append(json_filepath)
                    print(f"  - Successfully merged metadata into '{filename}'")

                else:
                    print("  - No 'photoTakenTime' found in JSON. Skipping metadata update.")
                    skipped_files += 1

            except Exception as e:
                print(f"  - An unexpected error occurred while processing '{filename}': {e}")
                skipped_files += 1
        else:
            print(f"\nSkipping '{filename}': No corresponding JSON file found.")
            skipped_files += 1
    
    print("\n--------------------")
    print("      COMPLETE      ")
    print("--------------------")
    print(f"Processed: {processed_files} files")
    print(f"Skipped:   {skipped_files + len(raw_files)} files (including RAW files)")

    if used_json_files:
        print("\n")
        while True:
            delete_choice = input(f"Do you want to delete the {len(used_json_files)} successfully used JSON files? (yes/no): ").lower().strip()
            if delete_choice in ['yes', 'y', 'no', 'n']:
                break
            else:
                print("Invalid input. Please enter 'yes' or 'no'.")

        if delete_choice in ['yes', 'y']:
            deleted_count = 0
            print("\nDeleting JSON files...")
            for json_file in used_json_files:
                try:
                    os.remove(json_file)
                    print(f"  - Deleted '{os.path.basename(json_file)}'")
                    deleted_count += 1
                except OSError as e:
                    print(f"  - Error deleting '{os.path.basename(json_file)}': {e}")
            print(f"\nSuccessfully deleted {deleted_count} JSON files.")
        else:
            print("\nSkipping JSON file deletion.")


if __name__ == '__main__':
    main()
