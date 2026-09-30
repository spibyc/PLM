"""Controlled file storage: content-addressed, write-once, SHA-256 verified."""
import hashlib
import os
import re
import tempfile
import unicodedata
import uuid
import zipfile
from pathlib import Path
from typing import BinaryIO

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.context import Actor
from app.core.config import get_settings
from app.core.errors import DomainError, NotFound
from app.models import Attachment, FileObject
from app.services import audit

# extension -> acceptable detected MIME prefixes
ALLOWED: dict[str, tuple[str, ...]] = {
    ".zip": ("application/zip", "application/x-zip"),
    ".pdf": ("application/pdf",),
    ".png": ("image/png",),
    ".jpg": ("image/jpeg",), ".jpeg": ("image/jpeg",),
    ".kicad_sym": ("text/",), ".kicad_mod": ("text/",), ".lib": ("text/",),
    ".step": ("text/", "model/", "application/octet-stream"), ".stp": ("text/", "model/", "application/octet-stream"),
    ".wrl": ("text/", "model/"),
    ".txt": ("text/",), ".csv": ("text/", "application/csv"), ".md": ("text/",),
    ".cir": ("text/",), ".sp": ("text/",), ".spice": ("text/",), ".ibs": ("text/",),
    ".docx": ("application/vnd.openxmlformats", "application/zip"),
    ".xlsx": ("application/vnd.openxmlformats", "application/zip"),
    ".pptx": ("application/vnd.openxmlformats", "application/zip"),
    ".odt": ("application/vnd.oasis.opendocument", "application/zip"),
    ".ods": ("application/vnd.oasis.opendocument", "application/zip"),
}
DOC_KINDS = ("gerbers", "kicad_project", "datasheet", "kicad_symbol", "kicad_footprint", "model_3d", "drawing", "simulation_model",
             "application_note", "qualification", "compliance_declaration", "certificate",
             "certificate_of_conformance", "inspection_record", "other")


def sanitize_filename(name: str) -> str:
    name = unicodedata.normalize("NFC", name or "")
    name = name.replace("\\", "/").split("/")[-1]
    name = re.sub(r"[\x00-\x1f\x7f]", "", name)
    name = re.sub(r'[<>:"|?*]', "_", name).strip(" .")
    if not name:
        raise DomainError("Invalid filename", "bad_filename")
    stem, dot, ext = name.rpartition(".")
    if dot and len(name) > 200:
        name = stem[: 200 - len(ext) - 1] + "." + ext
    return name[:200]


def _ext(name: str) -> str:
    low = name.lower()
    for e in sorted(ALLOWED, key=len, reverse=True):
        if low.endswith(e):
            return e
    return ""


def detect_mime(path: str) -> str:
    try:
        import magic

        return magic.from_file(path, mime=True) or "application/octet-stream"
    except Exception:  # libmagic unavailable -> fail closed on binary types below
        return "application/octet-stream"


def _root() -> Path:
    return Path(get_settings().filestore_path)


def _key(sha: str) -> str:
    return f"objects/sha256/{sha[:2]}/{sha[2:4]}/{sha}"


