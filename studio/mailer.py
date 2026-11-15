"""Sending account emails (verify your address, reset your password) over SMTP.

Works with any provider that offers SMTP: Resend, Postmark, Brevo, Amazon SES, Google Workspace and so on. Set
CREATIVECUT_SMTP_HOST, CREATIVECUT_SMTP_PORT (587), CREATIVECUT_SMTP_USER, CREATIVECUT_SMTP_PASSWORD_FILE (a file holding the
password or API key) and CREATIVECUT_MAIL_FROM ("Creative Cut <hello@yourdomain.com>"). Without them nothing is sent and the
link is written to the server log instead, which is enough for running Creative Cut on your own machine."""
import html
import logging
import re
import smtplib
import ssl
import threading
from email.message import EmailMessage
from email.utils import formataddr, make_msgid, parseaddr

from . import config

log = logging.getLogger("creativecut.mail")


def ready() -> bool:
    return bool(config.SMTP_HOST and config.MAIL_FROM)


LOGO = config.ROOT / "web" / "brand" / "logo-email.png"   # PNG: email apps don't show SVG
LOGO_CID = "creativecut-logo"


def theme() -> dict:
    """The site's colours from web/theme.css, so the emails match the pages. Read when the server starts."""
    try:
        css = (config.ROOT / "web" / "theme.css").read_text(encoding="utf-8")
    except OSError:
        css = ""
    return dict(re.findall(r"--c-([a-z0-9-]+)\s*:\s*(#[0-9A-Fa-f]{6})", css))


_T = theme()


def _c(name: str, fallback: str) -> str:
    return _T.get(name, fallback)



def _html(title: str, intro: str, button: str, link: str, outro: str, logo_src: str = "cid:" + LOGO_CID) -> str:
    """The branded email: logo, a white card with the message and one big button, and a quiet footer.
    Tables and inline styles only, because that is what every email app renders the same way."""
    e = html.escape
    site = config.PUBLIC_URL
    bg, brand, deep, ink = _c("bg", "#0B0A24"), _c("brand", "#E8175D"), _c("brand-deep", "#B00F45"), _c("ink", "#15110F")
    font = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light only"><title>{e(title)}</title></head>
<body style="margin:0;padding:0;background:{bg};-webkit-text-size-adjust:100%">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:{bg}">{e(intro)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{bg}"><tr><td align="center" style="padding:36px 14px">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:520px">
    <tr><td style="padding:0 6px 22px"><a href="{e(site)}" style="text-decoration:none">
      <img src="{e(logo_src)}" width="124" height="66" alt="Creative Cut" style="display:block;border:0;width:124px;height:66px"></a></td></tr>
    <tr><td style="background:#FFFFFF;border-radius:18px;border:1px solid #EFDCDC;padding:36px 34px">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
        <tr><td style="font-family:{font};font-size:24px;line-height:1.25;font-weight:700;color:{ink};padding-bottom:12px">{e(title)}</td></tr>
        <tr><td style="font-family:{font};font-size:16px;line-height:1.65;color:#52668F;padding-bottom:28px">{e(intro)}</td></tr>
        <tr><td style="padding-bottom:28px">
          <table role="presentation" cellpadding="0" cellspacing="0"><tr><td style="border-radius:12px;background:{brand}">
            <a href="{e(link)}" style="display:inline-block;padding:14px 28px;font-family:{font};font-size:16px;font-weight:700;color:#FFFFFF;text-decoration:none;border-radius:12px">{e(button)}</a>
          </td></tr></table></td></tr>
        <tr><td style="font-family:{font};font-size:14px;line-height:1.6;color:#6C82AB;padding-bottom:22px">{e(outro)}</td></tr>
        <tr><td style="border-top:1px solid #EFDCDC;padding-top:18px;font-family:{font};font-size:12px;line-height:1.6;color:#7E93BA">
          Button not working? Copy this link into your browser:<br><a href="{e(link)}" style="color:{deep};word-break:break-all">{e(link)}</a></td></tr>
      </table></td></tr>
    <tr><td align="center" style="padding:24px 10px 0;font-family:{font};font-size:12px;line-height:1.7;color:#7E93BA">
      You're getting this because of your Creative Cut account. We only email you about your account.<br>
      <a href="{e(site)}" style="color:#6C82AB;text-decoration:underline">Creative Cut</a> &nbsp;·&nbsp;
      <a href="{e(site)}/privacy" style="color:#6C82AB;text-decoration:underline">Privacy</a> &nbsp;·&nbsp;
      <a href="{e(site)}/terms" style="color:#6C82AB;text-decoration:underline">Terms</a></td></tr>
  </table></td></tr></table></body></html>"""


def preview(title="Confirm your email", intro="Thanks for joining Creative Cut. Confirm this is your email address to start clipping.",
            button="Confirm my email", link=None, outro="The link works for 3 days. If you didn't sign up, you can ignore this email.") -> str:
    """The same email for viewing in a browser: the logo is inlined so it shows without an email app."""
    import base64
    data = "data:image/png;base64," + base64.b64encode(LOGO.read_bytes()).decode() if LOGO.is_file() else ""
    return _html(title, intro, button, link or config.PUBLIC_URL + "/auth/verify?t=example", outro, logo_src=data)


def send(to: str, subject: str, title: str, intro: str, button: str, link: str, outro: str) -> bool:
    """Send in the background. Returns False when no mail service is set up (the link goes to the log)."""
    if not ready():
        if config.HTTPS:      # a real site: a sign-in link must never sit in a log file
            log.warning("Email not set up, so nothing was sent: %s", subject)
        else:                 # on your own computer the link is printed so you can use it
            print(f"[Creative Cut mail] {subject} for {to}: {link}", flush=True)
        return False
    msg = EmailMessage()
    name, addr = parseaddr(config.MAIL_FROM)
    msg["From"] = formataddr((name or "Creative Cut", addr))
    msg["To"] = to
    msg["Subject"] = subject
    msg["Message-ID"] = make_msgid(domain=addr.split("@")[-1] if "@" in addr else None)
    msg.set_content(f"{title}\n\n{intro}\n\n{button}: {link}\n\n{outro}\n")
    msg.add_alternative(_html(title, intro, button, link, outro), subtype="html")
    if LOGO.is_file():   # the logo travels inside the email, so it shows without loading anything from the web
        msg.get_payload()[1].add_related(LOGO.read_bytes(), maintype="image", subtype="png", cid=f"<{LOGO_CID}>",
                                         filename="creativecut.png", disposition="inline")

    def work():
        try:
            if config.SMTP_PORT == 465:
                with smtplib.SMTP_SSL(config.SMTP_HOST, 465, context=ssl.create_default_context(), timeout=20) as s:
                    if config.SMTP_USER:
                        s.login(config.SMTP_USER, config.smtp_password())
                    s.send_message(msg)
            else:
                with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=20) as s:
                    s.starttls(context=ssl.create_default_context())
                    if config.SMTP_USER:
                        s.login(config.SMTP_USER, config.smtp_password())
                    s.send_message(msg)
        except Exception as e:  # noqa: BLE001
            log.error("Could not send %r to %s: %s", subject, to, e)
            print(f"[Creative Cut mail] could not send {subject!r} to {to}: {e}", flush=True)

    threading.Thread(target=work, daemon=True).start()
    return True
