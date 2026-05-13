"""Octopus runtime API client.

Wraps the auth, document, and configuration services exposed by Octopus.
"""

import base64
import json

import requests
from flask import current_app
from flask_babel import gettext as _

from .config import (
    OCTO_CLIENT_ID, OCTO_CLIENT_SECRET, OCTO_DOMAIN, OCTO_GRANT_TYPE,
)
from .db import engineNexoraDB
from .extensions import cache


def get_access_token(domain=None):
    if domain is None:
        domain = OCTO_DOMAIN
    cache_key = f"octo_access_token_{domain}"
    token = cache.get(cache_key)
    if token:
        return token

    url = f"https://{domain}/auth/connect/token"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    body = {
        "grant_type": OCTO_GRANT_TYPE,
        "client_id": OCTO_CLIENT_ID,
        "client_secret": OCTO_CLIENT_SECRET,
    }

    try:
        response = requests.post(url=url, headers=headers, data=body, timeout=10)
        response.raise_for_status()
        data = response.json()

        timeout = data.get("expires_in", 3000) - 60
        token = data["access_token"]
        cache.set(cache_key, token, timeout=timeout)
        return token
    except requests.exceptions.RequestException as e:
        print(f"Error fetching access token: {e}")
        return None


def get_domain_for_workitem(workitem_id):
    return OCTO_DOMAIN


def get_workitemdata_param(workitem_id, domain=None):
    if domain is None:
        domain = OCTO_DOMAIN
    url = f"https://{domain}/api/processservice/api/v2.1/processService/WorkItems/{workitem_id}/load"
    access_token = get_access_token(domain)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    response = requests.get(url=url, headers=headers, timeout=10)
    str_content = json.dumps(response.json())
    base64_bytes = base64.b64encode(str_content.encode("utf-8"))
    base64_string = base64_bytes.decode("utf-8")

    return base64_string, response.json()["DocumentID"]


@cache.cached(timeout=3600, key_prefix="index_field_mappings")
def get_index_field_mappings():
    mapping = {}
    conn = None
    cursor = None
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT SourceFieldName, TargetKey FROM IndexFieldMappings")
        for row in cursor.fetchall():
            mapping[row.SourceFieldName] = row.TargetKey
    except Exception as e:
        current_app.logger.error(f"Failed to load IndexFieldMappings: {e}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
    return mapping


def get_extensions_urls_fields(workitemdata, document_id, domain=None):
    if domain is None:
        domain = OCTO_DOMAIN
    url = (
        f"https://{domain}/api/documentservice/api/v2.1/documentService/thin/Document/"
        f"{document_id}?WithExtensions=false&WithDocumentStructure=true"
        f"&WithTables=false&WithDocumentAudits=true&LoadMediaStreams=true"
    )
    access_token = get_access_token(domain)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "workitemdata": workitemdata,
    }

    try:
        response = requests.get(url=url, headers=headers, timeout=10)
        response.raise_for_status()
        doc_json = response.json()
    except Exception as e:
        current_app.logger.error(f"Error fetching document details: {e}")
        return [], [], {}

    urls = []
    extensions = []
    fields = {}

    field_mapping = get_index_field_mappings()

    if doc_json.get("DocumentType") == "Batch" and doc_json.get("ChildDocuments"):
        items_to_process = doc_json["ChildDocuments"]
    else:
        items_to_process = [doc_json]

    for item in items_to_process:
        media_list = item.get("Media") or []
        for media in media_list:
            ext = str(media.get("Extension", "")).lower()
            if ext in (".jpg", ".jpeg", ".png", ".tif"):
                urls.append(media["Url"])
                extensions.append(ext)

        index_fields = item.get("IndexFields") or []
        for field_obj in index_fields:
            source_name = field_obj.get("Name")
            if source_name in field_mapping:
                target_key = field_mapping[source_name]
                field_value = field_obj.get("FieldValue", {}).get("Text")
                if target_key not in fields and field_value is not None:
                    fields[target_key] = field_value
    return extensions, urls, fields


def get_media(url, domain=None):
    if domain is None:
        domain = OCTO_DOMAIN
    access_token = get_access_token(domain)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    response = requests.get(url=url, headers=headers, timeout=10)
    return response.content


@cache.memoize()
def get_activity_type_name(activity_instance_id: str, domain: str = None) -> str:
    if domain is None:
        domain = OCTO_DOMAIN
    activity_instances_url = (
        f"https://{domain}/api/configurationservice/api/v2.1/configservice/"
        f"ActivityInstances/{activity_instance_id}"
    )
    access_token = get_access_token(domain)
    headers = {"Authorization": f"Bearer {access_token}"}

    try:
        response = requests.get(url=activity_instances_url, headers=headers, timeout=10)
        response.raise_for_status()
        activity_instance_config = response.json()
        return activity_instance_config.get("ActivityTypeName", "Unknown Activity")
    except requests.exceptions.RequestException as e:
        print(f"Error fetching activity instance {activity_instance_id}: {e}")
        return _("Error fetching activity instance")
