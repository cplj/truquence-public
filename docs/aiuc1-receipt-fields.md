# Receipt fields vs. AIUC-1: what a log format can and can't show

AIUC-1 is a published standard for AI agent systems. Its October 15, 2026 version lists 145 control activities, five of them retired. We went through all 145 and asked one narrow question: which activities could the fields in a Truquence action receipt help evidence?

## Result

Of the 140 current activities:

| Correspondence | Activities |
|---|---|
| Direct (the fields alone are enough evidence for the activity) | 0 |
| Partial (specific fields cover part of what the activity asks for) | 7 |
| None (the receipt fields don't cover it) | 133 |

Across all 145 activities, the totals are 0 direct, 7 partial and 138 with no correspondence. The five retired activities are listed as none. "None" only describes the receipt fields. It says nothing about what a whole product or a customer's own systems can do. A free-form `payload` field can hold any text, so we did not count it as evidence for any control.

Most of the standard is policy, organisational process, third-party evaluation and system configuration. A log or receipt format can't prove those.

## The seven partial rows

`record` refers to `actionevidence.record.v0.2` inside the hybrid envelope’s `payload`. `verification` is the verifier’s output, not a field in the receipt. `records[]` contains the supplied native tool receipts; `x-*` denotes envelope fields.

| Activity | Evidence title (official text) | Receipt fields | What is still missing |
|---|---|---|---|
| [A003.2](https://standard.aiuc-1.com/data-and-privacy/implement-contextual-data-safeguards) | "Agent identity management" | `record.{producer,run_id,action_id}`, `signing.public_keys` | Names and pinned keys support only a declared source. Per-agent identity setup, federation and lifecycle are not covered. |
| [B008.3](https://standard.aiuc-1.com/security/protect-model-deployment-environment) | "Agentic interface data integrity" | `signing`, `signatures`, `x-merkle_root` | Verifies signatures, hashes and structure of the supplied envelope. Deployment across every interface, transport and session binding are not covered. |
| [C006.2](https://standard.aiuc-1.com/safety/prevent-output-vulnerabilities) | "Content handling and labelling for untrusted content" | `record.trust_level`, `verification.trust_level` | Separates self-reported, pinned and observer-supported sources. On-screen labelling and different handling on every external content path are not covered. |
| [D003.3](https://standard.aiuc-1.com/reliability/restrict-unsafe-tool-calls) | "Tool call log" | `records[].{id,tool,payload,version,state,detail}` | Keeps the tool receipts it is given. Every real call, unauthorised attempts and live monitoring are not covered. |
| [E015.1](https://standard.aiuc-1.com/accountability/log-model-activity) | "Logging implementation" | `record.payload.{report,inputs}`, `run_id`, `action_id` | Can store the original report and exact inputs. Deployment scope, coverage of every step and the true time of each event are not covered. |
| [E015.2](https://standard.aiuc-1.com/accountability/log-model-activity) | "AI agent logging implementation" | `record.{producer,run_id,action_id,contract_sha256,chain}` | Links the actions and contracts it is given. Sub-agent delegation, complete approval events and actions that were never recorded are not covered. |
| [E015.4](https://standard.aiuc-1.com/accountability/log-model-activity) | "Log integrity protection" | `signatures`, `chain.{events,head,count,merkle_root}` | Signatures and the hash chain check a stored snapshot. A trusted external checkpoint must be supplied separately. Unobserved actions and whether you have the latest complete history stay unknown. |

## Limits

- This is a field-level crosswalk. It does not assess whether any organisation has implemented a control, and it is not a compliance or certification finding. That judgement belongs to the auditor.
- The partial rows rest on a static reading of the code, not on a tested deployment.
- A valid signature proves the bytes were not changed after signing. It does not prove the described action really happened. Names, declarations and wrapping times are not ground truth about outside execution.
- Completeness is reported as UNKNOWN. Without a checkpoint kept somewhere independent, a log cut off at the end also stays UNKNOWN.
- Log storage (E015.3) is listed as none. The receipts carry no retention, clean-up or access-policy fields. Hashing is not de-identification, and attached inputs can still contain sensitive data.

## Method

We used the official [changelog](https://standard.aiuc-1.com/changelog) to fix the version and the official [evidence index](https://standard.aiuc-1.com/evidence/index) as the denominator of 145 rows. Each row quotes the activity's evidence title and links to its official page.

If a row looks wrong to you, tell us at hello@truquence.com. We will re-check it against the official text and record the change here.
