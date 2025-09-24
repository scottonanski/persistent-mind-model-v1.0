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

**Title:** System and Method for Model‑Agnostic Persistent Artificial Intelligence Identity and Memory Management

**Author / Discloser:** Scott Onanski — Published via GitHub (August 2025)

**Abstract / Purpose:**
A platform‑agnostic system that enables persistence of an AI "mind" across model backends and runs via an append‑only ledger, deterministic reconstruction, and a portable mind schema. The disclosure documents the architecture, core components, and methods to establish prior art and prevent patent claims on the described inventions.

### Key Components (novel elements)

1. **Portable Mind Schema** — a platform‑independent serializable schema that stores identity traits, commitments, priorities, and state values allowing an AI "mind" to be reconstructed deterministically on different LLM backends.

2. **Append‑Only Event Ledger** — deterministic, tamper‑evident log of events, commitments, reflections, trait adjustments, and policy updates that serves as canonical memory for the persistent mind.

3. **Deterministic Reconstruction Engine** — a deterministic replay mechanism that rebuilds an AI’s internal state from ledger events without retraining the underlying LLM, enabling reproducible identity transfer between models and hosts.

4. **Model‑Agnostic Execution Layer** — an abstraction that decouples procedural identity and decision logic from any single LLM; the same mind schema and ledger can be executed on multiple LLM backends (local or remote) with consistent behavior.

5. **Reflection & Commitment Cycle** — a built‑in loop where the system records commitments, revisits them, updates traits (e.g., OCEAN‑style), and ratchets capability while enforcing gating checks (truth‑first, safety constraints, reproducibility checks).

6. **Encrypted Backup & Transfer Mechanism** — secure export/import of the portable mind schema plus event ledger enabling migration of a persistent mind across machines and clouds while preserving cryptographic integrity and confidentiality.

7. **Metricization & Governance Signals** — continuous metrics (e.g., IAS, GAS) derived from ledger activity to guide policy updates, reflection cadence, and identity adoption heuristics.

8. **Sandboxed Measurement & Tracing** — execution sandboxes and tracers for candidate evaluations, ensuring experimental changes are measured and validated without leaking state or causing irreversible changes to the canonical ledger.

### Novelty & Advantages

* **Separation of mind and model:** The architecture isolates the persistent identity from any single model instance, enabling porting, long‑term continuity, and deterministic replay.
* **Ledger‑driven identity:** Identity and commitments are captured as first‑class artifacts in an append‑only ledger, enabling provenance, audit, and deterministic reconstruction.
* **Reproducible transfer without retraining:** The deterministic reconstruction engine allows restarting or migrating a mind without re‑training, merely by replaying ledger events into a compatible schema and execution layer.
* **Safety & evaluation gates:** Integrated gates and sandboxing for candidate improvements prevent unchecked capability escalations and prioritize truth and safety.

### Purpose of Disclosure

This public disclosure documents prior art for the system and method described above and is intended to: (a) establish a public record of the invention, (b) prevent improper patent claims by third parties, and (c) clarify licensing conditions for commercial use.

**Copyright © 2025 Scott Onanski. All rights reserved.**

---

## Contact & Licensing Inquiries

For commercial licensing inquiries, partnership discussions, or to request re‑licensing of contributions, contact:

**Email:** [s.onanski@gmail.com](mailto:s.onanski@gmail.com)

---

*End of license & prior‑art disclosure.*
