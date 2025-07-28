# AURELIUS - Autonomous Business Management Backend System

AURELIUS is a production-ready, modular autonomous backend system for automated business management and online sales. It integrates social media platforms, payment processing, AI-powered content generation, and advanced analytics to provide a complete business automation solution.

## 🚀 Features

### Core Capabilities
- **Autonomous Social Media Management**: Automated posting, engagement, and replies across Twitter/X, Mastodon, and Discord
- **AI-Powered Content Generation**: Uses OpenAI GPT-4/GPT-4o for creating engaging content, sales copy, and automated responses
- **Payment Processing**: Complete PayPal integration with order management, webhook handling, and sales tracking
- **Advanced Analytics**: Real-time reporting on engagement, sales, and system performance
- **Auto-Learning System**: Continuously learns from interactions to optimize strategies
- **Production-Ready**: Comprehensive error handling, logging, security, and rate limiting

### Social Media Integration
- **Twitter/X**: Automated posting, mention monitoring, DM management, engagement tracking
- **Mastodon**: Status posting, notification handling, boost/favorite automation
- **Discord**: Bot integration, webhook posting, channel management, interaction handling

### Business Management
- **Sales Automation**: PayPal order creation, payment capture, refund processing
- **Customer Engagement**: AI-powered responses to inquiries and mentions
- **Lead Management**: Automated lead tracking and follow-up systems
- **Performance Analytics**: Daily, weekly, and monthly business reports

### Technical Features
- **Async Architecture**: Non-blocking operations using asyncio
- **Data Persistence**: Redis primary with local storage fallback
- **Security**: Input sanitization, XSS protection, secure API handling
- **Rate Limiting**: Configurable limits per platform with intelligent throttling
- **Comprehensive Logging**: Structured logging with loguru
- **Modular Design**: Independent, testable modules with type hints

## 📋 Requirements

### API Keys Required
- **OpenAI/OpenRouter**: For AI content generation
- **Twitter API**: Consumer keys, access tokens, bearer token
- **Mastodon**: Access token and instance URL
- **Discord**: Bot token and webhook URL
- **PayPal**: Client ID, secret, and webhook configuration

### Optional Services
- **Redis**: For data persistence (falls back to local storage)

## 🛠 Installation

### 1. Clone and Setup
```bash
# Navigate to the aurelius directory
cd aurelius

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration
```bash
# Copy environment template
cp .env.example .env

# Edit .env with your API keys and configuration
nano .env
```

### 3. Required Environment Variables
```env
# OpenAI/OpenRouter
OPENAI_API_KEY=your_openai_api_key
OPENROUTER_API_KEY=your_openrouter_api_key

# Social Media APIs
TWITTER_API_KEY=your_twitter_api_key
TWITTER_API_SECRET=your_twitter_api_secret
TWITTER_ACCESS_TOKEN=your_twitter_access_token
TWITTER_ACCESS_TOKEN_SECRET=your_twitter_access_token_secret
TWITTER_BEARER_TOKEN=your_twitter_bearer_token

MASTODON_ACCESS_TOKEN=your_mastodon_access_token
MASTODON_API_BASE_URL=https://mastodon.social

DISCORD_BOT_TOKEN=your_discord_bot_token
DISCORD_WEBHOOK_URL=your_discord_webhook_url

# PayPal
PAYPAL_CLIENT_ID=your_paypal_client_id
PAYPAL_CLIENT_SECRET=your_paypal_client_secret
PAYPAL_MODE=sandbox  # or 'live' for production

# Optional Redis
REDIS_URL=redis://localhost:6379
```

## 🚀 Usage

### Starting the System
```bash
# Run AURELIUS
python -m aurelius.main

# Or run directly
python aurelius/main.py
```

### System Startup
The system will:
1. Initialize all modules and API connections
2. Start the Discord bot
3. Begin scheduled tasks for posting, monitoring, and analytics
4. Start the main event loop for autonomous operations

### Monitoring
- Check logs in `logs/aurelius.log`
- Monitor system health through logged metrics
- View analytics reports generated automatically

## 📊 System Architecture

### Core Modules
```
aurelius/
├── main.py                 # Main orchestrator
├── config.py              # Configuration management
├── logging_config.py      # Logging setup
├── core/
│   ├── ai.py             # AI service integration
│   └── scraper.py        # Web scraping utilities
├── modules/
│   ├── social/           # Social media integrations
│   │   ├── twitter.py    # Twitter/X API
│   │   ├── mastodon.py   # Mastodon API
│   │   └── discord.py    # Discord bot/webhook
│   ├── sales/
│   │   └── paypal.py     # PayPal integration
│   ├── analytics/
│   │   └── reports.py    # Analytics and reporting
│   └── auto_learning/
│       └── learner.py    # Machine learning system
├── db/
│   └── redis_client.py   # Data persistence
└── utils/
    ├── security.py       # Security utilities
    └── rate_limit.py     # Rate limiting
