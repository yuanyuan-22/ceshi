import os
import zipfile
from xml.etree import ElementTree as ET


class UploadedFileReadError(ValueError):
    pass


DOCX_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

def read_text_file(path: str) -> str:
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

def _local_name(tag: str) -> str:
    return str(tag or "").rsplit("}", 1)[-1]

def _read_docx_text_from_zip(path: str) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            xml_bytes = archive.read("word/document.xml")
    except FileNotFoundError as exc:
        raise UploadedFileReadError(f"uploaded file not found: {path}") from exc
    except zipfile.BadZipFile as exc:
        raise UploadedFileReadError("invalid DOCX file") from exc
    except KeyError as exc:
        raise UploadedFileReadError("invalid DOCX file: missing word/document.xml") from exc

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise UploadedFileReadError("invalid DOCX file: malformed XML") from exc

    paragraphs = []
    for para in root.findall(".//w:body/w:p", DOCX_NS):
        parts = []
        for node in para.iter():
            tag = _local_name(node.tag)
            if tag == "t" and node.text:
                parts.append(node.text)
            elif tag == "tab":
                parts.append("\t")
            elif tag in {"br", "cr"}:
                parts.append("\n")
        text = "".join(parts).strip()
        if text:
            paragraphs.append(text)

    return "\n".join(paragraphs)

def read_docx_text(path: str) -> str:
    try:
        from docx import Document
    except Exception:
        return _read_docx_text_from_zip(path)

    try:
        doc = Document(path)
    except Exception:
        return _read_docx_text_from_zip(path)

    text = []
    for para in doc.paragraphs:
        text.append(para.text)
    return "\n".join(text)

def extract_text_from_uploaded(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".txt":
        return read_text_file(file_path)
    if ext == ".docx":
        return read_docx_text(file_path)
    # fallback: try as text
    try:
        return read_text_file(file_path)
    except Exception:
        return ""
