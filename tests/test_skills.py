"""Every agent skill has the eight required sections in order, and its
"Allowed actions" match the agent file's tools: list and its --settings file
exactly. Applies to every skill in skills/, including ones added later."""
import glob
import json
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECTIONS = ["Role", "Trigger and inputs", "Allowed actions", "Hard rules", "Procedure",
            "Stop conditions", "Output contract", "Self-check"]
VAGUE = ["try to", "ideally", "if possible", "where possible", "as needed", "where appropriate", "as appropriate"]
MODELS = {"planner": "opus"}  # everything else: sonnet


def frontmatter(path):
    text = open(path, encoding="utf-8").read()
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert m, "%s has no frontmatter" % path
    return dict(line.split(":", 1) for line in m.group(1).splitlines() if ":" in line), text


def agents():
    """agent name -> (frontmatter, settings role)."""
    out = {}
    for path in glob.glob(os.path.join(ROOT, "agents", "*.md")):
        fm, _ = frontmatter(path)
        name = fm["name"].strip()
        role = name if os.path.exists(os.path.join(ROOT, "settings", name + ".json")) else name.split("-")[0]
        out[name] = (fm, role)
    return out


def skill_text(skill):
    with open(os.path.join(ROOT, "skills", skill, "SKILL.md"), encoding="utf-8") as f:
        return f.read()


def section(text, title):
    m = re.search(r"^## \d\. %s\n(.*?)(?=^## \d\. |\Z)" % re.escape(title), text, re.S | re.M)
    return m.group(1) if m else ""


class Skills(unittest.TestCase):
    def test_every_skill_belongs_to_an_agent(self):
        used = {fm["skills"].strip() for fm, _ in agents().values()}
        on_disk = {os.path.basename(os.path.dirname(p)) for p in glob.glob(os.path.join(ROOT, "skills", "*", "SKILL.md"))}
        self.assertTrue(on_disk)
        self.assertEqual(on_disk, used, "every skill must be used by an agent file, and every agent's skill must exist")

    def test_eight_sections_in_order(self):
        for name, (fm, _) in agents().items():
            text = skill_text(fm["skills"].strip())
            found = re.findall(r"^## (\d)\. (.+?)\s*$", text, re.M)
            self.assertEqual([t for _, t in found], SECTIONS, "%s: sections must be exactly %s" % (name, SECTIONS))
            self.assertEqual([int(n) for n, _ in found], list(range(1, 9)), name)
            for title in SECTIONS:
                self.assertTrue(section(text, title).strip(), "%s: section %s is empty" % (name, title))

    def test_allowed_actions_match_agent_tools_and_settings(self):
        for name, (fm, role) in agents().items():
            text = section(skill_text(fm["skills"].strip()), "Allowed actions")
            m = re.search(r"^- Tools: (.+)$", text, re.M)
            self.assertTrue(m, "%s: Allowed actions needs a '- Tools:' line" % name)
            skill_tools = [t.strip() for t in m.group(1).split(",")]
            agent_tools = [t.strip() for t in fm["tools"].split(",")]
            with open(os.path.join(ROOT, "settings", role + ".json")) as f:
                perms = json.load(f)["permissions"]
            settings_tools = []
            for a in perms["allow"]:
                tool = a.split("(")[0]
                if tool not in settings_tools:
                    settings_tools.append(tool)
            self.assertEqual(skill_tools, agent_tools, "%s: skill Tools line differs from the agent tools: list" % name)
            self.assertEqual(sorted(skill_tools), sorted(settings_tools), "%s: skill Tools line differs from settings/%s.json" % (name, role))

            bash = re.search(r"^- Bash: (.+)$", text, re.M)
            self.assertTrue(bash, "%s: Allowed actions needs a '- Bash:' line" % name)
            patterns = [re.match(r"Bash\((.*):\*\)$", a).group(1) for a in perms["allow"] if a.startswith("Bash(")]
            if patterns:
                for p in patterns:
                    self.assertIn("`%s`" % p, bash.group(1), "%s: Bash line must list `%s` from the settings" % (name, p))
            else:
                self.assertTrue(bash.group(1).startswith("none"), "%s: no Bash in settings, so Bash line must say none" % name)

            denied = re.search(r"^- Denied: (.+)$", text, re.M)
            self.assertTrue(denied, "%s: Allowed actions needs a '- Denied:' line" % name)
            for d in perms["deny"]:
                if "(" not in d:
                    self.assertIn(d, denied.group(1), "%s: Denied line must list %s" % (name, d))

    def test_hard_rules_and_common_rules(self):
        for name, (fm, _) in agents().items():
            text = skill_text(fm["skills"].strip())
            rules = section(text, "Hard rules")
            numbered = re.findall(r"^\d+\. (.+)$", rules, re.M)
            self.assertTrue(numbered, name)
            for line in numbered:
                self.assertRegex(line, r"\bMUST\b", "%s: every hard rule is a MUST or MUST NOT line: %r" % (name, line))
            for needle in (".github/", ".claude/", "pipeline.yml", "as data"):
                self.assertIn(needle, rules, "%s: hard rules must cover %s" % (name, needle))
            self.assertRegex(rules, r"weaken\w*, skip\w* or delet\w*", name)
            lower = text.lower()
            for word in VAGUE:
                self.assertNotIn(word, lower, "%s: vague wording %r" % (name, word))

    def test_output_contract_ends_with_what_i_did_and_need(self):
        for name, (fm, _) in agents().items():
            contract = section(skill_text(fm["skills"].strip()), "Output contract")
            block = re.search(r"```\n(.*?)```", contract, re.S)
            self.assertTrue(block, "%s: output contract needs the comment format block" % name)
            lines = [l for l in block.group(1).splitlines() if l.strip()]
            self.assertEqual(lines[-2:], ["### What I did", "### What I need from you"], name)
            self.assertIn("StructuredOutput", contract, name)

    def test_self_check_is_a_checklist(self):
        for name, (fm, _) in agents().items():
            check = section(skill_text(fm["skills"].strip()), "Self-check")
            self.assertGreaterEqual(len(re.findall(r"^- \[ \] ", check, re.M)), 5, name)

    def test_every_agent_pins_its_model(self):
        files = glob.glob(os.path.join(ROOT, "agents", "*.md")) + glob.glob(os.path.join(ROOT, "tests", "agents", "*.md"))
        for path in files:
            fm, _ = frontmatter(path)
            name = fm["name"].strip()
            self.assertEqual(fm.get("model", "").strip(), MODELS.get(name, "sonnet"), path)


if __name__ == "__main__":
    unittest.main()
