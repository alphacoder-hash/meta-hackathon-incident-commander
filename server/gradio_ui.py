import gradio as gr
import requests
import json
import os
from typing import Dict, List, Any

class IncidentCommanderUI:
    def __init__(self, api_url: str = "http://localhost:7860"):
        # Internally on HF, the app talks to itself on localhost
        self.api_url = api_url

    def _reset(self, task_id: str):
        try:
            # Match the final server/environment.py ResetResult structure
            resp = requests.post(f"{self.api_url}/reset", json={"task_id": task_id})
            resp.raise_for_status()
            data = resp.json()
            
            # Reset results often wrap the observation
            obs = data.get("observation", data)
            return self._format_output(obs)
        except Exception as e:
            return f"### ⚠️ Error\nFailed to reset environment: {str(e)}"

    def _step(self, response: str):
        try:
            if not response or len(response.strip()) < 5:
                return "### ⚠️ Warning\nPlease provide a more detailed analysis before submitting."
                
            # Send free-text response matching the finale architecture
            payload = {"response": response}
            resp = requests.post(f"{self.api_url}/step", json=payload)
            resp.raise_for_status()
            obs = resp.json()
            
            return self._format_output(obs)
        except Exception as e:
            return f"### ⚠️ Error\nAction submission failed: {str(e)}"

    def _format_output(self, obs: Dict):
        """Format the text-based observation for a premium layout."""
        # Main report with nice formatting
        report = obs.get("incident_report", "No report available.")
        
        # Meta info
        task_id = obs.get("task_id", "N/A").upper()
        step = obs.get("step_number", 0)
        max_steps = obs.get("max_steps", 3)
        total_reward = obs.get("total_reward", 0.0)
        feedback = obs.get("feedback", "")
        done = obs.get("done", False)

        status_color = "🟢 COMPLETE" if done else "🔴 ACTIVE"
        
        md = f"## {status_color} | Tier: {task_id} | Progress: {step}/{max_steps}\n"
        md += f"**Current Score:** `{total_reward:.2f}`\n\n"
        
        if feedback:
            md += f"> [!NOTE]\n> **System Feedback:** {feedback}\n\n"

        md += "---\n### 📄 Incident Report (Live Context)\n"
        md += f"{report}\n\n"
        
        if done:
            md += "---\n## 🏆 Triage Complete\n"
            md += f"**Final Session Score:** `{total_reward:.2f}`\n"
            md += "Click **Reset** to try another scenario or a higher difficulty tier."

        return md

def build_ui(api_url: str = "http://localhost:7860"):
    ui_engine = IncidentCommanderUI(api_url)
    
    # Modern "Soft" theme with custom accent components
    with gr.Blocks(title="IncidentCommander Dashboard", theme=gr.themes.Soft(primary_hue="red", secondary_hue="slate")) as demo:
        gr.Markdown("""
        # 🚨 IncidentCommander: SRE Intelligence Dashboard
        *State-of-the-art Agentic Incident Response Environment*
        """)
        
        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("### 🕹️ Operation Control")
                task_dropdown = gr.Dropdown(
                    choices=[("Easy (Single Crash)", "easy"), 
                             ("Medium (Red Herring)", "medium"), 
                             ("Hard (Cascading P0)", "hard")],
                    value="easy",
                    label="Target Difficulty Tier"
                )
                reset_btn = gr.Button("🚀 RESET / INITIALIZE INCIDENT", variant="primary")
                
                gr.Markdown("---")
                gr.Markdown("### 🧠 Incident Response Analysis")
                response_input = gr.Textbox(
                    lines=10, 
                    placeholder="Enter your root cause analysis, identified red herrings, and prioritized remediation plan here...",
                    label="Response / Analysis Report"
                )
                submit_btn = gr.Button("⚡ SUBMIT FOR GRADING", variant="secondary")
                
                gr.Markdown("""
                ---
                ### ℹ️ Grading Criteria
                - **Easy**: ID failing service & root cause.
                - **Medium**: Explicitly flag 'Red Herring' signals.
                - **Hard**: Prioritize actions (FIRST, SECOND, THIRD).
                """)

            with gr.Column(scale=2):
                main_output = gr.Markdown("### [STATUS] Awaiting initialization...\nSelect a difficulty tier and click 'Reset' to start triaging.")

        # Event Handlers
        reset_btn.click(ui_engine._reset, inputs=[task_dropdown], outputs=[main_output])
        submit_btn.click(ui_engine._step, inputs=[response_input], outputs=[main_output])

    return demo

if __name__ == "__main__":
    # Local fallback for testing
    demo = build_ui()
    demo.launch(server_name="0.0.0.0", server_port=7860)
