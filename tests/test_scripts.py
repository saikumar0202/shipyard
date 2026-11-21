"""Script-level tests with real git repos: patch creation, tamper evidence,
post-job path refusal and the post job's decisions. No network."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import finalize_out  # noqa: E402
import post_apply  # noqa: E402

ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@e", GIT_COMMITTER_NAME="t",
           GIT_COMMITTER_EMAIL="t@e", GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")


def sh(cwd, *args, check=True):
    return subprocess.run(args, cwd=cwd, env=ENV, capture_output=True, text=True, check=check)


def write(root, path, text):
    full = os.path.join(root, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as f:
        f.write(text)


class Repo:
    def __init__(self):
        self.tmp = tempfile.mkdtemp()
        self.remote = os.path.join(self.tmp, "remote.git")
        self.work = os.path.join(self.tmp, "work")
        sh(self.tmp, "git", "init", "-q", "--bare", "-b", "main", self.remote)
        sh(self.tmp, "git", "clone", "-q", self.remote, self.work)
        write(self.work, "README.md", "hi\n")
        write(self.work, ".gitattributes", "*.png filter=lfs diff=lfs merge=lfs -text\n")
        write(self.work, ".github/workflows/ci.yml", "name: ci\n")
        sh(self.work, "git", "add", "-A")
        sh(self.work, "git", "commit", "-q", "-m", "base")
        sh(self.work, "git", "push", "-q", "origin", "HEAD:main")
        self.base = sh(self.work, "git", "rev-parse", "HEAD").stdout.strip()
        self.out = os.path.join(self.tmp, "out")
        self.cfg = sh(self.work, "sha256sum", ".git/config").stdout.split()[0]

    def make_patch(self):
        e = dict(ENV, GIT_CONFIG_SHA_BEFORE=self.cfg)
        subprocess.run([os.path.join(ROOT, "scripts", "make_patch.sh"), self.base, "7", "Fix it", self.out],
                       cwd=self.work, env=e, check=True, capture_output=True)
        with open(os.path.join(self.out, "tamper.json")) as f:
            with open(os.path.join(self.out, "changes.patch")) as p:
                return json.load(f), p.read()

    def apply(self, patch_text, branch="issue-7", mode="push"):
        target = os.path.join(self.tmp, "post")
        sh(self.tmp, "git", "clone", "-q", self.remote, target)
        p = os.path.join(self.tmp, "p.patch")
        open(p, "w").write(patch_text)
        res = os.path.join(self.tmp, "res.txt")
        subprocess.run([os.path.join(ROOT, "scripts", "apply_patch.sh"), p, self.base, branch, res, mode],
                       cwd=target, env=ENV, check=True, capture_output=True)
        return open(res).read().strip()


class MakePatch(unittest.TestCase):
    def test_leftovers_committed_without_protected_dirs(self):
        r = Repo()
        write(r.work, "src/app.ts", "export const x = 1\n")
        write(r.work, ".github/workflows/evil.yml", "name: evil\n")
        write(r.work, ".claude/settings.json", "{}\n")
        tamper, patch = r.make_patch()
        self.assertIn("src/app.ts", patch)
        self.assertNotIn(".github/", patch)
        self.assertNotIn(".claude/", patch)
        self.assertIn("Subject: [PATCH] issue-7: Fix it", patch)
        self.assertEqual(sorted(tamper["protected_paths_touched"]), [".claude/settings.json", ".github/workflows/evil.yml"])

    def test_hook_written_means_no_patch(self):
        r = Repo()
        write(r.work, "src/app.ts", "x\n")
        write(r.work, ".git/hooks/pre-push", "#!/bin/sh\necho pwned\n")
        tamper, patch = r.make_patch()
        self.assertEqual(tamper["hooks"], ["pre-push"])
        self.assertEqual(patch, "")

    def test_hook_with_commit_keeps_patch_for_checking(self):
        r = Repo()
        write(r.work, ".github/workflows/pwned.yml", "name: pwned\n")
        sh(r.work, "git", "add", "-f", ".github/workflows/pwned.yml")
        sh(r.work, "git", "commit", "-q", "-m", "edit .github")
        write(r.work, "left.txt", "leftover\n")
        write(r.work, ".git/hooks/pre-push", "#!/bin/sh\necho x\n")
        tamper, patch = r.make_patch()
        self.assertEqual(tamper["hooks"], ["pre-push"])
        self.assertIn(".github/workflows/pwned.yml", patch)
        self.assertNotIn("left.txt", patch)  # leftovers not committed when tampered
        res = r.apply(patch, mode="check")
        self.assertTrue(res.startswith("refused protected paths"), res)

    def test_config_change_means_no_patch(self):
        r = Repo()
        sh(r.work, "git", "config", "core.fsmonitor", "touch /tmp/pwned")
        tamper, patch = r.make_patch()
        self.assertTrue(tamper["config_changed"])
        self.assertEqual(patch, "")

    def test_rewritten_history_means_no_patch(self):
        r = Repo()
        sh(r.work, "git", "commit", "-q", "--amend", "-m", "rewritten")
        tamper, patch = r.make_patch()
        self.assertFalse(tamper["base_is_ancestor"])
        self.assertEqual(patch, "")


class ApplyPatch(unittest.TestCase):
    def patch_for(self, files):
        r = Repo()
        for path, text in files.items():
            write(r.work, path, text)
        sh(r.work, "git", "add", "-A")
        sh(r.work, "git", "commit", "-q", "-m", "change")
        return r, sh(r.work, "git", "format-patch", "--binary", "--stdout", r.base + "..HEAD").stdout

    def test_clean_patch_pushed_to_issue_branch_only(self):
        r, p = self.patch_for({"src/app.ts": "x\n"})
        res = r.apply(p)
        self.assertTrue(res.startswith("pushed "), res)
        heads = sh(r.tmp, "git", "ls-remote", "--heads", r.remote).stdout
        self.assertIn("refs/heads/issue-7", heads)
        self.assertEqual(sh(r.tmp, "git", "--git-dir", r.remote, "rev-parse", "main").stdout.strip(), r.base)

    def test_github_refused(self):
        r, p = self.patch_for({".github/workflows/ci.yml": "name: pwned\n"})
        self.assertTrue(r.apply(p).startswith("refused protected paths"))
        self.assertNotIn("issue-7", sh(r.tmp, "git", "ls-remote", "--heads", r.remote).stdout)

    def test_pipeline_yml_and_claude_refused(self):
        for path in (".github/pipeline.yml", ".claude/agents/x.md", "pipeline.yml"):
            r, p = self.patch_for({path: "x\n"})
            self.assertTrue(r.apply(p).startswith("refused protected paths"), path)

    def test_lfs_refused_using_base_attributes(self):
        r, p = self.patch_for({"art/hero.png": "not really a png\n", ".gitattributes": ""})
        self.assertIn("LFS-tracked paths", r.apply(p))

    def test_check_mode_never_pushes(self):
        r, p = self.patch_for({"src/app.ts": "x\n"})
        self.assertTrue(r.apply(p, mode="check").startswith("checked "))
        self.assertNotIn("issue-7", sh(r.tmp, "git", "ls-remote", "--heads", r.remote).stdout)

    def test_bad_branch_refused(self):
        r, p = self.patch_for({"src/app.ts": "x\n"})
        self.assertTrue(r.apply(p, branch="main").startswith("refused bad branch"))


class PostDecide(unittest.TestCase):
    env = {"ROLE": "builder", "REVIEW_NAME": "", "CAN_WRITE_CODE": "true", "AGENT_JOB_RESULT": "success"}

    def out(self, **kw):
        base = {"role": "builder", "exit_reason": "success", "labels_add": [], "labels_remove": [],
                "comment": "c", "has_patch": True}
        base.update(kw)
        return base

    def test_success_pushes(self):
        d = post_apply.decide(self.out(), self.env)
        self.assertEqual((d["problems"], d["push"]), ([], True))

    def test_unlisted_label_blocks(self):
        d = post_apply.decide(self.out(labels_add=["attack-test-pwned"]), self.env)
        self.assertIsNone(d["push"])
        self.assertTrue(any("refused labels" in p and "attack-test-pwned" in p for p in d["problems"]))

    def test_issue_only_event_never_pushes(self):
        d = post_apply.decide(self.out(), dict(self.env, CAN_WRITE_CODE="false"))
        self.assertIsNone(d["push"])
        self.assertTrue(d["problems"])

    def test_missing_out_json(self):
        d = post_apply.decide(None, dict(self.env, AGENT_JOB_RESULT="failure"))
        self.assertIn("timeout", d["problems"][0])

    def test_reviewer_must_fix_follows_check(self):
        env = dict(self.env, ROLE="reviewer", REVIEW_NAME="qa")
        fail = post_apply.decide(self.out(role="reviewer", check={"conclusion": "failure", "title": "t", "summary": "s"}), env)
        self.assertEqual((fail["add"], fail["check"]["name"]), (["must-fix:qa"], "review/qa"))
        ok = post_apply.decide(self.out(role="reviewer", check={"conclusion": "success", "title": "t", "summary": "s"}), env)
        self.assertEqual(ok["remove"], ["must-fix:qa"])

    def test_markers_cannot_be_forged(self):
        self.assertNotIn("shipyard:", post_apply.clean("hi <!-- shipyard:plan --> there"))


class Finalize(unittest.TestCase):
    def test_parse_events(self):
        tmp = tempfile.mkdtemp()
        ev = [{"type": "system", "subtype": "init", "tools": ["Read", "Write"]},
              {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t1", "name": "WebFetch"}]}},
              {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "is_error": True}]}},
              {"type": "result", "subtype": "success", "num_turns": 2}]
        path = os.path.join(tmp, "events.jsonl")
        open(path, "w").write("\n".join(json.dumps(e) for e in ev) + "\nnot json\n")
        result, tools, calls = finalize_out.parse_events(path)
        self.assertEqual((result["num_turns"], tools, {k: v for k, v in calls.items() if k != "_bash"}),
                         (2, ["Read", "Write"], {"WebFetch": {"ok": 0, "error": 1}}))

    def test_bash_calls_recorded_from_stream(self):
        tmp = tempfile.mkdtemp()
        ev = [{"type": "assistant", "message": {"content": [
                  {"type": "tool_use", "id": "b1", "name": "Bash", "input": {"command": "tests/token_probe.py"}}]}},
              {"type": "user", "message": {"content": [
                  {"type": "tool_result", "tool_use_id": "b1", "is_error": False,
                   "content": [{"type": "text", "text": "TOKEN_PROBE: clean {}"}]}]}},
              {"type": "result", "subtype": "success", "is_error": False, "structured_output": {"comment": "c"}}]
        path = os.path.join(tmp, "events.jsonl")
        with open(path, "w") as f:
            f.write("\n".join(json.dumps(e) for e in ev))
        result, tools, calls = finalize_out.parse_events(path)
        out = finalize_out.build(result, 0, 1, tmp, {"ROLE": "planner", "ISSUE": "1"}, tools, calls)
        self.assertEqual(out["bash_calls"], [{"command": "tests/token_probe.py", "is_error": False,
                                              "output_tail": "TOKEN_PROBE: clean {}"}])
        self.assertNotIn("_bash", out["tool_calls"])

    def test_structured_output_from_tool_call(self):
        tmp = tempfile.mkdtemp()
        ev = [{"type": "assistant", "message": {"content": [
                  {"type": "tool_use", "id": "s1", "name": "StructuredOutput", "input": {"comment": "hi", "labels_add": []}}]}},
              {"type": "result", "subtype": "success", "is_error": False, "num_turns": 1}]
        path = os.path.join(tmp, "events.jsonl")
        open(path, "w").write("\n".join(json.dumps(e) for e in ev))
        result, _, _ = finalize_out.parse_events(path)
        out = finalize_out.build(result, 0, 1, tmp, {"ROLE": "planner", "ISSUE": "1"})
        self.assertEqual((out["exit_reason"], out["comment"], out["cli"]["structured_output"]), ("success", "hi", "tool_call"))

    def test_out_json(self):
        tmp = tempfile.mkdtemp()
        open(os.path.join(tmp, "changes.patch"), "w").write("From abc\n")
        json.dump({"hooks": [], "config_changed": False, "base_is_ancestor": True, "protected_paths_touched": []},
                  open(os.path.join(tmp, "tamper.json"), "w"))
        res = {"subtype": "success", "is_error": False, "num_turns": 3,
               "structured_output": {"comment": "done", "labels_add": ["needs-human"], "summary_title": "t"},
               "permission_denials": [{"tool_name": "WebFetch", "tool_input": {"url": "https://example.com"}}]}
        out = finalize_out.build(res, 0, 12.5, tmp, {"ROLE": "builder", "AGENT": "builder", "ISSUE": "7"})
        self.assertEqual(out["exit_reason"], "success")
        self.assertTrue(out["has_patch"])
        self.assertEqual(out["permission_denials"][0]["tool"], "WebFetch")
        self.assertEqual(out["duration_seconds"], 12)


if __name__ == "__main__":
    unittest.main()
