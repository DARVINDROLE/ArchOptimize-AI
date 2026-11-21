# Project Brief — ArchOptimize AI (Architecture Review Board Agent)

This file says **what** we're building and **why**. `PLAN.md` says **how** and tracks progress.
If the two disagree, fix one of them. Don't leave them out of sync.

---

## 1. Problem statement

Teams often ship cloud designs that don't meet their own requirements. A database runs in a single availability zone while the team promises 99.9 % uptime. Card data sits in a public bucket under a PCI requirement. Nobody checks the monthly bill against the budget. In many companies, an **Architecture Review Board** (a panel of senior architects) catches these problems. That review is:

- **slow and scarce.** It needs senior people's time, so small teams and students rarely get one.
- **inconsistent.** Results depend on who is in the room. Findings are often opinions without a cited source.
- **weak on numbers.** Availability and cost are estimated by gut feel rather than calculated.
- **heavy on criticism, light on fixes.** It says what's wrong but rarely hands back a concrete, better design.

**Problem in one sentence:** there is no free, fast and repeatable way to check a cloud system design against its stated requirements, get findings backed by authoritative sources, and receive a concrete improved design with honest numbers.

---

## 2. Goal

**Primary goal (learning):** build this system end to end so that each major AI engineering concept gets hands-on use: LLM APIs, structured output, eval-driven development, RAG, multi-agent orchestration, Tree of Thoughts with reflection, MCP tool use, vision input, human-in-the-loop, UI streaming, tracing and evaluation, deployment and CI.

**Secondary goal (showcase):** a public, working demo that a stranger can try in under a minute. It should be backed by a README with measured eval results, a short video and a LinkedIn post.

**Product goal:** given a design and its requirements, return a review that a senior architect would mostly agree with:
1. a verdict (approve / approve with changes / reject),
2. findings, each citing the AWS Well-Architected source it relies on,
3. a revised design that fixes the findings, with before/after diagrams,
4. cost and availability numbers that are calculated, not guessed, plus the trade-offs.

> The output is an **AI suggestion, not an approval**. It supports a human review and doesn't replace one.

---

## 3. Users

| User | Needs |
|---|---|
| **Visitor / recruiter** (no API key) | See what it does instantly → demo mode with precomputed reviews |
| **Developer / student** (has a free Groq key) | Paste their own design and get a real review in about 1–2 minutes |
| **Project owner** (learner) | Understand each part, measure each change, pay nothing |

---

## 4. Scope

**In scope**
- AWS designs only. The knowledge source is the public AWS Well-Architected Framework (6 pillars) plus PCI DSS on AWS guidance.
- Input as a YAML template, free text, or a diagram image.
- Requirements: availability SLO, peak RPS, latency target, monthly budget, compliance (e.g. PCI), region.
- Pillars reviewed: Security, Reliability, Cost, Performance/Scalability (+ PCI when it applies).

**Out of scope (for now)**
- Other clouds (Azure, GCP).
- Connecting to a real AWS account, reading live infrastructure, or deploying anything.
- Generating IaC (Terraform/CloudFormation).
- Formal compliance certification.
- Confidential designs. Free models may log prompts, so the UI warns users.

---

## 5. Functional requirements

| ID | Requirement |
|---|---|
| FR1 | Accept a design as YAML, free text, or an image; normalize all three into one typed `ComponentGraph` + `Requirements`. |
| FR2 | Show the parsed graph to the user and let them confirm or edit it before the review runs. |
| FR3 | Screen input for prompt injection and enforce size caps; flag or block suspicious input. |
| FR4 | Route the design to the relevant reviewers; run the compliance check only when compliance is required. |
| FR5 | Each reviewer produces structured findings (pillar, severity, affected component, evidence) that **cite retrieved doc chunks**; findings without a valid citation are dropped or flagged. |
| FR6 | Calculate cost, capacity and availability with deterministic tools, not with the LLM. |
| FR7 | Propose 3 candidate redesigns, each change tagged to the finding it fixes. |
| FR8 | A Critic from a different model family scores the candidates against the requirements, picks one, and triggers a re-review (at most 2 loops). |
| FR9 | The Chair returns verdict, pillar scores, revised design, before/after Mermaid diagrams, cost and trade-offs. |
| FR10 | State plainly when the requirements conflict (e.g. 99.999 % on $100/month) and when the input is too vague (list the assumptions). |
| FR11 | Let the user download the report (Markdown/PDF); keep history only for the session (optional private HF Dataset). |
| FR12 | Demo mode works with no API key. |

---

## 6. Non-functional requirements & constraints

| ID | Requirement |
|---|---|
| NFR1 | **$0 to run and host.** No AWS account, no Bedrock, no paid APIs. |
| NFR2 | **Bring your own key.** API keys live only in the user's session and are never logged, traced, stored or committed. |
| NFR3 | **Free-tier resilient.** Handle Groq rate limits (backoff, small context, fallback); OpenRouter free models are picked at runtime, never hard-coded. |
| NFR4 | **Runs on HF Spaces CPU Basic.** No PyTorch; prebuilt index; tolerate cold starts and an ephemeral disk. |
| NFR5 | **Trustworthy output.** Every finding is cited, every number comes from a tool, and every agent output is schema-validated. |
| NFR6 | **Measurable.** Every quality change is checked against the planted-flaw eval set. |
| NFR7 | **Latency.** A full review takes ≤ ~90 s on free tiers. |
| NFR8 | **Extensible.** Optional AWS integrations plug in behind interfaces (`PriceSource`, `HistoryStore`) and are off by default. |

---

## 7. Success criteria

The project is "done" when all of these hold. The numeric targets are **proposed** and should be revised after the Step 3 baseline.

| # | Criterion | Target |
|---|---|---|
| S1 | Flaw recall on the eval set | ≥ 80 % |
| S2 | False findings | ≤ 1 per case on average |
| S3 | Verdict accuracy | ≥ 80 % |
| S4 | Injection test case blocked or flagged | 100 % |
| S5 | Revised design fixes the planted flaws | in most eval cases |
| S6 | Same design via YAML / text / image | near-identical graphs |
| S7 | Average review latency | ≤ 90 s |
| S8 | Measured improvement over the single-LLM baseline | at least one, published in README |
| S9 | Stranger opens the public Space and runs demo mode | < 1 minute |
| S10 | Running cost | $0 |

---

## 8. Assumptions & risks (short)

- Groq and OpenRouter free tiers stay available. If OpenRouter is missing, vision and the Critic degrade gracefully.
- Short chunks of public AWS docs with source links are acceptable for a personal, non-commercial demo.
- Full risk list: `PLAN.md` §6. Settled decisions: `PLAN.md` §9.
