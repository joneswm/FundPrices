# Deployment Guide

This document provides instructions for deploying the Fund Price Scraping project.

## Prerequisites

### System Requirements
- Python 3.7 or higher
- Linux/Unix environment (recommended for production)
- Minimum 2GB RAM
- 1GB free disk space

### Dependencies
- Playwright browser automation
- Coverage.py for testing
- Git for version control

## Installation

### 1. Clone Repository
```bash
git clone https://github.com/joneswm/FundPrices.git
cd FundPrices
```

### 2. Install Python Dependencies
```bash
pip install -r requirements.txt
```

### 3. Install Playwright Browsers
```bash
playwright install chromium
```

### 4. Verify Installation
```bash
python test_scrape_fund_price.py
```

## Configuration

### 1. Fund Configuration
Create or update `funds.txt` with your fund identifiers:
```
FT,GB00B1FXTF86
YH,IDTG.L
MS,LU0196696453
```

### 2. Data Directory
The application will create a `data/` directory for storing results:
- `latest_prices.csv`: Most recent prices
- `prices_history.csv`: Historical data

### 3. Environment Variables (Optional)
```bash
export FUNDS_FILE="custom_funds.txt"
export DATA_DIR="custom_data"
```

## Deployment Options

### Local Development
```bash
# Run once
python scrape_fund_price.py

# Run with custom configuration
python scrape_fund_price.py --funds custom_funds.txt --data-dir custom_data
```

### Cron Job (Linux/macOS)
Add to crontab for automated execution:
```bash
# Run every hour
0 * * * * cd /path/to/FundPrices && python scrape_fund_price.py

# Run every weekday at 9 AM
0 9 * * 1-5 cd /path/to/FundPrices && python scrape_fund_price.py
```

### GitHub Actions (Recommended)
The project includes GitHub Actions workflow for automated execution:

1. **Workflow File**: `.github/workflows/scrape-funds.yml`
2. **Schedule**: Configurable cron expression
3. **Triggers**: Manual and scheduled runs
4. **Output**: Commits results to repository

#### GitHub Actions Setup
1. Enable GitHub Actions in repository settings
2. Configure secrets if needed:
   - `FUNDS_CONFIG`: Custom fund configuration (optional)
3. Modify schedule in workflow file as needed

### Docker Deployment

#### Dockerfile
```dockerfile
FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Install Playwright browsers
RUN playwright install chromium

# Copy application files
COPY . .

# Create data directory
RUN mkdir -p data

# Run the application
CMD ["python", "scrape_fund_price.py"]
```

#### Build and Run
```bash
# Build image
docker build -t fund-prices .

# Run container
docker run -v $(pwd)/data:/app/data fund-prices

# Run with custom configuration
docker run -v $(pwd)/data:/app/data -v $(pwd)/funds.txt:/app/funds.txt fund-prices
```

### Cloud Deployment

#### AWS EC2
1. Launch EC2 instance (t3.micro or larger)
2. Install Python and dependencies
3. Set up cron job for automated execution
4. Configure CloudWatch for monitoring

#### Google Cloud Run
1. Create Dockerfile (see above)
2. Build and push to Google Container Registry
3. Deploy to Cloud Run with schedule trigger
4. Configure Cloud Scheduler for cron jobs

#### Azure Container Instances
1. Create container from Docker image
2. Set up Azure Logic Apps for scheduling
3. Configure storage account for data persistence

## Monitoring and Maintenance

### Logging
The application logs to stdout/stderr. For production:
```bash
# Redirect logs to file
python scrape_fund_price.py >> logs/scraper.log 2>&1

# Use systemd service for better log management
sudo systemctl start fund-prices
sudo journalctl -u fund-prices -f
```

### Health Checks
```bash
# Check if data directory exists and has recent files
ls -la data/

# Verify latest prices file is recent
stat data/latest_prices.csv

# Check for errors in logs
grep -i error logs/scraper.log
```

### Backup Strategy
```bash
# Backup data directory
tar -czf backup-$(date +%Y%m%d).tar.gz data/

# Automated backup script
#!/bin/bash
cd /path/to/FundPrices
tar -czf backups/data-backup-$(date +%Y%m%d-%H%M).tar.gz data/
find backups/ -name "data-backup-*.tar.gz" -mtime +30 -delete
```

## Security Considerations

### Network Security
- Use HTTPS endpoints when possible
- Implement rate limiting for web requests
- Consider using VPN for sensitive deployments

### Data Security
- Encrypt sensitive configuration files
- Use secure file permissions (600 for config files)
- Regular security updates for dependencies

### Access Control
- Limit file system permissions
- Use non-root user for execution
- Implement proper authentication for cloud deployments

## Troubleshooting

### Common Issues
1. **Playwright browser not found**: Run `playwright install chromium`
2. **Permission denied**: Check file permissions and user access
3. **Network timeouts**: Verify internet connectivity and target site availability
4. **Memory issues**: Monitor system resources, consider upgrading

### Debug Mode
```bash
# Enable verbose logging
python -u scrape_fund_price.py 2>&1 | tee debug.log

# Test individual components
python -c "from scrape_fund_price import read_fund_ids; print(read_fund_ids('funds.txt'))"
```

## Performance Optimization

### Resource Usage
- Monitor CPU and memory usage during execution
- Consider running during off-peak hours
- Implement retry logic for failed requests

### Scaling
- Use multiple instances for different fund sets
- Implement load balancing for high-volume scenarios
- Consider using message queues for asynchronous processing

## Rollback Procedures

### Version Management
```bash
# Tag releases
git tag -a v1.0.0 -m "Release version 1.0.0"
git push origin v1.0.0

# Rollback to previous version
git checkout v0.9.0
pip install -r requirements.txt
```

### Data Recovery
```bash
# Restore from backup
tar -xzf backup-20240115.tar.gz

# Re-run scraper for missing data
python scrape_fund_price.py
```
