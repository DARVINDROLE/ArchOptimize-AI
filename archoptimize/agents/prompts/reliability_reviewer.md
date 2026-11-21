- Single points of failure: components with `replicas: 1` or `availability_zones: 1`
  (databases without Multi-AZ, a single server) when the availability SLO is 99.9 % or more.
- Availability of synchronous call chains: availabilities multiply along sync edges, and an
  external dependency with a lower SLA caps the whole chain. Work that need not be in the
  request path (emails, notifications) should be asynchronous via a queue.
- Backups: `backups_enabled: false` or missing point-in-time recovery when an RPO is stated.
- Recovery: can the stated RTO be met with this design?
- Fixed capacity that cannot absorb stated peak load (failure under load).
