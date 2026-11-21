"""Routing, repro-guard and ready-check logic (Build order step 4)."""
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import ready_check  # noqa: E402
import review_plan  # noqa: E402
import repro_guard  # noqa: E402
import route  # noqa: E402


def ev(action, label, labels, state="open", pr=False):
    issue = {"number": 5, "state": state, "labels": [{"name": l} for l in labels]}
    if pr:
        issue["pull_request"] = {}
    return {"action": action, "label": {"name": label}, "issue": issue}


class Route(unittest.TestCase):
    def agent(self, *a, **k):
        return route.route("issues", ev(*a, **k))["agent"]

    def test_feature_approved(self):
        self.assertEqual(self.agent("labeled", "approved", ["feature", "approved"]), "builder")
        self.assertEqual(self.agent("labeled", "approved", ["idea", "approved"]), "none")

    def test_bug_repro(self):
        self.assertEqual(self.agent("labeled", "repro-ok", ["bug", "repro-ok"]), "builder")
        self.assertEqual(self.agent("labeled", "manual-repro", ["bug", "manual-repro"]), "builder")
        self.assertEqual(self.agent("labeled", "repro-ok", ["bug", "repro-ok", "hold"]), "none")

    def test_hold_release(self):
        self.assertEqual(self.agent("unlabeled", "hold", ["bug", "repro-ok"]), "builder")
        self.assertEqual(self.agent("unlabeled", "hold", ["bug"]), "none")
        self.assertEqual(self.agent("labeled", "approved", ["bug", "repro-ok", "hold", "approved"]), "builder")
        self.assertEqual(self.agent("labeled", "approved", ["bug", "approved"]), "none")

    def test_stops(self):
        self.assertEqual(self.agent("labeled", "approved", ["feature", "approved", "parked"]), "none")
        self.assertEqual(self.agent("labeled", "approved", ["feature", "approved"], state="closed"), "none")
        self.assertEqual(self.agent("labeled", "approved", ["feature", "approved"], pr=True), "none")
        self.assertEqual(route.route("issue_comment", ev("created", "", ["feature"]))["agent"], "none")


ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@e", GIT_COMMITTER_NAME="t",
           GIT_COMMITTER_EMAIL="t@e", GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")


class ReproGuard(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.old = os.getcwd()
        os.chdir(self.d)
        os.environ.update({k: v for k, v in ENV.items() if k.startswith("GIT_")})
        self.sh("git", "init", "-q")
        self.write("src/app.ts", "x\n")
        self.commit("base")
        self.write("src/app.test.ts", "test\n")
        self.repro = self.commit("repro test")

    def tearDown(self):
        os.chdir(self.old)
        for k in ENV:
            if k.startswith("GIT_"):
                os.environ.pop(k, None)

    def sh(self, *a):
        return subprocess.run(a, check=True, capture_output=True, text=True, env=ENV).stdout.strip()

    def write(self, p, t):
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(t)

    def commit(self, msg):
        self.sh("git", "add", "-A")
        self.sh("git", "commit", "-q", "-m", msg)
        return self.sh("git", "rev-parse", "HEAD")

    def test_fix_without_touching_test_passes(self):
        self.write("src/app.ts", "fixed\n")
        self.commit("fix")
        self.assertEqual(repro_guard.guard(self.repro), [])

    def test_modified_test_fails(self):
        self.write("src/app.test.ts", "weakened\n")
        self.commit("fix")
        self.assertEqual(len(repro_guard.guard(self.repro)), 1)

    def test_deleted_test_fails(self):
        os.remove("src/app.test.ts")
        self.commit("fix")
        self.assertIn("src/app.test.ts", repro_guard.guard(self.repro)[0])

    def test_linked_issue(self):
        self.assertEqual(repro_guard.linked_issue("Does a thing\n\nCloses #12"), 12)
        self.assertEqual(repro_guard.linked_issue("fixes #3"), 3)
        self.assertIsNone(repro_guard.linked_issue("see #4"))


class ReviewPlan(unittest.TestCase):
    def test_always_code_and_qa_plus_panel_labels(self):
        pr = {"number": 9, "body": "Adds x\n\nCloses #4", "labels": [{"name": "review:ui"}, {"name": "review:qa"}, {"name": "bug"}]}
        self.assertEqual(review_plan.plan(pr), (["code", "qa"], 4, ["ui"]))

    def test_issue_falls_back_to_pr(self):
        self.assertEqual(review_plan.plan({"number": 9, "body": None, "labels": []})[1], 9)


class Ready(unittest.TestCase):
    def run_(self, name, status="completed", conclusion="success", t="2026-01-01T00:00:00Z"):
        return {"name": name, "status": status, "conclusion": conclusion, "completed_at": t, "started_at": t}

    def test_required(self):
        ai = {"ai-review"}
        self.assertEqual(ready_check.required_checks("web", ai | {"review:code"}), ["test", "e2e", "review/code", "review/qa"])
        self.assertEqual(ready_check.required_checks("game", ai), ["test", "review/code", "review/qa"])
        self.assertEqual(ready_check.required_checks("web", ai | {"review:ui"}), ["test", "e2e", "review/code", "review/qa"])

    def test_without_ai_review_ci_alone_decides(self):
        self.assertEqual(ready_check.required_checks("web", {"review:code"}), ["test", "e2e"])
        self.assertEqual(ready_check.required_checks("game", set()), ["test"])

    def test_states(self):
        req = ["test", "e2e", "review/code", "review/qa"]
        all_ok = [self.run_(n) for n in req]
        self.assertEqual(ready_check.decide(req, all_ok)[:2], ("completed", "success"))
        self.assertEqual(ready_check.decide(req, all_ok[:3])[:2], ("in_progress", None))
        red = all_ok[1:] + [self.run_("test", conclusion="failure")]
        self.assertEqual(ready_check.decide(req, red)[:2], ("completed", "failure"))

    def test_newest_run_counts(self):
        req = ["review/qa"]
        runs = [self.run_("review/qa", conclusion="failure", t="2026-01-01T00:00:00Z"),
                self.run_("review/qa", conclusion="success", t="2026-01-02T00:00:00Z")]
        self.assertEqual(ready_check.decide(req, runs)[1], "success")


if __name__ == "__main__":
    unittest.main()
