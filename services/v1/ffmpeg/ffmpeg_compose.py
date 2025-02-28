import os
import subprocess
import json
from services.file_management import download_file

STORAGE_PATH = "/tmp/"

def get_extension_from_format(format_name):
    # Mapping of common format names to file extensions
    format_to_extension = {
        'mp4': 'mp4',
        'mov': 'mov',
        'avi': 'avi',
        'mkv': 'mkv',
        'webm': 'webm',
        'gif': 'gif',
        'apng': 'apng',
        'jpg': 'jpg',
        'jpeg': 'jpg',
        'png': 'png',
        'image2': 'png',  # Assume png for image2 format
        'rawvideo': 'raw',
        'mp3': 'mp3',
        'wav': 'wav',
        'aac': 'aac',
        'flac': 'flac',
        'ogg': 'ogg'
    }
    return format_to_extension.get(format_name.lower(), 'mp4')  # Default to mp4 if unknown

def get_metadata(filename, metadata_requests, job_id, record_id):
    metadata = {}
    metadata['record_id'] = record_id
    if metadata_requests.get('thumbnail'):
        thumbnail_filename = f"{os.path.splitext(filename)[0]}_thumbnail.jpg"
        thumbnail_command = [
            '/usr/local/bin/ffmpeg',
            '-i', filename,
            '-vf', 'select=eq(n\,0)',
            '-vframes', '1',
            thumbnail_filename
        ]
        try:
            subprocess.run(thumbnail_command, check=True, capture_output=True, text=True)
            if os.path.exists(thumbnail_filename):
                metadata['thumbnail'] = thumbnail_filename  # Return local path instead of URL
        except subprocess.CalledProcessError as e:
            print(f"Thumbnail generation failed: {e.stderr}")

    if metadata_requests.get('filesize'):
        metadata['filesize'] = os.path.getsize(filename)

    if metadata_requests.get('encoder') or metadata_requests.get('duration') or metadata_requests.get('bitrate'):
        ffprobe_command = [
            '/usr/local/bin/ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            filename
        ]
        result = subprocess.run(ffprobe_command, capture_output=True, text=True)
        probe_data = json.loads(result.stdout)
        
        if metadata_requests.get('duration'):
            metadata['duration'] = float(probe_data['format']['duration'])
        if metadata_requests.get('bitrate'):
            metadata['bitrate'] = int(probe_data['format']['bit_rate'])
        
        if metadata_requests.get('encoder'):
            metadata['encoder'] = {}
            for stream in probe_data['streams']:
                if stream['codec_type'] == 'video':
                    metadata['encoder']['video'] = stream.get('codec_name', 'unknown')
                elif stream['codec_type'] == 'audio':
                    metadata['encoder']['audio'] = stream.get('codec_name', 'unknown')

    return metadata