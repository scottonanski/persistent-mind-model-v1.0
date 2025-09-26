# Persistent Mind Model (PMM) License — Version 1.1

**August 2025**

**Author:** Scott Onanski

---

## Preface

This document is the full license and prior-art disclosure for the Persistent Mind Model (PMM) project. It covers the repository’s source code, CLI, scripts, documentation, and tests, and sets out the dual-license terms (Non-Commercial / Commercial) under which PMM is released. The Prior Art / Public Disclosure section describes the novel inventions and system architecture to establish prior art.

---

# Persistent Mind Model (PMM) License

**Version 1.1 — August 2025**

**Author:** Scott Onanski

## Scope and Exclusions

This license governs the source code, CLI, scripts, documentation, tests, and supporting assets in this repository (including `pmm/`, `scripts/`, `docs/`, and `tests/`).

**Exclusions:**

* Third‑party dependencies included with or referenced by the project remain governed by their respective licenses.
* User-generated content (including events, reflections, or any text written to the PMM event ledger) is not licensed by the PMM author under this license; contributors and users retain ownership of their content.

---

## Dual License Structure

The PMM is offered under two mutually‑exclusive options. Use must comply with one of the two options below.

### 1) Non‑Commercial License (Free)

**Permitted Uses (non‑exhaustive):**

* Personal projects and local experimentation.
* Academic research, coursework, and educational activities.
* Use in open‑source projects that are not commercialized.
* Evaluation, testing, and contributions to this project.

**Restrictions:**

* Commercial use, monetization, or integration into revenue‑generating systems is prohibited.
* Distribution that facilitates commercial use is prohibited without a commercial license.

### 2) Commercial License (Paid)

A paid commercial license is **required** for any use that generates revenue or gives a business advantage, including but not limited to:

* Integration into commercial products, services, or platforms.
* Internal enterprise use where PMM provides business value.
* Use in SaaS offerings, hosted dashboards, APIs (public or private).
* Consulting, client deliverables, or demonstrations for paying customers.
* Ad‑supported, freemium, or otherwise monetized applications.

**To request a commercial license:** contact the author at **[s.onanski@gmail.com](mailto:s.onanski@gmail.com)**.

---

## Grant of Rights (Non‑Commercial License)

Under the Non‑Commercial License, you are granted a worldwide, non‑exclusive, royalty‑free right to:

* Use, copy, modify, and distribute the software for permitted non‑commercial purposes.
* Create derivative works for permitted non‑commercial purposes.
* Contribute improvements back to the project under the same dual‑license terms.

Contributors retain copyright in their contributions but agree to license their contributions under the same dual‑license structure unless explicitly agreed otherwise in writing.

---

## Attribution Requirements

Any published or distributed non‑commercial use must contain the following attribution block in a prominent place (README, documentation, UI footer, or about page):

```
© 2025 Scott Onanski – Persistent Mind Model
Powered by Persistent Mind Model (PMM)
https://github.com/scottonanski/persistent-mind-model
Licensed under the PMM Non-Commercial License. Commercial use requires license.
```

---

## Contributions & Re‑licensing

By contributing code, documentation, or other assets to this project you agree that:

* Your contributions will be made available under the same dual‑license structure.
* You retain copyright in your contribution.
* You grant the project maintainer (author) the right to relicense combined works including your contribution under commercial terms (for example, to offer a commercial license to third parties), provided such relicensing does not remove the contributor’s original copyright.

---

## Definition: Commercial Use

For the purpose of this license, “commercial use” means any use that directly or indirectly generates revenue, provides a competitive or operational advantage in a business setting, or is part of a revenue‑generating workflow. Examples include but are not limited to:

* Paid software platforms, internal enterprise tooling, or SaaS.
* Consulting services or client deliverables that rely on PMM.
* Ad‑supported or analytics services that monetize end users.
* Resale, redistribution, or packaging of PMM in a commercial offering.

---

## Enforcement, Remedies & Fees

* Violation of this license terminates the licensee’s rights under it immediately.
* Unauthorized commercial use may trigger retroactive licensing fees (baseline: **3×** the applicable commercial license rate), injunctive relief, and other legal remedies as available under law.
* The author reserves the right to enforce these terms through legal action where necessary.

