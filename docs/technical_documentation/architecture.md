# System Architecture

## Overview

The Fund Price Scraping system is designed to collect fund and stock prices from multiple sources, store them in various formats, and provide automated daily collection through GitHub Actions.

## Architecture Components

### 1. Core Scraping Engine

**Purpose**: Extract price data from financial websites using web scraping techniques.

**Components**:
- **Playwright**: Headless browser automation for JavaScript-heavy websites
- **Source Handlers**: Specialized handlers for each data source (FT, Yahoo, Morningstar)
- **Error Handling**: Graceful handling of network issues, timeouts, and parsing errors

**Design Decisions**:
- **Playwright over Selenium**: Better performance and reliability for modern websites
- **Headless Mode**: Reduces resource usage and improves CI/CD compatibility
- **Common Settings**: Unified timeout, user-agent, and wait strategies across sources

### 2. Configuration Management

**Purpose**: Manage fund identifiers and source configurations without code changes.

**Components**:
- **funds.txt**: Simple text-based configuration file
- **Source Codes**: Two-character identifiers (FT, YH, MS) for easy management
- **Parser**: Robust parsing with whitespace and empty line handling

**Design Decisions**:
- **Text-based Configuration**: Simple, version-controllable, human-readable
- **Two-character Codes**: Balance between readability and brevity
- **Flexible Format**: Easy to add new sources without code changes

### 3. Data Storage Layer

**Purpose**: Store price data in multiple formats for different use cases.

**Components**:
- **Individual Price Files**: `latest_<identifier>.price` for single fund access
- **Latest Prices CSV**: `latest_prices.csv` for current price overview
- **Historical Data CSV**: `prices_history.csv` for trend analysis

**Design Decisions**:
- **Multiple Formats**: Different formats for different use cases
- **Append Strategy**: Historical data preserved while latest data overwritten
- **Standard CSV**: Widely compatible format for data analysis tools

### 4. Automation Layer

**Purpose**: Provide reliable, scheduled execution without manual intervention.

**Components**:
- **GitHub Actions**: Cloud-based CI/CD platform
- **Cron Scheduling**: Daily execution at 5pm EST (22:00 UTC)
- **Manual Triggers**: On-demand execution capability
- **Git Integration**: Automatic data persistence to version control

**Design Decisions**:
- **GitHub Actions**: Free, reliable, well-integrated with Git
- **UTC Scheduling**: Avoids daylight saving time complications
- **Data Persistence**: Version control provides historical record and backup

## Data Flow

```
1. Configuration Read
   ↓
2. Source Selection
   ↓
3. Web Scraping (Playwright)
   ↓
4. Price Extraction
   ↓
5. Data Storage (Multiple Formats)
   ↓
6. Git Commit & Push
```

## Error Handling Strategy

### 1. Graceful Degradation
- Individual fund failures don't stop the entire process
- Failed funds marked as "N/A" or "Error: <message>"
- Partial results still saved to output files

### 2. Network Resilience
- Timeout handling (30s for page load, 60s for selector wait)
- Retry logic for transient failures
- User-agent spoofing to avoid blocking

### 3. Data Validation
- Price format validation (numeric values)
- Source configuration validation
- File operation error handling

## Security Considerations

### 1. Authentication
- GitHub Actions uses `GITHUB_TOKEN` for repository access
- No hardcoded credentials in code
- Token permissions limited to repository content

### 2. Data Privacy
- Only public price data is collected
- No personal or sensitive information processed
- Data stored in public repository (intentional for transparency)

### 3. Rate Limiting
- Single browser instance processes all funds sequentially
- Natural delays between requests prevent overwhelming sources
- Respectful scraping practices (user-agent, reasonable timeouts)

## Scalability Considerations

### 1. Horizontal Scaling
- Each fund processed independently
- Easy to parallelize across multiple workers
- Stateless design allows multiple instances

### 2. Vertical Scaling
- Memory usage scales with number of funds
- Browser instance shared across all funds
- Efficient resource utilization

### 3. Future Extensibility
- Modular source handler design
- Configuration-driven fund management
- Easy to add new data sources

## Monitoring and Observability

### 1. Execution Monitoring
- GitHub Actions provides execution logs
- Success/failure status clearly reported
- Execution time tracked

### 2. Data Quality Monitoring
- Price validation ensures numeric values
- Historical data tracking shows trends
- Missing data clearly identified

### 3. Error Tracking
- Detailed error messages for debugging
- Failed fund identification
- Network and parsing error categorization

## Technology Stack

### Core Technologies
- **Python 3.10+**: Main programming language
- **Playwright**: Web scraping and browser automation
- **GitHub Actions**: CI/CD and automation platform

### Dependencies
- **playwright**: Browser automation
- **csv**: Standard library for CSV operations
- **datetime**: Standard library for date handling
- **os**: Standard library for file operations

### Development Tools
- **unittest**: Testing framework
- **coverage**: Test coverage measurement
- **VS Code/Cursor**: IDE with test integration

## Performance Characteristics

### Execution Time
- **Unit Tests**: < 1 second
- **Functional Tests**: ~15 seconds (including real web scraping)
- **Production Run**: Varies by number of funds and network conditions

### Resource Usage
- **Memory**: ~100-200MB (Playwright browser instance)
- **CPU**: Low (headless browser, sequential processing)
- **Network**: Moderate (one request per fund)

### Scalability Limits
- **Funds per Run**: 100+ (limited by execution time)
- **Concurrent Runs**: Multiple (GitHub Actions limits)
- **Data Storage**: Limited by repository size (GitHub limits) 