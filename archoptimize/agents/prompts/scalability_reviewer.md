- Capacity vs `peak_rps`: is the compute tier (instance size × replicas, autoscaling limits)
  able to serve the peak? A single small instance cannot serve thousands of RPS.
- No autoscaling for spiky or growing traffic (fixed replicas, no `autoscaling`).
- Read-heavy workloads hitting the database directly at high RPS with no cache / CDN.
- Latency: long synchronous chains or cross-service hops that make `p95_latency_ms`
  unrealistic.
- Database scaling limits (single writer under a write spike, no read replicas).
