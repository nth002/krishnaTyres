import uuid
import os

from django.conf import settings
from supabase import create_client


supabase = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_SERVICE_KEY
)


# ═════════════════════════════════════════════════════════════════════════════
# GENERIC UPLOAD (used by products, documents, etc.)
# ═════════════════════════════════════════════════════════════════════════════
def upload_image(file, folder, u_id):
    """
    Upload any file to Supabase under `<folder>/<u_id>/<uuid>.<ext>`.

    Returns:
        (signed_url, file_name)
    """
    # Get original file extension
    original_name = file.name
    extension = os.path.splitext(original_name)[1]

    if extension:
        extension = extension.lower()
    else:
        extension = ""

    # Unique filename
    unique_name = f"{uuid.uuid4()}{extension}"

    # Path inside bucket: profile/1/<uuid>.jpg
    file_name = f"{folder}/{u_id}/{unique_name}"

    # Read uploaded file
    file_bytes = file.read()

    # Upload to Supabase
    supabase.storage.from_(
        settings.SUPABASE_BUCKET
    ).upload(
        file_name,
        file_bytes,
        file_options={
            "content-type": file.content_type or "application/octet-stream",
            "cache-control": "3600",
            "upsert": "false"
        }
    )

    # Generate signed URL (valid for 7 days)
    signed_response = supabase.storage.from_(
        settings.SUPABASE_BUCKET
    ).create_signed_url(
        file_name,
        60 * 60 * 24 * 7
    )

    # Handle SDK response variations
    if isinstance(signed_response, dict):
        signed_url = (
            signed_response.get("signedURL")
            or signed_response.get("signedUrl")
        )
    else:
        signed_url = signed_response

    if not signed_url:
        raise Exception("Failed to generate signed file URL")

    return signed_url, file_name


# ═════════════════════════════════════════════════════════════════════════════
# PROFILE-SPECIFIC WRAPPER (new)
# Called by update_profile_image view with just (file, u_id)
# ═════════════════════════════════════════════════════════════════════════════
def upload_profile_image(file, u_id):
    """
    Upload a profile image for a specific user.
    Thin wrapper around upload_image() with folder='profile'.
    """
    return upload_image(file=file, folder="profile", u_id=u_id)


# ═════════════════════════════════════════════════════════════════════════════
# (Optional) Convenience wrappers for other uploads
# ═════════════════════════════════════════════════════════════════════════════
def upload_product_image(file, u_id):
    return upload_image(file=file, folder="product", u_id=u_id)


def upload_document(file, u_id):
    return upload_image(file=file, folder="document", u_id=u_id)