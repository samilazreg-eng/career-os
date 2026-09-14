"""Real-Git Career OS core conformance tests (stdlib only).

Run: python test_core_conformance.py --source C:/path/to/career-os/src
Expected baseline invariants are asserted normally: known bugs remain FAIL,
never skipped or marked expectedFailure. Every test copies unmodified source
so each run exercises an isolated installation on disk.

Career has no single global repository: like 'git init', 'career init'
always targets the current working directory, and HEAD.json lives inside
each repository at '<repo>/.career/HEAD.json' (never shared between
repositories). CAREER_REPO_DIR pins the target repository explicitly,
bypassing directory discovery; it is primarily a testing/scripting knob.
The empty HEAD and allow-empty Git root commit in seed() are explicit fixture
preconditions, NOT capabilities attributed to career init.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'src'
EMPTY = dict(context='', mission='', thread='')

class CoreConformance(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='career-validation-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.app = self.base / 'app'
        shutil.copytree(SOURCE, self.app/'bin', ignore=shutil.ignore_patterns('__pycache__'))
        for original in SOURCE.rglob('*.py'):
            copied = self.app/'bin'/original.relative_to(SOURCE)
            self.assertEqual(hashlib.sha256(original.read_bytes()).digest(), hashlib.sha256(copied.read_bytes()).digest())
        self.repo = self.base/'archive with spaces'
        self.cwd = self.base/'external with spaces'
        self.cwd.mkdir()
        self.env = {k:v for k,v in os.environ.items() if not k.startswith(('GIT_', 'CAREER_'))}
        self.env.update(CAREER_REPO_DIR=str(self.repo), PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1', GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1', GIT_AUTHOR_NAME='Validation', GIT_AUTHOR_EMAIL='validation@example.invalid', GIT_COMMITTER_NAME='Validation', GIT_COMMITTER_EMAIL='validation@example.invalid', GIT_TERMINAL_PROMPT='0')

    @property
    def head(self):
        # Computed from self.repo (rather than cached at setUp) since HEAD.json
        # now lives inside each repository and tests may repoint self.repo.
        return self.repo/'.career'/'HEAD.json'

    def run_process(self, argv):
        return subprocess.run(argv, cwd=self.cwd, env=self.env, text=True, encoding='utf-8', capture_output=True, timeout=20)

    def cli(self, *args):
        return self.run_process([sys.executable, str(self.app/'bin'/'main.py'), *args])

    def git(self, *args):
        return self.run_process(['git', '-C', str(self.repo), *args])

    def ok(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def state(self, value=None):
        if value is not None:
            self.head.parent.mkdir(parents=True, exist_ok=True)
            self.head.write_text(json.dumps(value), encoding='utf-8')
        return json.loads(self.head.read_text())

    def seed(self):
        self.state(EMPTY)
        self.ok(self.cli('init'))
        self.ok(self.git('config','core.autocrlf','false'))
        self.ok(self.git('commit','--allow-empty','-m','Validation fixture root'))

    def hierarchy(self, depth=3):
        self.seed()
        for kind, name in list(zip(('context','mission','thread'),('snt','daedalux','debugging')))[:depth]:
            self.ok(self.cli(kind,'start',name))

    def refs(self):
        return self.ok(self.git('for-each-ref','--format=%(refname:short)','refs/heads')).stdout.splitlines()

    def assert_position(self, context='', mission='', thread=''):
        self.assertEqual(self.state(),dict(context=context,mission=mission,thread=thread))
        parts = [v for v in (context,mission,thread) if v]
        kind = 'thread' if thread else 'mission' if mission else 'context' if context else 'career'
        expected='/'.join([*parts,'@'+kind])
        self.assertEqual(self.ok(self.git('branch','--show-current')).stdout.strip(),expected)

    def capture(self, name='main text.txt', content='alpha\nbeta\n'):
        p=self.cwd/name
        p.write_text(content,encoding='utf-8')
        self.ok(self.cli('add',name))
        self.assertEqual(p.read_text(),content)
        return p

    def test_init_creates_git_root_from_unrelated_cwd(self):
        r=self.ok(self.cli('init'))
        self.assertIn('Initialized empty Git repository',r.stdout)
        self.assertEqual(r.stderr,'')
        self.assertTrue((self.repo/'.git').is_dir())
        self.assertEqual(self.git('branch','--show-current').stdout.strip(),'@career')

    def test_fresh_init_supports_status_without_manual_state(self):
        self.ok(self.cli('init'))
        self.ok(self.cli('status'))

    def test_fresh_init_retains_root_after_first_context(self):
        self.state(EMPTY)
        self.ok(self.cli('init'))
        self.ok(self.cli('context','start','snt'))
        self.assertIn('@career',self.refs())

    def test_repeated_init_preserves_existing_commit_and_branch(self):
        self.hierarchy(1)
        before=self.git('rev-parse','HEAD').stdout
        self.ok(self.cli('init'))
        self.assertEqual(before,self.git('rev-parse','HEAD').stdout)
        self.assert_position('snt')

    def test_default_repository_is_current_working_directory(self):
        self.env.pop('CAREER_REPO_DIR')
        self.ok(self.cli('init'))
        self.assertTrue((self.cwd/'.git').is_dir())
        self.assertTrue((self.cwd/'.career'/'HEAD.json').is_file())
        self.assertFalse((self.app/'repo').exists())

    def test_second_repository_in_sibling_directory_is_independent(self):
        self.env.pop('CAREER_REPO_DIR')
        first=self.cwd
        self.ok(self.cli('init'))
        self.ok(self.cli('context','start','snt'))
        self.assertEqual(json.loads((first/'.career'/'HEAD.json').read_text())['context'],'snt')

        second=self.base/'other project'; second.mkdir()
        self.cwd=second
        self.ok(self.cli('init'))
        self.assertTrue((second/'.git').is_dir())
        self.assertEqual(json.loads((second/'.career'/'HEAD.json').read_text()),EMPTY)

        self.ok(self.cli('status'))
        self.assertEqual(json.loads((first/'.career'/'HEAD.json').read_text())['context'],'snt')

    def test_absolute_repo_override_is_cwd_independent(self):
        self.seed()
        before=self.ok(self.cli('status'))
        self.cwd=self.base
        after=self.ok(self.cli('status'))
        self.assertEqual((before.stdout,before.stderr),(after.stdout,after.stderr))

    def test_relative_repo_override_is_resolved_against_cwd(self):
        # A relative CAREER_REPO_DIR is resolved against the current working
        # directory, like any relative path passed to git itself -- it is
        # deliberately NOT cwd-independent, unlike an absolute override.
        self.env['CAREER_REPO_DIR']='relative-archive'
        self.ok(self.cli('init'))
        self.assertTrue((self.cwd/'relative-archive'/'.git').is_dir())
        self.ok(self.cli('status'))

        self.cwd=self.base
        r=self.cli('status')
        self.assertNotEqual(r.returncode,0)
        self.assertFalse((self.base/'relative-archive').exists())

    def test_add_root_relative_source_spaces_and_index(self):
        self.seed()
        p=self.capture()
        self.assertEqual((self.repo/p.name).read_bytes(),p.read_bytes())
        self.assertEqual(self.git('diff','--cached','--name-only').stdout.strip(),p.name)

    def test_status_matches_git_clean_staged_modified_deleted(self):
        self.seed()
        for stage in range(4):
            if stage==1: self.capture()
            if stage==2:
                self.ok(self.cli('commit','-m','Track'))
                (self.repo/'main text.txt').write_text('modified\n')
            if stage==3: (self.repo/'main text.txt').unlink()
            actual=self.cli('status'); expected=self.git('status')
            self.assertEqual((actual.returncode,actual.stdout,actual.stderr),(expected.returncode,expected.stdout,expected.stderr))

    def test_diff_patch_history_and_no_state_change(self):
        self.seed(); self.capture(); self.ok(self.cli('commit','-m','Track'))
        before=self.state(); commit=self.git('rev-parse','HEAD').stdout
        self.assertEqual(self.ok(self.cli('diff')).stdout,'')
        (self.repo/'main text.txt').write_text('alpha\ngamma\n')
        r=self.ok(self.cli('diff'))
        self.assertIn('-beta',r.stdout); self.assertIn('+gamma',r.stdout)
        self.assertEqual(r.stdout,self.git('diff-index','--patch','HEAD').stdout)
        self.ok(self.git('add','--','main text.txt')); self.ok(self.cli('commit','-m','Update'))
        self.assertEqual(self.ok(self.cli('diff')).stdout,'')
        self.assertEqual(self.state(),before)
        self.assertNotEqual(self.git('rev-parse','HEAD').stdout,commit)

    def test_diff_binary_and_deleted(self):
        self.seed()
        (self.cwd/'binary.bin').write_bytes(b'\x00\x01text')
        self.ok(self.cli('add','binary.bin'))
        self.assertIn('Binary files',self.ok(self.cli('diff')).stdout)
        self.ok(self.cli('commit','-m','Binary'))
        (self.repo/'binary.bin').unlink()
        self.assertIn('deleted file mode',self.ok(self.cli('diff')).stdout)

    def test_commit_message_history_previous_commit_and_clean_attempt(self):
        self.seed(); old=self.git('rev-parse','HEAD').stdout.strip(); self.capture()
        self.ok(self.cli('commit','-m','Exact message é'))
        self.assertEqual(self.git('log','-1','--format=%B').stdout.strip(),'Exact message é')
        self.assertEqual(self.git('rev-parse','HEAD~1').stdout.strip(),old)
        self.assertIn('+alpha',self.git('diff','HEAD~1','HEAD').stdout)
        self.ok(self.git('cat-file','-e',old))
        r=self.cli('commit','-m','Clean')
        self.assertEqual(r.returncode,1); self.assertIn('nothing to commit',r.stdout); self.assertEqual(r.stderr,'')

    def test_context_switch_clears_descendants(self):
        self.hierarchy(); self.ok(self.cli('context','start','visteon'))
        self.ok(self.cli('context','switch','snt')); self.assert_position('snt')

    def test_mission_switch_clears_thread(self):
        self.hierarchy(); self.ok(self.cli('mission','start','other'))
        self.ok(self.cli('mission','switch','daedalux')); self.assert_position('snt','daedalux')

    def test_thread_switch(self):
        self.hierarchy(); self.ok(self.cli('thread','start','architecture'))
        self.ok(self.cli('thread','switch','debugging')); self.assert_position('snt','daedalux','debugging')

    def test_marker_topology_and_physical_projection(self):
        self.hierarchy()
        for path in ['snt','snt/daedalux','snt/daedalux/debugging']:
            self.assertTrue((self.repo/path/'.career').is_file())
        self.ok(self.cli('thread','start','architecture'))
        self.ok(self.cli('context','start','visteon'))
        self.assertEqual(set(self.refs()),{'@career','snt/@context','snt/daedalux/@mission','snt/daedalux/debugging/@thread','snt/daedalux/architecture/@thread','visteon/@context'})

    def test_sibling_thread_branches_from_structural_parent(self):
        self.hierarchy()
        parent=self.git('rev-parse','snt/daedalux/@mission').stdout
        self.ok(self.cli('thread','start','architecture'))
        self.assertEqual(self.git('rev-parse','HEAD~1').stdout,parent)

    def test_parent_required_for_mission(self):
        self.seed(); r=self.cli('mission','start','orphan')
        self.assertNotEqual(r.returncode,0); self.assert_position()

    def test_parent_required_for_thread(self):
        self.seed(); r=self.cli('thread','start','orphan')
        self.assertNotEqual(r.returncode,0); self.assert_position()

    def test_missing_source_and_directory_fail_without_traceback(self):
        self.seed()
        for source in ['missing','.', 'bad<>path']:
            with self.subTest(source=source):
                r=self.cli('add',source)
                self.assertNotEqual(r.returncode,0)
                self.assertNotIn('Traceback',r.stderr)

    def test_add_before_init_is_side_effect_free(self):
        # HEAD.json now lives inside the repository, so it cannot exist
        # before the repository does -- nothing to seed here.
        (self.cwd/'resource.txt').write_text('data')
        r=self.cli('add','resource.txt')
        self.assertNotEqual(r.returncode,0)
        self.assertFalse(self.repo.exists())

    def test_malformed_head_fails_cleanly(self):
        self.seed(); self.head.write_text('{')
        r=self.cli('status'); self.assertNotEqual(r.returncode,0)
        self.assertNotIn('Traceback',r.stderr)

    def test_inconsistent_head_is_rejected_before_capture(self):
        self.seed(); self.state(dict(context='ghost',mission='',thread=''))
        (self.cwd/'payload').write_text('data')
        self.assertNotEqual(self.cli('add','payload').returncode,0)
        self.assertFalse((self.repo/'ghost').exists())

    def test_windows_backslash_cannot_escape_repository(self):
        self.seed(); outside=self.base/'outside'
        self.state(dict(context='..\\outside',mission='',thread=''))
        (self.cwd/'payload').write_text('data'); self.cli('add','payload')
        self.assertFalse((outside/'payload').exists())

    def test_absolute_physical_path_cannot_escape_repository(self):
        self.seed(); outside=self.base/'outside'
        self.state(dict(context=str(outside),mission='',thread=''))
        (self.cwd/'payload').write_text('data'); self.cli('add','payload')
        self.assertFalse((outside/'payload').exists())

    def test_invalid_identifier_does_not_change_state_or_projection(self):
        self.seed(); r=self.cli('context','start','with space')
        self.assertNotEqual(r.returncode,0)
        self.assert_position(); self.assertFalse((self.repo/'with space').exists())

    def test_git_failure_does_not_advance_state(self):
        self.hierarchy(1); before=self.state()
        (self.repo/'.git'/'index.lock').write_text('fixture lock')
        r=self.cli('context','start','locked')
        self.assertNotEqual(r.returncode,0); self.assertEqual(self.state(),before)

    def test_current_branch_removal_preserves_git_failure(self):
        self.hierarchy()
        r=self.git('branch','-d','snt/daedalux/debugging/@thread')
        self.assertNotEqual(r.returncode,0); self.assertIn('cannot delete branch',r.stderr)
        self.assert_position('snt','daedalux','debugging')

    def test_init_file_collision_fails_without_traceback(self):
        self.repo.write_text('existing file')
        r=self.cli('init'); self.assertNotEqual(r.returncode,0)
        self.assertEqual(self.repo.read_text(),'existing file'); self.assertNotIn('Traceback',r.stderr)

    def test_duplicate_start_with_staged_work_is_rejected(self):
        self.hierarchy(1); self.ok(self.cli('context','start','visteon'))
        self.capture(); before=self.state(); old=self.git('rev-parse','HEAD').stdout
        r=self.cli('context','start','snt')
        self.assertNotEqual(r.returncode,0)
        self.assertEqual(self.state(),before); self.assertEqual(self.git('rev-parse','HEAD').stdout,old)

    def test_repo_override_does_not_share_active_head(self):
        self.hierarchy(1)
        self.repo=self.base/'second archive'; self.env['CAREER_REPO_DIR']=str(self.repo)
        self.ok(self.cli('init'))
        self.assert_position()

    def test_slash_traversal_cannot_escape_repository(self):
        self.seed(); outside=self.base/'outside'
        r=self.cli('context','start','../outside')
        self.assertNotEqual(r.returncode,0)
        self.assertFalse(outside.exists()); self.assert_position()

    def test_start_backslash_traversal_cannot_escape_repository(self):
        self.seed(); outside=self.base/'outside'
        self.cli('context','start','..\\outside')
        self.assertFalse(outside.exists())

    def test_head_schema_is_checked_before_status(self):
        self.seed(); self.state(dict(context='',mission='orphan',thread=''))
        self.assertNotEqual(self.cli('status').returncode,0)

    def test_logical_paths_have_expected_composition(self):
        self.seed()
        for state, expected in [(EMPTY,''), (dict(context='snt',mission='',thread=''),'snt'), (dict(context='snt',mission='daedalux',thread=''),'snt/daedalux'), (dict(context='snt',mission='daedalux',thread='debugging'),'snt/daedalux/debugging')]:
            self.state(state)
            code='import sys; sys.path.insert(0,sys.argv[1]); from head import Head; print(Head().path)'
            r=self.ok(self.run_process([sys.executable,'-c',code,str(self.app/'bin')]))
            self.assertEqual(r.stdout.strip(),expected)

    def test_inactive_mission_finish_preserves_active_context(self):
        self.hierarchy(1); old=self.git('rev-parse','HEAD').stdout
        r=self.cli('mission','finish')
        self.assertNotEqual(r.returncode,0)
        self.assertTrue((self.repo/'snt'/'.career').exists())
        self.assertEqual(self.git('rev-parse','HEAD').stdout,old)

    def test_inactive_thread_finish_preserves_active_mission(self):
        self.hierarchy(2); old=self.git('rev-parse','HEAD').stdout
        r=self.cli('thread','finish')
        self.assertNotEqual(r.returncode,0)
        self.assertTrue((self.repo/'snt'/'daedalux'/'.career').exists())
        self.assertEqual(self.git('rev-parse','HEAD').stdout,old)

    def test_failed_finish_checkout_preserves_uncommitted_data(self):
        self.hierarchy(); before=self.state(); old=self.git('rev-parse','HEAD').stdout
        marker=self.repo/'snt'/'daedalux'/'debugging'/'.career'
        marker.write_text('uncommitted marker change')
        r=self.cli('thread','finish')
        self.assertNotEqual(r.returncode,0)
        self.assertEqual(marker.read_text(),'uncommitted marker change')
        self.assertEqual(self.state(),before); self.assertEqual(self.git('rev-parse','HEAD').stdout,old)

def install_lifecycle_tests():
    for depth,kind in enumerate(('context','mission','thread'),1):
        names=('snt','daedalux','debugging')[:depth]
        def start(self, depth=depth,names=names):
            self.hierarchy(depth); self.assert_position(*names)
            self.assertTrue((self.repo/'/'.join(names)/'.career').exists())
            self.capture(); self.assertTrue((self.repo/'/'.join(names)/'main text.txt').exists())
            self.assertIn('/'.join(names)+'/main text.txt',self.git('diff','--cached','--name-only').stdout)
        def unknown(self,depth=depth,kind=kind):
            self.hierarchy(depth); before=self.state()
            r=self.cli(kind,'switch','unknown'); self.assertNotEqual(r.returncode,0)
            self.assertEqual(self.state(),before)
        def finish(self,depth=depth,kind=kind,names=names):
            self.hierarchy(depth); old=self.git('rev-parse','HEAD').stdout.strip()
            self.ok(self.cli(kind,'finish'))
            self.assert_position(*names[:-1]); self.assertNotIn('/'.join(names)+'/@'+kind,self.refs())
            self.assertFalse((self.repo/'/'.join(names)).exists()); self.ok(self.git('cat-file','-e',old))
        def duplicate(self,depth=depth,kind=kind,names=names):
            self.hierarchy(depth); before=self.state(); old=self.git('rev-parse','HEAD').stdout
            r=self.cli(kind,'start',names[-1]); self.assertNotEqual(r.returncode,0)
            self.assertEqual(self.state(),before); self.assertEqual(self.git('rev-parse','HEAD').stdout,old)
        def empty_finish(self,kind=kind):
            self.seed()
            sentinel=self.repo/'untracked-sentinel.txt'; sentinel.write_text('must survive')
            before={str(p.relative_to(self.repo)):p.read_bytes() for p in self.repo.rglob('*') if p.is_file()}
            r=self.cli(kind,'finish'); self.assertNotEqual(r.returncode,0)
            after={str(p.relative_to(self.repo)):p.read_bytes() for p in self.repo.rglob('*') if p.is_file()}
            self.assertEqual(set(after),set(before),'An inactive finish removed repository files')
            self.assertEqual(after,before)
        for label,method in [('start_capture',start),('unknown_switch_preserves_head',unknown),('finish',finish),('duplicate_same_position',duplicate),('inactive_finish_preserves_repository',empty_finish)]:
            setattr(CoreConformance,'test_'+kind+'_'+label,method)

install_lifecycle_tests()
if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,default=SOURCE)
    args,remaining=parser.parse_known_args()
    SOURCE=args.source.resolve()
    if not (SOURCE/'main.py').is_file(): parser.error('--source must identify the Career OS bin directory')
    unittest.main(argv=[sys.argv[0],*remaining],verbosity=2)
