from unittest.mock import patch

def test_ai_translates_all_passages_in_one_call_preserving_originals():
    from backend.application.description_translation import english_passages
    from unittest.mock import Mock
    original = [{'id': 'p1', 'text': 'Berichte erstellen.'}, {'id': 'p2', 'text': 'Daten prüfen.'}]
    generate = Mock(spec=[], return_value={'passages': [{'id': 'p1', 'text': 'Create reports.'}, {'id': 'p2', 'text': 'Check data.'}]})
    with patch('backend.application.description_translation.source_language', return_value='de'):
        result = english_passages(original, generate=generate)
    assert generate.call_count == 1
    assert result[0]['original_text'] == original[0]['text']
    assert result[1]['text'] == 'Check data.'

def test_ai_translation_rejects_missing_or_reordered_passages():
    import pytest
    from backend.application.description_translation import english_passages
    with patch('backend.application.description_translation.source_language', return_value='de'):
        with pytest.raises(ValueError, match='translation_passage_mismatch'):
            english_passages([{'id': 'p1', 'text': 'Berichte erstellen.'}], generate=lambda _: {'passages': []})

def test_translation_preserves_passage_ids_and_original_evidence():
    from backend.application.description_translation import english_passages
    passages = [{'id': 'p1', 'text': 'Erstellen Sie Berichte.'}]
    with patch('backend.application.description_translation.source_language', return_value='de'):
        result = english_passages(passages, generate=lambda _: {'passages': [{'id': 'p1', 'text': 'Create reports.'}]})
    assert result == [{'id': 'p1', 'text': 'Create reports.', 'original_text': 'Erstellen Sie Berichte.'}]
    assert passages[0]['text'] == 'Erstellen Sie Berichte.'

def test_english_passages_do_not_call_translation():
    from backend.application.description_translation import english_passages
    passages = [{'id': 'p1', 'text': 'Create reports.'}]
    from unittest.mock import Mock
    translate = Mock(spec=[])
    with patch('backend.application.description_translation.source_language', return_value='en'):
        assert english_passages(passages, generate=translate) == passages
        translate.assert_not_called()

def test_nemo_gets_english_input_and_original_quotes_remain_valid():
    from backend.application.vps_job_descriptions import build_pilot_description
    source = 'Erstellen Sie monatliche Berichte und analysieren Sie die Unternehmensdaten.'
    prompts = []
    def generate(prompt):
        prompts.append(prompt)
        return {'items': [{'section': 'responsibilities', 'text': 'Create monthly reports.',
                           'source_ids': ['p1'], 'source_quote': source}], 'header_candidates': {}}
    with patch('backend.application.description_translation.english_passages', return_value=[
            {'id': 'p1', 'text': 'Create monthly reports and analyze business data.', 'original_text': source}]):
        result = build_pilot_description({'description': source, '_translate_before_nemo': True}, generate, require_source_quotes=True)
    assert 'Create monthly reports and analyze business data.' in prompts[0]
    assert result['summary']['responsibilities'][0]['source_quote'] == source
    assert result['structured_description']['source_passages'][0]['text'] == source
    assert result['structured_description']['translation_pipeline'] == 'english_input_v1'
