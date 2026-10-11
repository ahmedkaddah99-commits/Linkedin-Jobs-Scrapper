from __future__ import annotations

from html import escape
from pathlib import Path
import shutil

from backend.config.job_seeker import cfg_str, load_job_seeker_config, normalize_windows_env_path


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "test CV" / "04_web_inspired_templates"
ASSETS_DIR = OUTPUT_DIR / "_assets"


PROFILE = {
    "name": "Ahmed Kaddah",
    "headline": "Operations and Logistics Support",
    "location": "Erlangen / Nuremberg, Germany",
    "email": "ahmed.kaddah@tutamail.com",
    "linkedin": "https://www.linkedin.com/in/ahmed-kaddah-3a1a88183/",
    "github": "https://github.com/ahmedkaddah99-commits?tab=repositories",
    "summary": (
        "Operations and logistics support professional with hands-on experience managing more than "
        "1,600 e-scooters across 7 cities, coordinating 7 transport vans, completing daily readiness "
        "checks, and supporting customer-facing field operations. Recognized for fast response times, "
        "reliable execution, onboarding new team members, and disciplined daily documentation. "
        "Available immediately for warehouse, logistics, operational support, and service roles."
    ),
    "skills": [
        "Fleet coordination",
        "Warehouse and field operations",
        "Transport van logistics",
        "Daily inspections and readiness checks",
        "Inventory counting and documentation",
        "Customer-facing service",
        "Team onboarding",
        "Shift reliability",
        "Arabic (Native)",
        "English (C1)",
        "German (B1/B2)",
    ],
    "experience": [
        {
            "role": "Logistics and Fleet Operations Associate",
            "company": "Zeus Scooters GmbH",
            "period": "Dec 2023 - Jul 2024",
            "bullets": [
                "Managed day-to-day support for a fleet of more than 1,600 e-scooters across 7 cities.",
                "Coordinated logistics using 7 transport vans to keep assets available and operational.",
                "Completed daily maintenance checks and readiness inspections to support reliable service.",
                "Trained new team members on operational routines and day-to-day execution.",
            ],
        },
        {
            "role": "Service and Operations Associate",
            "company": "Roxy Mobility GmbH",
            "period": "Dec 2020 - Oct 2024",
            "bullets": [
                "Handled daily field service and customer support in a fast-moving operating environment.",
                "Coordinated with partners including Deutsche Bahn on site and logistics-related tasks.",
                "Earned top recognition for the fastest response time in the city.",
                "Maintained daily records and inventory tracking for operational equipment.",
            ],
        },
        {
            "role": "Project and Team Assistant",
            "company": "General Administration and Logistics",
            "period": "Nov 2024 - Present",
            "bullets": [
                "Supported daily data capture and task tracking for ongoing team activities.",
                "Prepared materials for workshops and team sessions.",
                "Provided general administrative support to improve workflow consistency.",
            ],
        },
    ],
    "education": [
        {
            "degree": "M.Sc. Information Systems",
            "school": "University Example",
            "period": "Completed",
            "details": "Focus on analytics, business systems, and digital operations.",
        }
    ],
    "availability": "Available immediately for full-time or mini-job roles.",
}


RESEARCH_ITEMS = [
    {
        "title": "University of Pennsylvania resume guidance",
        "url": "https://careerservices.upenn.edu/channels/resume/",
        "reason": "Clear ATS guidance: simple, consistent design; use white space; avoid graphics and text boxes.",
    },
    {
        "title": "Yale resume action verbs",
        "url": "https://ocs.yale.edu/resources/resume-action-verbs/",
        "reason": "Useful for stronger bullets focused on accomplishment rather than duty language.",
    },
    {
        "title": "Europass CV guidance",
        "url": "https://europass.europa.eu/en/create-europass-cv",
        "reason": "Supports a Europe-familiar structure, reverse chronological order, and tailored About Me framing.",
    },
    {
        "title": "Overleaf MTeck's Resume",
        "url": "https://www.overleaf.com/latex/templates/mtecks-resume/fzgztpkgngjc",
        "reason": "Strong single-column ATS-oriented pattern with simple, maintainable styling.",
    },
    {
        "title": "Overleaf CV Sidebar Template",
        "url": "https://www.overleaf.com/latex/templates/cv-sidebar-template/mnwdwhxbxgdg",
        "reason": "Shows a lightweight sidebar pattern that still stays visually clean.",
    },
    {
        "title": "Overleaf Monocol Navbar CV",
        "url": "https://www.overleaf.com/latex/templates/monocol-navbar-cv/xdhwjpkpmxyv",
        "reason": "Shows a compact left-rail contact pattern that feels modern without heavy layout logic.",
    },
]


TEMPLATES = [
    {
        "slug": "01_ats_single_column",
        "title": "ATS Single Column",
        "subtitle": "Most robust and easiest to generate",
        "source_summary": "Inspired by UPenn guidance and Overleaf MTeck's Resume.",
    },
    {
        "slug": "02_editorial_sidebar",
        "title": "Editorial Sidebar",
        "subtitle": "Soft visual hierarchy with minimal code",
        "source_summary": "Inspired by Overleaf CV Sidebar Template.",
    },
    {
        "slug": "03_mono_nav",
        "title": "Mono Nav",
        "subtitle": "Modern left rail, simple body flow",
        "source_summary": "Inspired by Overleaf Monocol Navbar CV.",
    },
    {
        "slug": "04_europass_lite",
        "title": "Europass Lite",
        "subtitle": "European familiar structure, lighter visual weight",
        "source_summary": "Inspired by Europass structure but simplified for code generation.",
    },
    {
        "slug": "05_signal_header",
        "title": "Signal Header",
        "subtitle": "Bold header band with grouped content blocks",
        "source_summary": "Inspired by editorial banner layouts and resume landing-page hierarchy.",
    },
    {
        "slug": "06_ledger_split",
        "title": "Ledger Split",
        "subtitle": "Asymmetric grid with dense role detail",
        "source_summary": "Inspired by compact consulting-style CV layouts that still stay generator-friendly.",
    },
]


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _resolve_profile_photo_source() -> Path | None:
    config = load_job_seeker_config()
    configured_path = normalize_windows_env_path(cfg_str(config, ("candidate", "profile_image_path"), ""))
    candidates = []
    if configured_path:
        candidates.append(Path(configured_path))
    candidates.append(ROOT / "user_config" / "_profile_from_cv.png")

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _prepare_profile_photo_asset() -> str:
    _ensure_dir(ASSETS_DIR)
    source = _resolve_profile_photo_source()
    if source is None:
        return ""
    target = ASSETS_DIR / f"profile_photo{source.suffix.lower()}"
    shutil.copy2(source, target)
    return target.relative_to(OUTPUT_DIR).as_posix()


