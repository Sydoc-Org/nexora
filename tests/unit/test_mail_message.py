"""_build_message assembles the Graph sendMail payload."""

import base64

from nx_lib.mail import _build_message


def test_basic_message_shape():
    m = _build_message("a@b.ch", "Subj", "<p>hi</p>")
    assert m["subject"] == "Subj"
    assert m["body"] == {"contentType": "HTML", "content": "<p>hi</p>"}
    assert m["toRecipients"] == [{"emailAddress": {"address": "a@b.ch"}}]


def test_inline_image_attachment():
    m = _build_message(
        ["a@b.ch"], "S", '<img src="cid:chart">', inline_images=[("chart", b"\x89PNG", "image/png")]
    )
    att = m["attachments"][0]
    assert att["isInline"] is True
    assert att["contentId"] == "chart"
    assert att["@odata.type"] == "#microsoft.graph.fileAttachment"
    assert base64.b64decode(att["contentBytes"]) == b"\x89PNG"


def test_file_and_inline_attachments_combine():
    m = _build_message(
        ["a@b.ch"],
        "S",
        "x",
        attachments=[("r.xlsx", b"PK", "application/zip")],
        inline_images=[("chart", b"\x89PNG", "image/png")],
    )
    names = [a.get("name") for a in m["attachments"]]
    assert "r.xlsx" in names
    assert sum(1 for a in m["attachments"] if a.get("isInline")) == 1
