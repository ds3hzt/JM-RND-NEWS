import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import update_news


def candidate(source='https://example.com/news', region='국내', published='2026-10-23'):
    return {
        'title': '커넥터 도금 기술 동향',
        'source': source,
        'region': region,
        'published': published,
    }


def recommendation(source='https://example.com/news', region='국내'):
    return {
        'region': region,
        'category': '도금기술',
        'title': '커넥터 도금 기술 동향',
        'summary': 'RSS 제목에서 확인 가능한 내용입니다.',
        'keywords': ['커넥터', '도금'],
        'background': '세부 배경은 원문을 확인해야 합니다.',
        'impact': '추정: 관련 공정의 적용성을 검토할 수 있습니다.',
        'source': source,
    }


class CandidateCollectionTests(unittest.TestCase):
    def test_expanded_search_runs_when_recent_search_has_no_new_candidate(self):
        recent = [('국내', '기본 검색')]
        expanded = [('해외', '확대 검색')]
        with patch.object(update_news, 'QUERIES', recent), patch.object(
            update_news, 'EXPANDED_QUERIES', expanded
        ), patch.object(
            update_news, 'fetch',
            side_effect=lambda query, region, days: [candidate(region=region)] if days == 30 else [],
        ) as fetch:
            found = update_news.collect_candidates([])

        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]['region'], '해외')
        self.assertEqual([call.args[2] for call in fetch.call_args_list], [7, 30])

    def test_expanded_search_reports_no_candidates(self):
        with patch.object(update_news, 'QUERIES', [('국내', '기본')]), patch.object(
            update_news, 'EXPANDED_QUERIES', [('해외', '확대')]
        ), patch.object(update_news, 'fetch', return_value=[]):
            with self.assertRaisesRegex(RuntimeError, '확대 검색에서 새 후보'):
                update_news.collect_candidates([])


class PublishingTests(unittest.TestCase):
    def test_one_verified_article_is_published(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'news.json').write_text('[]', encoding='utf-8')
            with patch.object(update_news, 'ROOT', root), patch.object(
                update_news, 'TODAY', '2026-10-23'
            ), patch.object(
                update_news, 'collect_candidates', return_value=[candidate()]
            ), patch.object(
                update_news, 'generate', return_value=[recommendation()]
            ):
                update_news.main()

            published = json.loads((root / 'news.json').read_text(encoding='utf-8'))
            self.assertEqual(len(published), 1)
            self.assertEqual(published[0]['date'], '2026-10-23')

    def test_invalid_ai_result_retries_with_one_candidate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'news.json').write_text('[]', encoding='utf-8')
            with patch.object(update_news, 'ROOT', root), patch.object(
                update_news, 'TODAY', '2026-10-23'
            ), patch.object(
                update_news, 'collect_candidates', return_value=[candidate()]
            ), patch.object(
                update_news, 'generate', side_effect=[[], [recommendation()]]
            ) as generate:
                update_news.main()

            self.assertEqual(generate.call_count, 2)
            published = json.loads((root / 'news.json').read_text(encoding='utf-8'))
            self.assertEqual(len(published), 1)

    def test_generate_formats_prompt_for_single_candidate(self):
        response = {'choices': [{'message': {'content': json.dumps({'articles': []})}}]}
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}), patch.object(
            update_news.urllib.request, 'urlopen', return_value=io.BytesIO(json.dumps(response).encode())
        ) as urlopen:
            self.assertEqual(update_news.generate([candidate()]), [])

        request = urlopen.call_args.args[0]
        payload = json.loads(request.data)
        prompt = payload['messages'][0]['content']
        self.assertIn('뉴스 1~1건', prompt)
        self.assertIn('{"articles":[', prompt)


if __name__ == '__main__':
    unittest.main()
