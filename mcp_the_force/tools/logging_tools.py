"""MCP tool: run raw LogsQL queries against VictoriaLogs."""

from typing import Any
from .base import ToolSpec
from .registry import tool
from .descriptors import Route
from ..local_services.logging import LoggingService

LOGSQL_POCKET_GUIDE = """
LogsQL pocket guide
───────────────────
QUERY CORE – one-liners
  _time:5m error                    # AND implicit, put _time first
  _time:5m error OR warning         # use OR, NOT/-, and () for precedence
  {app="api"} error                 # label/stream filter
  status:error                      # field selector (default _msg)

FILTER PATTERNS
  word        : error               # matches "error" anywhere
  phrase      : "disk full"         # exact phrase match
  prefix      : erro*               # prefix matching
  substring   : _msg~"fatal"        # substring search
  exact/multi : status:=500         # exact match
              : status:=(500,503)   # multiple values
  range/cmp   : latency_ms:>500     # comparison operators
  regex       : url:~"/api/.+"      # regular expression
  empty/any   : user:_              # empty field
              : user:*              # any value

TOP PIPES (|)
  sort by (_time desc)              # sort results
  limit N / head N                  # limit output
  fields f1,f2                      # select fields
  stats count() by (endpoint)       # aggregations
  where latency_ms > 1000           # filter after initial query
  top 10 endpoint                   # top values
  uniq by (user)                    # unique values
  extract "re" as x                 # regex extraction
  sample N                          # random sampling

STATS FUNCTIONS
  count(), sum(x), avg(x), min/max(x), quantile(0.95)(x), 
  histogram(x,bucket), rate(x), count_uniq(x), values(x)

SPEED HINTS
  - Always start with _time:XXX to narrow time range
  - Use {label=value} filters early in query
  - Sort/regex only after initial filters
  - Use sample N for large result sets
"""


@tool
class SearchMCPDebugLogs(ToolSpec):
    """Run a raw LogsQL query against VictoriaLogs debug logs (developer mode only).

{guide}

Examples
────────
1. Last 20 errors
   _time:30m error | sort by (_time desc) | head 20

2. Top endpoints by slow (>1s) calls
   _time:15m latency_ms:>1000 | stats by (endpoint) count() slow | sort by (slow desc) | head 5

3. Per-minute error rate
   _time:1h error | stats by (bucket=_time(1m)) count() errors

4. Search specific app and severity
   _time:5m {{app="mcp-the-force"}} severity:error

5. Find specific text pattern
   _time:2h "CallToolRequest" {{project="/Users/myproject"}}
""".format(guide=LOGSQL_POCKET_GUIDE)

    # Required for @tool decorator
    model_name = "search_mcp_debug_logs"
    description = """Run a raw LogsQL query against VictoriaLogs debug logs (developer mode only).

LogsQL pocket guide
───────────────────
QUERY CORE – one-liners
  _time:5m error                    # AND implicit, put _time first
  _time:5m error OR warning         # use OR, NOT/-, and () for precedence
  {app="api"} error                 # label/stream filter
  status:error                      # field selector (default _msg)

FILTER PATTERNS
  word        : error               # matches "error" anywhere
  phrase      : "disk full"         # exact phrase match
  prefix      : erro*               # prefix matching
  substring   : _msg~"fatal"        # substring search
  exact/multi : status:=500         # exact match
              : status:=(500,503)   # multiple values
  range/cmp   : latency_ms:>500     # comparison operators
  regex       : url:~"/api/.+"      # regular expression
  empty/any   : user:_              # empty field
              : user:*              # any value

TOP PIPES (|)
  sort by (_time desc)              # sort results
  limit N / head N                  # limit output
  fields f1,f2                      # select fields
  stats count() by (endpoint)       # aggregations
  where latency_ms > 1000           # filter after initial query
  top 10 endpoint                   # top values
  uniq by (user)                    # unique values
  extract "re" as x                 # regex extraction
  sample N                          # random sampling

STATS FUNCTIONS
  count(), sum(x), avg(x), min/max(x), quantile(0.95)(x), 
  histogram(x,bucket), rate(x), count_uniq(x), values(x)

SPEED HINTS
  - Always start with _time:XXX to narrow time range
  - Use {label=value} filters early in query
  - Sort/regex only after initial filters
  - Use sample N for large result sets

Examples
────────
1. Last 20 errors
   _time:30m error | sort by (_time desc) | head 20

2. Top endpoints by slow (>1s) calls
   _time:15m latency_ms:>1000 | stats by (endpoint) count() slow | sort by (slow desc) | head 5

3. Per-minute error rate
   _time:1h error | stats by (bucket=_time(1m)) count() errors

4. Search specific app and severity
   _time:5m {app="mcp-the-force"} severity:error

5. Find specific text pattern
   _time:2h "CallToolRequest" {project="/Users/myproject"}"""

    # Use local service instead of adapter
    service_cls = LoggingService
    adapter_class = None  # Signal to executor that this runs locally
    timeout = 30

    # Single parameter: the raw LogsQL query
    query: Any = Route.adapter(
        description="Full LogsQL query string. Will be sent unmodified to VictoriaLogs.",
    )
