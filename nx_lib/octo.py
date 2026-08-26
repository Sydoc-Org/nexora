"""Octopus runtime API client.

Wraps the auth, document, and configuration services exposed by Octopus.
"""

import base64
import hashlib
import io
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlsplit, urlunsplit

import requests
from flask import current_app
from flask_babel import gettext as _

from . import mapping_config
from .clients import octo_creds_for_domain
from .config import OCTO_DOMAIN
from .extensions import cache
from .field_locations import extract_field_locations, items_of
from .table_locations import extract_table_locations


def get_access_token(domain=None):
    if domain is None:
        domain = OCTO_DOMAIN
    cache_key = f"octo_access_token_{domain}"
    token = cache.get(cache_key)
    if token:
        return token

    client_id, client_secret, grant_type = octo_creds_for_domain(domain)
    url = f"https://{domain}/auth/connect/token"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    body = {
        "grant_type": grant_type,
        "client_id": client_id,
        "client_secret": client_secret,
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
        current_app.logger.error(f"Error fetching access token: {e}")
        return None


def get_workitemdata_param(workitem_id, domain=None):
    if domain is None:
        domain = OCTO_DOMAIN
    url = (
        f"https://{domain}/api/processservice/api/v2.1/processService/WorkItems/{workitem_id}/load"
    )
    access_token = get_access_token(domain)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.get(url=url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        document_id = data.get("DocumentID")
        if not document_id:
            current_app.logger.error(f"Workitem data payload missing DocumentID for {workitem_id}")
            return None

        str_content = json.dumps(data)
        base64_bytes = base64.b64encode(str_content.encode("utf-8"))
        base64_string = base64_bytes.decode("utf-8")
        return base64_string, document_id
    except (requests.exceptions.RequestException, KeyError, ValueError) as e:
        current_app.logger.error(f"Error fetching workitem data for {workitem_id}: {e}")
        return None


def get_index_field_mappings():
    """SourceFieldName -> TargetKey, from the mapping_config registry (#98).

    Kept as the stable seam its hot-path callers (get_extensions_urls_fields
    and friends) import -- only the storage moved. No caching of its own
    anymore: mapping_config.registry() caches upstream (60s, never caches a
    load failure), so the old ``@cache.cached`` here would only re-cache the
    same data for longer and risk pinning a stale/failed {} for an hour, the
    exact bug that decorator was already guarded against."""
    return mapping_config.field_aliases()


def get_extensions_urls_fields(workitemdata, document_id, domain=None, with_tables=False):
    """Fetch the Octopus thin document and return
    ``(extensions, urls, fields, field_sources, table_sources)``.

    ``table_sources`` is always ``[]`` unless ``with_tables=True`` — only the
    document viewer (``api_get_media_info``) opts in, so the larger
    ``WithTables=true`` payload never burdens the scalar-only callers."""
    if domain is None:
        domain = OCTO_DOMAIN
    url = (
        f"https://{domain}/api/documentservice/api/v2.1/documentService/thin/Document/"
        f"{document_id}?WithExtensions=false&WithDocumentStructure=true"
        f"&WithTables={'true' if with_tables else 'false'}&WithDocumentAudits=true&LoadMediaStreams=true"
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
        return [], [], {}, [], []

    urls = []
    extensions = []
    fields = {}
    # Per-leaf-item count of PDF-expanded page slots, in the same order as
    # items_to_process / items_of(doc_json) below. field_locations.py and
    # table_locations.py are deliberately I/O-free (see their module
    # docstrings), so the real PDF page counting -- fetch + pypdfium2, done
    # once per PDF medium in the loop below -- happens here and gets threaded
    # into extract_field_locations/extract_table_locations as pre-computed
    # data, instead of those pure modules re-deriving it (or silently treating
    # PDFs as 0-page media, which used to undercount the offset for any leaf
    # item after a PDF in a mixed PDF+image container).
    pdf_page_counts = []

    field_mapping = get_index_field_mappings()

    # Flatten container documents (Octo "Batch", MS02 MobScnBatch/Dossier/...)
    # to their leaf documents — recursively, via the shared helper — so a parent
    # workitem surfaces the pages + fields that live on its children, at any
    # depth. Single documents and one-level batches are unaffected.
    items_to_process = items_of(doc_json)

    # First pass (no I/O): resolve each item's media list and collect every
    # distinct PDF media URL that needs a page count.
    item_media = []
    pdf_urls_to_count = set()
    for item in items_to_process:
        resolved_media = []
        for media in item.get("Media") or []:
            ext = str(media.get("Extension", "")).lower()
            raw_url = media.get("Url")
            if not raw_url:
                continue
            url = _media_url_for_gateway(raw_url, domain)
            if ext in (".jpg", ".jpeg", ".png", ".tif"):
                resolved_media.append(("img", url, ext))
            elif ext == ".pdf":
                resolved_media.append(("pdf", url, ext))
                pdf_urls_to_count.add(url)
        item_media.append(resolved_media)

    # Counting a PDF's pages means downloading the whole document
    # (pdf_src_bytes) and parsing it -- a container/batch workitem with
    # several PDF media items paid for that sequentially, one at a time,
    # which was the dominant cost behind get_media_info's worst-case latency.
    # Resolve every distinct PDF concurrently instead.
    pdf_page_count_by_url = {}
    if pdf_urls_to_count:
        _app = current_app._get_current_object()

        def _count_pdf(pdf_url):
            with _app.app_context():
                try:
                    return pdf_url, pdf_page_count(pdf_src_bytes(pdf_url, domain))
                except Exception as e:
                    current_app.logger.error(f"pdf expand: {e}")
                    return pdf_url, 0

        with ThreadPoolExecutor(max_workers=min(10, len(pdf_urls_to_count))) as executor:
            futures = [executor.submit(_count_pdf, u) for u in pdf_urls_to_count]
            for future in as_completed(futures):
                pdf_url, n_pages = future.result()
                pdf_page_count_by_url[pdf_url] = n_pages

    # Second pass (no I/O): rebuild urls/extensions in original item/media
    # order using the resolved PDF page counts, and extract fields.
    for item, resolved_media in zip(items_to_process, item_media, strict=True):
        item_pdf_pages = 0
        for kind, url, ext in resolved_media:
            if kind == "img":
                urls.append(url)
                extensions.append(ext)
            else:
                # One PDF media = N page images. Expand into per-page slots so
                # the viewer shows every page; each slot carries its 0-based
                # page in the URL fragment and is rasterised on demand by
                # api_get_media_raw.
                n_pages = pdf_page_count_by_url.get(url, 0)
                for p in range(n_pages):
                    urls.append(f"{url}#page={p}")
                    extensions.append(".pdf")
                item_pdf_pages += n_pages
        pdf_page_counts.append(item_pdf_pages)

        index_fields = item.get("IndexFields") or []
        for field_obj in index_fields:
            source_name = field_obj.get("Name")
            if source_name in field_mapping:
                target_key = field_mapping[source_name]
                field_value = field_obj.get("FieldValue", {}).get("Text")
                if target_key not in fields and field_value is not None:
                    fields[target_key] = field_value

    field_sources = extract_field_locations(doc_json, field_mapping, pdf_page_counts)
    table_sources = extract_table_locations(doc_json, pdf_page_counts) if with_tables else []
    return extensions, urls, fields, field_sources, table_sources


def get_media(url, domain=None):
    if domain is None:
        domain = OCTO_DOMAIN
    access_token = get_access_token(domain)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    response = requests.get(url=url, headers=headers, timeout=10)
    response.raise_for_status()
    return response.content


def _media_url_for_gateway(url, domain):
    """Octo's document service sometimes advertises media-stream URLs on its bare
    internal storage host (e.g. ``https://mobscn02/...``) instead of the gateway
    FQDN we actually reach it at -- that bare host doesn't resolve off the Octo
    network, so the fetch 500s. When the host has no dot it's such an internal
    name: swap it for ``domain`` (the resolvable gateway, which serves the same
    ``/api/documentservice/`` path). URLs that already carry an FQDN are left as
    is. Only the host changes; scheme/path/query/fragment are preserved.
    # ponytail: "no dot == internal host" heuristic; revisit only if some Octo
    # ever serves media from a real, separate FQDN distinct from the gateway."""
    if not domain:
        return url
    parts = urlsplit(url)
    host = parts.hostname or ""
    if not host or "." in host:
        return url
    return urlunsplit((parts.scheme or "https", domain, parts.path, parts.query, parts.fragment))


def pdf_src_bytes(url, domain=None):
    """Raw bytes of a PDF media stream, cached briefly by URL so rendering each
    page doesn't re-download the whole document."""
    key = "pdf_src_" + hashlib.sha1(url.encode("utf-8")).hexdigest()
    cached = cache.get(key)
    if cached is not None:
        return cached
    data = get_media(url, domain)
    cache.set(key, data, timeout=3600)
    return data


def pdf_page_count(pdf_bytes):
    """Page count of a PDF, or 0 if pypdfium2 is unavailable or the bytes don't
    parse. Lazy import so a missing wheel degrades PDF support gracefully (the
    pages just don't appear) instead of breaking this module's import, mirroring
    the psycopg2 graceful-degrade pattern."""
    try:
        import pypdfium2 as pdfium
    except Exception:
        current_app.logger.warning("pypdfium2 not installed -- PDF media pages will not render")
        return 0
    try:
        doc = pdfium.PdfDocument(pdf_bytes)
        try:
            return len(doc)
        finally:
            doc.close()
    except Exception as e:
        current_app.logger.error(f"pdf_page_count: {e}")
        return 0


def render_pdf_page_jpeg(pdf_bytes, page_index, scale=2.0):
    """Render one PDF page to JPEG bytes (RGB). Raises on a bad page index or
    unparseable bytes -- the caller turns that into a 500."""
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(pdf_bytes)
    try:
        bitmap = doc[page_index].render(scale=scale)
        buf = io.BytesIO()
        bitmap.to_pil().convert("RGB").save(buf, format="JPEG", quality=85)
        return buf.getvalue()
    finally:
        doc.close()


@cache.memoize(timeout=86400)
def get_activity_type_name(activity_instance_id: str, domain: str | None = None) -> str:
    # ActivityTypeName is process config, not per-workitem data -- the same
    # activity_instance_id is looked up for every workitem that passed
    # through it, so a day-long timeout (vs. the 5-minute app default) keeps
    # audit-history loading warm instead of re-fetching from Octo repeatedly
    # through the day.
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
        current_app.logger.error(f"Error fetching activity instance {activity_instance_id}: {e}")
        return _("Error fetching activity instance")