def _photo_markup(photo_src: str, *, img_class: str = "profile-photo", shell_class: str = "photo-shell") -> str:
    if photo_src:
        return (
            f'<div class="{escape(shell_class)}">'
            f'<img class="{escape(img_class)}" src="{escape(photo_src)}" alt="Candidate profile photo">'
            "</div>"
        )
    return (
        f'<div class="{escape(shell_class)} photo-shell-placeholder">'
        '<div class="photo-placeholder-copy">Profile photo</div>'
        "</div>"
    )


def _variant_title(base_title: str) -> str:
    suffix = "With Photo" if PROFILE.get("photo_src") else "No Photo"
    return f"{base_title} ({suffix})"


def _html_page(title: str, body: str, extra_css: str = "") -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    :root {{
      color-scheme: light;
    }}
    * {{
      box-sizing: border-box;
    }}
    html, body {{
      margin: 0;
      padding: 0;
      background:
        radial-gradient(circle at top left, rgba(194, 214, 255, 0.25), transparent 32%),
        linear-gradient(180deg, #f6f4ef 0%, #ece9e2 100%);
      color: #111827;
      font-family: "Segoe UI", "Helvetica Neue", sans-serif;
    }}
    a {{
      color: inherit;
      text-decoration-thickness: 1px;
      text-underline-offset: 0.15em;
    }}
    .screen-toolbar {{
      position: sticky;
      top: 0;
      z-index: 50;
      display: flex;
      gap: 0.75rem;
      align-items: center;
      justify-content: space-between;
      padding: 0.9rem 1.2rem;
      backdrop-filter: blur(10px);
      background: rgba(255, 255, 255, 0.82);
      border-bottom: 1px solid rgba(17, 24, 39, 0.08);
    }}
    .screen-toolbar .meta {{
      font-size: 0.92rem;
      color: #475569;
    }}
    .toolbar-actions {{
      display: flex;
      gap: 0.75rem;
      align-items: center;
    }}
    .toolbar-button {{
      appearance: none;
      border: 0;
      border-radius: 999px;
      padding: 0.72rem 1rem;
      background: #111827;
      color: white;
      font: inherit;
      cursor: pointer;
    }}
    .toolbar-link {{
      font-size: 0.92rem;
      color: #334155;
    }}
    .page-wrap {{
      padding: 1.5rem;
    }}
    .sheet {{
      width: 210mm;
      min-height: 297mm;
      margin: 0 auto;
      background: white;
      box-shadow: 0 28px 70px rgba(15, 23, 42, 0.15);
      overflow: hidden;
    }}
    .muted {{
      color: #64748b;
    }}
    .caps {{
      text-transform: uppercase;
      letter-spacing: 0.16em;
    }}
    .tag {{
      display: inline-block;
      padding: 0.22rem 0.58rem;
      border-radius: 999px;
      background: #e2e8f0;
      font-size: 0.74rem;
      font-weight: 600;
      letter-spacing: 0.05em;
      text-transform: uppercase;
    }}
    .photo-shell {{
      width: 34mm;
      height: 44mm;
      overflow: hidden;
      border-radius: 18px;
      border: 1px solid rgba(15, 23, 42, 0.12);
      background: linear-gradient(180deg, #eef2f7 0%, #dfe8f1 100%);
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
    }}
    .profile-photo {{
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }}
    .photo-shell-placeholder {{
      border-style: dashed;
      background:
        repeating-linear-gradient(
          135deg,
          rgba(148, 163, 184, 0.12),
          rgba(148, 163, 184, 0.12) 8px,
          rgba(255, 255, 255, 0.8) 8px,
          rgba(255, 255, 255, 0.8) 16px
        );
    }}
    .photo-placeholder-copy {{
      padding: 0.6rem;
      text-align: center;
      font-size: 0.72rem;
      line-height: 1.35;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: #475569;
    }}
    @media print {{
      html, body {{
        background: white;
      }}
      .screen-toolbar {{
        display: none;
      }}
      .page-wrap {{
        padding: 0;
      }}
      .sheet {{
        width: auto;
        min-height: auto;
        margin: 0;
        box-shadow: none;
      }}
      @page {{
        size: A4;
        margin: 10mm;
      }}
    }}
    {extra_css}
  </style>
</head>
<body>
  <div class="screen-toolbar">
    <div class="meta">{escape(title)} · print-ready HTML prototype</div>
    <div class="toolbar-actions">
      <a class="toolbar-link" href="index.html">Back to gallery</a>
      <button class="toolbar-button" onclick="window.print()">Print / Save PDF</button>
    </div>
  </div>
  <div class="page-wrap">
    {body}
  </div>
</body>
</html>
"""


def _render_list(items: list[str], cls: str = "") -> str:
    class_attr = f' class="{cls}"' if cls else ""
    return "<ul{0}>{1}</ul>".format(
        class_attr,
        "".join(f"<li>{escape(item)}</li>" for item in items),
    )


def _render_experience(block_class: str, bullet_class: str = "") -> str:
    blocks = []
    for item in PROFILE["experience"]:
        bullets = _render_list(item["bullets"], bullet_class)
        blocks.append(
            f"""
            <section class="{block_class}">
              <div class="role-line">
                <div>
                  <h3>{escape(item['role'])}</h3>
                  <p class="company">{escape(item['company'])}</p>
                </div>
                <div class="period">{escape(item['period'])}</div>
              </div>
              {bullets}
            </section>
            """
        )
    return "\n".join(blocks)


def _research_links_html() -> str:
    rows = []
    for item in RESEARCH_ITEMS:
        rows.append(
            f"<li><a href=\"{escape(item['url'])}\">{escape(item['title'])}</a> — {escape(item['reason'])}</li>"
        )
    return "<ul>" + "".join(rows) + "</ul>"


def _template_ats_single_column() -> str:
    photo = _photo_markup(PROFILE.get("photo_src", ""), shell_class="photo-shell ats-photo-shell")
    body = f"""
    <main class="sheet ats-sheet">
      <header class="ats-header">
        <div class="ats-topline">
          <div class="name-block">
            <p class="caps eyebrow">ATS-safe / code-light</p>
            <h1>{escape(PROFILE['name'])}</h1>
            <p class="headline">{escape(PROFILE['headline'])}</p>
          </div>
          {photo}
        </div>
        <div class="contact-grid">
          <span>{escape(PROFILE['location'])}</span>
          <a href="mailto:{escape(PROFILE['email'])}">{escape(PROFILE['email'])}</a>
          <a href="{escape(PROFILE['linkedin'])}">LinkedIn</a>
          <a href="{escape(PROFILE['github'])}">GitHub</a>
        </div>
      </header>
      <section class="section">
        <h2>Professional Summary</h2>
        <p>{escape(PROFILE['summary'])}</p>
      </section>
      <section class="section">
        <h2>Core Skills</h2>
        <p class="skill-line">{escape(" | ".join(PROFILE['skills']))}</p>
      </section>
      <section class="section">
        <h2>Experience</h2>
        {_render_experience("experience-card")}
      </section>
      <section class="section split-footer">
        <div>
          <h2>Education</h2>
          <p><strong>{escape(PROFILE['education'][0]['degree'])}</strong><br>{escape(PROFILE['education'][0]['school'])}<br>{escape(PROFILE['education'][0]['details'])}</p>
        </div>
        <div>
          <h2>Availability</h2>
          <p>{escape(PROFILE['availability'])}</p>
        </div>
      </section>
    </main>
    """
    css = """
      .ats-sheet {
        padding: 20mm 18mm 18mm;
        font-family: "Aptos", "Segoe UI", sans-serif;
      }
      .ats-header {
        border-bottom: 2px solid #0f172a;
        padding-bottom: 12px;
        margin-bottom: 18px;
      }
      .ats-topline {
        display: flex;
        gap: 18px;
        justify-content: space-between;
        align-items: flex-start;
      }
      .eyebrow {
        margin: 0 0 8px;
        color: #64748b;
        font-size: 0.72rem;
        font-weight: 700;
      }
      .ats-header h1 {
        margin: 0;
        font-size: 2.2rem;
        line-height: 1;
      }
      .headline {
        margin: 8px 0 0;
        font-size: 1.02rem;
        color: #334155;
      }
      .ats-photo-shell {
        border-radius: 20px;
      }
      .contact-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 6px 20px;
        margin-top: 12px;
        font-size: 0.9rem;
        color: #475569;
      }
      .section + .section {
        margin-top: 18px;
      }
      .section h2 {
        margin: 0 0 10px;
        font-size: 0.8rem;
        font-weight: 800;
        letter-spacing: 0.16em;
        text-transform: uppercase;
      }
      .section p {
        margin: 0;
        line-height: 1.5;
        font-size: 0.97rem;
      }
      .skill-line {
        color: #0f172a;
      }
      .experience-card + .experience-card {
        margin-top: 14px;
      }
      .role-line {
        display: flex;
        justify-content: space-between;
        gap: 16px;
        align-items: baseline;
      }
      .role-line h3 {
        margin: 0;
        font-size: 1rem;
      }
      .company {
        margin-top: 3px !important;
        font-size: 0.9rem !important;
        color: #475569;
      }
      .period {
        white-space: nowrap;
        font-size: 0.84rem;
        color: #64748b;
      }
      .experience-card ul {
        margin: 8px 0 0 18px;
        padding: 0;
      }
      .experience-card li {
        margin-top: 4px;
        line-height: 1.45;
      }
      .split-footer {
        display: grid;
        grid-template-columns: 1.2fr 0.8fr;
        gap: 28px;
      }
    """
    return _html_page(_variant_title("ATS Single Column CV"), body, css)


def _template_editorial_sidebar() -> str:
    skills = "".join(f"<li>{escape(skill)}</li>" for skill in PROFILE["skills"])
    photo = _photo_markup(PROFILE.get("photo_src", ""), shell_class="photo-shell sidebar-photo-shell")
    body = f"""
    <main class="sheet sidebar-sheet">
      <aside class="sidebar">
        <div class="sidebar-inner">
          <span class="tag">Sidebar</span>
          <div class="sidebar-photo-wrap">{photo}</div>
          <h1>{escape(PROFILE['name'])}</h1>
          <p class="sidebar-headline">{escape(PROFILE['headline'])}</p>
          <div class="sidebar-block">
            <h2>Contact</h2>
            <p>{escape(PROFILE['location'])}</p>
            <p><a href="mailto:{escape(PROFILE['email'])}">{escape(PROFILE['email'])}</a></p>
            <p><a href="{escape(PROFILE['linkedin'])}">LinkedIn</a></p>
            <p><a href="{escape(PROFILE['github'])}">GitHub</a></p>
          </div>
          <div class="sidebar-block">
            <h2>Core Skills</h2>
            <ul class="sidebar-skills">{skills}</ul>
          </div>
          <div class="sidebar-block">
            <h2>Availability</h2>
            <p>{escape(PROFILE['availability'])}</p>
          </div>
        </div>
      </aside>
      <section class="content">
        <div class="content-intro">
          <p class="caps content-kicker">Soft visual hierarchy / low layout complexity</p>
          <p>{escape(PROFILE['summary'])}</p>
        </div>
        <section class="content-section">
          <h2>Experience</h2>
          {_render_experience("editorial-card", "editorial-bullets")}
        </section>
        <section class="content-section">
          <h2>Education</h2>
          <div class="education-row">
            <strong>{escape(PROFILE['education'][0]['degree'])}</strong>
            <span>{escape(PROFILE['education'][0]['school'])}</span>
            <p>{escape(PROFILE['education'][0]['details'])}</p>
          </div>
        </section>
      </section>
    </main>
    """
    css = """
      .sidebar-sheet {
        display: grid;
        grid-template-columns: 70mm 1fr;
        min-height: 297mm;
        font-family: Georgia, "Palatino Linotype", serif;
      }
      .sidebar {
        background:
          linear-gradient(180deg, #13304a 0%, #1f4b64 100%);
        color: #f8fafc;
      }
      .sidebar-inner {
        padding: 18mm 12mm 16mm;
      }
      .sidebar h1 {
        margin: 16px 0 0;
        font-size: 1.9rem;
        line-height: 1.05;
      }
      .sidebar-photo-wrap {
        margin-top: 16px;
      }
      .sidebar-photo-shell {
        width: 100%;
        height: 58mm;
        border-radius: 22px;
        border-color: rgba(248, 250, 252, 0.18);
      }
      .sidebar-headline {
        margin: 10px 0 0;
        line-height: 1.4;
        color: rgba(248, 250, 252, 0.88);
      }
      .sidebar-block {
        margin-top: 22px;
      }
      .sidebar-block h2 {
        margin: 0 0 10px;
        font: 700 0.76rem/1 "Segoe UI", sans-serif;
        text-transform: uppercase;
        letter-spacing: 0.16em;
        color: rgba(248, 250, 252, 0.72);
      }
      .sidebar-block p {
        margin: 8px 0 0;
        line-height: 1.45;
      }
      .sidebar-skills {
        margin: 0;
        padding-left: 18px;
      }
      .sidebar-skills li + li {
        margin-top: 6px;
      }
      .content {
        padding: 17mm 16mm 16mm;
        background:
          radial-gradient(circle at top right, rgba(171, 198, 255, 0.18), transparent 28%),
          linear-gradient(180deg, #fffefb 0%, #ffffff 100%);
      }
      .content-kicker {
        margin: 0 0 10px;
        color: #7c8ba1;
        font-size: 0.72rem;
        font-weight: 700;
      }
      .content-intro p:last-child {
        margin: 0;
        font-size: 1rem;
        line-height: 1.65;
        color: #243649;
      }
      .content-section {
        margin-top: 22px;
      }
      .content-section h2 {
        margin: 0 0 12px;
        font: 700 0.82rem/1 "Segoe UI", sans-serif;
        text-transform: uppercase;
        letter-spacing: 0.15em;
        color: #183b58;
      }
      .editorial-card + .editorial-card {
        margin-top: 14px;
        padding-top: 14px;
        border-top: 1px solid rgba(24, 59, 88, 0.1);
      }
      .role-line {
        display: flex;
        justify-content: space-between;
        gap: 16px;
      }
      .role-line h3 {
        margin: 0;
        font-size: 1.04rem;
        color: #10293f;
      }
      .company {
        margin: 5px 0 0 !important;
        color: #5c6f82;
      }
      .period {
        white-space: nowrap;
        font: 600 0.8rem/1.3 "Segoe UI", sans-serif;
        color: #6b7d90;
      }
      .editorial-bullets {
        margin: 10px 0 0 18px;
        padding: 0;
      }
      .editorial-bullets li {
        margin-top: 5px;
        line-height: 1.48;
        color: #1f3144;
      }
      .education-row span {
        display: block;
        margin-top: 4px;
        color: #64748b;
      }
      .education-row p {
        margin: 8px 0 0;
        line-height: 1.55;
      }
    """
    return _html_page(_variant_title("Editorial Sidebar CV"), body, css)


def _template_mono_nav() -> str:
    skill_tags = "".join(f"<span>{escape(skill)}</span>" for skill in PROFILE["skills"])
    photo = _photo_markup(PROFILE.get("photo_src", ""), shell_class="photo-shell mono-photo-shell")
    body = f"""
    <main class="sheet mono-sheet">
      <aside class="mono-rail">
        <div class="rail-card">
          <p class="rail-label">Navigation rail</p>
          <div class="mono-photo-wrap">{photo}</div>
          <h1>{escape(PROFILE['name'])}</h1>
          <p class="rail-headline">{escape(PROFILE['headline'])}</p>
          <nav class="rail-nav">
            <a href="#summary">Summary</a>
            <a href="#experience">Experience</a>
            <a href="#skills">Skills</a>
            <a href="#education">Education</a>
          </nav>
          <div class="rail-contact">
            <p>{escape(PROFILE['location'])}</p>
            <p><a href="mailto:{escape(PROFILE['email'])}">{escape(PROFILE['email'])}</a></p>
          </div>
        </div>
      </aside>
      <section class="mono-main">
        <section id="summary" class="mono-block hero-block">
          <span class="tag">Mono Nav</span>
          <p>{escape(PROFILE['summary'])}</p>
        </section>
        <section id="experience" class="mono-block">
          <h2>Experience</h2>
          {_render_experience("mono-card", "mono-bullets")}
        </section>
        <section id="skills" class="mono-block">
          <h2>Skills</h2>
          <div class="skill-cloud">{skill_tags}</div>
        </section>
        <section id="education" class="mono-block two-up">
          <div>
            <h2>Education</h2>
            <p><strong>{escape(PROFILE['education'][0]['degree'])}</strong><br>{escape(PROFILE['education'][0]['school'])}</p>
            <p class="muted">{escape(PROFILE['education'][0]['details'])}</p>
          </div>
          <div>
            <h2>Links</h2>
            <p><a href="{escape(PROFILE['linkedin'])}">LinkedIn profile</a></p>
            <p><a href="{escape(PROFILE['github'])}">GitHub profile</a></p>
            <p>{escape(PROFILE['availability'])}</p>
          </div>
        </section>
      </section>
    </main>
    """
    css = """
      .mono-sheet {
        display: grid;
        grid-template-columns: 58mm 1fr;
        font-family: "Trebuchet MS", "Segoe UI", sans-serif;
      }
      .mono-rail {
        background:
          linear-gradient(180deg, #081b2d 0%, #0d2e4b 100%);
        color: white;
        padding: 16mm 8mm;
      }
      .rail-card {
        position: sticky;
        top: 24px;
      }
      .rail-label {
        margin: 0 0 12px;
        font-size: 0.72rem;
        letter-spacing: 0.16em;
        text-transform: uppercase;
        color: rgba(255, 255, 255, 0.66);
      }
      .mono-photo-wrap {
        margin-bottom: 14px;
      }
      .mono-photo-shell {
        width: 100%;
        height: 50mm;
        border-radius: 24px;
        border-color: rgba(255, 255, 255, 0.14);
      }
      .mono-rail h1 {
        margin: 0;
        font-size: 1.76rem;
        line-height: 1.02;
      }
      .rail-headline {
        margin: 10px 0 0;
        color: rgba(255, 255, 255, 0.82);
        line-height: 1.45;
      }
      .rail-nav {
        margin-top: 22px;
        display: grid;
        gap: 10px;
      }
      .rail-nav a {
        color: white;
        text-decoration: none;
        font-weight: 700;
      }
      .rail-contact {
        margin-top: 22px;
        font-size: 0.92rem;
        color: rgba(255, 255, 255, 0.82);
      }
      .mono-main {
        padding: 16mm;
        background:
          radial-gradient(circle at 85% 0%, rgba(135, 206, 235, 0.18), transparent 28%),
          linear-gradient(180deg, #fbfdff 0%, #ffffff 100%);
      }
      .mono-block + .mono-block {
        margin-top: 18px;
      }
      .hero-block {
        padding: 14px 16px;
        border: 1px solid rgba(13, 46, 75, 0.1);
        background: #f4f8fb;
      }
      .hero-block p {
        margin: 12px 0 0;
        line-height: 1.6;
      }
      .mono-block h2 {
        margin: 0 0 10px;
        font-size: 0.82rem;
        text-transform: uppercase;
        letter-spacing: 0.16em;
        color: #3b4f63;
      }
      .mono-card + .mono-card {
        margin-top: 16px;
      }
      .role-line {
        display: flex;
        justify-content: space-between;
        gap: 18px;
      }
      .role-line h3 {
        margin: 0;
        font-size: 1rem;
      }
      .company {
        margin: 4px 0 0 !important;
      }
      .period {
        font-size: 0.82rem;
        white-space: nowrap;
        color: #64748b;
      }
      .mono-bullets {
        margin: 8px 0 0 18px;
        padding: 0;
      }
      .mono-bullets li + li {
        margin-top: 5px;
      }
      .skill-cloud {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
      }
      .skill-cloud span {
        padding: 0.38rem 0.65rem;
        border-radius: 999px;
        background: #e8f0f7;
        color: #17324d;
        font-size: 0.86rem;
      }
      .two-up {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 22px;
      }
      .two-up p {
        margin: 0;
        line-height: 1.55;
      }
      .two-up p + p {
        margin-top: 8px;
      }
    """
    return _html_page(_variant_title("Mono Nav CV"), body, css)


def _template_europass_lite() -> str:
    experiences = []
    for item in PROFILE["experience"]:
        experiences.append(
            f"""
            <div class="eu-row">
              <div class="eu-label">{escape(item['period'])}</div>
              <div class="eu-content">
                <h3>{escape(item['role'])}</h3>
                <p class="company">{escape(item['company'])}</p>
                {_render_list(item['bullets'], "eu-bullets")}
              </div>
            </div>
            """
        )
    skills = "".join(f"<li>{escape(skill)}</li>" for skill in PROFILE["skills"])
    photo = _photo_markup(PROFILE.get("photo_src", ""), shell_class="photo-shell eu-photo-shell")
    body = f"""
    <main class="sheet eu-sheet">
      <header class="eu-header">
        <div>
          <p class="caps">Europass-inspired</p>
          <h1>{escape(PROFILE['name'])}</h1>
        </div>
        <div class="eu-header-meta">
          <div class="eu-photo-wrap">{photo}</div>
          <p>{escape(PROFILE['location'])}</p>
          <p><a href="mailto:{escape(PROFILE['email'])}">{escape(PROFILE['email'])}</a></p>
          <p><a href="{escape(PROFILE['linkedin'])}">LinkedIn</a></p>
        </div>
      </header>
      <section class="eu-section">
        <div class="eu-label about-label">About Me</div>
        <div class="eu-content">
          <p>{escape(PROFILE['summary'])}</p>
        </div>
      </section>
      <section class="eu-section">
        <div class="eu-label">Work Experience</div>
        <div class="eu-content">
          {''.join(experiences)}
        </div>
      </section>
      <section class="eu-section">
        <div class="eu-label">Skills</div>
        <div class="eu-content">
          <ul class="skill-columns">{skills}</ul>
        </div>
      </section>
      <section class="eu-section">
        <div class="eu-label">Education</div>
        <div class="eu-content">
          <h3>{escape(PROFILE['education'][0]['degree'])}</h3>
          <p class="company">{escape(PROFILE['education'][0]['school'])}</p>
          <p>{escape(PROFILE['education'][0]['details'])}</p>
        </div>
      </section>
    </main>
    """
    css = """
      .eu-sheet {
        padding: 14mm 14mm 14mm;
        font-family: Cambria, Georgia, serif;
        background:
          linear-gradient(90deg, #f6f4ed 0 46mm, white 46mm 100%);
      }
      .eu-header {
        display: grid;
        grid-template-columns: 1fr 60mm;
        gap: 16px;
        margin-bottom: 14px;
      }
      .eu-header h1 {
        margin: 8px 0 0;
        font-size: 2rem;
      }
      .eu-header-meta {
        font-size: 0.9rem;
        color: #475569;
      }
      .eu-photo-wrap {
        margin-bottom: 10px;
      }
      .eu-photo-shell {
        width: 100%;
        height: 48mm;
        border-radius: 14px;
      }
      .eu-header-meta p {
        margin: 0 0 6px;
      }
      .eu-section {
        display: grid;
        grid-template-columns: 40mm 1fr;
        gap: 14px;
        padding-top: 12px;
        margin-top: 12px;
        border-top: 1px solid rgba(15, 23, 42, 0.1);
      }
      .eu-label {
        font: 700 0.8rem/1.4 "Segoe UI", sans-serif;
        text-transform: uppercase;
        letter-spacing: 0.12em;
        color: #37506b;
      }
      .about-label {
        padding-top: 2px;
      }
      .eu-content p {
        margin: 0;
        line-height: 1.55;
      }
      .eu-row + .eu-row {
        margin-top: 12px;
        padding-top: 12px;
        border-top: 1px dashed rgba(55, 80, 107, 0.15);
      }
      .eu-row {
        display: grid;
        grid-template-columns: 28mm 1fr;
        gap: 10px;
      }
      .eu-row .eu-label {
        font-size: 0.75rem;
        letter-spacing: 0.08em;
      }
      .eu-content h3 {
        margin: 0;
        font-size: 1rem;
      }
      .company {
        margin: 4px 0 0 !important;
        color: #607286;
      }
      .eu-bullets {
        margin: 8px 0 0 18px;
        padding: 0;
      }
      .eu-bullets li + li {
        margin-top: 5px;
      }
      .skill-columns {
        columns: 2;
        column-gap: 26px;
        margin: 0;
        padding-left: 18px;
      }
      .skill-columns li {
        break-inside: avoid;
        margin-bottom: 6px;
      }
    """
    return _html_page(_variant_title("Europass Lite CV"), body, css)


def _template_signal_header() -> str:
    photo = _photo_markup(PROFILE.get("photo_src", ""), shell_class="photo-shell signal-photo-shell")
    body = f"""
    <main class="sheet signal-sheet">
      <header class="signal-header">
        <div class="signal-copy">
          <p class="caps signal-kicker">Browser-editable concept</p>
          <h1>{escape(PROFILE['name'])}</h1>
          <p class="signal-headline">{escape(PROFILE['headline'])}</p>
          <p class="signal-summary">{escape(PROFILE['summary'])}</p>
        </div>
        {photo}
      </header>
      <section class="signal-meta">
        <span>{escape(PROFILE['location'])}</span>
        <a href="mailto:{escape(PROFILE['email'])}">{escape(PROFILE['email'])}</a>
        <a href="{escape(PROFILE['linkedin'])}">LinkedIn</a>
        <a href="{escape(PROFILE['github'])}">GitHub</a>
      </section>
      <div class="signal-grid">
        <div>
          <section class="signal-section">
            <h2>Skills</h2>
            <div class="signal-tags">{''.join(f"<span>{escape(skill)}</span>" for skill in PROFILE['skills'])}</div>
          </section>
          <section class="signal-section">
            <h2>Education</h2>
            <p><strong>{escape(PROFILE['education'][0]['degree'])}</strong></p>
            <p>{escape(PROFILE['education'][0]['school'])}</p>
            <p>{escape(PROFILE['education'][0]['details'])}</p>
          </section>
        </div>
        <div>
          <section class="signal-section">
            <h2>Experience</h2>
            {_render_experience("signal-role", "signal-bullets")}
          </section>
        </div>
      </div>
    </main>
    """
    css = """
      .signal-sheet {
        padding: 0 0 18mm;
        font-family: "Aptos", "Segoe UI", sans-serif;
      }
      .signal-header {
        display: flex;
        justify-content: space-between;
        gap: 18px;
        align-items: flex-start;
        padding: 18mm 18mm 14mm;
        background:
          radial-gradient(circle at top right, rgba(251, 191, 36, 0.28), transparent 34%),
          linear-gradient(135deg, #18324a 0%, #0f172a 100%);
        color: white;
      }
      .signal-kicker {
        margin: 0 0 10px;
        color: rgba(255, 255, 255, 0.72);
      }
      .signal-header h1 {
        margin: 0;
        font-size: 2.45rem;
      }
      .signal-headline {
        margin: 10px 0 0;
        font-size: 1.08rem;
        color: rgba(255, 255, 255, 0.88);
      }
      .signal-summary {
        margin: 14px 0 0;
        max-width: 88%;
        line-height: 1.7;
        color: rgba(255, 255, 255, 0.84);
      }
      .signal-photo-shell {
        border-radius: 22px;
        border-color: rgba(255, 255, 255, 0.2);
        background: rgba(255, 255, 255, 0.06);
      }
      .signal-meta {
        display: flex;
        flex-wrap: wrap;
        gap: 10px 16px;
        padding: 12px 18mm 0;
        color: #475569;
        font-size: 0.9rem;
      }
      .signal-grid {
        display: grid;
        grid-template-columns: 0.78fr 1.22fr;
        gap: 22px;
        padding: 12px 18mm 0;
      }
      .signal-section + .signal-section {
        margin-top: 18px;
      }
      .signal-section h2 {
        margin: 0 0 10px;
        font-size: 0.8rem;
        font-weight: 800;
        letter-spacing: 0.16em;
        text-transform: uppercase;
        color: #18324a;
      }
      .signal-tags {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
      }
      .signal-tags span {
        display: inline-flex;
        padding: 0.36rem 0.7rem;
        border-radius: 999px;
        background: #eef4fa;
        border: 1px solid rgba(24, 50, 74, 0.1);
        font-size: 0.82rem;
        font-weight: 700;
      }
      .signal-role + .signal-role {
        margin-top: 14px;
        padding-top: 14px;
        border-top: 1px solid rgba(24, 50, 74, 0.1);
      }
      .signal-role h3 {
        margin: 0;
        font-size: 1rem;
      }
      .signal-role .company {
        margin: 4px 0 0;
        color: #5b6b7b;
      }
      .signal-role .period {
        color: #5b6b7b;
        font-weight: 700;
      }
      .signal-role .role-line {
        display: flex;
        justify-content: space-between;
        gap: 12px;
      }
      .signal-bullets {
        margin: 8px 0 0 18px;
        padding: 0;
      }
      .signal-bullets li + li {
        margin-top: 5px;
      }
    """
    return _html_page(_variant_title("Signal Header CV"), body, css)


def _template_ledger_split() -> str:
    photo = _photo_markup(PROFILE.get("photo_src", ""), shell_class="photo-shell ledger-photo-shell")
    body = f"""
    <main class="sheet ledger-sheet">
      <header class="ledger-header">
        <div class="ledger-headline-block">
          <p class="caps">Compact detail-heavy layout</p>
          <h1>{escape(PROFILE['name'])}</h1>
          <p class="ledger-headline">{escape(PROFILE['headline'])}</p>
        </div>
        <div class="ledger-side">
          {photo}
          <div class="ledger-links">
            <p>{escape(PROFILE['location'])}</p>
            <p><a href="mailto:{escape(PROFILE['email'])}">{escape(PROFILE['email'])}</a></p>
            <p><a href="{escape(PROFILE['linkedin'])}">LinkedIn</a></p>
            <p><a href="{escape(PROFILE['github'])}">GitHub</a></p>
          </div>
        </div>
      </header>
      <div class="ledger-grid">
        <aside class="ledger-rail">
          <section class="ledger-section">
            <h2>Profile</h2>
            <p>{escape(PROFILE['summary'])}</p>
          </section>
          <section class="ledger-section">
            <h2>Skills</h2>
            <ul class="ledger-skill-list">{''.join(f"<li>{escape(skill)}</li>" for skill in PROFILE['skills'])}</ul>
          </section>
          <section class="ledger-section">
            <h2>Education</h2>
            <p><strong>{escape(PROFILE['education'][0]['degree'])}</strong></p>
            <p>{escape(PROFILE['education'][0]['school'])}</p>
            <p>{escape(PROFILE['education'][0]['details'])}</p>
          </section>
        </aside>
        <section class="ledger-main">
          <section class="ledger-section">
            <h2>Experience</h2>
            {_render_experience("ledger-role", "ledger-bullets")}
          </section>
          <section class="ledger-section">
            <h2>Availability</h2>
            <p>{escape(PROFILE['availability'])}</p>
          </section>
        </section>
      </div>
    </main>
    """
    css = """
      .ledger-sheet {
        padding: 16mm 16mm 18mm;
        font-family: "Segoe UI", "Helvetica Neue", sans-serif;
      }
      .ledger-header {
        display: flex;
        justify-content: space-between;
        gap: 18px;
        padding-bottom: 14px;
        border-bottom: 2px solid #18324a;
      }
      .ledger-header h1 {
        margin: 8px 0 0;
        font-size: 2.25rem;
      }
      .ledger-headline {
        margin: 10px 0 0;
        color: #475569;
        font-size: 1rem;
      }
      .ledger-side {
        display: grid;
        gap: 10px;
        justify-items: end;
      }
      .ledger-photo-shell {
        border-radius: 20px;
      }
      .ledger-links {
        text-align: right;
        font-size: 0.84rem;
        color: #5b6b7b;
      }
      .ledger-links p {
        margin: 0;
      }
      .ledger-links p + p {
        margin-top: 4px;
      }
      .ledger-grid {
        display: grid;
        grid-template-columns: 0.84fr 1.16fr;
        gap: 22px;
        margin-top: 16px;
      }
      .ledger-section + .ledger-section {
        margin-top: 18px;
      }
      .ledger-section h2 {
        margin: 0 0 10px;
        font-size: 0.8rem;
        font-weight: 800;
        letter-spacing: 0.16em;
        text-transform: uppercase;
        color: #18324a;
      }
      .ledger-section p {
        margin: 0;
        line-height: 1.6;
      }
      .ledger-skill-list {
        margin: 0;
        padding-left: 18px;
      }
      .ledger-skill-list li + li {
        margin-top: 5px;
      }
      .ledger-role + .ledger-role {
        margin-top: 14px;
        padding-top: 14px;
        border-top: 1px solid rgba(24, 50, 74, 0.1);
      }
      .ledger-role .role-line {
        display: flex;
        justify-content: space-between;
        gap: 12px;
      }
      .ledger-role h3 {
        margin: 0;
        font-size: 1rem;
      }
      .ledger-role .company {
        margin: 4px 0 0;
        color: #5b6b7b;
      }
      .ledger-role .period {
        color: #5b6b7b;
        font-weight: 700;
      }
      .ledger-bullets {
        margin: 8px 0 0 18px;
        padding: 0;
      }
      .ledger-bullets li + li {
        margin-top: 5px;
      }
    """
    return _html_page(_variant_title("Ledger Split CV"), body, css)


def _gallery_html() -> str:
    cards = []
    for template in TEMPLATES:
        cards.append(
            f"""
            <article class="card">
              <div class="card-copy">
                <span class="tag">{escape(template['title'])}</span>
                <h2>{escape(template['title'])}</h2>
                <p class="subtitle">{escape(template['subtitle'])}</p>
                <p>{escape(template['source_summary'])}</p>
                <p class="photo-note">Profile photo slot included.</p>
                <div class="actions">
                  <a class="primary" href="{escape(template['slug'])}.html">With photo</a>
                  <a class="secondary" href="{escape(template['slug'])}_no_photo.html">No photo</a>
                </div>
              </div>
            </article>
            """
        )
    research_items = "".join(
        f"<li><a href=\"{escape(item['url'])}\">{escape(item['title'])}</a> — {escape(item['reason'])}</li>"
        for item in RESEARCH_ITEMS
    )
    body = f"""
    <main class="gallery-shell">
      <section class="hero">
        <p class="caps hero-kicker">Web-inspired CV gallery</p>
        <h1>Lightweight templates worth implementing in code</h1>
        <p class="hero-copy">
          These are not copies of the source templates. They are code-light adaptations built from the
          design patterns that kept showing up in the research: simple structure, strong hierarchy,
          restrained decoration, reverse chronology, and ATS-safe content flow.
        </p>
      </section>
      <section class="cards">
        {''.join(cards)}
      </section>
      <section class="research">
        <h2>Research links</h2>
        <ul>{research_items}</ul>
      </section>
    </main>
    """
    css = """
      body {
        background:
          radial-gradient(circle at top left, rgba(168, 208, 255, 0.35), transparent 24%),
          radial-gradient(circle at 85% 10%, rgba(247, 196, 145, 0.3), transparent 22%),
          linear-gradient(180deg, #f7f3eb 0%, #f5f7fb 100%);
      }
      .gallery-shell {
        max-width: 1120px;
        margin: 0 auto;
        padding: 40px 24px 60px;
      }
      .hero {
        max-width: 760px;
      }
      .hero-kicker {
        margin: 0 0 14px;
        font-size: 0.76rem;
        letter-spacing: 0.18em;
        color: #475569;
        font-weight: 700;
      }
      .hero h1 {
        margin: 0;
        font: 700 clamp(2.4rem, 5vw, 4rem)/0.95 Georgia, "Times New Roman", serif;
        color: #0f172a;
      }
      .hero-copy {
        margin: 18px 0 0;
        font-size: 1.05rem;
        line-height: 1.7;
        color: #334155;
      }
      .cards {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 18px;
        margin-top: 30px;
      }
      .card {
        min-height: 250px;
        border-radius: 24px;
        border: 1px solid rgba(15, 23, 42, 0.08);
        background:
          linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(255, 255, 255, 0.9)),
          linear-gradient(135deg, rgba(198, 216, 255, 0.2), rgba(255, 241, 225, 0.24));
        box-shadow: 0 20px 44px rgba(15, 23, 42, 0.08);
      }
      .card-copy {
        padding: 24px;
      }
      .card h2 {
        margin: 16px 0 0;
        font: 700 1.7rem/1.05 Georgia, serif;
      }
      .subtitle {
        margin: 10px 0 0;
        font-weight: 700;
        color: #4f6275;
      }
      .card p:last-of-type {
        line-height: 1.6;
        color: #334155;
      }
      .photo-note {
        margin-top: 10px;
        font-size: 0.9rem;
        font-weight: 700;
        color: #1d4ed8;
      }
      .actions {
        margin-top: 18px;
      }
      .primary {
        display: inline-flex;
        align-items: center;
        gap: 0.45rem;
        padding: 0.78rem 1rem;
        border-radius: 999px;
        background: #0f172a;
        color: white;
        text-decoration: none;
        font-weight: 700;
      }
      .secondary {
        display: inline-flex;
        align-items: center;
        gap: 0.45rem;
        padding: 0.78rem 1rem;
        border-radius: 999px;
        border: 1px solid rgba(15, 23, 42, 0.12);
        background: white;
        color: #0f172a;
        text-decoration: none;
        font-weight: 700;
      }
      .research {
        margin-top: 30px;
        padding: 22px 24px;
        border-radius: 22px;
        background: rgba(255, 255, 255, 0.78);
        border: 1px solid rgba(15, 23, 42, 0.06);
      }
      .research h2 {
        margin: 0 0 12px;
        font: 700 1.25rem/1 Georgia, serif;
      }
      .research ul {
        margin: 0;
        padding-left: 20px;
      }
      .research li + li {
        margin-top: 8px;
      }
      @media (max-width: 800px) {
        .cards {
          grid-template-columns: 1fr;
        }
      }
      @media print {
        .gallery-shell {
          max-width: none;
          padding: 0;
        }
        .cards {
          grid-template-columns: 1fr;
        }
        .card,
        .research {
          box-shadow: none;
        }
      }
    """
    return _html_page("Web-Inspired CV Template Gallery", body, css)


def _readme_text() -> str:
    return """# Web-Inspired CV Templates

This folder contains print-ready HTML CV prototypes chosen from web research because they are both:

- light to generate in code
- visually strong enough to compare with the repo's current CV outputs

Implemented templates:

- `01_ats_single_column.html`
- `01_ats_single_column_no_photo.html`
- `02_editorial_sidebar.html`
- `02_editorial_sidebar_no_photo.html`
- `03_mono_nav.html`
- `03_mono_nav_no_photo.html`
- `04_europass_lite.html`
- `04_europass_lite_no_photo.html`
- `05_signal_header.html`
- `05_signal_header_no_photo.html`
- `06_ledger_split.html`
- `06_ledger_split_no_photo.html`
- `index.html` gallery entry point

Photo support:

- Every template includes profile photo support.
- If a candidate photo exists in the configured repo path, it is copied into `_assets/` and rendered automatically.
- If no photo exists, the layout still renders with a clean placeholder so the slot remains easy to use.

Why these patterns:

- `ATS Single Column`: highest robustness and lowest generation complexity
- `Editorial Sidebar`: best visual payoff for minimal layout code
- `Mono Nav`: modern feel without complex composition logic
- `Europass Lite`: Europe-familiar structure without the full Europass visual heaviness
- `Signal Header`: strongest visual presence while still remaining code-light
- `Ledger Split`: dense, practical layout for detail-heavy applications

Research sources:

"""


def build_templates() -> list[Path]:
    _ensure_dir(OUTPUT_DIR)
    photo_src = _prepare_profile_photo_asset()
    PROFILE["photo_src"] = photo_src

    created_files: list[Path] = []
    template_builders = [
        ("01_ats_single_column.html", _template_ats_single_column, photo_src),
        ("01_ats_single_column_no_photo.html", _template_ats_single_column, ""),
        ("02_editorial_sidebar.html", _template_editorial_sidebar, photo_src),
        ("02_editorial_sidebar_no_photo.html", _template_editorial_sidebar, ""),
        ("03_mono_nav.html", _template_mono_nav, photo_src),
        ("03_mono_nav_no_photo.html", _template_mono_nav, ""),
        ("04_europass_lite.html", _template_europass_lite, photo_src),
        ("04_europass_lite_no_photo.html", _template_europass_lite, ""),
        ("05_signal_header.html", _template_signal_header, photo_src),
        ("05_signal_header_no_photo.html", _template_signal_header, ""),
        ("06_ledger_split.html", _template_ledger_split, photo_src),
        ("06_ledger_split_no_photo.html", _template_ledger_split, ""),
        ("index.html", _gallery_html, photo_src),
    ]

    for filename, builder, variant_photo_src in template_builders:
        PROFILE["photo_src"] = variant_photo_src
        path = OUTPUT_DIR / filename
        path.write_text(builder(), encoding="utf-8")
        created_files.append(path)
    PROFILE["photo_src"] = photo_src

    readme_lines = [_readme_text()]
    for item in RESEARCH_ITEMS:
        readme_lines.append(f"- {item['title']}: {item['url']}")
    (OUTPUT_DIR / "README.md").write_text("\n".join(readme_lines) + "\n", encoding="utf-8")
    created_files.append(OUTPUT_DIR / "README.md")

    research_body = "\n".join(
        [
            "# Web Research Notes",
            "",
            "Selection logic:",
            "",
            "- I prioritized layouts that preserve a clear reading order and avoid heavy template machinery.",
            "- I treated official career-service ATS advice as the constraint layer.",
            "- I used template galleries as inspiration for layout shapes, not as material to reproduce verbatim.",
            "",
            "Sources:",
            "",
            *[
                f"- [{item['title']}]({item['url']}): {item['reason']}"
                for item in RESEARCH_ITEMS
            ],
            "",
            "Result:",
            "",
            "- The best code-light options are still a disciplined single-column base, a restrained sidebar, a simple left rail, and a Europass-style information grid.",
        ]
    )
    (OUTPUT_DIR / "research_notes.md").write_text(research_body + "\n", encoding="utf-8")
    created_files.append(OUTPUT_DIR / "research_notes.md")

    return created_files


def main() -> int:
    created = build_templates()
    for path in created:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
