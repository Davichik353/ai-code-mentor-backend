from unittest.mock import patch, AsyncMock
from test_learning import LearningWorkflowTests
from learning import Learning
import main

class AdminTests(LearningWorkflowTests):
    def setUp(self):
        super().setUp()
        self.admin_env=patch('admin.admin_emails',return_value={'teacher@example.com'});self.admin_env.start();self.addCleanup(self.admin_env.stop)
        with Learning(self.db.db_path).connect() as c:
            c.execute('UPDATE users SET email_verified=1')
        self.student_id=self.db.get_user_by_email('student@example.com')['id']

    def test_permissions_and_no_credentials(self):
        for endpoint in ('users','classrooms','ai','system'):
            self.assertEqual(self.client.get('/admin/'+endpoint,headers=self.student).status_code,403)
            self.assertEqual(self.client.get('/admin/'+endpoint).status_code,401)
        self.assertFalse(self.client.get('/admin/access',headers=self.student).json()['is_admin'])
        self.assertTrue(self.client.get('/admin/access',headers=self.teacher).json()['is_admin'])
        users=self.client.get('/admin/users?q=student',headers=self.teacher).json()
        self.assertEqual(users['total'],1)
        for secret in ('password','token','verification_token','reset_token'):self.assertNotIn(secret,str(users))
        with Learning(self.db.db_path).connect() as c:c.execute("UPDATE users SET email_verified=0 WHERE email='teacher@example.com'")
        self.assertEqual(self.client.get('/admin/users',headers=self.teacher).status_code,403)

    def test_block_revokes_sessions_and_unblock_requires_new_login(self):
        path='/admin/users/'+self.student_id+'/block'
        data={'blocked':True,'reason':'Test suspension by administrator'}
        self.assertEqual(self.client.post(path,headers=self.outsider,json=data).status_code,403)
        self.assertEqual(self.client.post(path,headers=self.teacher,json=data).status_code,200)
        self.assertEqual(self.client.get('/auth/me',headers=self.student).status_code,401)
        self.assertEqual(self.client.post('/auth/login',json={'email':'student@example.com','password':'Learning-Test-Password1!'}).status_code,403)
        self.assertEqual(self.client.post('/admin/users/'+self.db.get_user_by_email('teacher@example.com')['id']+'/block',headers=self.teacher,json=data).status_code,409)
        self.assertEqual(self.client.post(path,headers=self.teacher,json={**data,'blocked':False}).status_code,200)
        self.assertEqual(self.client.get('/auth/me',headers=self.student).status_code,401)
        login=self.client.post('/auth/login',json={'email':'student@example.com','password':'Learning-Test-Password1!'})
        self.assertEqual(login.status_code,200)
        self.assertEqual(self.client.get('/auth/me',headers={'Authorization':'Bearer '+login.json()['access_token']}).status_code,200)
        with Learning(self.db.db_path).connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM admin_user_blocks').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM admin_audit').fetchone()[0],2)

    def test_ai_limits_persist_and_gate_analysis_mentor_import(self):
        settings={'enabled':False,'per_user':2,'total':10}
        self.assertEqual(self.client.post('/admin/ai',headers=self.student,json=settings).status_code,403)
        self.assertEqual(self.client.post('/admin/ai',headers=self.teacher,json={**settings,'per_user':11}).status_code,422)
        self.assertEqual(self.client.post('/admin/ai',headers=self.teacher,json=settings).status_code,200)
        self.assertEqual(self.client.get('/admin/ai',headers=self.teacher).json()['settings'],settings)
        with patch.object(main.analyzer,'analyze',new_callable=AsyncMock) as ai:
            self.assertEqual(self.client.post('/analyze',headers=self.student,json={'code':'print(123)','filename':'main.py'}).status_code,503);ai.assert_not_called()
        self.call('POST','/assignments/'+self.assignment+'/mentor',self.student,{'code':'print(123)'},503)
        self.call('POST','/groups/'+self.group['id']+'/assignment-drafts',self.teacher,{'text':'Read two integers and print their sum.'},503)

    def test_assign_teacher_archive_school_and_audit(self):
        group='/admin/groups/'+self.group['id']
        self.assertEqual(self.client.post(group+'/teacher',headers=self.teacher,json={'email':'student@example.com'}).status_code,409)
        self.assertEqual(self.client.post(group+'/teacher',headers=self.teacher,json={'email':'outsider@example.com'}).status_code,200)
        self.call('GET','/groups/'+self.group['id'],self.teacher,status=404)
        self.assertTrue(self.call('GET','/groups/'+self.group['id'],self.outsider)['can_manage'])
        self.assertEqual(self.client.post(group+'/archive',headers=self.teacher,json={'archived':True}).status_code,200)
        self.assertTrue(self.call('GET','/groups/'+self.group['id'],self.outsider)['archived'])
        school=self.call('POST','/schools',self.outsider,{'title':'Admin test school'},201)
        self.assertEqual(self.client.post('/admin/schools/'+school['id']+'/administrator',headers=self.teacher,json={'email':'student@example.com'}).status_code,200)
        self.assertTrue(self.call('GET','/schools/'+school['id'],self.student)['is_admin'])
        system=self.client.get('/admin/system',headers=self.teacher).json()
        self.assertIsNone(system['backup']);self.assertEqual(len(system['audit']),3)
        self.assertEqual(system['health']['checks']['database']['status'],'ok')
