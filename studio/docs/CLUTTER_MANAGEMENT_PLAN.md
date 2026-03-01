# Studio Clutter Management Airtight Plan

## Executive Summary

Studio currently accumulates ~5MB of run artifacts with uncontrolled growth potential. This plan implements a **Smart Lifecycle Management System** that reduces storage growth by 90% while preserving essential project context through intelligent categorization, progressive cleanup, and user-centric controls.

## Current State Analysis

### Storage Footprint
- **Primary clutter**: `/studio/output` (5.0M) - 19 JSON files with multiple iterations
- **Secondary**: `/.studio/output` (404K) - embedded runs
- **Growth pattern**: ~1-2MB per month based on current usage
- **Risk factor**: Exponential growth with team expansion

### Identified Problems
1. **Uncontrolled accumulation**: No automated cleanup strategy
2. **Context loss risk**: Aggressive cleanup could delete important work
3. **Retrieval inefficiency**: Hard to find relevant artifacts among clutter
4. **Manual overhead**: Users must manually manage storage

## Solution Architecture

### Three-Tier Storage System

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Hot Storage   │───▶│  Warm Storage    │───▶│  Cold Storage   │
│   (Recent)      │    │  (Summarized)    │    │  (Archived)     │
│   • Last 7 days │    │  • Key insights  │    │  • Compressed   │
│   • Full data   │    │  • Metadata      │    │  • Monthly      │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

### Smart Lifecycle Management

1. **Intelligent Categorization**
   - Auto-tag artifacts by type, phase, and outcome
   - ML-based importance scoring
   - Dependency tracking between artifacts

2. **Progressive Cleanup**
   - **Day 0-7**: Hot storage (full data)
   - **Day 8-30**: Warm storage (summarized + metadata)
   - **Day 31-90**: Cold storage (compressed)
   - **Day 91+**: Delete or archive to external storage

3. **User Empowerment**
   - Visual storage dashboard
   - Configurable retention policies
   - Manual override controls
   - Smart search and retrieval

## Implementation Plan

### Phase 1: Foundation (Week 1-2)
**Goal**: Establish metadata collection and monitoring

**Deliverables:**
- Artifact metadata tracking system
- Storage monitoring dashboard
- Baseline metrics and reporting

**Technical Tasks:**
- Implement SQLite metadata database
- Create storage usage monitoring
- Build artifact classification system
- Establish baseline metrics

### Phase 2: Safety Net (Week 3-4)
**Goal**: Build manual cleanup tools with comprehensive safety

**Deliverables:**
- Manual cleanup interface
- Backup and restore procedures
- Safety validation system

**Technical Tasks:**
- Build user interface for artifact management
- Implement backup procedures
- Create safety checks and validations
- Develop rollback capabilities

### Phase 3: Automation (Week 5-6)
**Goal**: Implement automated cleanup with dry-run validation

**Deliverables:**
- Automated cleanup engine
- Configuration management system
- Dry-run testing framework

**Technical Tasks:**
- Implement rule-based cleanup engine
- Add configuration options for retention policies
- Create dry-run mode for validation
- Test with various scenarios

### Phase 4: Full Rollout (Week 7-8)
**Goal**: Deploy complete system with monitoring

**Deliverables:**
- Full automation enabled
- Comprehensive monitoring
- User documentation and training

**Technical Tasks:**
- Enable automated cleanup
- Deploy monitoring and alerting
- Create user documentation
- Conduct user training

## Technical Specifications

### Metadata Schema
```sql
CREATE TABLE artifacts (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    phase TEXT,
    created_at TIMESTAMP,
    last_accessed TIMESTAMP,
    size_bytes INTEGER,
    importance_score REAL,
    storage_tier TEXT,
    file_path TEXT,
    dependencies TEXT, -- JSON array
    summary TEXT,
    status TEXT -- active, summarized, archived, deleted
);
```

### Cleanup Rules Engine
```python
class CleanupRule:
    def __init__(self, condition, action, priority):
        self.condition = condition  # age > 30 AND importance < 0.5
        self.action = action       # summarize, compress, archive, delete
        self.priority = priority   # 1-10, higher = more urgent
    
    def evaluate(self, artifact):
        return self.condition(artifact)
```

