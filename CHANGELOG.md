# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2025-11-22

### Added
- Initial release
- User authentication with Mail.ru CalDAV
- Main menu with action buttons
- Meeting creation wizard (7 steps)
- View all meetings for today
- View current and future meetings for today
- Meeting details display
- Meeting notifications (cancelled, rescheduled, new)
- Reminder notifications (15 minutes before)
- Encrypted password storage (Fernet)
- SQLite database with three models (User, UserState, MeetingCache)
- WebSocket listener for Mattermost events
- HTTP server for button actions (port 8080)
- Automatic change detection and notification system
- Docker & Docker Compose support for Portainer Stacks
- Environment variable configuration
- Comprehensive documentation (README, Contributing guide)
- Support for @username and email parsing for meeting attendees
- Support for optional descriptions and locations in meetings

### Features
- Direct message only operation
- User state management for multi-step dialogs
- Meeting cache with hash-based change detection
- Configurable timezone support
- Configurable check interval and reminder time
- Secure password encryption with Fernet
- Support for Mail.ru CalDAV Calendar

### Documentation
- Complete README with usage examples
- CONTRIBUTING.md with development guidelines
- .env.example with all configuration options
- Inline code documentation with docstrings
- Docker deployment instructions

### Security
- No passwords stored in plaintext
- Fernet symmetric encryption for credentials
- Environment variable-based configuration
- No password logging

## Future Versions

### Planned Features (v1.1)
- [ ] Edit existing meetings
- [ ] Delete meetings
- [ ] Multi-calendar support
- [ ] Meeting attachments
- [ ] Recurring meetings
- [ ] Calendar sharing
- [ ] Export to iCal format
- [ ] Timezone-aware datetime handling
- [ ] API documentation (OpenAPI/Swagger)
- [ ] Unit tests
- [ ] Integration tests
- [ ] Performance optimizations
- [ ] Redis caching support
- [ ] Meeting RSVP management
- [ ] Slack integration (in addition to Mattermost)

### Under Consideration
- [ ] Web UI for settings
- [ ] Meeting polling/voting
- [ ] Integration with other CalDAV servers (Google Calendar, Outlook)
- [ ] Multilingual support
- [ ] Meeting templates
- [ ] Smart time suggestions based on availability
- [ ] Email notifications (SMTP)
- [ ] SMS reminders
- [ ] Meeting transcription
- [ ] Meeting recording integration

## Notes

### Version Strategy
- **Major** - Breaking changes, significant features
- **Minor** - New features, backward compatible
- **Patch** - Bug fixes, minor improvements

### Support Policy
- Latest version: Full support
- Previous version: Bug fixes only
- Older versions: Community support via Issues

### Breaking Changes
None in v1.0.0 (initial release)
