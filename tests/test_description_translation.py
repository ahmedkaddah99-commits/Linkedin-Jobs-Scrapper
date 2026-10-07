from unittest.mock import patch

def test_translation_preserves_passage_ids_and_original_evidence():
    from backend.application.description_translation import english_passages
    passages = [{'id': 'p1', 'text': 'Erstellen Sie Berichte.'}]
    with patch('backend.application.description_translation.source_language', return_value='de'), patch('backend.application.description_translation.translate_text', return_value='Create reports.'):
        result = english_passages(passages)
    assert result == [{'id': 'p1', 'text': 'Create reports.', 'original_text': 'Erstellen Sie Berichte.'}]
    assert passages[0]['text'] == 'Erstellen Sie Berichte.'

def test_english_passages_do_not_call_translation():
    from backend.application.description_translation import english_passages
    passages = [{'id': 'p1', 'text': 'Create reports.'}]
    with patch('backend.application.description_translation.source_language', return_value='en'), patch('backend.application.description_translation.translate_text') as translate:
        assert english_passages(passages) == passages
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
    assert result['structured_description']['translation_pipeline'] == 'argos_english_v1'
