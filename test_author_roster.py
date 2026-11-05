import io
import unittest
import zipfile
from author_roster import parse_word_names,identify_word_authors
from unittest.mock import patch


def document(body):
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w') as z:z.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'+body+'</w:body></w:document>')
    return buffer.getvalue()


def table(rows):
    return '<w:tbl>'+''.join('<w:tr>'+''.join('<w:tc><w:p><w:r><w:t>'+cell+'</w:t></w:r></w:p></w:tc>' for cell in row)+'</w:tr>' for row in rows)+'</w:tbl>'


class AuthorRosterTests(unittest.TestCase):
    def test_parser_preserves_unknown_layout_without_guessing_authors(self):
        result=parse_word_names('统计表.docx',document(table([['编号','参展人','诗文作者'],['1','张三','李白']])))
        self.assertNotIn('authors',result)
        self.assertEqual(result['blocks'][0]['rows'][1],['1','张三','李白'])

    def test_ai_selects_author_and_returns_source_evidence(self):
        doc=parse_word_names('名单.docx',document(table([['任意排版','备注'],['张三','书写者'],['李白','诗文原作者']])))
        response={'entries':[dict(name='张三',status='clear',block_id=0,row=1,column=0,quote='张三',reason='旁边说明为书写者')]}
        with patch('author_roster.request_json',return_value=response) as request:result=identify_word_authors(doc,('key','url','model'))
        self.assertEqual(result['authors'],['张三'])
        self.assertIn('李白',request.call_args.args[0][0]['text'])
        self.assertIn('第 2 行',result['entries'][0]['location'])

    def test_uncertain_and_invented_names_are_not_saved_automatically(self):
        doc=parse_word_names('名单.docx',document(table([['张三','王五']])))
        response={'entries':[dict(name='张三',status='uncertain',block_id=0,row=0,column=0,quote='张三',reason='身份不明确'),dict(name='李四',status='clear',block_id=0,row=0,column=1,quote='李四')]}
        with patch('author_roster.request_json',return_value=response):result=identify_word_authors(doc,('key','url','model'))
        self.assertEqual(result['authors'],[])
        self.assertEqual(len(result['entries']),1)
        self.assertIn('1 项',result['message'])

    def test_only_images_cannot_be_claimed_as_read(self):
        with self.assertRaisesRegex(ValueError,'没有可读取的文字'):parse_word_names('扫描.docx',document('<w:p/>'))

    def test_legacy_and_invalid_documents_rejected(self):
        for filename,raw in [('名单.doc',b'bad'),('名单.docx',b'bad')]:
            with self.assertRaises(ValueError):parse_word_names(filename,raw)


if __name__=='__main__':unittest.main()
