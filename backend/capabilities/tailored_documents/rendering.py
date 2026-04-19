import os
import shutil
import subprocess
import zipfile
from copy import deepcopy
from pathlib import Path
from typing import Dict, List

from backend.config.job_seeker import cfg_str, load_job_seeker_config, normalize_windows_env_path

from .common import sanitize_filename
from .generation import format_header_location


DEFAULT_LANGUAGES = [
    "Arabic \u2014 Native",
    "English \u2014 C1",
    "German \u2014 B1/B2",
]

CV_TEMPLATE_PRESETS = {
    "classic": {
        "id": "classic",
        "label": "Classic",
        "description": "Traditional single-column CV with strong dividers.",
        "heading_case": "upper",
        "base_font_size": 10.5,
        "header_font_size": 12.0,
        "divider_weight": "6",
        "photo_width": 1.5,
        "top_offset_inches": 0.45,
    },
    "modern": {
        "id": "modern",
        "label": "Modern",
        "description": "Crisper spacing and accent-led section styling.",
        "heading_case": "title",
        "base_font_size": 10.8,
        "header_font_size": 12.5,
        "divider_weight": "10",
        "photo_width": 1.45,
        "top_offset_inches": 0.35,
    },
    "compact": {
        "id": "compact",
        "label": "Compact",
        "description": "Tighter spacing for concise one-page applications.",
        "heading_case": "upper",
        "base_font_size": 10.0,
        "header_font_size": 11.5,
        "divider_weight": "4",
        "photo_width": 1.25,
        "top_offset_inches": 0.35,
    },
    "europass": {
        "id": "europass",
        "label": "EuroPass-style",
        "description": "Structured section headers with softer neutral styling.",
        "heading_case": "title",
        "base_font_size": 10.2,
        "header_font_size": 11.8,
        "divider_weight": "8",
        "photo_width": 1.35,
        "top_offset_inches": 0.4,
    },
}

CV_COLOR_SCHEMES = {
    "classic_navy": {
        "id": "classic_navy",
        "label": "Classic Navy",
        "primary": "1F3A5F",
        "accent": "2EC4B6",
        "surface": "EAF3FF",
    },
    "ocean_teal": {
        "id": "ocean_teal",
        "label": "Ocean Teal",
        "primary": "006B5F",
        "accent": "14B8A6",
        "surface": "E5FFFB",
    },
    "forest": {
        "id": "forest",
        "label": "Forest",
        "primary": "2F5D50",
        "accent": "8AA06F",
        "surface": "F0F7F3",
    },
    "slate": {
        "id": "slate",
        "label": "Slate",
        "primary": "334155",
        "accent": "60A5FA",
        "surface": "EEF2FF",
    },
    "burgundy": {
        "id": "burgundy",
        "label": "Burgundy",
        "primary": "7C2D12",
        "accent": "EA580C",
        "surface": "FFF1EB",
    },
    "charcoal": {
        "id": "charcoal",
        "label": "Charcoal",
        "primary": "111827",
        "accent": "6B7280",
        "surface": "F3F4F6",
    },
}

CV_FONT_OPTIONS = [
    {"id": "Calibri", "label": "Calibri"},
    {"id": "Arial", "label": "Arial"},
    {"id": "Georgia", "label": "Georgia"},
    {"id": "Cambria", "label": "Cambria"},
    {"id": "Aptos", "label": "Aptos"},
]

ALLOWED_PROFILE_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}


def resolve_profile_image_path(raw_path: str):
    candidate = normalize_windows_env_path(raw_path)
    if not candidate:
        return None
    image_path = Path(candidate)
    if image_path.suffix.lower() not in ALLOWED_PROFILE_IMAGE_SUFFIXES:
        return None
    return image_path if image_path.exists() and image_path.is_file() else None


def resolve_optional_image_path(raw_path: str):
    candidate = normalize_windows_env_path(raw_path)
    if not candidate:
        return None
    image_path = Path(candidate)
    return image_path if image_path.exists() and image_path.is_file() else None


