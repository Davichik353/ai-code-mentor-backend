"""Integration tests for learning workflow, access boundaries and opt-in publication."""
import os
import secrets
import sqlite3
from storage import connect
import tempfile
import unittest
from unittest.mock import patch
os.environ.setdefault('JWT_SECRET', secrets.token_urlsafe(48))
os.environ['REQUIRE_EMAIL_VERIFICATION']='false'
from fastapi.testclient import TestClient
import main
from database import Database
from learning import Learning
from learning_content import TEMPLATES


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

    def test_paste_report_is_saved_and_visible_to_teacher_only(self):
        payload = {**self.payload(), 'code_paste_detected': True}
        attempt = self.call('POST', f'/assignments/{self.assignment}/submissions', self.student, payload, 201)
        self.assertTrue(attempt['code_paste_detected'])
        for user in (self.teacher, self.student):
            detail = self.call('GET', f"/submissions/{attempt['id']}", user)
            self.assertTrue(detail['code_paste_detected'])
        self.call('GET', f"/submissions/{attempt['id']}", self.outsider, status=404)
        clean = self.submit()
        self.assertFalse(self.call('GET', f"/submissions/{clean['id']}", self.teacher)['code_paste_detected'])

    def test_board_exposes_only_own_latest_attempt_data(self):
        self.call('POST','/groups/join',self.outsider,{'code':self.group['join_code']})
        mine=self.call('POST',f"/assignments/{self.assignment}/submissions",self.student,self.payload(),201)
        other=self.call('POST',f"/assignments/{self.assignment}/submissions",self.outsider,self.payload(),201)
        learner=self.call('GET',f"/groups/{self.group['id']}",self.student)
        self.assertEqual([s['id'] for s in learner['my_submissions']], [mine['id']])
        self.assertNotIn('members',learner)
        self.assertNotIn('submissions',learner)
        self.assertEqual(learner['member_count'],2)
        teacher=self.call('GET',f"/groups/{self.group['id']}",self.teacher)
        self.assertEqual({s['id'] for s in teacher['submissions']},{mine['id'],other['id']})

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

    def test_leave_group_revokes_access_preserves_work_and_allows_rejoin(self):
        attempt = self.submit()
        path = f"/groups/{self.group['id']}"
        self.call('POST', path+'/leave', status=401)
        self.call('POST', path+'/leave', self.outsider, {}, 404)
        self.call('POST', path+'/leave', self.teacher, {}, 409)
        self.call('POST', path+'/leave', self.student, {})
        self.assertEqual(self.call('GET', '/groups', self.student), [])
        self.call('GET', path, self.student, status=404)
        self.call('GET', f'/assignments/{self.assignment}', self.student, status=404)
        self.call('POST', f'/assignments/{self.assignment}/submissions', self.student, self.payload(), 404)
        detail = self.call('GET', path, self.teacher)
        self.assertEqual(detail['members'], [])
        self.assertEqual(detail['submissions'][0]['id'], attempt['id'])
        self.call('POST', '/groups/join', self.student, {'code': self.group['join_code']})
        detail = self.call('GET', f'/assignments/{self.assignment}', self.student)
        self.assertEqual(detail['submissions'][0]['id'], attempt['id'])

    def test_archive_permissions_preservation_and_restore(self):
        attempt = self.submit()
        path = f"/groups/{self.group['id']}"
        for action in ('archive', 'restore'):
            self.call('POST', path+'/'+action, status=401)
            self.call('POST', path+'/'+action, self.student, {}, 404)
            self.call('POST', path+'/'+action, self.outsider, {}, 404)
        self.call('POST', path+'/archive', self.teacher, {})
        self.call('POST', path+'/archive', self.teacher, {})
        self.assertTrue(self.call('GET', '/groups', self.student)[0]['archived'])
        self.call('POST', '/groups/join', self.outsider, {'code': self.group['join_code']}, 409)
        self.call('POST', path+'/assignments', self.teacher, {'template_id':'sum-py'}, 409)
        self.call('POST', f'/assignments/{self.assignment}/submissions', self.student, self.payload(), 409)
        detail = self.call('GET', f'/assignments/{self.assignment}', self.student)
        self.assertTrue(detail['archived'])
        self.assertFalse(detail['can_submit'])
        self.assertEqual(detail['submissions'][0]['id'], attempt['id'])
        self.call('GET', f"/submissions/{attempt['id']}", self.teacher)
        self.call('GET', path, self.outsider, status=404)
        self.call('POST', path+'/restore', self.teacher, {})
        self.assertFalse(self.call('GET', path, self.teacher)['archived'])
        self.call('POST', '/groups/join', self.outsider, {'code': self.group['join_code']})
        self.submit()

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
        self.assertEqual(len(templates),len(TEMPLATES))
        self.assertTrue(all(all(k in t for k in ("category", "category_title", "difficulty", "difficulty_title")) for t in templates))
        self.assertNotIn('solution',str(templates)); self.assertNotIn('hints',str(templates))

    def test_joined_member_cannot_manage_group_even_after_switching_profile_role(self):
        attempt=self.submit()
        self.call('POST','/profile',self.student,{'role':'teacher'})
        # A teacher workspace lets this account create a separate group, not administer its teacher's group.
        own=self.call('POST','/groups',self.student,{'title':'My separate group'},201)
        self.call('POST',f"/groups/{own['id']}/assignments",self.student,{'template_id':'maximum-py'},201)
        detail=self.call('GET',f"/groups/{self.group['id']}",self.student)
        self.assertFalse(detail['is_owner'])
        self.assertFalse(detail['can_manage'])
        for key in ('join_code','members','submissions','summary'):
            self.assertNotIn(key,detail)
        self.call('POST',f"/groups/{self.group['id']}/assignments",self.student,{'template_id':'maximum-py'},404)
        self.call('POST',f"/submissions/{attempt['id']}/review",self.student,
                  {'decision':'approved','feedback':'I cannot approve my own solution in another group.'},404)
        item=self.call('GET',f'/assignments/{self.assignment}',self.student)
        self.assertTrue(item['can_submit'])
        self.assertFalse(item['can_manage'])
        # Group permissions derive from ownership, even if its owner changes the global workspace mode.
        self.call('POST','/profile',self.teacher,{'role':'learner'})
        owner=self.call('GET',f"/groups/{self.group['id']}",self.teacher)
        self.assertTrue(owner['can_manage'])
        item=self.call('GET',f'/assignments/{self.assignment}',self.teacher)
        self.assertFalse(item['can_submit'])
        self.assertTrue(item['can_manage'])
        self.assertIn('starter_code',item)

    def test_duplicate_template_is_not_assigned_twice(self):
        self.call('POST',f"/groups/{self.group['id']}/assignments",self.teacher,{'template_id':'sum-js'},409)
        items=self.call('GET',f"/groups/{self.group['id']}",self.teacher)['assignments']
        self.assertEqual(len(items),1)
        self.assertEqual(items[0]['template_id'],'sum-js')
        # A different language is a different exercise; another group can use the same exercise.
        self.call('POST',f"/groups/{self.group['id']}/assignments",self.teacher,{'template_id':'sum-py'},201)
        other=self.call('POST','/groups',self.teacher,{'title':'Another group'},201)
        self.call('POST',f"/groups/{other['id']}/assignments",self.teacher,{'template_id':'sum-js'},201)

    def test_legacy_assignment_metadata_is_added_without_rewriting_snapshot(self):
        with Learning(self.db.db_path).connect() as c:
            import json
            original=c.execute('SELECT content FROM learning_assignments WHERE id=?',(self.assignment,)).fetchone()[0]
            content=json.loads(original)
            for name in ('category','category_title','difficulty','difficulty_title'):
                content.pop(name,None)
            snapshot=json.dumps(content)
            c.execute('UPDATE learning_assignments SET content=? WHERE id=?',(snapshot,self.assignment))
        item=self.call('GET',f'/assignments/{self.assignment}',self.student)
        self.assertIn('category',item)
        listing=self.call('GET',f"/groups/{self.group['id']}",self.student)['assignments']
        self.assertIn('difficulty',listing[0])
        with Learning(self.db.db_path).connect() as c:
            self.assertEqual(c.execute('SELECT content FROM learning_assignments WHERE id=?',(self.assignment,)).fetchone()[0],snapshot)

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
        with connect(self.db.db_path) as c:
            for table in ('learning_groups','learning_assignments','learning_members','learning_submissions'):
                self.assertEqual(c.execute('SELECT COUNT(*) FROM '+table).fetchone()[0],0)

    def test_locale_validation_and_bilingual_content(self):
        self.call('POST','/profile',self.student,{'locale':'invalid'},422)
        p=self.call('POST','/profile',self.student,{'locale':'uz'})
        self.assertEqual(p['locale'],'uz')
        detail=self.call('GET',f'/assignments/{self.assignment}',self.student)
        self.assertTrue(detail['prompt']['ru']); self.assertTrue(detail['prompt']['uz'])
        glossary=self.call('GET','/glossary',self.student)
        self.assertGreaterEqual(len(glossary),40)
        self.assertTrue(all(item.get('title',{}).get('ru') and item.get('title',{}).get('uz') and item.get('examples') for item in glossary))
