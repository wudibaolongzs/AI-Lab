# Luogu remote protocol verification

Official source retrieved 2026-11-08 via a bounded HTTPS GET:
https://docs.lgapi.cn/open/redocusaurus/open.yaml
Documentation: https://docs.lgapi.cn/open/openapi

Base URL: https://open-v1.lgapi.cn. HTTP Basic authentication uses the raw
OpenAppToken (username:password), base64 encoded. Set LUOGU_OPENAPP_TOKEN only
on the server. Never expose it to a browser.

POST /judge/problem accepts pid, lang, o2, code, trackId. The successful JSON
response contains requestId. Python uses python3/c; C++17 uses cxx/17/gcc.

GET /judge/result returns 204 before any result, or a JudgeCallback containing
requestId, trackId, type, data.compile, and data.judge (including subtasks/cases).
Results are cached officially for only one hour. The OpenAPI lists /judge/result
but declares id as a PATH parameter without any {id} placeholder. Therefore the
precise result URL is **unverified**. The adapter's ?id= form is provisional.
An operator must confirm this with the vendor before enabling live operation.

Documented JudgeStatus integers: 0 Waiting, 1 Judging, 2 Compile Error,
3 Output Limit Exceeded, 4 Memory Limit Exceeded, 5 Time Limit Exceeded,
6 Wrong Answer, 7 Runtime Error, 11 Invalid, 12 Accepted,
14 Overall Unaccepted. Only documented terminal integers (or compile.success=false)
complete a local result. Unknown statuses stay judging and preserve raw JSON.
A successful compile alone never means Accepted.

Both LUOGU_ENABLED=1 and LUOGU_PROTOCOL_VERIFIED=1 and configured credentials
are necessary. All default to disabled. No real submissions were used to develop
or test this integration. Public config reveals flags only.

POST /api/remote/submissions requires an authenticated classroom student,
exercise_id, language, code, client_submission_id and upload_confirmed:true.
GET /api/remote/submissions/{id} returns only records belonging to that same
class and student. LUOGU_DB defaults to data/remote.sqlite3. Persisted records
contain a source SHA256, never source text. Reusing a client ID with changed
content returns 409. Submission identity and budget are committed before network
access. A timeout is uncertain; never automatically resubmit it. Restart recovers
old submitting records as uncertain. Limits: 2 concurrent network calls,
10 submissions per student per rolling hour, 50 globally per rolling 24 hours.
Browser-driven polling is throttled server-side to 2/5/10 seconds; the UI should
auto-poll for at most 120 seconds and offer manual refresh afterwards. Pending
results expire after an hour. Read errors retain cached partial results. No
WebSocket or automatic submission retry is used.
