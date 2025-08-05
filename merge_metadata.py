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

import os
import json
import piexif
import mutagen.mp4
from datetime import datetime, timezone

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
    Finds the corresponding JSON file for a given media file.
    Google Takeout can have several naming conventions.
    """
    base_name, _ = os.path.splitext(media_filename)
    
    potential_exact_matches = [
        f"{media_filename}.json",
        f"{base_name}.json"
    ]

    for json_name in potential_exact_matches:
        if json_name in all_files:
            return os.path.join(directory, json_name)

    for f in all_files:
        if f.startswith(media_filename) and f.lower().endswith('.json'):
            return os.path.join(directory, f)

    for f in all_files:
        if f.startswith(base_name) and f.lower().endswith('.json'):
            return os.path.join(directory, f)

    return None

def main():
    """
    Main function to process media files in the specified directory.
    """
    media_directory = '.'

    print(f"Starting metadata merge in directory: {os.path.abspath(media_directory)}")
    processed_files = 0
    skipped_files = 0
    used_json_files = [] 

    try:
        all_files = os.listdir(media_directory)
    except FileNotFoundError:
        print(f"Error: Directory not found at '{media_directory}'. Please check the path.")
        return

    media_files = [f for f in all_files if f.lower().endswith(('.jpg', '.jpeg', '.mp4'))]

    if not media_files:
        print("No JPG, JPEG, or MP4 files found in the directory.")
        return

    print(f"Found {len(media_files)} media files to process.")

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
                    
                    # --- Handle JPG files ---
                    if filename.lower().endswith(('.jpg', '.jpeg')):
                        try:
                            exif_dict = piexif.load(media_filepath)
                        except (piexif.InvalidImageDataError, ValueError):
                            print(f"  - No valid EXIF data in '{filename}'. Creating new EXIF data.")
                            exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}
                        
                        date_str = dt_object.strftime("%Y:%m:%d %H:%M:%S")
                        exif_dict['Exif'][piexif.ExifIFD.DateTimeOriginal] = date_str.encode('utf-8')
                        exif_dict['Exif'][piexif.ExifIFD.DateTimeDigitized] = date_str.encode('utf-8')
                        exif_dict['0th'][piexif.ImageIFD.DateTime] = date_str.encode('utf-8')
                        print(f"  - Found and set EXIF date to: {date_str}")
                        
                        if 'geoData' in metadata and metadata['geoData']['latitude'] != 0.0:
                            lat = metadata['geoData']['latitude']
                            lon = metadata['geoData']['longitude']
                            exif_dict = set_gps_location(exif_dict, lat, lon)
                            print(f"  - Found and set GPS to: Lat {lat}, Lon {lon}")
                        
                        exif_bytes = piexif.dump(exif_dict)
                        piexif.insert(exif_bytes, media_filepath)

                    # --- Handle MP4 files ---
                    elif filename.lower().endswith('.mp4'):
                        video = mutagen.mp4.MP4(media_filepath)
                        # The '\xa9day' atom stores the creation date in ISO 8601 format.
                        utc_dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                        date_str_iso = utc_dt.isoformat()
                        video['\xa9day'] = date_str_iso
                        video.save()
                        print(f"  - Found and set MP4 creation date to: {date_str_iso}")

                    # Update the file's modified date for both types
                    if timestamp:
                        os.utime(media_filepath, (timestamp, timestamp))
                        print(f"  - Set file 'Date modified' to match 'Date taken'.")
                    
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
    print(f"Skipped:   {skipped_files} files")

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
