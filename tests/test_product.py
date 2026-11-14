from unittest.mock import patch, AsyncMock
from test_learning import LearningWorkflowTests
from assignment_import import TaskDraft
from pydantic import ValidationError
import os

class ProductTests(LearningWorkflowTests):
    def test_lifecycle_deadlines_grades_export_and_drafts(self):
        group='/groups/'+self.group['id']; item='/assignments/'+self.assignment
        student_id=self.call('GET',group,self.teacher)['members'][0]['id']
        self.call('POST',item+'/settings',self.student,{},404)
        self.call('POST',item+'/settings',self.teacher,{'due_at':'2020-01-01T00:00:00'},422)
        self.call('POST',item+'/settings',self.teacher,{'due_at':'2020-01-01T00:00:00Z','allow_late':False,'hints_allowed':False,'solution_allowed':False})
        self.call('POST',item+'/submissions',self.student,self.payload(),409)
        self.call('POST',item+'/hints',self.student,{},403)
        self.call('POST',item+'/mentor',self.student,{'code':'print(1)'},403)
        self.call('POST',item+'/solution',self.student,{'reflection':'I need to understand what the program does.'},403)
        self.call('POST',item+'/settings',self.teacher,{'due_at':'2020-01-01T00:00:00Z','allow_late':True})
        work=self.submit();self.assertTrue(work['late'])
        self.call('POST','/submissions/'+work['id']+'/review',self.teacher,{'decision':'approved','feedback':'Correct solution and explanation of boundary cases.','score':85})
        self.assertEqual(self.call('GET','/submissions/'+work['id'],self.student)['score'],85)
        response=self.client.get('/learning'+group+'/journal.csv',headers=self.teacher)
        self.assertEqual(response.status_code,200);self.assertIn(';85;',response.text)
        self.assertEqual(self.client.get('/learning'+group+'/journal.csv',headers=self.student).status_code,404)
        draft={'revision':0,'payload':{'assignmentCode':'print(42)','codePasteDetected':'true'}}
        self.call('POST',item+'/draft',self.outsider,draft,404)
        saved=self.call('POST',item+'/draft',self.student,draft);self.assertEqual(saved['revision'],1)
        self.call('POST',item+'/draft',self.student,draft,409)
        saved=self.call('POST',item+'/draft',self.student,{'revision':1,'payload':{'assignmentCode':'print(43)'}})
        self.assertEqual(saved['payload']['codePasteDetected'],'true')
        self.assertEqual(self.call('GET',item+'/draft',self.student)['payload']['assignmentCode'],'print(43)')
        self.call('POST',group+'/members/'+student_id+'/remove',self.outsider,{},404)
        self.call('POST',group+'/members/'+student_id+'/remove',self.teacher,{})
        self.call('POST','/groups/join',self.student,{'code':self.group['join_code']},403)
        self.call('GET',item+'/draft',self.student,status=404)
        self.call('GET','/submissions/'+work['id'],self.teacher)
        self.call('POST',group+'/members/'+student_id+'/restore',self.teacher,{})
        self.call('POST','/groups/join',self.student,{'code':self.group['join_code']})
        rotated=self.call('POST',group+'/invite/rotate',self.teacher,{})
        self.assertNotEqual(rotated['join_code'],self.group['join_code'])
        self.call('POST','/groups/join',self.outsider,{'code':self.group['join_code']},404)

    def test_school_transfer_keeps_work_and_revokes_old_teacher(self):
        work=self.submit(); school=self.call('POST','/schools',self.teacher,{'title':'School'},201)['id']; path='/schools/'+school
        self.call('GET',path,self.outsider,status=404)
        invitation=self.call('POST',path+'/invite',self.teacher,{})
        self.call('POST','/schools/join',self.outsider,{'id':invitation['code']})
        self.call('POST','/schools/join',self.student,{'id':invitation['code']},404)
        detail=self.call('GET',path,self.teacher)
        teacher_id=next(m['id'] for m in detail['staff'] if m['id']!=detail['admin_id'])
        self.call('POST',path+'/groups',self.outsider,{'id':self.group['id']},404)
        self.call('POST',path+'/groups',self.teacher,{'id':self.group['id']})
        shared=self.call('POST',path+'/library',self.teacher,{'id':self.assignment})
        library=self.call('GET',path,self.outsider)['library']
        self.assertEqual(library[0]['id'],shared['id'])
        self.call('POST',path+'/transfer',self.outsider,{'group_id':self.group['id'],'teacher_id':teacher_id},404)
        self.call('POST',path+'/transfer',self.teacher,{'group_id':self.group['id'],'teacher_id':teacher_id})
        self.call('GET','/submissions/'+work['id'],self.teacher,status=404)
        self.call('GET','/submissions/'+work['id'],self.outsider)
        self.call('POST',path+'/staff/'+teacher_id+'/remove',self.teacher,{},409)
        self.call('POST',path+'/library/assign',self.outsider,{'group_id':self.group['id'],'library_id':shared['id']},201)
        self.assertEqual(self.client.delete('/auth/account',headers=self.teacher).status_code,409)
        self.assertEqual(self.client.delete('/auth/account',headers=self.outsider).status_code,409)
        self.call('POST',path+'/transfer',self.teacher,{'group_id':self.group['id'],'teacher_id':detail['admin_id']})
        self.call('POST',path+'/staff/'+teacher_id+'/remove',self.teacher,{})
        self.call('GET',path,self.outsider,status=404)

    def test_server_grading_does_not_trust_browser_and_hides_outputs(self):
        path='/assignments/'+self.assignment
        self.call('POST',path+'/settings',self.teacher,{'server_check':True},503)
        with patch('judge.configured',return_value=True):
            self.call('POST',path+'/settings',self.teacher,{'server_check':True})
        detail=self.call('GET',path,self.student);self.assertEqual(detail['tests'],[])
        self.call('POST',path+'/settings',self.teacher,{'server_check':False},409)
        cases=[{'stdout':'secret input','error':'secret error','passed':False} for i in range(3)]
        with patch('learning.run_cases',return_value=cases) as run:
            result=self.call('POST',path+'/run',self.student,{'code':'print(1)'})
            self.assertNotIn('secret',str(result))
            work=self.submit() # forged successful browser report must not pass
            self.assertFalse(work['tests_passed']);self.assertEqual(work['verification'],'server_verified')
            self.assertNotIn('secret',str(work)); self.assertEqual(run.call_count,2)
        read=self.call('GET','/submissions/'+work['id'],self.student)
        self.assertEqual(read['tests'],[]);self.assertNotIn('secret',str(read))
        self.assertIn('secret',str(self.call('GET','/submissions/'+work['id'],self.teacher)))
        self.assertNotIn('secret',str(self.call('GET',path,self.student)))

    def test_mentor_context_and_permissions(self):
        path='/assignments/'+self.assignment+'/mentor'
        with patch('learning_product_routes.advise',new_callable=AsyncMock,return_value={'observation':'Read input','next_step':'Convert','question':'Why?'}) as ai:
            self.call('POST',path,self.outsider,{'code':'print(1)'},404); ai.assert_not_called()
            self.call('POST',path,self.student,{'code':'print(1)','locale':'uz'})
            self.assertEqual(ai.call_args.args[-1],'uz')

    def test_encrypted_backup_restores_school_and_draft(self):
        from cryptography.fernet import Fernet
        from scripts.backup_database import backup, restore
        from pathlib import Path
        import sqlite3
        school=self.call('POST','/schools',self.teacher,{'title':'Backup school'},201)
        self.call('POST','/assignments/'+self.assignment+'/draft',self.student,{'revision':0,'payload':{'assignmentCode':'print(123)'}})
        key=Fernet.generate_key(); encrypted=Path(self.tmp.name)/'snapshot.fernet'; restored=Path(self.tmp.name)/'restored.sqlite3'
        backup(encrypted,key,self.db.db_path); restore(encrypted,restored,key)
        with sqlite3.connect(restored) as c:
            self.assertEqual(c.execute('SELECT title FROM learning_schools WHERE id=?',(school['id'],)).fetchone()[0],'Backup school')
            self.assertIn('print(123)',c.execute('SELECT payload FROM learning_drafts').fetchone()[0])
            self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])