def store(db: Session, actor: Actor, stream: BinaryIO, filename: str) -> tuple[FileObject, str]:
    safe = sanitize_filename(filename)
    ext = _ext(safe)
    if not ext:
        raise DomainError(f"File type not allowed. Allowed: {', '.join(sorted(ALLOWED))}", "bad_type")
    limit = get_settings().max_upload_mb * 1024 * 1024
    root = _root()
    (root / "tmp").mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256()
    size = 0
    fd, tmp = tempfile.mkstemp(dir=root / "tmp")
    try:
        with os.fdopen(fd, "wb") as out:
            while chunk := stream.read(1024 * 1024):
                size += len(chunk)
                if size > limit:
                    raise DomainError(f"File exceeds maximum size of {get_settings().max_upload_mb} MB", "too_large")
                h.update(chunk)
                out.write(chunk)
        if size == 0:
            raise DomainError("Empty file", "empty")
        mime = detect_mime(tmp)
        if not any(mime.startswith(p) for p in ALLOWED[ext]):
            raise DomainError(f"File content ({mime}) does not match extension {ext}", "mime_mismatch")
        if ext == ".zip" and not zipfile.is_zipfile(tmp):
            raise DomainError("File is not a valid ZIP archive", "bad_archive")
        sha = h.hexdigest()
        fo = db.execute(select(FileObject).where(FileObject.sha256 == sha)).scalar_one_or_none()
        if fo is None:
            dest = root / _key(sha)
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                os.chmod(tmp, 0o440)
                os.replace(tmp, dest)
            fo = FileObject(sha256=sha, size_bytes=size, mime_type=mime, storage_key=_key(sha),
                            created_by=actor.user_id)
            db.add(fo)
            db.flush()
        return fo, safe
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def attach(db: Session, actor: Actor, object_type: str, object_id: uuid.UUID, stream: BinaryIO, filename: str,
           doc_kind: str, description: str | None, label: str | None) -> Attachment:
    if doc_kind not in DOC_KINDS:
        raise DomainError(f"Unknown document kind '{doc_kind}'", "validation")
    fo, safe = store(db, actor, stream, filename)
    a = Attachment(object_type=object_type, object_id=object_id, file_object_id=fo.id, filename=safe,
                   doc_kind=doc_kind, description=description, uploaded_by=actor.user_id)
    db.add(a)
    db.flush()
    audit.record(db, actor, "upload", object_type, object_id, label,
                 after={"attachment_id": a.id, "filename": safe, "doc_kind": doc_kind, "sha256": fo.sha256,
                        "size_bytes": fo.size_bytes, "mime_type": fo.mime_type})
    return a


def open_attachment(db: Session, actor: Actor, attachment_id: uuid.UUID) -> tuple[Attachment, FileObject, Path]:
    row = db.execute(select(Attachment, FileObject).join(FileObject, FileObject.id == Attachment.file_object_id)
                     .where(Attachment.id == attachment_id)).one_or_none()
    if row is None:
        raise NotFound("Attachment")
    a, fo = row
    path = _root() / fo.storage_key
    if not path.exists():
        raise DomainError("Stored file is missing. Run integrity verification.", "file_missing", 500)
    audit.record(db, actor, "download", a.object_type, a.object_id, a.filename,
                 after={"attachment_id": a.id, "sha256": fo.sha256})
    return a, fo, path


def verify_integrity(db: Session, actor: Actor) -> dict:
    root = _root()
    findings = []
    ok = 0
    known = set()
    for fo in db.execute(select(FileObject).order_by(FileObject.created_at)).scalars():
        known.add(fo.storage_key)
        p = root / fo.storage_key
        if not p.exists():
            result = "MISSING"
        elif p.stat().st_size != fo.size_bytes:
            result = "SIZE_MISMATCH"
        else:
            h = hashlib.sha256()
            with open(p, "rb") as f:
                while chunk := f.read(1024 * 1024):
                    h.update(chunk)
            result = "OK" if h.hexdigest() == fo.sha256 else "HASH_MISMATCH"
        fo.last_verified_at = func.clock_timestamp()
        fo.last_verify_result = result
        if result == "OK":
            ok += 1
        else:
            findings.append({"sha256": fo.sha256, "storage_key": fo.storage_key, "result": result})
    objdir = root / "objects"
    if objdir.exists():
        for p in objdir.rglob("*"):
            if p.is_file():
                key = str(p.relative_to(root))
                if key not in known:
                    findings.append({"sha256": p.name, "storage_key": key, "result": "ORPHAN"})
    summary = {"files_ok": ok, "findings": findings, "checked": ok + len([f for f in findings if f["result"] != "ORPHAN"])}
    audit.record(db, actor, "integrity_verification", "file_store", None, "file store",
                 after={"files_ok": ok, "problems": len(findings)})
    return summary
