from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_taskflow_phase_controller import FakeQueue, c, manifest_zip


class NativeRepairTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        plan_path = self.repo / "plans" / "one.plan"
        plan_path.parent.mkdir()
        plan_path.write_text("project Native Repair\nid native-repair\n[ ] S real deployed effect\n"
                             "    effect_probe_command: /usr/bin/printf ok\n"
                             "    effect_probe_expected: ok\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.repo), "add", "plans/one.plan"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                        "commit", "-qm", "plan"], check=True)
        self.plan = c.parse_plan(plan_path)
        self.step = self.plan.by_id()["S"]
        self.state = self.repo / "state"
        self.q = FakeQueue()
        research_zip = self.repo / "research.zip"
        manifest_zip(research_zip, self.plan.sha256, {"RESEARCH_REPORT.md": b"source evidence"})
        self.research_digest = hashlib.sha256(research_zip.read_bytes()).hexdigest()
        research = c.job_base(self.plan, self.step, "research", provider="codex.research", priority=50, dependencies=[])
        research.update(state="complete", effect_evidence=[{"kind": "research_zip", "ref": self.research_digest,
                                                             "path": str(research_zip)}])
        self.q.jobs[research["id"]] = research
        self.work_zip = self.repo / "work.zip"
        manifest_zip(self.work_zip, self.plan.sha256,
                     {"EXTERNAL_EFFECT_INSTRUCTIONS.md": b"deploy work", "src/a.py": b"print(1)"})
        self.work_digest = hashlib.sha256(self.work_zip.read_bytes()).hexdigest()
        prompt = c.chatgpt_prompt(self.plan, self.step, {"sha256": self.research_digest})
        chat = c.job_base(self.plan, self.step, "chatgpt_sandbox", provider="chatgpt.com", priority=50, dependencies=[])
        chat.update(state="complete", prompt=prompt, prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
                    assigned_employee="ChatGPT chat-mode native sandbox", reasoning_effort="xhigh",
                    attachment_refs=[{"ref": "file:" + str(research_zip), "sha256": self.research_digest}])
        self.q.jobs[chat["id"]] = chat
        self.original = chat

    def complete_chat(self, job, *, native=False):
        cid = "conversation-" + job["id"]
        evidence = [{"kind": "chatgpt_sandbox_artifact", "ref": self.work_digest, "path": str(self.work_zip)},
                    {"kind": "provider_conversation", "ref": cid},
                    {"kind": "central_conversation_readback", "ref": cid}]
        if native:
            evidence.append({"kind": "provider_observed_native_exec", "tool": "container.exec",
                             "ref": "result-1", "call_ref": "call-1", "raw_stream_sha256": "a" * 64})
        job.update(state="complete", conversation_id=cid, effect_evidence=evidence)

    def tick(self):
        with mock.patch.object(c, "run_secretary", return_value={"completed": False}):
            return c.run_once(queue=self.q, plan=self.plan, role="Elliot Mercer", secretary=self.repo / "secretary",
                              state_root=self.state, worker_id="test-worker", manager="Manager", priority=50,
                              external_employee="Rina Hale", active_step_ids={"S"})

    def test_missing_native_proof_queues_one_retry_without_effect_handoff(self):
        self.complete_chat(self.original)
        first = self.tick()
        retry_id = c.phase_job_id(self.plan, "S", "chatgpt_sandbox", 1)
        retry = self.q.get(retry_id)
        self.assertEqual(retry["state"], "queued")
        self.assertEqual(retry["attachment_refs"], self.original["attachment_refs"])
        self.assertEqual(retry["taskflow_dependencies"], [self.original["id"]])
        self.assertEqual(retry["phase_attempt"], 1)
        self.assertIn(self.original["prompt"], retry["prompt"])
        self.assertIsNone(self.q.get(c.phase_job_id(self.plan, "S", "external_effect")))
        self.assertTrue(any(a.get("phase") == "native_compute_repair" for a in first["actions"]))
        self.tick()
        self.assertEqual(sum(1 for j in self.q.jobs.values() if j.get("provider") == "chatgpt.com"), 2)

    def test_d1_row_without_local_only_plan_or_attempt_fields_recovers(self):
        self.complete_chat(self.original)
        self.original["taskflow_plan_receipt"] = {"plan_sha256": self.plan.sha256,
                                                  "taskflow_step": "S", "phase": "chatgpt_sandbox"}
        for key in ("plan_text", "plan_source_ref", "payload", "phase_attempt"):
            self.original.pop(key, None)
        self.tick()
        retry = self.q.get(c.phase_job_id(self.plan, "S", "chatgpt_sandbox", 1))
        self.assertIsNotNone(retry)
        for key in ("plan_text", "plan_source_ref", "payload", "phase_attempt"):
            retry.pop(key, None)
        self.complete_chat(retry, native=True)
        result = self.tick()
        self.assertTrue(any(a.get("phase") == "external_effect" for a in result["actions"]))

    def test_ambiguous_inflight_turn_is_never_retried(self):
        self.original["state"] = "claimed"
        self.tick()
        self.assertIsNone(self.q.get(c.phase_job_id(self.plan, "S", "chatgpt_sandbox", 1)))
        self.assertIsNone(self.q.get(c.phase_job_id(self.plan, "S", "external_effect")))

    def test_successful_repair_hands_off_exact_returned_zip(self):
        self.complete_chat(self.original)
        self.tick()
        retry = self.q.get(c.phase_job_id(self.plan, "S", "chatgpt_sandbox", 1))
        self.complete_chat(retry, native=True)
        result = self.tick()
        effect = self.q.get(c.phase_job_id(self.plan, "S", "external_effect"))
        self.assertEqual(effect["state"], "effect_pending")
        self.assertEqual(effect["attachment_refs"][0]["sha256"], self.work_digest)
        self.assertTrue(any(a.get("phase") == "external_effect" and a.get("chat_attempt") == 1
                            for a in result["actions"]))

    def test_three_definitive_failures_route_terminal_without_more_sends(self):
        self.complete_chat(self.original)
        self.tick()
        for attempt in (1, 2):
            retry = self.q.get(c.phase_job_id(self.plan, "S", "chatgpt_sandbox", attempt))
            self.complete_chat(retry)
            result = self.tick()
        self.assertIsNone(self.q.get(c.phase_job_id(self.plan, "S", "chatgpt_sandbox", 3)))
        self.assertIsNone(self.q.get(c.phase_job_id(self.plan, "S", "external_effect")))
        failure = json.loads((self.state / self.plan.project_id / "S" / "native_compute_failure.json").read_text())
        self.assertEqual(failure["state"], "terminal_failure")
        self.assertEqual(len(failure["attempt_job_ids"]), 3)
        self.assertTrue(any(a.get("phase") == "native_compute_exhausted" for a in result["actions"]))
        self.tick()
        self.assertEqual(sum(1 for j in self.q.jobs.values() if j.get("provider") == "chatgpt.com"), 3)


if __name__ == "__main__":
    unittest.main()