```

### Data Flow
1. **Content Generation**: AI creates platform-specific content
2. **Social Posting**: Content distributed across platforms with rate limiting
3. **Engagement Monitoring**: Automated responses to mentions and messages
4. **Sales Processing**: PayPal orders and payments handled automatically
5. **Analytics Collection**: Performance data gathered and analyzed
6. **Learning Optimization**: System learns and improves strategies

## 🔧 Configuration Options

### Rate Limiting
```env
TWITTER_DAILY_POST_LIMIT=50
TWITTER_HOURLY_POST_LIMIT=5
MASTODON_DAILY_POST_LIMIT=100
MASTODON_HOURLY_POST_LIMIT=10
DISCORD_DAILY_POST_LIMIT=200
DISCORD_HOURLY_POST_LIMIT=20
```

### AI Configuration
```env
OPENAI_MODEL=openai/gpt-4o
DEFAULT_SYSTEM_PROMPT=Your custom system prompt
SALES_PROMPT_TEMPLATE=Your sales template
```

### Logging
```env
LOG_LEVEL=INFO
LOG_FILE_PATH=logs/aurelius.log
```

## 📈 Analytics and Reporting

### Automated Reports
- **Daily Reports**: Engagement, sales, and system metrics
- **Weekly Reports**: Trend analysis and performance comparisons
- **Monthly Reports**: Comprehensive business analytics

### Metrics Tracked
- Social media engagement rates
- Content performance analytics
- Sales conversion rates
- Payment processing statistics
- System performance metrics
- Error rates and uptime

## 🧠 Auto-Learning System

The learning module continuously analyzes:
- Content performance patterns
- Optimal posting times
- Engagement triggers
- Sales conversion factors
- Platform effectiveness

### Learning Outputs
- Content strategy recommendations
- Timing optimizations
- Engagement improvements
- Sales funnel enhancements

## 🔒 Security Features

### Input Sanitization
- XSS protection for all user inputs
- SQL injection prevention
- Content validation before posting

### API Security
- Secure credential management
- Rate limit enforcement
- Error handling without data exposure

### Data Protection
- Encrypted sensitive data storage
- Secure webhook validation
- Access logging and monitoring

## 🚨 Error Handling

### Comprehensive Error Management
- Detailed error logging with context
- Graceful degradation on API failures
- Automatic retry mechanisms
- Fallback systems for critical functions

### Monitoring and Alerts
- System health checks every 5 minutes
- Performance metric tracking
- Error rate monitoring
- Uptime statistics

## 🧪 Testing

### Running Tests
```bash
# Run all tests
python -m pytest aurelius/tests/

# Run specific module tests
python -m pytest aurelius/tests/test_social.py
```

### Test Coverage
- Unit tests for all modules
- Integration tests for API connections
- Mock testing for external services
- Error scenario testing

## 🔄 Maintenance

### Regular Tasks
- Monitor log files for errors
- Update API keys before expiration
- Review and adjust rate limits
- Analyze performance reports

### Updates
- Keep dependencies updated
- Monitor API changes from providers
- Review and update AI prompts
- Optimize based on learning insights

## 📞 Support and Troubleshooting

### Common Issues

**Configuration Errors**
- Verify all required API keys are set
- Check API key permissions and scopes
- Ensure webhook URLs are accessible

**Connection Issues**
- Test individual API connections
- Check network connectivity
- Verify rate limits aren't exceeded

**Performance Issues**
- Monitor Redis connection
- Check system resources
- Review error logs for patterns

### Logs Location
- Main log: `logs/aurelius.log`
- Error log: `logs/errors.log`
- System metrics in Redis or local storage

## 🤝 Contributing

### Development Setup
1. Fork the repository
2. Create feature branch
3. Install development dependencies
4. Run tests before committing
5. Follow code style guidelines

### Code Standards
- Type hints for all functions
- Comprehensive error handling
- Detailed logging
- Security-first approach
- Async/await patterns

## 📄 License

This project is proprietary software. All rights reserved.

## 🔗 API Documentation

### Social Media APIs
- [Twitter API v2](https://developer.twitter.com/en/docs/twitter-api)
- [Mastodon API](https://docs.joinmastodon.org/api/)
- [Discord API](https://discord.com/developers/docs/intro)

### Payment Processing
- [PayPal API](https://developer.paypal.com/docs/api/overview/)

### AI Services
- [OpenAI API](https://platform.openai.com/docs)
- [OpenRouter API](https://openrouter.ai/docs)

---

**AURELIUS** - Autonomous Business Management System
Built for production-scale business automation with enterprise-grade reliability and security.
