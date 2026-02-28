"""
Performance benchmarks for Studio workflows.

Measures performance of key operations to track regressions.
"""
import sys
import tempfile
import time
from pathlib import Path

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from validators.document_validator import DocumentValidator

# Import scopes functions from run_phase
import run_phase
load_scopes_config = run_phase.load_scopes_config
allocate_iterations = run_phase.allocate_iterations


@pytest.fixture
def temp_files(tmp_path):
    """Create temporary test files of various sizes."""
    files = {}
    
    # Small file (1KB)
    small = tmp_path / "small.md"
    small.write_text("# Test\n" + ("Line of text.\n" * 50))
    files['small'] = small
    
    # Medium file (10KB)
    medium = tmp_path / "medium.md"
    medium.write_text("# Test\n" + ("Line of text with more content here.\n" * 500))
    files['medium'] = medium
    
    # Large file (100KB)
    large = tmp_path / "large.md"
    large.write_text("# Test\n" + ("Line of text with even more content to fill space.\n" * 5000))
    files['large'] = large
    
    return files


@pytest.fixture
def scopes_config(tmp_path):
    """Create a test scopes config."""
    config_file = tmp_path / "scopes.toml"
    config_file.write_text("""
[scopes.high_level]
focus = "Architecture"
max_iterations = 4

[scopes.implementation]
focus = "Implementation"
max_iterations = 2

[scopes.polish]
focus = "Polish"
max_iterations = 1
""")
    return config_file


def benchmark(func, *args, iterations=10, **kwargs):
    """Run a function multiple times and return average time."""
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        func(*args, **kwargs)
        end = time.perf_counter()
        times.append(end - start)
    
    avg = sum(times) / len(times)
    min_time = min(times)
    max_time = max(times)
    
    return {
        'avg': avg,
        'min': min_time,
        'max': max_time,
        'iterations': iterations
    }


def test_benchmark_document_validation_small(temp_files, benchmark_info=True):
    """Benchmark document validation on small files."""
    validator = DocumentValidator()
    required_sections = ["Test", "Introduction", "Conclusion"]
    
    result = benchmark(
        validator.check_completeness,
        temp_files['small'],
        required_sections,
        iterations=100
    )
    
    if benchmark_info:
        print(f"\n📊 Small file validation (1KB):")
        print(f"   Average: {result['avg']*1000:.2f}ms")
        print(f"   Min: {result['min']*1000:.2f}ms, Max: {result['max']*1000:.2f}ms")
    
    # Performance assertion: should be < 10ms on average
    assert result['avg'] < 0.01, f"Small file validation too slow: {result['avg']*1000:.2f}ms"


def test_benchmark_document_validation_medium(temp_files, benchmark_info=True):
    """Benchmark document validation on medium files."""
    validator = DocumentValidator()
    required_sections = ["Test", "Introduction", "Conclusion"]
    
    result = benchmark(
        validator.check_completeness,
        temp_files['medium'],
        required_sections,
        iterations=50
    )
    
    if benchmark_info:
        print(f"\n📊 Medium file validation (10KB):")
        print(f"   Average: {result['avg']*1000:.2f}ms")
        print(f"   Min: {result['min']*1000:.2f}ms, Max: {result['max']*1000:.2f}ms")
    
    # Performance assertion: should be < 50ms on average
    assert result['avg'] < 0.05, f"Medium file validation too slow: {result['avg']*1000:.2f}ms"


def test_benchmark_document_validation_large(temp_files, benchmark_info=True):
    """Benchmark document validation on large files."""
    validator = DocumentValidator()
    required_sections = ["Test", "Introduction", "Conclusion"]
    
    result = benchmark(
        validator.check_completeness,
        temp_files['large'],
        required_sections,
        iterations=20
    )
    
    if benchmark_info:
        print(f"\n📊 Large file validation (100KB):")
        print(f"   Average: {result['avg']*1000:.2f}ms")
        print(f"   Min: {result['min']*1000:.2f}ms, Max: {result['max']*1000:.2f}ms")
    
    # Performance assertion: should be < 200ms on average
    assert result['avg'] < 0.2, f"Large file validation too slow: {result['avg']*1000:.2f}ms"


def test_benchmark_scopes_loading(scopes_config, benchmark_info=True):
    """Benchmark scopes configuration loading."""
    result = benchmark(
        load_scopes_config,
        scopes_config,
        iterations=100
    )
    
    if benchmark_info:
        print(f"\n📊 Scopes config loading:")
        print(f"   Average: {result['avg']*1000:.2f}ms")
        print(f"   Min: {result['min']*1000:.2f}ms, Max: {result['max']*1000:.2f}ms")
    
    # Performance assertion: should be < 5ms on average
    assert result['avg'] < 0.005, f"Scopes loading too slow: {result['avg']*1000:.2f}ms"


def test_benchmark_iteration_allocation(scopes_config, benchmark_info=True):
    """Benchmark iteration allocation calculation."""
    config = load_scopes_config(scopes_config)
    
    result = benchmark(
        allocate_iterations,
        config,
        10,
        iterations=1000
    )
    
    if benchmark_info:
        print(f"\n📊 Iteration allocation:")
        print(f"   Average: {result['avg']*1000:.2f}ms")
        print(f"   Min: {result['min']*1000:.2f}ms, Max: {result['max']*1000:.2f}ms")
    
    # Performance assertion: should be < 1ms on average
    assert result['avg'] < 0.001, f"Iteration allocation too slow: {result['avg']*1000:.2f}ms"


def test_benchmark_file_size_check(temp_files, benchmark_info=True):
    """Benchmark file size checking."""
    validator = DocumentValidator()
    
    def check_size(path):
        size = path.stat().st_size
        return size <= validator.MAX_FILE_SIZE
    
    result = benchmark(
        check_size,
        temp_files['large'],
        iterations=10000
    )
    
    if benchmark_info:
        print(f"\n📊 File size check:")
        print(f"   Average: {result['avg']*1000:.2f}ms")
        print(f"   Min: {result['min']*1000:.2f}ms, Max: {result['max']*1000:.2f}ms")
    
    # Performance assertion: should be < 0.1ms on average
    assert result['avg'] < 0.0001, f"File size check too slow: {result['avg']*1000:.2f}ms"


@pytest.mark.benchmark
def test_performance_summary(capsys):
    """Run all benchmarks and print summary."""
    print("\n" + "=" * 60)
    print("Studio Performance Benchmarks")
    print("=" * 60)
    
    # This marker allows running all benchmarks with: pytest -m benchmark -s


if __name__ == "__main__":
    # Run benchmarks with output
    pytest.main([__file__, "-v", "-s", "-m", "not benchmark"])
