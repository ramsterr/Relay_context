# Context Handover Improvement Plan

## Executive Summary

Based on the comprehensive technical review (7.58/10), this plan addresses critical gaps in:
1. **Mathematical Validity** - Drift metric formalization
2. **Production Reliability** - Idempotency, retry policies, error handling
3. **Context Quality** - Improved token budgeting algorithm
4. **Scalability** - Vector DB backend option
5. **Code Quality** - CI/CD, type checking, linting
6. **Documentation** - API reference, examples, troubleshooting

---

## Phase 1: Critical Fixes (High Priority)

### 1.1 Formalize Drift Metric Fusion (`measurement/drift.py`)

**Problem**: KL divergence requires probability distributions but is applied to raw embeddings without proper mapping.

**Solution**:
- Add explicit probability distribution mapping for semantic KL
- Document normalization strategy for all metrics
- Add configurable weighting with sensible defaults
- Add unit tests for edge cases

**Files to modify**:
- `src/context_handover/measurement/drift.py`
- `tests/test_drift.py` (new)

### 1.2 Add Idempotency & Retry Logic (`pipeline/pipeline.py`)

**Problem**: Async workers lack idempotency keys → duplicate atoms on retry. No DLQ or backpressure.

**Solution**:
- Add idempotency key generation for events
- Implement exponential backoff retry with max attempts
- Add Dead Letter Queue for failed events
- Implement circuit breaker pattern for external dependencies

**Files to modify**:
- `src/context_handover/pipeline/pipeline.py`
- `src/context_handover/pipeline/retry_policy.py` (new)
- `src/context_handover/pipeline/circuit_breaker.py` (new)

### 1.3 Improve Token Budgeting (`core/budget.py`)

**Problem**: Greedy selection is suboptimal. Doesn't maximize semantic value per token.

**Solution**:
- Implement bounded knapsack approximation
- Add value-per-token scoring (salience × confidence / token_cost)
- Preserve mandatory atoms (DECISION, CONSTRAINT) as hard constraints
- Add configuration for optimization strategy

**Files to modify**:
- `src/context_handover/core/budget.py`

### 1.4 Add Error Handling & Fallbacks

**Problem**: No handling for LLM rate limits, embedding failures, Redis disconnects.

**Solution**:
- Add retry decorators with exponential backoff
- Implement fallback extractors (LLM → regex → minimal)
- Add connection health checks for Redis
- Graceful degradation when dependencies fail

**Files to modify**:
- `src/context_handover/extraction/extraction.py`
- `src/context_handover/core/registry.py`
- `src/context_handover/pipeline/pipeline.py`

---

## Phase 2: Medium Priority Improvements

### 2.1 Vector DB Backend Option (`core/registry.py`)

**Problem**: AtomRegistry memory footprint grows unbounded without TTL or vector DB offload.

**Solution**:
- Create abstract storage backend interface
- Implement in-memory backend (current behavior)
- Add optional Qdrant/Chroma/Weaviate backends
- Add TTL-based pruning for old atoms
- Implement incremental index updates

**Files to create**:
- `src/context_handover/storage/base.py`
- `src/context_handover/storage/memory_backend.py`
- `src/context_handover/storage/vector_backend.py`

**Files to modify**:
- `src/context_handover/core/registry.py`

### 2.2 PII Redaction Hook (`extraction/extraction.py`)

**Problem**: No PII handling, encryption, or compliance considerations.

**Solution**:
- Add pre-extraction PII detection hook
- Implement configurable redaction patterns (email, phone, API keys)
- Add encryption-at-rest option for sensitive atoms
- Document GDPR compliance considerations

**Files to create**:
- `src/context_handover/security/pii_redactor.py`

**Files to modify**:
- `src/context_handover/extraction/extraction.py`

### 2.3 Session DAG Merge Strategy (`pipeline/trace_context.py`)

**Problem**: DAG merge/conflict resolution strategy is undocumented.

**Solution**:
- Document conflict scenarios (contradictory atoms across branches)
- Implement atom contestation tracking
- Add merge policies (latest-wins, majority-votes, manual-review)
- Track provenance for merged atoms

**Files to modify**:
- `src/context_handover/pipeline/trace_context.py`
- `src/context_handover/core/atoms.py` (add conflict metadata)

---

## Phase 3: Code Quality & DX (Low Priority)

### 3.1 CI/CD Pipeline Setup

**Create**:
- `.github/workflows/ci.yml` with:
  - pytest with coverage (>80% threshold)
  - mypy type checking
  - ruff linting
  - black formatting check
- `.pre-commit-config.yaml`
- `CONTRIBUTING.md`

### 3.2 Type Safety Improvements

**Files to modify**:
- All modules: Add complete type annotations
- Create `src/context_handover/types.py` for shared types
- Run mypy with strict mode

### 3.3 Documentation Enhancements

**Create**:
- `docs/api_reference.md` - Complete API docs
- `docs/configuration.md` - All config options
- `docs/troubleshooting.md` - Common issues
- `docs/examples/` - Integration examples (LangChain, AutoGen, etc.)

**Modify**:
- `README.md` - Add architecture diagram, quickstart, benchmarks section

### 3.4 Benchmarking Suite

**Create**:
- `benchmarks/drift_benchmark.py` - Drift computation cost
- `benchmarks/handover_latency.py` - End-to-end handover timing
- `benchmarks/token_savings.py` - Compare vs naive context passing

---

## Implementation Timeline

| Week | Tasks | Deliverables |
|------|-------|--------------|
| 1 | 1.1 Drift formalization, 1.4 Error handling | Validated metrics, robust error recovery |
| 2 | 1.2 Idempotency & retry, 1.3 Budget improvement | Production-ready pipeline, better context selection |
| 3 | 2.1 Vector DB backend, 2.2 PII redaction | Scalable storage, compliance hooks |
| 4 | 2.3 DAG merge strategy, 3.1 CI/CD | Conflict resolution, automated testing |
| 5 | 3.2 Type safety, 3.3 Documentation | Type-checked codebase, complete docs |
| 6 | 3.4 Benchmarks, polish | Performance data, release candidate |

---

## Testing Strategy

### Unit Tests
- Test all drift metrics with known inputs/outputs
- Test idempotency (same event twice = one atom)
- Test budget algorithms against optimal solutions
- Test error recovery paths

### Integration Tests
- Full handover cycle with mock LLM/embeddings
- Redis pipeline with failure injection
- Vector DB backend end-to-end

### Load Tests
- 1000+ atoms in registry
- Concurrent handovers
- Long-running sessions (100+ messages)

---

## Success Metrics

After implementation, target scores:
- **Architecture & Design**: 8.5 → 9.5
- **Core Algorithms**: 7.5 → 9.0
- **Implementation Quality**: 7.0 → 9.0
- **Performance & Scalability**: 6.5 → 8.5
- **Security & Reliability**: 6.0 → 8.5
- **Overall**: 7.58 → 8.8-9.2

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Breaking changes | Semantic versioning, deprecation warnings |
| Performance regression | Benchmark before/after, profiling |
| Dependency conflicts | Pin versions, compatibility matrix |
| Adoption friction | Migration guide, backward-compatible APIs |

---

## Next Steps

1. **Immediate**: Start with Phase 1 (critical fixes)
2. **Week 1**: Complete drift formalization + error handling
3. **Week 2**: Complete idempotency + budget improvements
4. **Review**: Assess progress, adjust priorities
5. **Continue**: Phases 2-3 based on user feedback
