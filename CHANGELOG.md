# Changelog

## 1.0.5
Fixed Force conversations not showing in project history search
Added complete Ollama adapter with LiteLLM integration and model discovery  
Fixed deep research models to use web_search_preview tool correctly
Added comprehensive test coverage with 100% unit test pass rate

## 1.0.4
Fixed critical context loss bug with files over 500KB causing API retry failures
Added configurable file size limits (50MB per file, 200MB total)
Implemented deferred cache updates to prevent context loss on failed API calls

## 1.0.3
Upgraded Claude Opus to version 4.1
Added vector store deduplication system with two-level caching for cost reduction
Fixed hash collision bugs and cross-platform hashing inconsistencies
Enhanced vector store API optimization with parallel file uploads

## 1.0.2
Added TokenBudgetOptimizer for intelligent context management with tiktoken-based optimization
Fixed critical context window overflow issues
Fixed history storage configuration bug (memory.sync → history.sync)
Added E2E test reliability with retry mechanisms for OpenAI vector store consistency

## 1.0.1
Added FusionTree algorithm for ultra-efficient file tree representation (60-90% token savings)
Fixed deep research models to use web_search_preview tool

## 1.0.0
Initial public release with multi-provider AI model support
Added intelligent context management with vector store integration
Implemented multi-turn conversation support via UnifiedSessionCache
Added project history search across conversations and git commits
Comprehensive configuration system with YAML + environment variable support