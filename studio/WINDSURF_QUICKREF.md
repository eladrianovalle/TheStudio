# Studio + Windsurf Quick Reference

## 🚀 One-Time Setup

Add to `~/.zshrc`:
```bash
export PATH="/Users/orcpunk/Repos/_TheGameStudio/studio:$PATH"
```

Then: `source ~/.zshrc`

## 💬 Talk to Studio from Any Project

Open any project in Windsurf and ask Cascade:

### Market Validation
> "Use Studio to evaluate: A 3D stealth horror roguelike"

### Design Validation  
> "Run Studio design phase on: A puzzle platformer with portal mechanics"

### Tech Validation
> "Check technical feasibility using Studio: A multiplayer card battler"

### Full Pipeline
> "Run this through all Studio phases: A cozy farming sim with time travel"

## 📋 Direct Commands

```bash
# Single phase
studio evaluate "Your idea" --phase market
studio evaluate "Your idea" --phase design
studio evaluate "Your idea" --phase tech

# Full pipeline
studio pipeline "Your idea"

# List phases
studio list-phases

# JSON output
studio evaluate "Your idea" --phase market --format json
```

## 🎯 What Each Phase Does

- **Market**: Is there demand? Will it sell?
- **Design**: Is the gameplay fun? Is scope reasonable?
- **Tech**: Can we build it? Will it perform?

## 📖 Full Documentation

See [WINDSURF_USAGE.md](./docs/WINDSURF_USAGE.md) for complete guide with examples.
