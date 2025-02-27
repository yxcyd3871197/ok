import requests
import json
import logging

logger = logging.getLogger(__name__)

import urllib.parse

def trigger_webhook(webhook_url, record_id, data):
    """
    Triggers a webhook with the given URL, record ID, and data.
    """
    if not webhook_url:
        logger.warning("Webhook URL is not provided. Skipping webhook trigger.")
        return

    # Extract record_id from webhook_url if it exists
    parsed_url = urllib.parse.urlparse(webhook_url)
    query_params = urllib.parse.parse_qs(parsed_url.query)
    record_id_from_url = query_params.get('record_id', [None])[0]

    payload = {
        "record_id": record_id_from_url or record_id,  # Use record_id from URL if available, otherwise use the provided record_id
        "data": data
    }

    headers = {'Content-type': 'application/json'}

    try:
        response = requests.post(webhook_url, data=json.dumps(payload), headers=headers)
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
        logger.info(f"Webhook triggered successfully. Status code: {response.status_code}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to trigger webhook: {e}")
