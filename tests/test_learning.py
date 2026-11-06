"""Integration tests for learning workflow, access boundaries and opt-in publication."""
import os
import secrets
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
os.environ.setdefault('JWT_SECRET', secrets.token_urlsafe(48))
os.environ['REQUIRE_EMAIL_VERIFICATION']='false'
from fastapi.testclient import TestClient
import main
from database import Database


class LearningWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=Database(self.tmp.name+'/app.sqlite')
        self.patch=patch.object(main,'db',self.db); self.patch.start()
        main.registration_ip_limiter.clear()
        main.registration_email_limiter.clear()
        main.api_limiter.clear()
        main.auth_ip_limiter.clear()
        main.login_limiter.clear()
        main.reset_limiter.clear()
        self.client=TestClient(main.app); self.client.__enter__()
        self.teacher=self.register('teacher@example.com','Teacher')
        self.student=self.register('student@example.com','Student')
        self.outsider=self.register('outsider@example.com','Other learner')
        self.call('POST','/profile',self.teacher,{'role':'teacher'})
        self.group=self.call('POST','/groups',self.teacher,{'title':'Pilot group'},201)
        self.call('POST','/groups/join',self.student,{'code':self.group['join_code']})
        self.assignment=self.call('POST',f"/groups/{self.group['id']}/assignments",self.teacher,{'template_id':'sum-js'},201)['id']

    def tearDown(self):
        self.client.__exit__(None,None,None); self.patch.stop(); self.tmp.cleanup()

    def register(self,email,name):
        r=self.client.post('/auth/register',json={'email':email,'password':'Learning-Test-Password1!','display_name':name})
        self.assertEqual(r.status_code,201,r.text)
        return {'Authorization':'Bearer '+r.json()['access_token']}

    def call(self,method,path,user=None,body=None,status=200):
        r=self.client.request(method,'/learning'+path,headers=user or {},**({'json':body} if body is not None else {}))
        self.assertEqual(r.status_code,status,r.text)
        return r.json()

    def payload(self,pass_tests=True):
        return {'code':'console.log(Number(prompt()) + Number(prompt()))',
                'results':[{'stdout':s} for s in (['5','-10','7'] if pass_tests else ['0','0','0'])],
                'explanation':'I convert both inputs to numbers and add them. Negative numbers are included.',
                'changed_code':'console.log(Number(prompt()) + Number(prompt()) + Number(prompt()))',
                'change_explanation':'The modified program reads one extra input and adds it to the previous sum.'}

    def submit(self,passed=True):
        return self.call('POST',f'/assignments/{self.assignment}/submissions',self.student,self.payload(passed),201)

    def test_group_and_assignment_access_isolation(self):
        self.call('GET','/profile',status=401)
        self.call('POST','/groups',self.student,{'title':'No teacher role'},403)
        self.call('GET',f"/groups/{self.group['id']}",self.outsider,status=404)
        self.call('GET',f'/assignments/{self.assignment}',self.outsider,status=404)
        detail=self.call('GET',f"/groups/{self.group['id']}",self.student)
        for key in ('join_code','members','submissions','summary'):
            self.assertNotIn(key,detail)
        self.call('POST',f"/groups/{self.group['id']}/assignments",self.student,{'template_id':'sum-py'},404)
        # Becoming a teacher grants no access to other teachers' groups.
        self.call('POST','/profile',self.outsider,{'role':'teacher'})
        self.call('POST',f"/groups/{self.group['id']}/assignments",self.outsider,{'template_id':'sum-py'},404)
        templates=self.call('GET','/templates',self.student)
        self.assertEqual(len(templates),6)
        self.assertNotIn('solution',str(templates)); self.assertNotIn('hints',str(templates))

    def test_hints_are_progressive_and_example_requires_reflection(self):
        path=f'/assignments/{self.assignment}'
        detail=self.call('GET',path,self.student)
        self.assertEqual(detail['hints'],[]); self.assertNotIn('solution',detail)
        self.call('POST',path+'/solution',self.student,{'reflection':'I have tried to convert the input into a number.'},409)
        for count in (1,2,3,3):
            data=self.call('POST',path+'/hints',self.student,{})
            self.assertEqual(len(data['hints']),count)
        self.call('POST',path+'/solution',self.student,{'reflection':'short'},422)
        data=self.call('POST',path+'/solution',self.student,{'reflection':'I tried several inputs and cannot identify the conversion error.'})
        self.assertIn('Number',data['solution'])
        self.assertEqual(len(self.call('GET',path,self.student)['hints']),3)
        self.call('POST',path+'/hints',self.outsider,{},404)

    def test_defense_and_browser_reports_are_not_automatic_grades(self):
        payload=self.payload(); payload['changed_code']=payload['code']
        self.call('POST',f'/assignments/{self.assignment}/submissions',self.student,payload,422)
        payload=self.payload(); payload['results']=payload['results'][:1]
        self.call('POST',f'/assignments/{self.assignment}/submissions',self.student,payload,422)
        payload=self.payload(); payload['explanation']=' '*25
        self.call('POST',f'/assignments/{self.assignment}/submissions',self.student,payload,422)
        submission=self.submit()
        self.assertEqual(submission['status'],'pending_review')
        self.assertEqual(submission['verification'],'browser_report_unverified')
        self.assertTrue(submission['tests_passed'])
        path='/submissions/'+submission['id']
        self.call('GET',path,self.outsider,status=404)
        self.call('POST',path+'/review',self.student,{'decision':'approved','feedback':'My own submission should not be approved by me.'},404)
        self.call('POST',path+'/review',self.teacher,{'decision':'approved','feedback':'Reviewed source, explanation and changed requirement.'})
        self.assertEqual(self.call('GET',path,self.student)['status'],'approved')
        self.call('POST',f'/assignments/{self.assignment}/submissions',self.teacher,self.payload(),403)

    def test_failed_tests_are_counted_once_per_latest_learner_attempt(self):
        failed=self.submit(False); self.submit(False)
        self.call('POST','/submissions/'+failed['id']+'/review',self.teacher,{'decision':'approved','feedback':'Cannot approve tests that have failed.'},409)
        group=self.call('GET',f"/groups/{self.group['id']}",self.teacher)
        self.assertEqual(group['summary']['attempts'],2)
        self.assertEqual([f['learners'] for f in group['summary']['common_failures']],[1,1,1])
        self.submit(True)
        group=self.call('GET',f"/groups/{self.group['id']}",self.teacher)
        self.assertEqual(group['summary']['common_failures'],[])

    def test_portfolio_is_opt_in_reviewed_only_and_revocable(self):
        p=self.call('GET','/portfolio',self.student)
        url='/portfolios/'+p['slug']
        self.call('GET',url,status=404)
        self.submit(True)
        self.assertEqual(self.call('GET','/portfolio',self.student)['completed'],0)
        approved=self.submit(True)
        self.call('POST','/submissions/'+approved['id']+'/review',self.teacher,{'decision':'approved','feedback':'Student explained conversion and implemented the extra input.'})
        self.call('POST','/profile',self.student,{'locale':'uz','bio':'My reviewed projects','portfolio_public':True})
        p=self.call('GET',url)
        self.assertEqual(p['completed'],1); self.assertEqual(p['skills'],['JavaScript'])
        self.assertEqual(p['display_name'],'Student')
        for private in ('@example.com','join_code','code_hash','explanation','source','Pilot group'):
            self.assertNotIn(private,str(p))
        self.call('POST','/profile',self.student,{'portfolio_public':False})
        self.call('GET',url,status=404)

    def test_delete_account_removes_learning_data_and_public_link(self):
        submission=self.submit()
        p=self.call('POST','/profile',self.student,{'portfolio_public':True})
        self.assertEqual(self.client.delete('/auth/account',headers=self.student).status_code,200)
        self.call('GET','/portfolios/'+p['slug'],status=404)
        self.call('GET','/submissions/'+submission['id'],self.teacher,status=404)
        group=self.call('GET',f"/groups/{self.group['id']}",self.teacher)
        self.assertEqual(group['members'],[])
        self.assertEqual(self.client.delete('/auth/account',headers=self.teacher).status_code,200)
        with sqlite3.connect(self.db.db_path) as c:
            for table in ('learning_groups','learning_assignments','learning_members','learning_submissions'):
                self.assertEqual(c.execute('SELECT COUNT(*) FROM '+table).fetchone()[0],0)

    def test_locale_validation_and_bilingual_content(self):
        self.call('POST','/profile',self.student,{'locale':'invalid'},422)
        p=self.call('POST','/profile',self.student,{'locale':'uz'})
        self.assertEqual(p['locale'],'uz')
        detail=self.call('GET',f'/assignments/{self.assignment}',self.student)
        self.assertTrue(detail['prompt']['ru']); self.assertTrue(detail['prompt']['uz'])
        self.assertEqual(len(self.call('GET','/glossary',self.student)),5)
