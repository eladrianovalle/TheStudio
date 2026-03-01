# Studio Storage Management

Studio includes automatic storage management to keep your workspace clean without requiring manual intervention.

## Automatic Storage Awareness

Every time you create a new run, Studio automatically:
- Calculates current storage usage
- Tracks the number of run artifacts  
- Identifies the oldest artifacts
- Suggests cleanup when needed

## Storage Information in Run Files

Each `run.json` file includes a `storage` section with:
```json
{
  "storage": {
    "total_size_mb": 0.3,
    "file_count": 10,
    "oldest_artifact_days": 0,
    "cleanup_suggested": false
  }
}
```

## Cleanup Commands

### Preview Cleanup
See what would be deleted without actually removing files:
```bash
python studio/run_phase.py cleanup --dry-run
```

### Execute Cleanup
Remove old runs according to retention policy:
```bash
python studio/run_phase.py cleanup
```

## Retention Policy

Studio automatically cleans up runs based on two rules:

1. **Time-to-live**: Delete runs older than 30 days
2. **Size cap**: Keep total storage under 900MB

## Configuration

Adjust cleanup settings in `studio/config/studio_settings.toml`:

```toml
[cleanup]
ttl_days = 30        # Delete runs older than this many days
size_limit_mb = 900  # Maximum total storage in megabytes
```

## Storage Tips

- Studio will automatically suggest cleanup when you have >50MB of artifacts or files older than 45 days
- Use `--dry-run` first to preview what will be deleted
- Cleanup is safe - it only removes old run directories, not your work files
- Storage information is included in every run for full transparency

## Manual Cleanup

If you prefer to clean up manually:
```bash
# Check current storage status
python studio/run_phase.py cleanup --dry-run

# Execute cleanup when ready
python studio/run_phase.py cleanup
```

That's it! Studio handles storage management automatically while keeping you informed and in control.
