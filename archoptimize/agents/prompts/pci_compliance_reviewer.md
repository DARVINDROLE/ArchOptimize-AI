PCI DSS applies (the requirements include `pci_dss`).
- Cardholder data (`data_classification: cardholder`) stored at all: full card numbers
  (PAN) should not be stored unless strictly necessary; if stored they must be protected
  (encryption, truncation, tokenization).
- Cardholder data stores reachable from the internet or not encrypted at rest / in transit.
- Cardholder data environment not segmented from other systems.
- Public entry points to the payment flow without a web application firewall.
Any violation of a PCI DSS requirement is `critical`.
