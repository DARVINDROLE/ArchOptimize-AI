- Compare the CALCULATED monthly cost (given below the documentation, from the calculator
  tools) with `monthly_budget_usd`. Use those numbers; never invent prices. If the cost is
  over budget, report it with the numbers as evidence.
- Over-provisioning: capacity far above the stated peak RPS (e.g. huge instances for tens
  of requests per second); the calculated capacity shows how much headroom there is.
- Budget vs other requirements: when meeting the SLO / RPS / latency would clearly cost more
  than the budget, say so (this is a requirement conflict, not just a cost finding).
- Missing cheaper options that fit the workload (caching, managed/serverless services,
  autoscaling instead of peak-sized fixed fleets).
