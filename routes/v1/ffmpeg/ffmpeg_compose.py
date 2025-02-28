import os
import logging
from flask import Blueprint, request, jsonify
from app_utils import *
from services.authentication import authenticate
from services.cloud_storage import upload_file
import subprocess
import json
from services.file_management import download_file

v1_ffmpeg_compose_bp = Blueprint('v1_ffmpeg_compose', __name__)
logger = logging.getLogger(__name__)

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
        'jpeg': 'jpeg',
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

def process_ffmpeg_compose(data, job_id, webhook_url, record_id):
    output_filenames = []

    # Build FFmpeg command
    command = ["ffmpeg"]

    # Add global options
    for option in data.get("global_options", []):
        command.append(option["option"])
        if "argument" in option and argument is not None:
            command.append(str(option["argument"]))

    # Add inputs
    for input_data in data["inputs"]:
        if "options" in input_data:
            for option in input_data["options"]:
                command.append(option["option"])
                if "argument" in option and argument is not None:
                    command.append(str(option["argument"]))
        input_path = download_file(input_data["file_url"], STORAGE_PATH)
        command.extend(["-i", input_path])

    # Add filters
    if data.get("filters"):
        filter_complex = ";".join(filter_obj["filter"] for filter_obj in data["filters"])
        command.extend(["-filter_complex", filter_complex])

    # Add outputs
    for i, output in enumerate(data["outputs"]):
        format_name = None
        for option in output["options"]:
            if option["option"] == "-f":
                format_name = option.get("argument")
        if format_name is None:
            extension = 'mp4'
        else:
            extension = get_extension_from_format(format_name)
        output_filename = os.path.join(STORAGE_PATH, f"{job_id}_output_{i}.{extension}")
        output_filenames.append(output_filename)

        for option in output["options"]:
            command.append(option["option"])
            if option["argument"] in option and argument is not None:
                command.append(str(option["argument"]))
        command.append(output_filename)

    # Execute FFmpeg command
    try:
        logger.info(f"Executing FFmpeg command: {' '.join(command)}")
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        logger.info(f"FFmpeg command output: {result.stdout}")
        logger.error(f"FFmpeg command error: {result.stderr}")
    except subprocess.CalledProcessError as e:
        raise Exception(f"FFmpeg command failed: {e.stderr} Command: {' '.join(command)}")

    # Clean up input files
    for input_data in data["inputs"]:
        input_path = os.path.join(STORAGE_PATH, os.path.basename(input_data["file_url"]))
        if os.path.exists(input_path):
            os.remove(input_path)

    # Get metadata if requested
    metadata = []
    if data.get("metadata"):
        for output_filename in output_filenames:
            metadata_result = get_metadata(output_filename, data["metadata"], job_id, record_id)
            metadata.append(metadata_result)

    return output_filenames, metadata

@v1_ffmpeg_compose_bp.route('/v1/ffmpeg/compose', methods=['POST'])
@authenticate
@validate_payload({
    "type": "object",
    "properties": {
        "inputs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "file_url": {"type": "string", "format": "uri"},
                    "options": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "option": {"type": "string"},
                                "argument": {"type": ["string", "number", "null"]}
                            },
                            "required": ["option"]
                        }
                    }
                },
                "required": ["file_url"]
            },
            "minItems": 1
        },
        "filters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "filter": {"type": "string"}
                },
                "required": ["filter"]
            }
        },
        "outputs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "options": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "option": {"type": "string"},
                                "argument": {"type": ["string", "number", "null"]}
                            },
                            "required": ["option"]
                        }
                    }
                },
                "required": ["options"]
            },
            "minItems": 1
        },
        "global_options": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "option": {"type": "string"},
                    "argument": {"type": ["string", "number", "null"]}
                },
                "required": ["option"]
            }
        },
        "metadata": {
            "type": "object",
            "properties": {
                "thumbnail": {"type": "boolean"},
                "filesize": {"type": "boolean"},
                "duration": {"type": "boolean"},
                "bitrate": {"type": "boolean"},
                "encoder": {"type": "boolean"}
            }
        },
        "webhook_url": {"type": "string", "format": "uri"},
        "id": {"type": "string"}
    },
    "required": ["inputs", "outputs"],
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=False)
def ffmpeg_api(job_id, data):
    logger.info(f"Job {job_id}: Received flexible FFmpeg request")

    webhook_url = data.get("webhook_url")
    record_id = data.get("id")

    try:
        output_filenames, metadata = process_ffmpeg_compose(data, job_id, webhook_url, record_id)
        
        # Upload output files to GCP and create result array
        output_urls = []
        for i, output_filename in enumerate(output_filenames):
            if os.path.exists(output_filename):
                upload_url = upload_file(output_filename)
                output_info = {"file_url": upload_url}
                
                if metadata and i < len(metadata):
                    output_metadata = metadata[i]
                    if 'thumbnail' in output_metadata:
                        thumbnail_path = output_metadata['thumbnail']
                        if os.path.exists(thumbnail_path):
                            thumbnail_url = upload_file(thumbnail_path)
                            del output_metadata['thumbnail']
                            output_metadata['thumbnail_url'] = thumbnail_url
                            os.remove(thumbnail_path)  # Clean up local thumbnail file
                    output_info.update(output_metadata)
                
                output_urls.append(output_info)
                os.remove(output_filename)  # Clean up local output file after upload
            else:
                raise Exception(f"Expected output file {output_filename} not found")

        from services.webhook import trigger_webhook
        trigger_webhook(webhook_url, record_id, output_urls)

        return output_urls, "/v1/ffmpeg/compose", 200
        
    except Exception as e:
        logger.error(f"Job {job_id}: Error processing FFmpeg request - {str(e)}")
        return str(e), "/v1/ffmpeg/compose", 500