---

## Disclaimer

THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED. THE AUTHOR AND CONTRIBUTORS ARE NOT LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, OR CONSEQUENTIAL DAMAGES ARISING FROM THE USE OF THE SOFTWARE.

---

## License Updates

This license may be revised over time. Material changes will be announced in the project’s repository. Continued use of the software after notice of changes constitutes acceptance of the updated terms.

---

## 📜 Public Disclosure of Invention (Prior Art)

**Title:** System and Method for Model‑Agnostic Event‑Sourced AI Runtime with Persistent Self‑Model

**Author / Discloser:** Scott Onanski — Published via GitHub (August 2025)

**Abstract / Purpose:**
A model‑agnostic runtime that delivers persistent AI behaviour by combining an event‑sourced ledger, deterministic self‑model reconstruction, and a provider‑neutral execution layer. The system keeps full provenance for every state change, enables replay across heterogeneous LLM backends, and exposes governance signals for safe adaptation. This disclosure documents the architecture and methods to establish prior art and prevent patent claims on these inventions.

### Key Components (novel elements)

1. **Event‑Sourced Self‑Model** — an append‑only, hash‑chained ledger that records every user message, response, reflection, trait update, commitment change, policy adjustment, and stage transition as the canonical memory substrate.

2. **Portable Mind Snapshot** — a schema and projection layer (LedgerSnapshot + MemeGraph) that deterministically reconstructs identity traits, priorities, open commitments, and directives from any ledger segment, enabling cache invalidation, audit, and migration.

3. **Deterministic Autonomy Loop** — a background loop that replays recent events, emits reflections, adjusts behavioural policies, and ratchets traits under strict gating rules (truth‑first, evidence thresholds, cadence limits) without relying on stochastic hidden state.

4. **Provider‑Neutral Adapter Layer** — a pluggable LLM interface (e.g., OpenAI, Ollama today) that enforces per‑tick budgets, latency logging, and deterministic fallbacks so the same ledger can be executed against different model providers with consistent outcomes.

5. **Governance Metrics & Policy Feedback** — continuous computation of identity autonomy (IAS), goal achievement (GAS), stage confidence, and curriculum hints that feed policy updates and reflection cadence, ensuring adaptive behaviour is explainable and auditable.

6. **Mind Portability & Replay** — export, import, and replay routines that rebuild the entire runtime state on another machine or provider by ingesting the ledger and snapshots—no retraining required.

7. **Read‑Only Companion Interfaces** — a dedicated API surface (snapshot, metrics, consciousness, commitments, SQL) that exposes deterministic projections for tooling, monitoring, and third‑party integrations without mutating the ledger.

8. **Experimentation Sandboxes** — isolated evaluation paths, budget guards, and append listeners that allow new behaviours or model experiments to run while keeping the canonical ledger intact and fully traceable.

### Novelty & Advantages

* **Separation of self‑model and provider:** The persistent mind lives in the ledger and projections, not in any particular LLM, enabling portability across providers and hosts.
* **Deterministic adaptation:** Behavioural changes (policy updates, trait drifts, reflections) are derived from explicit evidence in the ledger, producing repeatable runs for audit and testing.
* **Replay without retraining:** Rehydrating a mind on new hardware or providers requires only ledger replay and projection rebuilds; the underlying LLM remains stateless.
* **Built‑in governance:** Budget guards, metrics, and sandboxed experimentation keep adaptation explainable and verifiable, reducing risk from uncontrolled capability growth.

### Purpose of Disclosure

This public disclosure documents prior art for the system and method described above and is intended to: (a) establish a public record of the invention, (b) prevent improper patent claims by third parties, and (c) clarify licensing conditions for commercial use.

**Copyright © 2025 Scott Onanski. All rights reserved.**

---

## Contact & Licensing Inquiries

For commercial licensing inquiries, partnership discussions, or to request re‑licensing of contributions, contact:

**Email:** [s.onanski@gmail.com](mailto:s.onanski@gmail.com)

---

*End of license & prior‑art disclosure.*