def resolve_assets_profile_png(docs_dir: Path):
    user_config_preferred = Path("user_config") / "_profile_from_cv.png"
    if user_config_preferred.exists() and user_config_preferred.is_file():
        return user_config_preferred

    assets_dir = docs_dir / "_assets"
    preferred = assets_dir / "_profile_from_cv.png"
    if preferred.exists() and preferred.is_file():
        return preferred
    user_config_png_files = sorted((Path("user_config")).glob("*.png")) if Path("user_config").exists() else []
    if user_config_png_files:
        return user_config_png_files[0]
    png_files = sorted(assets_dir.glob("*.png")) if assets_dir.exists() else []
    return png_files[0] if png_files else None


def get_document_design_options() -> dict:
    return {
        "templates": list(CV_TEMPLATE_PRESETS.values()),
        "color_schemes": list(CV_COLOR_SCHEMES.values()),
        "fonts": list(CV_FONT_OPTIONS),
    }


def _resolve_template(template_id: str) -> dict:
    return dict(CV_TEMPLATE_PRESETS.get(str(template_id or "").strip().lower()) or CV_TEMPLATE_PRESETS["classic"])


def _resolve_color_scheme(color_scheme_id: str) -> dict:
    raw_value = str(color_scheme_id or "").strip()
    if raw_value in CV_COLOR_SCHEMES:
        return dict(CV_COLOR_SCHEMES[raw_value])
    if len(raw_value.replace("#", "")) == 6:
        normalized = raw_value.replace("#", "").upper()
        return {
            "id": "custom",
            "label": "Custom",
            "primary": normalized,
            "accent": normalized,
            "surface": "F4F7FB",
        }
    return dict(CV_COLOR_SCHEMES["classic_navy"])


def find_cv_docx_source_path():
    candidates = []
    config = load_job_seeker_config()
    config_cv_path = normalize_windows_env_path(cfg_str(config, ("candidate", "cv_path"), ""))
    config_cv_docx_path = normalize_windows_env_path(cfg_str(config, ("candidate", "cv_docx_path"), ""))
    if config_cv_path:
        candidates.append(Path(config_cv_path))
    if config_cv_docx_path:
        candidates.append(Path(config_cv_docx_path))
    env_cv_path = normalize_windows_env_path(os.getenv("MY_CV_PATH", ""))
    if env_cv_path:
        candidates.append(Path(env_cv_path))
    candidates.append(Path("Ahmed Kaddah CV.docx"))
    candidates.append(Path(r"C:\Users\ahmed\OneDrive\Personal\CV\Ahmed Kaddah CV.docx"))

    for path in candidates:
        if path.exists() and path.is_file() and path.suffix.lower() == ".docx":
            return path
    return None


def extract_profile_image_from_cv_docx(cv_docx_path: Path, docs_dir: Path):
    try:
        docs_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(cv_docx_path, "r") as archive:
            media_files = [name for name in archive.namelist() if name.startswith("word/media/")]
            if not media_files:
                return None
            media_files.sort()
            first_media = media_files[0]
            extension = Path(first_media).suffix or ".png"
            output_path = docs_dir / f"_profile_from_cv{extension}"
            output_path.write_bytes(archive.read(first_media))
            return output_path if output_path.exists() else None
    except Exception:
        return None


