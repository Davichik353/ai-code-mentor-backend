import base64
import io
import zipfile
import unittest
from unittest.mock import patch, AsyncMock
from fastapi import HTTPException
from assignment_import import ImportRequest, extract_source, TaskDraft, DraftBatch
from test_learning import LearningWorkflowTests

TASK = dict(title='Сумма',prompt='Введите два целых числа, каждое на отдельной строке. Выведите их сумму.',language='Python',tests=[dict(stdin='2\n3',expected_stdout='5'),dict(stdin='-3\n3',expected_stdout='0')],defense_question='Как обрабатываются отрицательные числа?',change='Прочитайте третье число и добавьте к сумме.')

class ImportParsingTests(unittest.TestCase):
    def test_text_and_docx(self):
        self.assertEqual(extract_source(ImportRequest(text=TASK['prompt'])), TASK['prompt'])
        buf=io.BytesIO()
        with zipfile.ZipFile(buf,'w') as z:
            z.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:r><w:t>'+TASK['prompt']+'</w:t></w:r></w:p></w:document>')
        self.assertIn(TASK['prompt'],extract_source(ImportRequest(filename='task.docx',file_base64=base64.b64encode(buf.getvalue()).decode())))
    def test_invalid_file_and_empty(self):
        for data in [ImportRequest(),ImportRequest(filename='task.doc',file_base64='YWJj'),ImportRequest(filename='task.pdf',file_base64='invalid!')]:
            with self.assertRaises(HTTPException): extract_source(data)

class CustomAssignmentTests(LearningWorkflowTests):
    def test_custom_publish_permissions_and_content(self):
        path=f"/groups/{self.group['id']}/custom-assignments"
        self.call('POST',path,self.student,TASK,404)
        self.call('POST',path,self.outsider,TASK,404)
        created=self.call('POST',path,self.teacher,TASK,201)
        detail=self.call('GET',f"/assignments/{created['id']}",self.student)
        self.assertTrue(detail['custom'])
        self.assertEqual(detail['starter_code'],'')
        self.assertNotIn('solution',detail)
        self.assertEqual(detail['tests'],TASK['tests'])
        self.call('POST',path,self.teacher,{**TASK,'language':'Bash'},422)
        self.call('POST',f"/groups/{self.group['id']}/archive",self.teacher,{})
        self.call('POST',path,self.teacher,TASK,409)
    def test_generate_draft_is_not_publication(self):
        path=f"/groups/{self.group['id']}/assignment-drafts"
        with patch('learning_routes.generate_drafts',new_callable=AsyncMock,return_value=DraftBatch(tasks=[TaskDraft(**TASK)])) as generate:
            self.call('POST',path,self.student,{'text':TASK['prompt']},404)
            generate.assert_not_called()
            result=self.call('POST',path,self.teacher,{'text':TASK['prompt']})
            self.assertEqual(result['tasks'][0]['title'],'Сумма')
            group=self.call('GET',f"/groups/{self.group['id']}",self.teacher)
            self.assertEqual(len(group['assignments']),1)
