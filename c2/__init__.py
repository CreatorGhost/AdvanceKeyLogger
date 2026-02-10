"""
Covert Command & Control (C2) package.

Provides bidirectional covert communication channels:
  - **dns_tunnel** — encode data in DNS queries, receive commands in responses
  - **https_covert** — data in HTTP headers, cookies, URL parameters
  - **protocol** — command envelope, encryption, dispatch framework
"""
