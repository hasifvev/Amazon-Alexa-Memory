# Decision: simulated Alexa presentation, genuine MCP execution

Date: 2026-10-08. Approved by Lord Hasif as part of completion plan.

Retain the genuine official-SDK Streamable HTTP MCP server. The browser is explicitly a simulation, not an Amazon-certified or device-integrated product. Routing selects a tool; all browser tool execution uses real tools/call traffic. Optional Bedrock inference is off by default and has separate timing/limits.

The deployment candidate is synthetic-only. Selected speaker namespaces demonstrate scope but do not authenticate a person or provide personal-data privacy. Current-snapshot export/import is not full event-history backup. One process/one worker remains a deliberate persistence restriction.

Do not expand into OAuth certification, private production, new cloud resources or multiworker architecture in this closure pass. External submission/deploy/publishing approvals are separate.
