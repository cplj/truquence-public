# Security

Report suspected vulnerabilities privately to hello@truquence.com. Include a
minimal synthetic reproduction and the affected version. Do not include
credentials or private records. Public issue trackers are unsuitable for
sensitive vulnerability details.
We aim to acknowledge a report within 14 days. For a confirmed vulnerability we aim
to release a fix, or publish an advisory with a workaround, within 60 days, and to
credit the reporter if they wish. These timeframes are targets.

The HTTP interface is for loopback use only. It has no authentication and must
not be exposed to untrusted networks. Contract reports are unsigned summaries
of supplied evidence; callers must establish provenance independently. FAIL
and UNKNOWN both block acceptance. No report authorizes execution or retry.
