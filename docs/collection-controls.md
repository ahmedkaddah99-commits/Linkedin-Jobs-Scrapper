# Collection controls

Admin source imports accept a server-validated `scope` object:

```json
{
  "retrieval_mode": "bounded|custom|all_available",
  "max_jobs": 25,
  "max_pages": 20,
  "max_requests": 100,
  "max_credits": 0,
  "full_source_import": false
}
```

`max_jobs` is a maximum accepted-role cap. It is never a promise that the
source contains that many roles. The execution result exposes
`requested_job_limit`, `effective_job_limit`, `safety_ceiling`,
`pagination_complete`, `complete_snapshot`, `closure_safe`,
`completeness_state`, `stop_reason`, `observed_count`, `accepted_count`, and
`rejected_count` under the task's `collection` object.

`all_available` is accepted only for connectors whose backend capability
descriptor declares reliable pagination. It remains bounded by connector,
request, credit, and global safety ceilings. A ceiling stop produces an
incomplete snapshot and cannot close missing source jobs. Publication remains
an explicit review action; collection itself has no publication side effect.

`full_source_import` is retained as a legacy compatibility flag. It clears
the legacy scope filters, but it does not mean `all_available` and does not
claim pagination completeness.

The source list response contains the connector-derived `capabilities`,
`retrieval_modes`, and `all_available` availability object. Consumers should
render those values rather than maintaining a connector-name allow-list.