def create_cv_document(
    record: Dict,
    docs_dir: Path,
    run_date: str,
    candidate_name: str,
    candidate_email: str,
    cv_font_name: str,
    cv_template_id: str,
    cv_color_scheme: str,
    languages: List[str],
    profile_image_path,
    include_profile_image: bool,
    profile_links: List[Dict[str, str]],
) -> str:
    try:
        from docx import Document
        from docx.opc.constants import RELATIONSHIP_TYPE as RT
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        from docx.shared import Inches, Pt, RGBColor
    except Exception as exc:
        raise RuntimeError("python-docx is required to create Word files. Install: pip install python-docx") from exc

    job_id = str(record.get("job_id", "unknown"))
    title = str(record.get("title", "Untitled"))
    company = str(record.get("company", "Unknown Company"))
    header_location = format_header_location(record)
    safe_stem = sanitize_filename(f"{candidate_name}_{title}_{company}_{job_id}_CV", max_length=140)

    target_dir = docs_dir / run_date
    target_dir.mkdir(parents=True, exist_ok=True)

    cv_path = target_dir / f"{safe_stem}.docx"
    template = _resolve_template(cv_template_id)
    color_scheme = _resolve_color_scheme(cv_color_scheme)
    primary_rgb = RGBColor.from_string(color_scheme["primary"])

    doc = Document()
    for style_name in ("Normal", "Heading 1", "Heading 2", "List Bullet"):
        style = doc.styles[style_name]
        style.font.name = cv_font_name
        style.font.size = Pt(float(template["base_font_size"]))
        try:
            style.element.rPr.rFonts.set(qn("w:eastAsia"), cv_font_name)
        except Exception:
            pass

    section = doc.sections[0]
    margin = Inches(0.1)
    section.top_margin = margin
    section.bottom_margin = margin
    section.left_margin = margin
    section.right_margin = margin

    def add_hyperlink(paragraph, text: str, url: str, font_size_pt: float = 11.0):
        if not (text and url):
            return
        try:
            relationship_id = paragraph.part.relate_to(url, RT.HYPERLINK, is_external=True)
            hyperlink = OxmlElement("w:hyperlink")
            hyperlink.set(qn("r:id"), relationship_id)

            run = OxmlElement("w:r")
            run_properties = OxmlElement("w:rPr")

            color = OxmlElement("w:color")
            color.set(qn("w:val"), color_scheme["accent"])
            run_properties.append(color)

            no_underline = OxmlElement("w:u")
            no_underline.set(qn("w:val"), "none")
            run_properties.append(no_underline)

            font_size = OxmlElement("w:sz")
            font_size.set(qn("w:val"), str(int(font_size_pt * 2)))
            run_properties.append(font_size)

            font_size_cs = OxmlElement("w:szCs")
            font_size_cs.set(qn("w:val"), str(int(font_size_pt * 2)))
            run_properties.append(font_size_cs)

            run.append(run_properties)
            text_node = OxmlElement("w:t")
            text_node.text = text
            run.append(text_node)
            hyperlink.append(run)
            paragraph._p.append(hyperlink)
        except Exception:
            fallback_run = paragraph.add_run(text)
            fallback_run.font.color.rgb = None

    valid_profile_links = []
    for item in profile_links or []:
        if not isinstance(item, dict):
            continue
        link_url = str(item.get("url") or "").strip()
        if not link_url:
            continue
        link_text = str(item.get("text") or "").strip()
        if not link_text:
            continue
        valid_profile_links.append(
            {
                "text": link_text,
                "url": link_url,
                "logo_path": item.get("logo_path"),
            }
        )

    name_paragraph = doc.add_paragraph()
    name_paragraph.paragraph_format.space_before = Pt(0)
    name_paragraph.paragraph_format.space_after = Pt(2)
    language_values = [str(line).strip() for line in (languages or DEFAULT_LANGUAGES) if str(line).strip()]
    language_line = ", ".join(language_values)
    header_parts = [candidate_name, header_location, candidate_email]
    if language_line:
        header_parts.append(language_line)
    name_run = name_paragraph.add_run(" | ".join([part for part in header_parts if part]))
    name_run.bold = True
    name_run.font.size = Pt(float(template["header_font_size"]))
    name_run.font.name = cv_font_name
    name_run.font.color.rgb = primary_rgb

    def float_picture_right(run, inline_shape, top_offset_inches: float = 0.45):
        inline = inline_shape._inline
        drawing = run._r.xpath("./w:drawing")[0]

        anchor = OxmlElement("wp:anchor")
        anchor.set("simplePos", "0")
        anchor.set("relativeHeight", "251658240")
        anchor.set("behindDoc", "0")
        anchor.set("locked", "0")
        anchor.set("layoutInCell", "1")
        anchor.set("allowOverlap", "1")
        anchor.set("distT", "0")
        anchor.set("distB", "0")
        anchor.set("distL", "91440")
        anchor.set("distR", "91440")

        simple_pos = OxmlElement("wp:simplePos")
        simple_pos.set("x", "0")
        simple_pos.set("y", "0")
        anchor.append(simple_pos)

        position_h = OxmlElement("wp:positionH")
        position_h.set("relativeFrom", "margin")
        align = OxmlElement("wp:align")
        align.text = "right"
        position_h.append(align)
        anchor.append(position_h)

        position_v = OxmlElement("wp:positionV")
        position_v.set("relativeFrom", "margin")
        pos_offset = OxmlElement("wp:posOffset")
        pos_offset.text = str(int(top_offset_inches * 914400))
        position_v.append(pos_offset)
        anchor.append(position_v)

        extent = inline.xpath("./wp:extent")[0]
        anchor.append(deepcopy(extent))

        effect = inline.xpath("./wp:effectExtent")
        if effect:
            anchor.append(deepcopy(effect[0]))
        else:
            effect_extent = OxmlElement("wp:effectExtent")
            effect_extent.set("l", "0")
            effect_extent.set("t", "0")
            effect_extent.set("r", "0")
            effect_extent.set("b", "0")
            anchor.append(effect_extent)

        wrap_square = OxmlElement("wp:wrapSquare")
        wrap_square.set("wrapText", "bothSides")
        anchor.append(wrap_square)

        doc_pr = inline.xpath("./wp:docPr")[0]
        anchor.append(deepcopy(doc_pr))

        frame_pr = inline.xpath("./wp:cNvGraphicFramePr")
        if frame_pr:
            anchor.append(deepcopy(frame_pr[0]))

        graphic = inline.xpath("./a:graphic")[0]
        anchor.append(deepcopy(graphic))

        drawing.remove(inline)
        drawing.append(anchor)

    if include_profile_image and profile_image_path:
        try:
            image_run = name_paragraph.add_run()
            inline_shape = image_run.add_picture(
                str(profile_image_path),
                width=Inches(float(template["photo_width"])),
            )
            float_picture_right(
                image_run,
                inline_shape,
                top_offset_inches=float(template["top_offset_inches"]),
            )
        except Exception:
            pass

    if valid_profile_links:
        links_paragraph = doc.add_paragraph()
        links_paragraph.paragraph_format.space_before = Pt(0)
        links_paragraph.paragraph_format.space_after = Pt(2)
        icon_size_inches = 16 / 96.0
        for link_index, link_item in enumerate(valid_profile_links):
            if link_index > 0:
                links_paragraph.add_run("   ")
            logo_path = link_item.get("logo_path")
            if logo_path:
                try:
                    logo_run = links_paragraph.add_run()
                    logo_run.add_picture(str(logo_path), width=Inches(icon_size_inches), height=Inches(icon_size_inches))
                    links_paragraph.add_run(" ")
                except Exception:
                    pass
            add_hyperlink(
                links_paragraph,
                text=link_item["text"],
                url=link_item["url"],
                font_size_pt=11.0,
            )

    def add_section_separator() -> None:
        sep = doc.add_paragraph()
        sep.paragraph_format.space_before = Pt(0)
        sep.paragraph_format.space_after = Pt(0)
        sep.paragraph_format.line_spacing = Pt(1)
        p_pr = sep._p.get_or_add_pPr()
        p_bdr = OxmlElement("w:pBdr")
        bottom = OxmlElement("w:bottom")
        bottom.set(qn("w:val"), "single")
        bottom.set(qn("w:sz"), str(template["divider_weight"]))
        bottom.set(qn("w:space"), "0")
        bottom.set(qn("w:color"), color_scheme["primary"])
        p_bdr.append(bottom)
        p_pr.append(p_bdr)

    def add_section_heading(text: str):
        paragraph = doc.add_paragraph()
        heading_text = text.upper() if template["heading_case"] == "upper" else text.title()
        run = paragraph.add_run(heading_text)
        run.bold = True
        run.font.color.rgb = primary_rgb
        run.font.name = cv_font_name
        run.font.size = Pt(max(float(template["base_font_size"]) + 1.4, 11.0))
        return paragraph, run

    _, run_summary = add_section_heading("Professional Summary")
    doc.add_paragraph(str(record.get("cv_professional_summary") or "").strip())
    add_section_separator()

    _, run_exp = add_section_heading("Professional Experience")

    experiences = record.get("cv_professional_experience") or []
    for item in experiences:
        if not isinstance(item, dict):
            continue
        role_title = str(item.get("role_title") or "").strip()
        exp_company = str(item.get("company") or "").strip()
        period = str(item.get("period") or "").strip()
        headline_parts = [part for part in [role_title, exp_company, period] if part]
        if headline_parts:
            exp_header = doc.add_paragraph(" | ".join(headline_parts))
            exp_header.runs[0].bold = True
        for bullet in item.get("bullets", []):
            if str(bullet).strip():
                doc.add_paragraph(str(bullet).strip(), style="List Bullet")
    add_section_separator()

    _, run_initiatives = add_section_heading("Projects")
    initiatives = record.get("cv_strategic_initiatives") or []
    for item in initiatives:
        if not isinstance(item, dict):
            continue
        initiative_title = str(item.get("title") or "").strip()
        if initiative_title:
            ini_header = doc.add_paragraph(initiative_title)
            ini_header.runs[0].bold = True
        for bullet in item.get("bullets", []):
            if str(bullet).strip():
                doc.add_paragraph(str(bullet).strip(), style="List Bullet")
    add_section_separator()

    _, run_skills = add_section_heading("Skills")
    skills = record.get("cv_skills") or []
    if skills:
        doc.add_paragraph(", ".join([str(skill).strip() for skill in skills if str(skill).strip()]))
    add_section_separator()

    _, run_education = add_section_heading("Education")
    education_items = record.get("cv_education") or []
    for item in education_items:
        if not isinstance(item, dict):
            continue
        degree_title = str(item.get("degree_title") or "").strip()
        thesis_title = str(item.get("thesis_title") or "").strip()
        if degree_title:
            degree_paragraph = doc.add_paragraph(degree_title)
            degree_paragraph.runs[0].bold = True
        if thesis_title:
            doc.add_paragraph(thesis_title)
        for bullet in item.get("thesis_bullets", []):
            if str(bullet).strip():
                doc.add_paragraph(str(bullet).strip(), style="List Bullet")
    add_section_separator()

    doc.save(cv_path)
    return str(cv_path.resolve())


