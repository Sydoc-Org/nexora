import os
import sys

import requests

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from nx_lib.config import (
    GRAPH_CLIENT_ID,
    GRAPH_CLIENT_SECRET,
    GRAPH_PASSWORD,
    GRAPH_TENANT_ID,
    GRAPH_USERNAME,
)
from nx_lib.db import engine_nexora_db


def send_release_notice(email, full_name):
    def get_access_token():
        uri = f"https://login.microsoftonline.com/{GRAPH_TENANT_ID}/oauth2/v2.0/token"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        body = {
            "client_id": GRAPH_CLIENT_ID,
            "username": GRAPH_USERNAME,
            "password": GRAPH_PASSWORD,
            "grant_type": "password",
            "scope": "Mail.Send",
            "client_secret": GRAPH_CLIENT_SECRET,
        }
        try:
            response = requests.post(uri, headers=headers, data=body, timeout=10)
            return response.json()["access_token"]
        except Exception as e:
            print(e)

    uri = "https://graph.microsoft.com/v1.0/me/sendMail"
    access_token = get_access_token()
    headers = {"Authorization": f"Bearer {access_token}"}

    font_family = "font-family: 'Inter', Helvetica, Arial, sans-serif;"
    container_style = "max-width: 600px; margin: 0 auto; background-color: #fefdfb; padding: 20px;"
    button_style = (
        "background-color: #2563eb; color: #fefdfb; padding: 12px 24px; "
        "text-decoration: none; border-radius: 8px; font-weight: bold; "
        "display: inline-block; mso-padding-alt: 12px 24px;"
    )
    link_style = "color: #4b5563; text-decoration: none; margin-right: 15px; font-size: 14px;"
    text_style = "color: #4b5563; line-height: 1.6; font-size: 16px;"

    logo_url = "https://nexora.sydoc.ch/nexora/static/images/nexora-logo.gif"
    logo_banner_url = "https://nexora.sydoc.ch/nexora/static/images/sydoc-logo-banner.png"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Nexora Update</title>
    </head>
    <body style="margin: 0; padding: 0; background-color: #f3f4f6; {font_family}">

        <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #f3f4f6; padding: 20px;">
            <tr>
                <td align="center">

                    <table width="600" border="0" cellspacing="0" cellpadding="0" style="{container_style} border-radius: 8px;">

                        <tr>
                            <td align="center" style="padding-bottom: 20px;">
                                <a href="https://nexora.sydoc.ch"><img src="{logo_url}" alt="Nexora Logo" width="600" style="display: block;"></a>
                            </td>
                        </tr>

                        <tr>
                            <td align="center" style="padding-bottom: 60x;">
                                <a href="https://sydoc.ch/ueber-sydoc/news/" style="{link_style}">News</a>
                                <a href="https://sydoc.ch/ueber-sydoc/kundenmagazin/" style="{link_style}">Magazin</a>
                                <a href="https://sydoc.ch/ueber-sydoc/team/" style="{link_style}">Team</a>
                                <a href="mailto:support.helpdesk@sydoc.ch" style="{link_style}">Support</a>
                            </td>
                        </tr>

                        <tr>
                            <td style="padding: 0 10px;">
                                <h2 style="color: #374151; margin-top: 0;">Guten Tag {full_name},</h2>
                                <p style="{text_style}">
                                    Wir freuen uns, dass <strong>nexora 2.3.3</strong> jetzt online ist!
                                </p>
                                <p style="{text_style}">
                                Mit diesem Update führen wir eine neue Chat-Funktion ein, die die Kommunikation innerhalb von nexora deutlich vereinfacht.
                                    Zusätzlich könnt ihr nun Arbeitselemente direkt im Chat referenzieren, indem ihr die entsprechende ID im Format
                                    <strong>"/workitemid"</strong>
                                    eingebt.
                                    Weitere Verbesserungen und Optimierungen sind ebenfalls Teil dieses Updates, um eure Nutzungserfahrung noch effizienter und angenehmer zu gestalten.
                                </p>
                                <p style="{text_style}">
                                    Viel Spass beim Ausprobieren! <br>
                                    Bei Fragen stehen wir euch wie immer gerne zur Verfügung.
                                </p>

                                <p style="{text_style}">
                                    Freundliche Grüsse <br>
                                    Ben Streich
                                </p>
                            </td>
                        </tr>

                        <tr>
                            <td align="left" style="padding: 30px 10px;">
                                <a href="https://nexora.sydoc.ch/nexora/login" style="{button_style}">
                                    Login
                                </a>
                            </td>
                        </tr>




                        <tr>
                            <td align="center" style="padding-top: 30px; border-top: 1px solid #e5e7eb;">
                                <a href="https://sydoc.ch"><img src="{logo_banner_url}" alt="Sydoc Logo" width="600" style="display: block;"></a>                            </td>
                        </tr>

                        <tr>
                            <td align="center" style="padding-top: 15px;">
                                <p style="font-size: 12px; color: #9ca3af;">
                                    © 2026 Alle Rechte vorbehalten
                                </p>
                            </td>
                        </tr>

                    </table>

                </td>
            </tr>
        </table>
    </body>
    </html>
    """

    try:
        body = {
            "message": {
                "subject": "Update verfügbar: nexora 2.3.3 ist da!",
                "body": {"contentType": "HTML", "content": html_content},
                "toRecipients": [{"emailAddress": {"address": email}}],
            },
            "saveToSentItems": True,
        }

        response = requests.post(uri, headers=headers, json=body, timeout=10)
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False


conn = engine_nexora_db.raw_connection()
cur = conn.cursor()

cur.execute("SELECT Email, Fullname FROM USERS WHERE username <> 'demo.user'")
# cur.execute("SELECT Email, Fullname FROM USERS WHERE username = 'ben.streich'")
rows = cur.fetchall()

# [send_release_notice(row.Email, row.Fullname) for row in rows]
