# Security Policy

## Supported Versions

We actively support the following versions with security updates:

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

We take security vulnerabilities seriously. If you discover a security issue, please follow these steps:

### For Security Issues

**DO NOT** create a public GitHub issue for security vulnerabilities.

Instead, please:

1. **Email**: Send details to the maintainer at the email address listed in the repository
2. **Include**: 
   - Description of the vulnerability
   - Steps to reproduce the issue
   - Potential impact assessment
   - Any suggested fixes (if available)

### Response Timeline

- **Initial Response**: Within 48 hours of receiving your report
- **Status Updates**: Weekly updates on investigation progress
- **Resolution**: We aim to resolve critical security issues within 7 days

### What to Expect

1. **Acknowledgment**: We'll confirm receipt of your vulnerability report
2. **Investigation**: Our team will investigate and validate the issue
3. **Fix Development**: We'll develop and test a fix
4. **Coordinated Disclosure**: We'll work with you on disclosure timing
5. **Credit**: We'll provide appropriate credit for your responsible disclosure (if desired)

## Security Best Practices for Users

### Configuration Security

- **API Keys**: Store API keys in `secrets.yaml` (never commit to version control)
- **File Permissions**: Ensure `secrets.yaml` has 600 permissions (`chmod 600 secrets.yaml`)
- **Path Security**: Configure `security.path_blacklist` to restrict file access to sensitive directories

### Deployment Security

- **Docker**: Run containers as non-root user (default in our Docker images)
- **Network**: Use appropriate network isolation and firewalls
- **Logs**: Monitor logs for suspicious activity; secrets are automatically redacted

### Development Security

- **Dependencies**: Regularly update dependencies to get security patches
- **Testing**: Use isolated test environments with mock credentials
- **Pre-commit**: Use the provided pre-commit hooks to catch common issues

## Security Features

This project includes several security features:

- **Secret Redaction**: All logs automatically redact API keys and sensitive information
- **Path Restrictions**: Configurable filesystem access controls
- **Secure Defaults**: Configuration defaults prioritize security
- **Input Validation**: All inputs are validated using Pydantic models
- **Dependency Scanning**: Regular dependency security audits

## Threat Model

### In Scope

- Authentication and authorization bypasses
- Information disclosure vulnerabilities
- Code injection vulnerabilities
- Path traversal attacks
- Denial of service attacks
- Dependency vulnerabilities with exploitable impact

### Out of Scope

- Issues requiring physical access to the host system
- Social engineering attacks
- Brute force attacks on properly configured rate-limited endpoints
- Issues in third-party dependencies without proof of exploitability

## Attribution

We believe in responsible disclosure and will acknowledge security researchers who help improve our security posture. If you'd like to be credited for your contribution, please let us know how you'd like to be acknowledged when you submit your report.