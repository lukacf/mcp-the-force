# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2025-01-01

### Added
- Initial public release of MCP The-Force Server
- Multi-provider AI model support (OpenAI o3/o3-pro/o4-mini/gpt-4.1, Google Gemini 2.5 Pro/Flash, xAI Grok 3 Beta/Grok 4)
- Intelligent context management with vector store integration for large codebases
- Smart context overflow handling with automatic vector store creation
- Multi-turn conversation support across all models via UnifiedSessionCache
- Project history search across conversations and git commits
- Comprehensive configuration system with YAML + environment variable support
- Session management with configurable TTL and automatic cleanup
- Robust test suite with unit, integration, and Docker-in-Docker E2E tests
- Security features including secret redaction and path restrictions
- CLI tools for configuration management (`mcp-config`)
- FastMCP-based MCP protocol implementation
- Sophisticated tool system with dynamic parameter routing using Python descriptors
- Protocol-based adapter architecture for extensibility
- Background task management with operation timeouts and cancellation
- Comprehensive logging with VictoriaLogs integration
- Docker support with multi-stage builds and non-root containers

### Changed
- Migrated from "memory" to "history" terminology throughout codebase for clarity
- Upgraded to Production/Stable development status
- Consolidated vector store cleanup from external loiterkiller service to integrated VectorStoreManager

### Fixed
- E2E test cleanup now uses built-in VectorStoreManager instead of deprecated loiterkiller service
- Resolved import errors in history search functionality (`memory_search_declaration` → `history_search_declaration`)
- Cross-model history search tests properly maintain history records between calls
- Session management tests re-enabled and optimized with appropriate history disable parameters

### Security
- Comprehensive secret redaction in all logs and error messages
- Filesystem access restrictions via configurable path blacklist
- Secure configuration file permissions (600) for secrets.yaml
- No hardcoded credentials or sensitive information in codebase
- Docker containers run as non-root user with minimal privileges

### Documentation
- Comprehensive README with quick start guide and usage examples
- Detailed configuration reference in docs/CONFIGURATION.md
- Advanced integration guide in docs/ADVANCED.md
- Architecture analysis with design decisions and lessons learned
- Complete API documentation for all MCP tools
- Contributor guide with setup instructions and development workflow

### Technical Highlights
- Python 3.13+ with modern async/await patterns
- Type-safe design with Pydantic validation and Protocol-based interfaces
- Descriptor-based parameter routing system for clean tool definitions
- Stable-inline list context management for predictable multi-turn behavior
- Sophisticated test isolation and Docker-in-Docker E2E validation
- Extensible architecture supporting easy addition of new AI providers and tools

---

## Future Releases

This changelog will be updated with each release. See [GitHub Releases](https://github.com/lukacf/mcp-the-force/releases) for detailed release notes.