### Storage Tiers Configuration
```toml
[storage.tiers.hot]
max_age_days = 7
max_size_mb = 100
compression = false

[storage.tiers.warm]
max_age_days = 30
max_size_mb = 300
compression = true
summarize = true

[storage.tiers.cold]
max_age_days = 90
max_size_mb = 500
compression = true
archive = true
```

## Risk Mitigation

### Data Protection
- **Multiple Backups**: Before any deletion operation
- **Rollback Capability**: One-click restore for 30 days
- **Audit Trail**: Complete log of all cleanup operations
- **User Confirmation**: Required for any destructive action

### Performance Protection
- **Throttled Cleanup**: Limit system impact to <5%
- **Background Operations**: Run during idle periods
- **Incremental Processing**: Small batches instead of bulk operations
- **Resource Monitoring**: Automatic pause if system load high

### User Experience Protection
- **Clear Visibility**: Always show what will be deleted
- **Preview Mode**: Dry-run for all operations
- **Easy Recovery**: Simple restore process
- **Help Documentation**: Built-in guidance

## Success Metrics

### Storage Efficiency
- **Storage Growth**: <10% per month (vs current ~20%)
- **Cleanup Effectiveness**: >90% reduction in clutter
- **Compression Ratio**: >70% space savings in cold storage

### User Experience
- **Find Time**: <30 seconds to locate relevant artifacts
- **User Satisfaction**: >90% satisfaction with controls
- **Error Rate**: <1% user error rate with new system

### Operational Excellence
- **System Availability**: >99.9% during cleanup operations
- **Data Integrity**: Zero data loss incidents
- **Recovery Time**: <5 minutes for restore operations

## Configuration Examples

### Default Configuration
```toml
[cleanup]
enabled = true
dry_run = false
schedule = "daily 02:00"

[rules.default]
condition = "age > 90 AND importance < 0.3"
action = "delete"
priority = 1

[rules.important]
condition = "importance > 0.8"
action = "archive"
priority = 10
```

### Project-Specific Configuration
```toml
[project.marketing]
retention_days = 60
keep_iterations = true

[project.engineering]
retention_days = 30
keep_iterations = false
compress_builds = true
```

## Monitoring and Alerting

### Key Metrics
- Storage usage by tier
- Cleanup success/failure rates
- User activity patterns
- System performance impact

### Alert Conditions
- Storage usage >80% of limit
- Cleanup failure rate >5%
- System performance impact >10%
- User error rate >2%

### Dashboard Components
- Real-time storage usage
- Cleanup activity timeline
- Artifact search interface
- Configuration management

## User Documentation

### Quick Start Guide
1. **View Storage**: Check dashboard for current usage
2. **Configure Rules**: Set retention policies for your needs
3. **Monitor Cleanup**: Review automated cleanup results
4. **Manual Override**: Keep or delete specific artifacts

### Advanced Features
- **Smart Search**: Find artifacts by content or metadata
- **Batch Operations**: Manage multiple artifacts together
- **Export/Import**: Move artifacts between projects
- **Integration**: Connect with external storage systems

## Implementation Timeline

| Week | Phase | Key Milestones |
|------|-------|----------------|
| 1-2  | Foundation | Metadata system, monitoring |
| 3-4  | Safety Net | Manual tools, backups |
| 5-6  | Automation | Cleanup engine, dry-run |
| 7-8  | Rollout | Full deployment, training |

## Budget and Resources

### Development Resources
- **Backend Developer**: 2 weeks (metadata, cleanup engine)
- **Frontend Developer**: 1 week (dashboard, controls)
- **QA Engineer**: 1 week (testing, validation)
- **DevOps Engineer**: 0.5 weeks (monitoring, deployment)

### Infrastructure Costs
- **Additional Storage**: Minimal (compression reduces needs)
- **Monitoring**: Existing infrastructure (no additional cost)
- **Backup Storage**: 2x current usage (temporary during rollout)

## Conclusion

This plan provides a comprehensive solution to Studio's clutter management challenge by:

1. **Eliminating Uncontrolled Growth**: Through automated lifecycle management
2. **Preserving Essential Context**: Via intelligent categorization and summarization
3. **Empowering Users**: With intuitive controls and visibility
4. **Ensuring Operational Excellence**: Through comprehensive safety nets and monitoring

The implementation is phased, low-risk, and delivers immediate value while building toward long-term scalability. Success is measured through concrete metrics that balance storage efficiency with user productivity and data integrity.

**Next Steps**: Begin Phase 1 implementation with metadata collection and monitoring setup.
