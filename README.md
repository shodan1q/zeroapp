# AutoDev Agent

Autonomous app development pipeline that crawls requirements from the internet, uses Claude API to generate Flutter apps, builds them, and publishes to app stores.

## Architecture

The system operates as a six-layer pipeline:

1. **Crawler** - Scrapes app ideas from Reddit, ProductHunt, app store reviews
2. **Evaluator** - Scores feasibility, competition, monetization potential
3. **Generator** - Produces Flutter code via Claude API, file by file
4. **Assets** - Generates icons (DALL-E), screenshots, store listings
5. **Builder** - Compiles Flutter apps and signs for release
6. **Monitor** - Tracks metrics, success rates, revenue

## Quick Start

```bash
make install
cp .env.example .env
# Fill in API keys in .env
make migrate
make run
```

## Commands

```bash
autodev run          # Start the full pipeline
autodev crawl        # Run crawlers only
autodev evaluate     # Run evaluation on pending demands
autodev generate     # Generate code for approved demands
autodev build        # Build approved apps
autodev pipeline     # Run the complete pipeline once
```
