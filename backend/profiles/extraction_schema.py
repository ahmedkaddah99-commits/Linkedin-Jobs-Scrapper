"""Shared structured document-extraction response schema."""

_EXTRACTION_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "extracted_text": {"type": "string", "description": "Full extracted text content from the document or image."},
        "layout_sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Section heading or label."},
                    "type": {"type": "string", "description": "Section type: heading, paragraph, list, table, caption, annotation, comment."},
                    "text": {"type": "string", "description": "Text content of this section."},
                },
                "required": ["title", "type", "text"],
            },
        },
        "experience_details": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "employer": {"type": "string", "description": "Employer or organization name."},
                    "role": {"type": "string", "description": "Job title or role."},
                    "location": {"type": "string", "description": "Location of this experience."},
                    "start_date": {"type": "string", "description": "Start date as written."},
                    "end_date": {"type": "string", "description": "End date as written."},
                    "dates": {"type": "string", "description": "Original date range or duration."},
                    "bullets": {"type": "array", "items": {"type": "string"}, "description": "Bullet points describing responsibilities and achievements."},
                },
            },
        },
        "evidence_items": {
            "type": "array",
            "description": "Meaningful candidate claims tied to an experience_details entry.",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Complete reviewable claim."},
                    "evidence_type": {"type": "string", "description": "achievement, metric, responsibility, project, leadership, stakeholder, challenge, tool, education, or motivation."},
                    "inferred_employer": {"type": "string"},
                    "inferred_role": {"type": "string"},
                    "dates": {"type": "array", "items": {"type": "string"}},
                    "location": {"type": "string"},
                    "source_section": {"type": "string"},
                },
                "required": ["text", "evidence_type"],
            },
        },
        "confidence": {"type": "number", "description": "Overall confidence score between 0.0 and 1.0 for the extraction quality."},
        "warnings": {"type": "array", "items": {"type": "string"}, "description": "Any warnings about low-quality text, missing sections, or extraction issues."},
    },
    "required": ["extracted_text", "confidence", "warnings"],
}
