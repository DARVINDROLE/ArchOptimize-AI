- Data stores (databases, buckets, caches) reachable from the internet (`public: true`).
- Sensitive data (`confidential`, `cardholder`) not encrypted at rest (`encryption_at_rest: false`).
- Data in transit not encrypted (`encryption_in_transit: false`, `http` between services
  carrying confidential data).
- Internet-facing entry points (load balancer, API gateway, public compute) without a web
  application firewall / rate limiting in front of them, especially login or payment APIs.
- Clients able to reach internal components directly, bypassing the application tier.
