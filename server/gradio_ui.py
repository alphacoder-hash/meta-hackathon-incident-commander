import gradio as gr
import requests
import json
from typing import Dict, List, Any

class IncidentCommanderUI:
    def __init__(self, api_url: str = "http://localhost:7860"):
        self.api_url = api_url

    def _reset(self, task_id: str):
        try:
            resp = requests.post(f"{self.api_url}/reset", json={"task_id": task_id})
            resp.raise_for_status()
            data = resp.json()
            return self._format_output(data["observation"])
        except Exception as e:
            return f"Error: {str(e)}"

    def _step(self, action_type: str, target: str, cause: str):
        try:
            payload = {"action_type": action_type}
            if target: payload["target_service"] = target
            if cause: payload["root_cause_id"] = cause
            
            resp = requests.post(f"{self.api_url}/step", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return self._format_output(data["observation"])
        except Exception as e:
            return f"Error: {str(e)}"

    def _grade(self):
        try:
            resp = requests.get(f"{self.api_url}/grade")
            resp.raise_for_status()
            return f"## Final Score: {resp.json()['score']:.4f}\n\n```json\n" + json.dumps(resp.json(), indent=2) + "\n```"
        except Exception as e:
            return f"Error: {str(e)}"

    def _format_output(self, obs: Dict):
        # Service status table
        status_md = "### 🖥️ Service Status\n| Service | Healthy | Latency | Error Rate | CPU | Mem |\n|---|---|---|---|---|---|\n"
        for s in obs["service_statuses"]:
            h = "✅" if s["healthy"] else "❌"
            status_md += f"| {s['name']} | {h} | {s['latency_ms']}ms | {s['error_rate']:.1%} | {s['cpu_pct']}% | {s['memory_pct']}% |\n"
        
        # Alerts
        alerts_md = "### 🚨 Active Alerts\n"
        if not obs["alerts"]:
            alerts_md += "_None_\n"
        for a in obs["alerts"]:
            sev = "🔴" if a["severity"] == "critical" else "🟡"
            alerts_md += f"- {sev} **{a['service']}**: {a['message']}\n"

        # Logs
        logs_md = "### 📝 Recent Logs\n```text\n" + "\n".join(obs["logs"][-10:]) + "\n```"
        
        # Timeline
        timeline_md = "### ⏳ Incident Timeline\n" + "\n".join([f"- {t}" for t in obs["timeline"][-5:]])

        # Header info
        header = f"## Incident: {obs['incident_id']} | Task: {obs['task_id']} | Step: {obs['step']}/{obs['max_steps']}\n"
        header += f"**Reward**: {obs.get('total_reward', 0):.2f}\n"

        return f"{header}\n\n{status_md}\n\n{alerts_md}\n\n{logs_md}\n\n{timeline_md}"

def build_ui(api_url: str = "http://localhost:7860"):
    ui_engine = IncidentCommanderUI(api_url)
    
    with gr.Blocks(title="IncidentCommander Dashboard", theme=gr.themes.Soft()) as demo:
        gr.Markdown("# 🚨 IncidentCommander: DevOps OpenEnv Environment")
        
        with gr.Row():
            with gr.Column(scale=1):
                task_dropdown = gr.Dropdown(
                    choices=["single_service_crash", "cascading_failure", "bad_deployment", "silent_degradation"],
                    value="single_service_crash",
                    label="Select Scenario"
                )
                reset_btn = gr.Button("🚀 Reset / Start Episode", variant="primary")
                
                gr.Markdown("---")
                gr.Markdown("### 🛠️ Step Action")
                action_type = gr.Dropdown(
                    choices=["CHECK_LOGS", "CHECK_METRICS", "TRACE_REQUEST", "RESTART_SERVICE", "SCALE_UP", "ROLLBACK", "FAILOVER_DB", "CLEAR_CACHE", "DIAGNOSE", "ESCALATE"],
                    value="CHECK_LOGS",
                    label="Action Type"
                )
                target_svc = gr.Dropdown(
                    choices=["api_gateway", "auth", "database", "cache", "queue", "payment", "notification", "cdn"],
                    label="Target Service (Optional)"
                )
                root_cause = gr.Dropdown(
                    choices=["cache_oom", "database_overload", "payment_bad_deploy", "payment_memory_leak"],
                    label="Root Cause ID (For DIAGNOSE only)"
                )
                step_btn = gr.Button("⚡ Submit Action", variant="secondary")
                
                gr.Markdown("---")
                grade_btn = gr.Button("📊 Get Final Grade")
                grade_output = gr.Markdown()

            with gr.Column(scale=2):
                main_output = gr.Markdown("### Welcome, SRE. Reset to start the simulation.")

        # Event handlers
        reset_btn.click(ui_engine._reset, inputs=[task_dropdown], outputs=[main_output])
        step_btn.click(ui_engine._step, inputs=[action_type, target_svc, root_cause], outputs=[main_output])
        grade_btn.click(ui_engine._grade, outputs=[grade_output])

    return demo

if __name__ == "__main__":
    demo = build_ui()
    demo.launch(server_name="0.0.0.0", server_port=7861)
