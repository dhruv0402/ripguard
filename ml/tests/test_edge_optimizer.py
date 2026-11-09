"""Hardware claims must be backed by execution, not deployment targets."""
from pathlib import Path

import onnx
import pytest
from onnx import TensorProto, helper

from ml.inference import edge_optimizer as edge


@pytest.fixture
def optimizer(tmp_path, monkeypatch):
    model = helper.make_model(helper.make_graph(
        [helper.make_node('Identity', ['input'], ['output'])], 'tiny',
        [helper.make_tensor_value_info('input', TensorProto.FLOAT, [1, 1, 2, 2])],
        [helper.make_tensor_value_info('output', TensorProto.FLOAT, [1, 1, 2, 2])]),
        opset_imports=[helper.make_opsetid('', 13)], ir_version=8)
    path = tmp_path / 'tiny.onnx'
    onnx.save(model, path)
    monkeypatch.setattr(edge, 'trt', None)
    monkeypatch.setattr(edge.shutil, 'which', lambda _: None)
    opt = edge.EdgeOptimizer(str(path), input_shape=(1, 1, 2, 2))
    monkeypatch.setattr(opt, 'detect_edge_capabilities', lambda: {
        'has_native_tensorrt': False, 'has_trtexec_cli': False})
    return opt


def test_no_tensor_rt_does_not_create_fake_engine(optimizer):
    result = optimizer.compile_onnx_to_tensorrt()
    assert result['status'] == 'UNAVAILABLE'
    assert not Path(optimizer.engine_path).exists()
    assert result['sub_20w_certified'] is False


def test_existing_placeholder_is_not_success(optimizer):
    Path(optimizer.engine_path).write_bytes(b'TRT_FP16_ORIN_ENGINE_COMPILED\n')
    assert optimizer.compile_onnx_to_tensorrt()['status'] == 'UNAVAILABLE'


def test_cpu_benchmark_reports_only_measurements(optimizer, monkeypatch):
    monkeypatch.setattr(edge.ort, 'get_available_providers', lambda: ['CPUExecutionProvider'])
    result = optimizer.benchmark_edge_throughput(iterations=3, warmup=1)
    assert result['status'] == 'BENCHMARKED'
    assert result['active_provider'] == 'CPUExecutionProvider'
    assert result['host_fps'] > 0
    assert result['host_measured_latency_ms']['mean'] > 0
    assert result['power_consumption_w'] is None
    assert result['sub_20w_certified'] is False
    assert result['field_trial_ready'] is False
    assert 'jetson_orin_fp16_profile' not in result


@pytest.mark.parametrize('method', ['compile_onnx_to_tensorrt', 'benchmark_edge_throughput'])
def test_missing_model_is_structured_unavailable(optimizer, method):
    Path(optimizer.onnx_path).unlink()
    assert getattr(optimizer, method)()['status'] == 'UNAVAILABLE'


def test_corrupt_model_is_structured_failure(optimizer):
    Path(optimizer.onnx_path).write_bytes(b'not an onnx model')
    assert optimizer.benchmark_edge_throughput()['status'] == 'FAILED'


def test_missing_runtime_is_structured_unavailable(optimizer, monkeypatch):
    monkeypatch.setattr(edge, 'ort', None)
    assert optimizer.benchmark_edge_throughput()['status'] == 'UNAVAILABLE'


@pytest.mark.parametrize('iterations,warmup', [(0, 1), (-1, 0), (2, -1)])
def test_invalid_benchmark_counts(optimizer, iterations, warmup):
    assert optimizer.benchmark_edge_throughput(iterations, warmup)['status'] == 'FAILED'


def test_failed_compiler_does_not_reuse_existing_engine(optimizer, monkeypatch):
    from types import SimpleNamespace
    existing = Path(optimizer.engine_path)
    existing.write_bytes(b'old engine')
    monkeypatch.setattr(optimizer, 'detect_edge_capabilities', lambda: {
        'has_native_tensorrt': False, 'has_trtexec_cli': True})
    monkeypatch.setattr(edge.subprocess, 'run', lambda *a, **k: SimpleNamespace(
        returncode=1, stderr='invalid model'))
    result = optimizer.compile_onnx_to_tensorrt()
    assert result['status'] == 'FAILED'
    assert existing.read_bytes() == b'old engine'
    assert not Path(optimizer.metadata_path).exists()


def test_compiler_success_without_output_is_failure(optimizer, monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(optimizer, 'detect_edge_capabilities', lambda: {
        'has_native_tensorrt': False, 'has_trtexec_cli': True})
    monkeypatch.setattr(edge.subprocess, 'run', lambda *a, **k: SimpleNamespace(
        returncode=0, stderr=''))
    assert optimizer.compile_onnx_to_tensorrt()['status'] == 'FAILED'
    assert not Path(optimizer.engine_path).exists()
