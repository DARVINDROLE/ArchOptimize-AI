"""Assemble the Gradio interface.

Flow: keys (optional for demo) → Input (YAML / text) → Parse → confirm/edit the parsed
design (human in the loop) → Run review (live agent log) → result tabs → download report.
"""

from __future__ import annotations

import uuid

import gradio as gr

from archoptimize.design_parsing.yaml_design_parser import design_template_text
from archoptimize.web_ui import event_handlers as h

INTRO = """
# 🏛️ ArchOptimize AI — Architecture Review Board
A team of AI agents reviews your **AWS system design** against its requirements (uptime,
traffic, budget, compliance), cites the **AWS Well-Architected** docs, proposes **3
redesigns**, lets a **Critic** pick one and shows **before/after diagrams with real cost and
availability numbers**.

> **AI suggestion, not an approval.** · **Don't paste confidential designs** — free models
> may log prompts. · Your API keys stay in this browser session only.
"""

TEXT_PLACEHOLDER = (
    "Example: Customers use a web app on one EC2 m5.large server in a single AZ, backed by "
    "an RDS MySQL database (single AZ). We need 99.9% uptime, 500 requests/second at peak "
    "and a budget of $600/month."
)


def build_app() -> gr.Blocks:
    with gr.Blocks(title="ArchOptimize AI", analytics_enabled=False) as app:
        session_id = gr.State(lambda: uuid.uuid4().hex)
        gr.Markdown(INTRO)

        with gr.Accordion(
            "🔑 API keys (bring your own, free) — not needed for demo mode", open=False
        ):
            with gr.Row():
                groq_key = gr.Textbox(
                    label="Groq API key (required for reviews)",
                    type="password",
                    placeholder="gsk_… from console.groq.com/keys",
                )
                openrouter_key = gr.Textbox(
                    label="OpenRouter API key (optional: independent Critic + fallback)",
                    type="password",
                    placeholder="sk-or-… from openrouter.ai/settings/keys",
                )
            gr.Markdown(
                "Keys are used only for this session's requests and are never stored or logged."
            )

        with gr.Row():
            demo_choice = gr.Dropdown(
                label="🎬 Demo mode: open a precomputed review (no key needed)",
                choices=h.demo_titles(),
                scale=4,
            )
            demo_button = gr.Button("Open demo", scale=1)

        with gr.Tabs():
            with gr.Tab("1 · Input"):
                mode = gr.Radio(["YAML", "Text"], value="YAML", label="Input format")
                yaml_input = gr.Code(
                    value=design_template_text(), language="yaml", label="Design (YAML template)"
                )
                text_input = gr.Textbox(
                    lines=8,
                    label="Design (free text — needs a Groq key)",
                    placeholder=TEXT_PLACEHOLDER,
                )
                parse_button = gr.Button("Parse design →", variant="primary")

            with gr.Tab("2 · Confirm design"):
                parse_status = gr.Markdown()
                with gr.Row():
                    parsed_yaml = gr.Code(language="yaml", label="Parsed design (edit if needed)")
                    diagram = gr.Markdown(label="Diagram")
                refresh_button = gr.Button("Refresh diagram")
                review_button = gr.Button("Run review ▶", variant="primary")

            with gr.Tab("3 · Live agents"):
                progress = gr.Markdown("Run a review to see the agents work.")
            with gr.Tab("4 · Verdict"):
                verdict = gr.Markdown()
            with gr.Tab("5 · Findings"):
                findings = gr.Markdown()
            with gr.Tab("6 · Revised design"):
                design = gr.Markdown()
            with gr.Tab("7 · Cost & trade-offs"):
                cost = gr.Markdown()
            with gr.Tab("8 · Report"):
                trace = gr.Markdown()
                report_file = gr.File(label="Download the full report (Markdown)")

        results = [progress, verdict, findings, design, cost, trace, report_file]
        parse_button.click(
            h.parse_input,
            inputs=[mode, yaml_input, text_input, groq_key, openrouter_key],
            outputs=[parse_status, parsed_yaml, diagram],
        )
        refresh_button.click(h.preview_yaml, inputs=[parsed_yaml], outputs=[diagram])
        review_button.click(
            h.run_review_stream,
            inputs=[parsed_yaml, groq_key, openrouter_key, session_id],
            outputs=results,
        )
        demo_button.click(
            h.open_demo,
            inputs=[demo_choice],
            outputs=[parse_status, parsed_yaml, diagram, *results],
        )
        gr.Markdown(
            "Built with LangGraph · Groq · OpenRouter · Chroma + fastembed · MCP · Gradio. "
            "Source: [github.com/DARVINDROLE/ArchOptimize-AI](https://github.com/DARVINDROLE/ArchOptimize-AI)"
        )
    return app
