# email_helpers.py
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.base import MIMEBase
from email import encoders

def build_email_message(
    sender: str,
    to_email: str,
    cc_list: list,
    subject: str,
    html_body: str,
    file_bytes: bytes = None,
    filename: str = None,
    is_high_utilization: bool = False
) -> MIMEMultipart:
    """
    Constructs a MIMEMultipart message.
    If is_high_utilization and file_bytes are provided, wraps content in 
    multipart/related so the image displays inline with Content-ID: <utilization_snapshot_img>.
    """
    if file_bytes and is_high_utilization:
        # Use multipart/related for inline images
        msg = MIMEMultipart('related')
        msg['From'] = sender
        msg['To'] = to_email
        msg['Cc'] = ", ".join(cc_list) if cc_list else ""
        msg['Subject'] = subject

        # Attach HTML body
        msg.attach(MIMEText(html_body, 'html'))

        # Embed Image Inline
        try:
            image_part = MIMEImage(file_bytes)
            image_part.add_header('Content-ID', '<utilization_snapshot_img>')
            image_part.add_header('Content-Disposition', 'inline', filename=filename or "snapshot.png")
            msg.attach(image_part)
        except Exception as img_err:
            print(f"Error embedding inline image: {str(img_err)}")
    else:
        # Standard MIME structure for non-inline emails or regular attachments
        msg = MIMEMultipart('mixed')
        msg['From'] = sender
        msg['To'] = to_email
        msg['Cc'] = ", ".join(cc_list) if cc_list else ""
        msg['Subject'] = subject

        # Attach HTML body
        msg.attach(MIMEText(html_body, 'html'))

        # Regular file attachment (if any)
        if file_bytes and filename:
            try:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(file_bytes)
                encoders.encode_base64(part)
                part.add_header('Content-Disposition', f'attachment; filename="{filename}"')
                msg.attach(part)
            except Exception as att_err:
                print(f"Error attaching file: {str(att_err)}")

    return msg