def convert_docx_to_pdf(docx_path: str) -> str:
    source_path = Path(docx_path)
    target_path = source_path.with_suffix(".pdf")

    try:
        from docx2pdf import convert as docx2pdf_convert

        docx2pdf_convert(str(source_path), str(target_path))
        if target_path.exists():
            return str(target_path.resolve())
    except Exception:
        pass

    try:
        src = str(source_path.resolve()).replace("'", "''")
        dst = str(target_path.resolve()).replace("'", "''")
        ps_script = (
            "$word = New-Object -ComObject Word.Application; "
            "$word.Visible = $false; "
            f"$doc = $word.Documents.Open('{src}'); "
            f"$doc.SaveAs('{dst}', 17); "
            "$doc.Close(); "
            "$word.Quit();"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            check=True,
            capture_output=True,
            text=True,
        )
        if target_path.exists():
            return str(target_path.resolve())
    except Exception:
        pass

    office_cmd = shutil.which("soffice") or shutil.which("libreoffice")
    if office_cmd:
        try:
            subprocess.run(
                [office_cmd, "--headless", "--convert-to", "pdf", "--outdir", str(source_path.parent), str(source_path)],
                check=True,
                capture_output=True,
                text=True,
            )
            if target_path.exists():
                return str(target_path.resolve())
        except Exception:
            pass

    raise RuntimeError(
        "Unable to convert DOCX to PDF. Install docx2pdf + Microsoft Word, "
        "or install LibreOffice and add soffice to PATH."
    )
